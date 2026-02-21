@echo off
setlocal

cd /d "%~dp0.."
set "PROJECT_ROOT=%CD%"

:: Detect Desktop folder (OneDrive or standard)
set "DESKTOP=%USERPROFILE%\Desktop"
if exist "%USERPROFILE%\OneDrive\Desktop" set "DESKTOP=%USERPROFILE%\OneDrive\Desktop"

set "TARGET=%DESKTOP%\Vagus Bot Launcher.bat"

(
  echo @echo off
  echo cd /d "%PROJECT_ROOT%"
  echo set "PYTHONPATH=%%CD%%\src;%%CD%%"
  echo start "" pythonw scripts\vagus_bot_launcher.py
) > "%TARGET%"

echo Created: %TARGET%
echo.
echo Double-click the file on your Desktop to open the Vagus Bot launcher.
pause
