"""
[Phase 1 Session Helper] 네이버 밴드 최초 1회 로그인 및 band_auth.json 자동 생성 헬퍼
사용 방법:
1. python scripts/save_session.py 실행 (또는 login_session.bat 더블클릭)
2. 브라우저가 열리면 네이버/밴드 계정으로 로그인 수행
3. 로그인 완료 후 터미널 창에서 Enter 키 누름
4. 로컬에 band_auth.json 세션 쿠키 저장 완료!
"""

import os
import sys
import json
from playwright.sync_api import sync_playwright

AUTH_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "band_auth.json")


def save_naver_band_session():
    print("==================================================")
    print(" [Naver Band Session Helper] 네이버 밴드 로그인 세션 갱신")
    print("==================================================")
    print("1. 잠시 후 크롬 브라우저 창이 열립니다.")
    print("2. 밴드(band.us) 화면에서 정상적으로 로그인해 주세요.")
    print("3. 로그인 완료 후 이 창으로 돌아와 [Enter] 키를 누르면 세션이 자동 보관됩니다.\n")

    with sync_playwright() as p:
        # 사용자가 직접 보고 로그인할 수 있도록 headless=False 설정
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        try:
            page.goto("https://band.us", wait_until="domcontentloaded")
        except Exception as e:
            print(f"[!] 브라우저 연결 알림: {e}")

        try:
            input(">>> 브라우저에서 밴드 로그인을 완료하신 후 [Enter] 키를 누르세요... <<<")
        except EOFError:
            pass

        # 세션 쿠키 및 LocalStorage 상태를 band_auth.json에 저장
        context.storage_state(path=AUTH_FILE)
        browser.close()

    # 저장된 세션 검증
    if os.path.exists(AUTH_FILE):
        try:
            with open(AUTH_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            cookies = data.get("cookies", [])
            cookie_names = [c.get("name", "") for c in cookies]
            has_auth = any(n in ["NDS", "BAND_AUTH", "NNB", "nid_inf", "NID_AUT"] for n in cookie_names)
            
            print(f"\n[성공] 네이버 밴드 로그인 세션이 정상적으로 저장되었습니다! (총 {len(cookies)}개 쿠키)")
            print(f"저장 경로: {AUTH_FILE}")
            if has_auth:
                print("인증 상태: [유효] 로그인 인증 토큰이 정상 확인되었습니다.\n")
            else:
                print("인증 상태: [주의] 로그인 쿠키가 일부 누락되었을 수 있으니 수집 동작을 확인해 주세요.\n")
        except Exception as err:
            print(f"\n[성공] 세션 파일이 저장되었습니다: {AUTH_FILE} (검증 메모: {err})\n")
    else:
        print(f"\n[오류] {AUTH_FILE} 파일 생성에 실패했습니다.\n")
        sys.exit(1)


if __name__ == "__main__":
    save_naver_band_session()
