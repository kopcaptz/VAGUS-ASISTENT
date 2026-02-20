# Installation Guide

## Prerequisites

- Python 3.10+
- `pip`
- (Optional) Docker + Docker Compose
- (Optional) Playwright browsers for UI smoke tests

## Windows Setup

1. Clone repository and install dependencies:

```powershell
git clone https://github.com/kopcaptz/VAGUS-ASISTENT.git
cd VAGUS-ASISTENT
pip install -e .
```

1. Verify CLI entrypoint:

```powershell
vagus --help
```

1. Start API:

```powershell
scripts\run_windows.bat
```

1. Start Dashboard:

```powershell
set PYTHONPATH=.;src
streamlit run dashboard/main.py --server.port 8501
```

1. (Optional) Start local marketplace:

```powershell
scripts\run_marketplace.bat
```

## Docker Setup

Run all services:

```bash
docker-compose up -d
```

This includes:

- `api` on `8000`
- `dashboard` on `8501`
- `marketplace` on `8010`

## Optional Tools

### Playwright UI smoke tests

```powershell
pip install playwright
python -m playwright install chromium
python scripts/test_ui_smoke.py
```

### Telegram notification smoke test

```powershell
set TELEGRAM_BOT_TOKEN=<your_token>
set TELEGRAM_CHAT_ID=<your_chat_id>
python scripts/test_telegram_alert.py
```

## Health Checks

```powershell
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8501
curl http://127.0.0.1:8010/plugins/search
```
