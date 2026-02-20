@echo off
setlocal

cd /d "%~dp0.."
set "PROJECT_ROOT=%CD%"
set "PYTHONPATH=%PROJECT_ROOT%\src;%PROJECT_ROOT%"
set "SILENT=0"

if /I "%~1"=="--silent" set "SILENT=1"

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    exit /b 1
)

python -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if errorlevel 1 (
    echo [ERROR] Python 3.10+ is required.
    exit /b 1
)

python -c "import cryptography" >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Missing dependency: cryptography
    exit /b 1
)

if "%SILENT%"=="0" (
    set /p CONFIRM=Initialize API key storage in %USERPROFILE%\.vagus ? [y/N]:
    for /f "tokens=* delims= " %%A in ("%CONFIRM%") do set "CONFIRM=%%~A"
    if /I not "%CONFIRM%"=="y" (
        if /I not "%CONFIRM%"=="yes" (
            echo Cancelled.
            exit /b 1
        )
    )
)

python -c "from pathlib import Path; import sys; sys.path.insert(0, r'%PROJECT_ROOT%\src'); from vagus.security import KeyManager; km=KeyManager(); key=km._get_master_key(); d=Path.home()/'.vagus'; print(f'[OK] Initialized at: {d}'); print(f'[OK] Master key bytes: {len(key)}')"
if errorlevel 1 (
    echo [ERROR] Failed to initialize key storage.
    exit /b 1
)

echo [DONE] Windows key setup completed.
exit /b 0
