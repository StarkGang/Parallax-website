@echo off
setlocal enabledelayedexpansion
title Parallax Convention - Auto Config & Launcher

echo ===================================================
echo     PARALLAX 2026 - FULL-STACK AUTO-LAUNCHER
echo ===================================================
echo.

set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

:: Determine paths
if exist "%SCRIPT_DIR%backend" (
    set "BACKEND_DIR=%SCRIPT_DIR%backend"
    set "FRONTEND_DIR=%SCRIPT_DIR%frontend"
) else if exist "%SCRIPT_DIR%Parallax-website\backend" (
    set "BACKEND_DIR=%SCRIPT_DIR%Parallax-website\backend"
    set "FRONTEND_DIR=%SCRIPT_DIR%Parallax-website\frontend"
) else (
    echo [ERROR] Could not find backend and frontend directories!
    pause
    exit /b 1
)

:: ---------------------------------------------------
:: 1. Check & Configure Backend
:: ---------------------------------------------------
echo [1/4] Checking backend configuration...
if not exist "%BACKEND_DIR%\.env" (
    echo   [+] Creating backend .env from .env.example...
    copy "%BACKEND_DIR%\.env.example" "%BACKEND_DIR%\.env" >nul
)

if not exist "%BACKEND_DIR%\var" (
    mkdir "%BACKEND_DIR%\var" >nul 2>&1
)

:: Check for uv or python
set "PYTHON_CMD="
set "USE_UV=0"

where uv >nul 2>&1
if %errorlevel% equ 0 (
    set "USE_UV=1"
    set "PYTHON_CMD=uv run --python 3.12"
    echo   [+] Found 'uv' package manager.
) else (
    where python >nul 2>&1
    if %errorlevel% equ 0 (
        set "PYTHON_CMD=python"
        echo   [+] Found standard 'python'.
    ) else (
        where py >nul 2>&1
        if %errorlevel% equ 0 (
            set "PYTHON_CMD=py -3"
            echo   [+] Found 'py' launcher.
        ) else (
            echo   [!] Warning: Neither 'uv' nor 'python' was detected in PATH.
            echo   [!] Please install Python 3.12+ or uv.
            pause
            exit /b 1
        )
    )
)

:: ---------------------------------------------------
:: 2. Initialize Backend Dependencies & Database Seed
:: ---------------------------------------------------
echo [2/4] Setting up backend database and seed data...
cd /d "%BACKEND_DIR%"

if %USE_UV% equ 1 (
    echo   [+] Syncing backend environment with uv...
    call uv sync --quiet >nul 2>&1
    call uv run --python 3.12 python -c "import asyncio; from app.main import _bootstrap_local_dev; asyncio.run(_bootstrap_local_dev())"
) else (
    if not exist "%BACKEND_DIR%\.venv" (
        echo   [+] Creating virtual environment...
        %PYTHON_CMD% -m venv .venv
    )
    call "%BACKEND_DIR%\.venv\Scripts\activate.bat"
    pip install -q -r requirements.txt
    python -c "import asyncio; from app.main import _bootstrap_local_dev; asyncio.run(_bootstrap_local_dev())"
)
echo   [OK] Backend database is ready and seeded!

:: ---------------------------------------------------
:: 3. Setup Frontend Dependencies
:: ---------------------------------------------------
echo [3/4] Checking frontend dependencies...
cd /d "%FRONTEND_DIR%"

where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo   [ERROR] 'npm' was not found in PATH. Please install Node.js (https://nodejs.org).
    pause
    exit /b 1
)

if not exist "%FRONTEND_DIR%\node_modules" (
    echo   [+] Installing frontend npm packages (this only happens once)...
    call npm install
) else (
    echo   [OK] Frontend dependencies already installed.
)

:: ---------------------------------------------------
:: 4. Launch Services
:: ---------------------------------------------------
echo [4/4] Launching Backend & Frontend services...
echo.

:: Launch Backend in separate window
if %USE_UV% equ 1 (
    start "Parallax Backend API [Port 8000]" cmd /k "cd /d "%BACKEND_DIR%" && uv run --python 3.12 uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --reload"
) else (
    start "Parallax Backend API [Port 8000]" cmd /k "cd /d "%BACKEND_DIR%" && call "%BACKEND_DIR%\.venv\Scripts\activate.bat" && uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8000 --reload"
)

:: Launch Frontend in separate window
start "Parallax Frontend Vite [Port 5173]" cmd /k "cd /d "%FRONTEND_DIR%" && npm run dev"

echo ===================================================
echo   PARALLAX IS RUNNING!
echo   -------------------------------------------------
echo   * Frontend:  http://localhost:5173
echo   * API Docs:  http://localhost:8000/api/docs
echo   * Dev Admin: owner@parallax.local
echo ===================================================
echo.
echo Opening browser in 3 seconds...
timeout /t 3 /nobreak >nul
start http://localhost:5173

