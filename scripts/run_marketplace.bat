@echo off
setlocal

set "PYTHONPATH=.;src"
set "MARKETPLACE_HOST=127.0.0.1"
set "MARKETPLACE_PORT=8010"

echo Starting local marketplace server on %MARKETPLACE_HOST%:%MARKETPLACE_PORT%...
python -m uvicorn src.vagus.plugins.marketplace.api_server:create_marketplace_app --factory --host %MARKETPLACE_HOST% --port %MARKETPLACE_PORT%
