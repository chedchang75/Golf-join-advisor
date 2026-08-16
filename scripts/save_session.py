"""
[Phase 1 Session Helper] 네이버 밴드 최초 1회 로그인 및 band_auth.json 자동 생성 헬퍼
사용 방법:
1. python scripts/save_session.py 실행
2. 브라우저가 열리면 네이버/밴드 계정으로 로그인 수행
3. 로그인 완료 후 터미널 창에서 Enter 키 누름
4. 로컬에 band_auth.json 세션 쿠키 저장 완료!
"""

import os
import sys
from playwright.sync_api import sync_playwright

AUTH_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "band_auth.json")


def save_naver_band_session():
    print("==================================================")
    print(" [Phase 1 Helper] 네이버 밴드 로그인 세션 생성기")
    print("==================================================")
    print("1. 잠시 후 크롬 브라우저가 열립니다.")
    print("2. 밴드(band.us) 로그인 화면에서 정상적으로 로그인해 주세요.")
    print("3. 로그인 성공 후 이 터미널 화면으로 돌아와 Enter 키를 누르면 세션이 보관됩니다.\n")

    with sync_playwright() as p:
        # 사용자가 눈으로 보고 로그인할 수 있도록 headless=False 설정
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()

        page.goto("https://band.us", wait_until="domcontentloaded")

        input(">>> 밴드 로그인을 완료하신 후 [Enter] 키를 누르세요... <<<")

        # 세션 쿠키 및 LocalStorage 상태를 band_auth.json에 저장
        context.storage_state(path=AUTH_FILE)
        browser.close()

    print(f"\n[성공] 네이버 밴드 로그인 세션이 successfully 저장되었습니다!")
    print(f"저장 경로: {AUTH_FILE}\n")


if __name__ == "__main__":
    save_naver_band_session()
