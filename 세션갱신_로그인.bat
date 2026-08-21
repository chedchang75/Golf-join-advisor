@echo off
title Naver Band Session Login - Golf Join Advisor
cd /d "%~dp0"

echo ========================================================
echo       Naver Band Session Renewal / Login Helper
echo ========================================================
echo.
echo [1/2] Launching Chrome Browser for Naver Band Login...
echo [2/2] Please log in to Naver Band in the opened browser window.
echo.
echo * Step 1: Log in with your Naver Band account in the browser.
echo * Step 2: Return to this CMD window and press ENTER to save.
echo.
echo --------------------------------------------------------

python scripts/save_session.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Session renewal failed.
    echo Please check if Python and Playwright are installed properly.
    echo.
) else (
    echo.
    echo ========================================================
    echo  [SUCCESS] Naver Band session has been saved successfully!
    echo  You can now start Golf Join Advisor normally.
    echo ========================================================
)

echo.
pause
