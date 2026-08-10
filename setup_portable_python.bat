@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ============================================
echo    GoGame - Portable Python Setup
echo ============================================
echo.

REM --- Find current Python ---
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found. This script needs Python to set up portable runtime.
    pause
    exit /b 1
)

for /f "delims=" %%i in ('python -c "import sys; print(sys.prefix)"') do set SRC=%%i
for /f "delims=" %%i in ('python -c "import sys; print(sys.version)"') do set PYVER=%%i

echo [INFO] Source Python : %SRC%
echo [INFO] Version       : %PYVER%
echo.

REM --- Destination ---
set DEST=%~dp0python

REM --- Check if python folder already exists ---
if exist "%DEST%" (
    echo [WARN] "%DEST%" already exists.
    choice /c YN /m "Delete and recreate"
    if errorlevel 2 exit /b 0
    echo [INFO] Removing old python folder...
    rmdir /s /q "%DEST%"
)

REM --- Check tkinter is available ---
python -c "import tkinter" 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] Current Python does not have tkinter.
    echo         Please install Python with tcl/tk support first.
    echo         https://www.python.org/downloads/
    pause
    exit /b 1
)
echo [OK] tkinter available in source Python.

REM --- Copy Python ---
echo.
echo [INFO] Copying Python runtime to project folder...
echo         This may take 1-2 minutes...
echo         Source: %SRC%
echo         Dest  : %DEST%
echo.

robocopy "%SRC%" "%DEST%" /E /NFL /NDL /NJH /NJS /nc /ns /np ^
    /XD "__pycache__" "Doc" "include" "libs" "share" "man" ^
    /XF "*.pyc" "*.pyo" "*.chm"

if %errorlevel% geq 8 (
    echo [ERROR] Copy failed (error code %errorlevel%).
    pause
    exit /b 1
)
echo [OK] Python copied to project folder.

REM --- Keep site-packages for future use ---
if exist "%DEST%\Lib\site-packages" (
    echo [OK] site-packages preserved.
)

echo.
echo ============================================
echo    Setup complete!
echo.
echo    You can now run start.bat on any Windows
echo    machine without installing Python.
echo.
echo    To distribute, copy the entire project
echo    folder. The target machine just needs to
echo    double-click start.bat.
echo ============================================
echo.
pause
