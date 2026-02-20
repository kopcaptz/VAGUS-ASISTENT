# Troubleshooting

## `vagus` command not found

Install package in editable mode:

```powershell
pip install -e .
vagus --help
```

If still missing, ensure Python scripts directory is in `PATH`.

## Marketplace returns empty data

- If internet marketplace is unavailable, client switches to offline mode.
- Offline sample file is used from `data/marketplace_sample.json`.
- Verify file exists and is valid JSON.

To run local marketplace service:

```powershell
scripts\run_marketplace.bat
```

## API memory shows `0.0 MB` on Windows

- Ensure `psutil` is installed:

```powershell
pip install psutil
```

- Restart API after installation.

## Dashboard login issues

1. Check API is healthy: `curl http://127.0.0.1:8000/health`
1. Verify credentials for token endpoint:

```powershell
curl -X POST http://127.0.0.1:8000/api/v1/auth/token -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"password\":\"admin\"}"
```

1. Clear browser cache/session and retry.

## Playwright smoke test fails immediately

Install browser binaries:

```powershell
python -m playwright install chromium
```

Then rerun:

```powershell
python scripts/test_ui_smoke.py
```

## Telegram test does not send message

- Set both environment variables:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
- Run:

```powershell
python scripts/test_telegram_alert.py
```

If token/chat ID are missing, script exits with `SKIPPED`.
