# Parallax 2027: Auto Build Frontend & Start Backend
$ErrorActionPreference = "Stop"

Write-Host "========================================================" -ForegroundColor Cyan
Write-Host "  Parallax 2027: Auto Build Frontend & Start Backend" -ForegroundColor Cyan
Write-Host "========================================================" -ForegroundColor Cyan
Write-Host ""

$rootDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# 1. Build Frontend
Write-Host "[1/2] Building frontend production bundle (npm run build)..." -ForegroundColor Yellow
Push-Location "$rootDir\frontend"
try {
    npm run build
    if ($LASTEXITCODE -ne 0) {
        throw "Frontend build failed with exit code $LASTEXITCODE"
    }
} finally {
    Pop-Location
}

Write-Host ""
Write-Host "[2/2] Starting backend server (uv run uvicorn app.main:app)..." -ForegroundColor Green
Push-Location "$rootDir\backend"
try {
    uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
} finally {
    Pop-Location
}

