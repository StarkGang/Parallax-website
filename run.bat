@echo off
setlocal
echo ========================================================
echo   Parallax 2027: Auto Build Frontend ^& Start Backend
echo ========================================================
echo.

cd /d "%~dp0frontend"
echo [1/2] Building frontend production bundle (npm run build)...
call npm run build
if %ERRORLEVEL% neq 0 (
    echo [ERROR] Frontend build failed! Check errors above.
    pause
    exit /b %ERRORLEVEL%
)

echo.
echo [2/2] Starting backend server (uv run uvicorn app.main:app)...
cd /d "%~dp0backend"
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

