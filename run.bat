@echo off
title LanguageNut Bot
cd /d "%~dp0"
echo ========================================
echo   LanguageNut Bot Launcher
echo ========================================
echo.

:: Always grab the latest update from GitHub
echo [1/4] Checking for updates from GitHub...
git pull 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo   ! git not found or not a git repo. Skipping update check.
) else (
    echo   ✓ Update check complete.
)
echo.

:: Install / verify Python dependencies
echo [2/4] Installing dependencies...
pip install -r requirements.txt --quiet 2>nul
if %ERRORLEVEL% EQU 0 (
    echo   ✓ Dependencies ready.
) else (
    echo   ! pip install had issues. Trying again...
    pip install -r requirements.txt
)
echo.

:: Start the bot
echo [3/4] Starting LanguageNut bot...
echo.
python main.py

:: If bot exits, show message and wait
echo.
echo ========================================
echo   Bot has stopped (code: %ERRORLEVEL%)
echo   Close this window or press any key.
echo ========================================
pause

