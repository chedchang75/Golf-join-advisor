@echo off
title Golf Join Advisor
cd /d "%~dp0"

echo ========================================================
echo       Golf Join Advisor - Starting System
echo ========================================================
echo.
echo [1/2] Setting working directory...
echo [2/2] Launching Streamlit Server and Web Browser...
echo.
echo * Web Dashboard: http://localhost:8501
echo * To exit: Close this window or press Ctrl + C
echo.
echo --------------------------------------------------------

python -m streamlit run app.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Application failed to start.
    echo Please check if Python and Streamlit are installed properly.
    echo.
    pause
)
