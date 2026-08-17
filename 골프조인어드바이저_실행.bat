@echo off
chcp 65001 > nul
title 골프 조인 어드바이저 (Golf Join Advisor)

echo ========================================================
echo    ⛳ 골프 조인 어드바이저 (Golf Join Advisor) 실행기
echo ========================================================
echo.
echo [1/2] 프로젝트 작업 디렉토리로 이동 중...
cd /d "%~dp0"

echo [2/2] Streamlit 서버 구동 및 웹 브라우저 대시보드 자동 실행 중...
echo.
echo  * 웹 대시보드 주소: http://localhost:8501
echo  * 종료하려면 이 창을 닫거나 Ctrl + C 를 누르세요.
echo.
echo --------------------------------------------------------

python -m streamlit run app.py --server.headless=false

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo --------------------------------------------------------
    echo [!] 실행 도중 오류가 발생했습니다.
    echo     Python 또는 필수 라이브러리 설치 상태를 확인해 주세요.
    echo --------------------------------------------------------
    pause
)
