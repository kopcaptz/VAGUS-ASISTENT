# Vagus CLI Cheatsheet (Actual Commands)

This file documents commands verified against the current codebase.

## Entry Points

- Preferred installed CLI: `vagus`
- Alternative module run: `python -m src.vagus.cli` (environment-dependent)

## Authentication

- Get access token via API:
  - `curl -X POST http://127.0.0.1:8000/api/v1/auth/token -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"password\":\"admin\"}"`
- Save token for CLI:
  - `vagus login --api-url "http://127.0.0.1:8000" --api-key "<ACCESS_TOKEN>"`

## Task Commands

- Create task: `vagus task create "Hello" --type default`
- Task status: `vagus task status <TASK_ID>`
- List tasks: `vagus task list --limit 10`

## Agent Commands

- List agents (actual): `vagus agent list`
- Note: `vagus agents list` is not available in this version.

## Admin Commands

- System status: `vagus admin status`

## Plugin Commands

- List plugins: `vagus plugin list`
- Install plugin: `vagus plugin install <path-or-url-or-marketplace-id>`
- Enable/disable: `vagus plugin enable <name>` / `vagus plugin disable <name>`
- Uninstall: `vagus plugin uninstall <name>`

## API Keys (No Native CLI Subcommand Yet)

- There is currently no `vagus keys ...` command in this build.
- Use REST API endpoints instead:
  - List keys: `GET /api/v1/keys`
  - Validate one key: `POST /api/v1/keys/{key_name}/validate`
  - Keys health: `GET /api/v1/keys/health`
  - Run full health check: `POST /api/v1/keys/health/check`

## Router Test (No Native CLI Subcommand Yet)

- There is currently no `vagus router test ...` command.
- Use task flow as router smoke test:
  - `POST /api/v1/tasks` with prompt
  - Poll `GET /api/v1/tasks/{task_id}`

## Backup / Migration (Script-Based in Current Build)

- Backup create (actual):
  - `python scripts/backup_keys.py --output-dir "~/.vagus/backups" --validate`
- Backup dry-run:
  - `python scripts/backup_keys.py --dry-run`
- Migrate env to encrypted (actual):
  - `python scripts/migrate_env_to_encrypted.py --env-file .env --apply --force`
- Migration dry-run:
  - `python scripts/migrate_env_to_encrypted.py --env-file .env --dry-run`

## Alerting Test

- Telegram test alert:
  - `python scripts/test_telegram_alert.py`
- Requires both env vars:
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
