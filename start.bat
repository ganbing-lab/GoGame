@echo off
cd /d "%~dp0"

echo ================================
echo    Go Game - Weiqi / Baduk
echo ================================
echo.

REM --- Prefer portable Python in project folder ---
if exist "%~dp0python\python.exe" (
    echo [INFO] Using portable Python in project folder.
    echo.
    "%~dp0python\python.exe" main.py
    pause
    exit /b 0
)

REM --- Fallback: try uv ---
where uv >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] uv found, syncing environment...
    uv sync --quiet
    echo.
    uv run python main.py
    pause
    exit /b 0
)

REM --- Fallback: try system Python ---
where python >nul 2>&1
if %errorlevel% equ 0 (
    echo [INFO] Using system Python.
    echo.
    python main.py
    pause
    exit /b 0
)

echo [ERROR] No Python runtime found.
echo.
echo To make this game portable:
echo   1. Run setup_portable_python.bat on a machine with Python installed.
echo   2. Then copy the entire project folder to any Windows machine.
echo.
echo Or install Python from https://www.python.org/downloads/
pause
exit /b 1
