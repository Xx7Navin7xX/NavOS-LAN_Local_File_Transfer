@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

title Pura Services

:: 1. Check if Python 3 is already accessible
set "PYTHON_CMD="

:: Try 'py -3' launcher first
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    set "PYTHON_CMD=py -3"
    goto :RUN_SERVER
)

:: Try 'python' command
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    set "PYTHON_CMD=python"
    goto :RUN_SERVER
)

:: Try checking common local installation paths if not on PATH
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "C:\Program Files\Python3*" "C:\Python3*") do (
    if exist "%%~D\python.exe" (
        "%%~D\python.exe" -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>&1
        if !ERRORLEVEL! EQU 0 (
            set "PYTHON_CMD="%%~D\python.exe""
            goto :RUN_SERVER
        )
    )
)

:: 2. Python 3 is NOT installed. Attempt automated installation.
echo =====================================================================
echo  Python 3 was not detected on this computer.
echo  Pura Services requires Python 3.8+ to run.
echo =====================================================================
echo.
echo  Attempting automatic installation of Python 3...
echo.

:: Try via winget first (built into Windows 10/11)
where winget >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [1/2] Installing Python 3 via Windows Package Manager (winget)...
    winget install --id Python.Python.3.12 -e --accept-package-agreements --accept-source-agreements
    
    :: Re-check if installed
    timeout /t 3 /nobreak >nul
    py -3 --version >nul 2>&1 && set "PYTHON_CMD=py -3" && goto :RUN_SERVER
    python --version >nul 2>&1 && set "PYTHON_CMD=python" && goto :RUN_SERVER
)

:: Fallback: Download official python.org installer via PowerShell
echo [2/2] Downloading official Python installer from python.org...
set "TEMP_INSTALLER=%TEMP%\python_installer_%RANDOM%.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; " ^
    "Write-Host 'Downloading Python 3.12 installer...'; " ^
    "(New-Object Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.12.5/python-3.12.5-amd64.exe', '%TEMP_INSTALLER%')"

if exist "%TEMP_INSTALLER%" (
    echo Running Python installer (adding Python to PATH)...
    start /wait "" "%TEMP_INSTALLER%" /passive PrependPath=1 Include_test=0
    del "%TEMP_INSTALLER%" >nul 2>&1
    
    :: Refresh PATH in current session from registry
    for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "USER_PATH=%%B"
    for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "SYS_PATH=%%B"
    set "PATH=!USER_PATH!;!SYS_PATH!;!PATH!"
)

:: Re-verify after installer
py -3 --version >nul 2>&1 && set "PYTHON_CMD=py -3" && goto :RUN_SERVER
python --version >nul 2>&1 && set "PYTHON_CMD=python" && goto :RUN_SERVER

for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*" "C:\Program Files\Python3*" "C:\Python3*") do (
    if exist "%%~D\python.exe" (
        set "PYTHON_CMD="%%~D\python.exe""
        goto :RUN_SERVER
    )
)

echo.
echo [ERROR] Could not automatically install Python 3.
echo Please install Python 3 manually from https://www.python.org/downloads/
echo (Make sure to check 'Add Python to PATH' during installation).
echo.
pause
exit /b 1

:RUN_SERVER
echo Starting Pura Services with %PYTHON_CMD%...
%PYTHON_CMD% server.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Server exited with error code %ERRORLEVEL%.
    pause
)
