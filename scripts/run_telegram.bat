@echo off
setlocal

cd /d "%~dp0.."
set "PROJECT_ROOT=%CD%"

set "PYTHONPATH=%PROJECT_ROOT%\src;%PROJECT_ROOT%"

set "BOT_COUNT=0"
for /f %%I in ('wmic process where "name='python.exe' and CommandLine like '%%start_telegram_bot%%'" get ProcessId ^| findstr /R "[0-9]" ^| find /C /V ""') do set "BOT_COUNT=%%I"
if %BOT_COUNT% GTR 0 (
    echo Telegram bot is already running. Skipping duplicate start.
    exit /b 0
)

echo Starting Telegram bot...
python -c "import asyncio; from dotenv import load_dotenv; load_dotenv(); from vagus.layer3.channels.telegram.bot import start_telegram_bot; asyncio.run(start_telegram_bot())"
