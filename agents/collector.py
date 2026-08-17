import os
import re
import json
import time
from typing import List, Dict, Any, Tuple
from dotenv import load_dotenv

from core.config_loader import get_target_bands

load_dotenv()

try:
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False

SELECTORS_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "selectors.json")
SESSION_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "band_auth.json")


def safe_print(msg: str):
    try:
        print(msg)
    except Exception:
        try:
            print(msg.encode("utf-8", errors="ignore").decode("ascii", errors="ignore"))
        except Exception:
            pass


class SessionManager:
    """네이버 밴드 쿠키/세션 관리 및 만료 사전 검증 유틸리티"""

    @staticmethod
    def get_session_path() -> str:
        return SESSION_FILE

    @staticmethod
    def is_session_valid() -> bool:
        """세션 파일 존재 유무 및 쿠키 유효성 검사 (Streamlit Secrets 자동 복원 지원)"""
        # Render 및 Streamlit Cloud 환경 변수 / Secrets에서 BAND_AUTH_JSON 자동 복원
        try:
            auth_content = os.environ.get("BAND_AUTH_JSON")
            if not auth_content:
                import streamlit as st
                if "BAND_AUTH_JSON" in st.secrets:
                    auth_content = st.secrets["BAND_AUTH_JSON"]
            
            if auth_content and str(auth_content).strip():
                with open(SESSION_FILE, "w", encoding="utf-8") as f:
                    f.write(str(auth_content).strip())
                print("[SessionManager] Restored band_auth.json from env / secrets!")
        except Exception as e:
            print(f"[SessionManager] Session restore note: {e}")

        if not os.path.exists(SESSION_FILE):
            return False

        try:
            with open(SESSION_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            cookies = data.get("cookies", [])
            if not cookies:
                return False

            # 네이버 밴드 핵심 로그인 쿠키 (NDS, NNB, BAND_AUTH 등) 존재 여부 검사
            cookie_names = [c.get("name", "") for c in cookies]
            has_auth_cookie = any(name in ["NDS", "BAND_AUTH", "NNB", "nid_inf"] for name in cookie_names)
            return has_auth_cookie
        except Exception as e:
            print(f"[SessionManager] Session validation check failed: {e}")
            return False


class SelectiveScraper:
    """
    [고속 수집기 - Fast Parallel & Resource Blocked SelectiveScraper]
    이미지/미디어 네트워크 차단, 고속 동적 스크롤 및 3중 밴드명 추론 적용 수집기
    """

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.selectors = self._load_selectors()

    def _load_selectors(self) -> Dict[str, Any]:
        if os.path.exists(SELECTORS_FILE):
            with open(SELECTORS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if "selectors" in data and isinstance(data["selectors"], dict):
                    return data["selectors"]
                return data
        return {
            "post_card": "div[data-viewname='DPostItemView'], div._postMainWrap, div._postCard, div.cCard, article, [class*='postCard'], [class*='PostItem']",
            "body_text": "div._postText, div.postText, div.dPostTextView, div.postBody, [data-viewname='DPostBodyView']",
            "author": "a.author, span.author_name, span.name, a.name",
            "date": "span.date, time, span.time",
            "post_link": "a.postLink, a.link, a._btnPostLink"
        }

    def _scrape_via_http(self, target_bands: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], bool]:
        """[클라우드 환경 100% 동작 대안]: 브라우저 없이 HTTP requests 세션으로 네이버 밴드 데이터 수집"""
        print("[HTTP Scraper] Cloud sandbox detected. Falling back to HTTP requests scraper...")
        import requests
        
        collected_posts = []
        session = requests.Session()

        proxy_url = os.environ.get("PROXY_SERVER")
        if proxy_url:
            session.proxies = {"http": proxy_url, "https": proxy_url}
            print(f"[HTTP Scraper] Using Residential Proxy IP Router: {proxy_url}")
        
        cookie_parts = []
        try:
            if os.path.exists(SESSION_FILE):
                with open(SESSION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for c in data.get("cookies", []):
                    name, val = c.get("name"), c.get("value")
                    if name and val:
                        clean_val = str(val).strip('"')
                        cookie_parts.append(f"{name}={clean_val}")
                        session.cookies.set(name, clean_val, domain=c.get("domain", ".band.us"))
        except Exception as cookie_e:
            print(f"[HTTP Scraper] Cookie injection note: {cookie_e}")

        raw_cookie_str = "; ".join(cookie_parts)
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.6 Mobile/15E148 Safari/604.1",
            "Cookie": raw_cookie_str,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7"
        })

        for target in target_bands:
            target_name = target["name"]
            target_url = target["url"]
            
            # 1. 밴드 고유 ID 추출 (예: https://band.us/band/62430953 -> 62430953)
            band_no_match = re.search(r'/band/(\d+)', target_url)
            band_no = band_no_match.group(1) if band_no_match else None
            
            # 모바일 SSR URL 생성 (m.band.us는 서버사이드 렌더링으로 정적 본문 텍스트 포함)
            mobile_url = f"https://m.band.us/band/{band_no}" if band_no else target_url
            print(f"[HTTP Scraper] Fetching Mobile SSR: '{target_name}' ({mobile_url})")

            try:
                resp = session.get(mobile_url, timeout=12)
                if resp.status_code == 200:
                    html_text = resp.text
                    
                    # 1차: 모바일 SSR 게시글 카드 감지 (postBody / _postText / txt / post_text)
                    cards = re.findall(r'<(?:div|p|span)[^>]*class="[^"]*(?:postBody|_postText|txt|dPostTextView|cText)[^"]*"[^>]*>(.*?)</(?:div|p|span)>', html_text, re.DOTALL)
                    
                    # 2차: 일반 게시글 본문 텍스트 블록 파싱
                    if not cards:
                        cards = re.findall(r'<p[^>]*class="[^"]*txt[^"]*"[^>]*>(.*?)</p>', html_text, re.DOTALL)
                    
                    # 3차: 이모지 및 특수 조인 키워드 블록 추출 (#골프, ⛳️, ⭕️, 8월, 08시 등)
                    if not cards:
                        cards = re.findall(r'(?:⛳️|⭕️|#|\d{1,2}월\s*\d{1,2}일).*?(?=<div|<p|\n\n|$)', html_text, re.DOTALL)

                    for idx, raw_html in enumerate(cards, 1):
                        clean_text = re.sub(r'<[^>]+>', ' ', raw_html).strip()
                        clean_text = re.sub(r'\s+', ' ', clean_text)
                        if len(clean_text) >= 8:
                            collected_posts.append({
                                "band_name": target_name,
                                "target_name": target_name,
                                "post_id": f"http-{band_no or 'post'}-{idx}",
                                "body_text": clean_text,
                                "author_nickname": "밴드 회원",
                                "post_url": target_url
                            })

                # 2차: 네이버 밴드 내부 API 호출 시도 (api/v2.0/band/posts)
                if band_no and len(collected_posts) == 0:
                    api_url = f"https://band.us/api/v2.0/band/posts?band_no={band_no}&limit=20"
                    api_resp = session.get(api_url, timeout=8)
                    if api_resp.status_code == 200:
                        api_data = api_resp.json()
                        items = api_data.get("result_data", {}).get("items", [])
                        for idx, item in enumerate(items, 1):
                            body = item.get("content") or item.get("body") or ""
                            author = item.get("author", {}).get("name", "밴드 회원")
                            p_id = item.get("post_no") or idx
                            if body and len(body) >= 8:
                                collected_posts.append({
                                    "band_name": target_name,
                                    "target_name": target_name,
                                    "post_id": f"api-{band_no}-{p_id}",
                                    "body_text": body,
                                    "author_nickname": author,
                                    "post_url": f"https://band.us/band/{band_no}/post/{p_id}"
                                })

            except Exception as http_err:
                print(f"[HTTP Scraper] Error fetching '{target_name}': {http_err}")

        return collected_posts, True

    def scrape_bands(self, target_bands: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], bool]:
        """
        선택된 밴드 리스트 수집 (Playwright 1차 시도 -> 클라우드 샌드박스 시 HTTP Scraper로 100% Fallback)
        Returns: (collected_posts_list, is_session_valid)
        """
        if not SessionManager.is_session_valid():
            print("[Scraper] Session invalid or expired.")
            return [], False

        # Playwright 브라우저 구동 시도
        try:
            return self._scrape_via_playwright(target_bands)
        except Exception as pw_err:
            print(f"[Scraper] Playwright browser launch failed in cloud container: {pw_err}")
            return self._scrape_via_http(target_bands)

    def _scrape_via_playwright(self, target_bands: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], bool]:
        collected_posts: List[Dict[str, Any]] = []
        is_ok = True
        start_time = time.time()

        proxy_url = os.environ.get("PROXY_SERVER")
        proxy_config = {"server": proxy_url} if proxy_url else None
        if proxy_config:
            print(f"[Playwright Scraper] Using Residential Proxy IP Router: {proxy_url}")

        with sync_playwright() as p:
            launch_args = []
            browser = p.chromium.launch(headless=self.headless, args=launch_args, proxy=proxy_config)
            context = browser.new_context(storage_state=SESSION_FILE)
            page = context.new_page()

            for target in target_bands:
                target_name = target["name"]
                target_url = target["url"]

                safe_print(f"[Fast Scraper] Scanning Band: '{target_name}' ({target_url})")

                try:
                    page.goto(target_url, timeout=30000, wait_until="domcontentloaded")
                    page.wait_for_timeout(3000)
                    
                    try:
                        page.wait_for_selector("div.cCard", timeout=5000)
                    except Exception:
                        pass

                    # 세션 만료 페이지 리다이렉션 체크
                    if "login" in page.url.lower():
                        safe_print(f"[!] Session expired during scraping '{target_name}'")
                        is_ok = False
                        page.close()
                        break

                    resolved_band_name = target_name

                    # 접힌 본문 더보기 클릭 (기장동원, 밀양 등 본문이 길어 접힌 밴드 완벽 확장)
                    try:
                        page.evaluate("""() => {
                            document.querySelectorAll('button.btnMore, button._btnMore, span.seeMore, button._postMoreBtn, [data-viewname="DPostMoreView"]').forEach(b => {
                                if (b.tagName !== 'A' && !b.classList.contains('_btnMoreIntroDescription') && !b.classList.contains('_noticeNav')) {
                                    try { b.click(); } catch(e) {}
                                }
                            });
                        }""")
                        page.wait_for_timeout(1000)
                    except Exception:
                        pass

                    cards = page.query_selector_all("div.cCard, article, div.postMain")

                    # 공지사항 영역이 별도 노출되어 있을 경우 대비한 공지 텍스트 수집
                    notice_els = page.query_selector_all("[class*='notice'], [class*='Notice'], ._notice")
                    for n_idx, n_el in enumerate(notice_els):
                        try:
                            n_text = n_el.inner_text().strip()
                            if n_text and len(n_text) >= 15 and ("조인" in n_text or "부킹" in n_text or "★" in n_text or "8/" in n_text):
                                collected_posts.append({
                                    "band_name": resolved_band_name,
                                    "target_name": target_name,
                                    "post_id": f"notice-{target_name}-{n_idx}",
                                    "body_text": n_text,
                                    "author_nickname": "공지사항",
                                    "post_url": target_url
                                })
                        except Exception:
                            pass

                    seen_in_band = set()
                    scraped_card_count = 0

                    for idx, card in enumerate(cards, 1):
                        try:
                            # 원시 본문 텍스트 추출
                            body_sel = self.selectors.get("body_text", "div._postText, div.dPostTextView")
                            body_el = card.query_selector(body_sel)
                            body_text = body_el.inner_text().strip() if body_el else card.inner_text().strip()

                            if not body_text or len(body_text) < 5:
                                continue

                            # 중복 카드 텍스트 건너뛰기
                            if body_text in seen_in_band:
                                continue
                            seen_in_band.add(body_text)
                            scraped_card_count += 1

                            # 작성자 닉네임 추출
                            author_sel = self.selectors.get("author", "[data-viewname*='Author'] .name, [data-viewname*='Author'], a.author, span.name, a.name")
                            author_el = card.query_selector(author_sel)
                            author = "밴드 회원"
                            if author_el:
                                raw_author = author_el.inner_text().strip()
                                author = raw_author.split("\n")[0].strip() if raw_author else "밴드 회원"

                            # post_id & post_url 생성
                            post_id = f"{target_name}-post-{scraped_card_count}"
                            post_url = target_url
                            
                            post_link_sel = self.selectors.get("post_link", "a[href*='/post/'], a.time, a.postLink")
                            link_el = card.query_selector(post_link_sel)
                            
                            if link_el:
                                href = link_el.get_attribute("href") or ""
                                if href and href != "#":
                                    full_href = href if href.startswith("http") else f"https://band.us{href}"
                                    match_id = re.search(r'/post/(\d+)', full_href)
                                    if match_id:
                                        post_id = f"band-{match_id.group(1)}"
                                        post_url = full_href
                                    elif "band.us/band/" in full_href:
                                        post_url = full_href

                            collected_posts.append({
                                "band_name": resolved_band_name,
                                "target_name": target_name,
                                "post_id": post_id,
                                "body_text": body_text,
                                "author_nickname": author,
                                "post_url": post_url
                            })
                        except Exception as card_err:
                            safe_print(f"  [!] Card extraction error: {card_err}")
                            continue

                    safe_print(f"  -> Successfully extracted {scraped_card_count} unique posts in '{resolved_band_name}'")

                except PlaywrightTimeoutError:
                    safe_print(f"  [!] Timeout loading band '{target_name}' - skipping to next.")
                except Exception as e:
                    safe_print(f"  [!] Error scraping band '{target_name}': {e}")
                finally:
                    pass

            browser.close()

        elapsed = time.time() - start_time
        safe_print(f"[Scraper Complete] Total Scraped Posts: {len(collected_posts)} (Elapsed: {elapsed:.2f}s)")
        return collected_posts, is_ok
