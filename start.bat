@echo off
chcp 65001 >nul 2>&1
title SonicTranslator

echo.
echo  ╔══════════════════════════════════════════════════════════════╗
echo  ║           SonicTranslator — AI Terminal Translator          ║
echo  ║              Powered by Duck.ai + Playwright                ║
echo  ╚══════════════════════════════════════════════════════════════╝
echo.

:: ─── Check Python ───────────────────────────────────────────────────────
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. Install Python 3.8+ from https://python.org
    echo         Make sure "Add Python to PATH" is checked during install.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo [OK] Python %PYVER% detected

:: ─── Check pip ──────────────────────────────────────────────────────────
python -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [WARN] pip not found, installing...
    python -m ensurepip --upgrade >nul 2>&1
)

:: ─── Install dependencies ───────────────────────────────────────────────
echo [..] Checking dependencies...
python -c "import playwright, pyperclip, rich, prompt_toolkit" >nul 2>&1
if %errorlevel% neq 0 (
    echo [..] Installing dependencies from requirements.txt...
    python -m pip install -r requirements.txt -q
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install dependencies.
        pause
        exit /b 1
    )
    echo [OK] Dependencies installed
) else (
    echo [OK] All dependencies present
)

:: ─── Install Playwright Chromium ────────────────────────────────────────
python -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); p.chromium; p.stop()" >nul 2>&1
if %errorlevel% neq 0 (
    echo [..] Installing Playwright Chromium browser...
    python -m playwright install chromium
    if %errorlevel% neq 0 (
        echo [ERROR] Failed to install Chromium. Try: python -m playwright install chromium
        pause
        exit /b 1
    )
    echo [OK] Chromium installed
) else (
    echo [OK] Chromium browser ready
)

:: ─── Auto-update from GitHub ────────────────────────────────────────────
where git >nul 2>&1
if %errorlevel% equ 0 (
    echo [..] Checking for updates...
    git fetch origin main --quiet 2>nul
    if %errorlevel% equ 0 (
        for /f %%i in ('git rev-parse HEAD') do set LOCAL=%%i
        for /f %%i in ('git rev-parse origin/main') do set REMOTE=%%i
        if not "%LOCAL%"=="%REMOTE%" (
            echo [!!] Update available! Downloading...
            git pull origin main --quiet
            if %errorlevel% equ 0 (
                echo [OK] Updated to latest version
                echo [..] Reinstalling dependencies...
                python -m pip install -r requirements.txt -q
                python -m playwright install chromium
            ) else (
                echo [WARN] Update failed, continuing with current version
            )
        ) else (
            echo [OK] Already up to date
        )
    ) else (
        echo [..] Cannot reach GitHub, skipping update check
    )
) else (
    echo [..] Git not found, skipping auto-update
)

:: ─── Run SonicTranslator ────────────────────────────────────────────────
echo.
echo [..] Starting SonicTranslator...
echo.
cd /d "%~dp0src"
python st.py %*

:: If no arguments, keep window open on exit
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] SonicTranslator exited with error code %errorlevel%
    pause
)
