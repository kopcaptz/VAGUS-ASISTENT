# Migration Guide: ENV to Encrypted Keys

## Goal

Move provider keys from environment variables (`*_API_KEY`) and `.env` into encrypted key storage.

## Dry-run first (default)

```bash
python scripts/migrate_env_to_encrypted.py
```

This only prints what would be migrated.

## Apply migration

```bash
python scripts/migrate_env_to_encrypted.py --apply
```

Non-interactive mode:

```bash
python scripts/migrate_env_to_encrypted.py --apply --force
```

## Safety behavior

- Creates `.env.backup_<timestamp>` before editing `.env`
- Uses atomic write for `.env` replacement
- Restores previous encrypted store and `.env` backup on failure

## Backup and Restore

Create backup:

```bash
python scripts/backup_keys.py --validate
```

Restore (merge):

```bash
python scripts/restore_keys.py ~/.vagus/backups/keys_backup_YYYYMMDD_HHMMSS.vkb --strategy merge
```

Restore (replace):

```bash
python scripts/restore_keys.py ~/.vagus/backups/keys_backup_YYYYMMDD_HHMMSS.vkb --strategy replace
```

Validate backup:

```bash
python scripts/validate_backup.py ~/.vagus/backups/keys_backup_YYYYMMDD_HHMMSS.vkb
```

## Recovery scenarios

- Broken migration: restore `.env` from `.env.backup_*` and rerun in dry-run mode.
- Invalid backup file: run `validate_backup.py` to inspect checksum/decryption status.
- Cross-machine restore with password layer: pass `--password` when validating/restoring.
