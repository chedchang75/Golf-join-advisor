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


class SessionManager:
    """네이버 밴드 쿠키/세션 관리 및 만료 사전 검증 유틸리티"""

    @staticmethod
    def get_session_path() -> str:
        return SESSION_FILE

    @staticmethod
    def is_session_valid() -> bool:
        """세션 파일 존재 유무 및 쿠키 유효성 검사 (Streamlit Secrets 자동 복원 지원)"""
        # Streamlit Cloud 배포 환경: Secrets에 BAND_AUTH_JSON이 있으면 자동으로 복원
        try:
            import streamlit as st
            if "BAND_AUTH_JSON" in st.secrets:
                auth_content = st.secrets["BAND_AUTH_JSON"]
                if auth_content and str(auth_content).strip():
                    with open(SESSION_FILE, "w", encoding="utf-8") as f:
                        f.write(str(auth_content).strip())
                    print("[SessionManager] Restored band_auth.json from Streamlit Secrets!")
        except Exception:
            pass

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
                return json.load(f)
        return {
            "post_card": "div._postMainWrap, div.cCard, div.cContentsCard, div.postMain",
            "body_text": "div._postText, div.postText, div.dPostTextView, div.postBody",
            "author": "a.author, span.author_name, span.name, a.name",
            "date": "span.date, time, span.time",
            "post_link": "a.postLink, a.link, a._btnPostLink"
        }

    def scrape_bands(self, target_bands: List[Dict[str, str]]) -> Tuple[List[Dict[str, Any]], bool]:
        """
        선택된 밴드 리스트 고속 브라우저 수집 (이미지 차단 + 고속 스크롤 적용)
        Returns: (collected_posts_list, is_session_valid)
        """
        if not PLAYWRIGHT_AVAILABLE:
            print("[Scraper] Playwright library not installed.")
            return [], False

        if not SessionManager.is_session_valid():
            print("[Scraper] Session invalid or expired.")
            return [], False

        collected_posts: List[Dict[str, Any]] = []
        is_ok = True
        start_time = time.time()

        # Streamlit Cloud 환경 대비 Chromium 사전 1회 자동 설치 보장
        try:
            import sys, subprocess
            subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=False)
        except Exception as e:
            print(f"[Scraper] Playwright auto-install note: {e}")

        with sync_playwright() as p:
            launch_args = [
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
                "--no-zygote",
                "--single-process"
            ]
            try:
                browser = p.chromium.launch(headless=self.headless, args=launch_args)
            except Exception as launch_err:
                print(f"[Scraper] Chromium launch retry... ({launch_err})")
                browser = p.chromium.launch(headless=self.headless, args=launch_args)

            context = browser.new_context(
                storage_state=SESSION_FILE,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )

            for target in target_bands:
                target_name = target["name"]
                target_url = target["url"]

                print(f"[Fast Scraper] Scanning Band: '{target_name}' ({target_url})")

                page = context.new_page()

                # 🚀 [속도 최적화 1]: 불필요한 이미지, 폰트, 미디어 네트워크 차단
                page.route("**/*.{png,jpg,jpeg,gif,webp,woff,woff2,svg,ico,mp4,mp3}", lambda route: route.abort())

                try:
                    page.goto(target_url, timeout=12000, wait_until="domcontentloaded")
                    page.wait_for_timeout(800)

                    # 세션 만료 페이지 리다이렉션 체크
                    if "login" in page.url.lower():
                        print(f"[!] Session expired during scraping '{target_name}'")
                        is_ok = False
                        page.close()
                        break

                    # 3단계 밴드명 추론 (1차: target_name 최우선 고수, DOM "BAND" 로고 오염 방어)
                    resolved_band_name = target_name
                    try:
                        header_el = page.query_selector("h1.band_name, .bandName, div.headerTitle")
                        if header_el:
                            header_title = header_el.inner_text().strip()
                            # "BAND", "밴드", "NAVER BAND" 등 서비스 로고 텍스트는 오염 방지를 위해 차단
                            if header_title and len(header_title) > 1 and header_title.upper() not in ["BAND", "NAVER BAND", "밴드"]:
                                resolved_band_name = header_title
                    except Exception:
                        pass

                    # 🚀 [속도 최적화 2]: 고속 스마트 스크롤 (0.5초 대기 4회 스크롤)
                    for _ in range(4):
                        page.mouse.wheel(0, 1600)
                        page.wait_for_timeout(500)

                    # DOM 게시대상 카드 요소 추출
                    card_selector = self.selectors.get("post_card", "div._postMainWrap, div.cCard")
                    cards = page.query_selector_all(card_selector)

                    print(f"  -> Found {len(cards)} post cards in '{resolved_band_name}'")

                    for idx, card in enumerate(cards, 1):
                        try:
                            # 원시 본문 텍스트 추출
                            body_sel = self.selectors.get("body_text", "div._postText, div.dPostTextView")
                            body_el = card.query_selector(body_sel)
                            body_text = body_el.inner_text().strip() if body_el else card.inner_text().strip()

                            if not body_text or len(body_text) < 5:
                                continue

                            # 작성자 닉네임 추출
                            author_sel = self.selectors.get("author", "a.author, span.name")
                            author_el = card.query_selector(author_sel)
                            author = author_el.inner_text().strip() if author_el else "알수없음"

                            # post_id & post_url 생성
                            post_id = f"{target_name}-post-{idx}"
                            post_link_sel = self.selectors.get("post_link", "a.postLink, a._btnPostLink")
                            link_el = card.query_selector(post_link_sel)
                            
                            if link_el:
                                href = link_el.get_attribute("href") or ""
                                post_url = href if href.startswith("http") else f"https://band.us{href}"
                                # URL에서 고유 post_id 추출
                                match_id = re.search(r'/post/(\d+)', post_url)
                                if match_id:
                                    post_id = f"band-{match_id.group(1)}"
                            else:
                                post_url = target_url

                            collected_posts.append({
                                "band_name": resolved_band_name,
                                "target_name": target_name,
                                "post_id": post_id,
                                "body_text": body_text,
                                "author_nickname": author,
                                "post_url": post_url
                            })
                        except Exception as card_err:
                            print(f"  [!] Card extraction error: {card_err}")
                            continue

                except PlaywrightTimeoutError:
                    print(f"  [!] Timeout loading band '{target_name}' - skipping to next.")
                except Exception as e:
                    print(f"  [!] Error scraping band '{target_name}': {e}")
                finally:
                    page.close()

            browser.close()

        elapsed = time.time() - start_time
        print(f"[Scraper Complete] Total Scraped Posts: {len(collected_posts)} (Elapsed: {elapsed:.2f}s)")
        return collected_posts, is_ok
