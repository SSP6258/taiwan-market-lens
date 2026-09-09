@echo off
setlocal
cd /d "%~dp0"
title Taiwan Market Lens - Streamlit
if not exist ".venv\Scripts\python.exe" (
    echo Project environment is missing. Run these commands first:
    echo.
    echo python -m venv .venv
    echo .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" launch.py
if errorlevel 1 (
    echo.
    echo Startup failed. Please check the message above.
    pause
    exit /b 1
)
endlocal
