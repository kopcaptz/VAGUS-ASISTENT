@echo off
setlocal

cd /d "%~dp0.."
set "PROJECT_ROOT=%CD%"

set "PYTHONPATH=%PROJECT_ROOT%\src;%PROJECT_ROOT%"
set "VAGUS_CONFIG_PATH=%PROJECT_ROOT%\configs\windows.yaml"
set "STREAMLIT_SERVER_HEADLESS=true"
set "STREAMLIT_BROWSER_GATHER_USAGE_STATS=false"

if /I "%~1"=="dashboard" (
    echo Starting Streamlit dashboard with Windows environment...
    streamlit run dashboard/main.py
    goto :eof
)

echo Starting Vagus API with Windows config...
python -m uvicorn vagus.layer3.api.main:app --host 127.0.0.1 --port 8000
