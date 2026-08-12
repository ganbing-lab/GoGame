@echo off
title GoGame Server
cd /d "%~dp0"

set PORT=8080

echo ================================
echo    GoGame HTTP Server
echo    Port: %PORT%
echo ================================
echo.

where uv >nul 2>&1
if %errorlevel% equ 0 (
    uv run python server.py --port %PORT%
    pause
    exit /b 0
)

where python >nul 2>&1
if %errorlevel% equ 0 (
    python server.py --port %PORT%
    pause
    exit /b 0
)

echo [ERROR] Python not found. Install Python 3.10+ or uv.
pause
exit /b 1
