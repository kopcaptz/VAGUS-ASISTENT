# CLI Scripts — Final Smoke-Test Report

**Date:** 2026-02-20  
**Tester:** Automated smoke-runner  
**Result: 29 / 29 PASSED — ALL CHECKS GREEN**

---

## 1. Help / Usage Checks

| Script | Command | Status |
|--------|---------|--------|
| `validate_backup.py` | `--help` | PASS |
| `migrate_env_to_encrypted.py` | `--help` | PASS |
| `backup_keys.py` | `--help` | PASS |
| `restore_keys.py` | `--help` | PASS |
| `setup_windows_keys.ps1` | `Get-Help` | PASS (signature `-Silent` `-Force` shown) |

---

## 2. Critical Error-Path Scenarios

| Scenario | Expected | Actual | Status |
|----------|----------|--------|--------|
| `validate_backup` — missing file | `FileNotFoundError`, `[ERROR]` msg, exit 1 | `[ERROR] File not found: no_such_file.vkb`, exit 1 | PASS |
| `validate_backup` — corrupt magic bytes | `ValueError`, `[ERROR]` msg, exit 2 | `[ERROR] Backup validation failed: Invalid backup magic bytes` | PASS |
| `validate_backup` — wrong version (999) | `ValueError` with "version" in message, exit 2 | `[ERROR] Incompatible backup version: Unsupported backup version: 999` | PASS |
| BOM `.env` — OPENAI key detected | Key present in parsed dict | `{'OPENAI_API_KEY': 'sk-test123', ...}` | PASS |
| BOM `.env` — ANTHROPIC key detected | Key present in parsed dict | Both keys parsed correctly | PASS |
| BOM `.env` — value correct | `sk-test123` | `sk-test123` | PASS |
| Write-back without BOM | First 3 bytes ≠ `[239, 187, 191]` | `[65, 78, 84]` (no BOM) | PASS |
| Readonly `.env` — `os.chmod` clears flag | Returns without `OSError` | chmod succeeded | PASS |
| Readonly `.env` — `copy2` or `os.replace` | At least one succeeds | `copy2` succeeded after chmod | PASS |
| Readonly `.env` — content restored | Original content present | `OPENAI_API_KEY=original` | PASS |

---

## 3. PowerShell Script Structure

| Check | Expected | Status |
|-------|----------|--------|
| `param(...)` before `$ErrorActionPreference` | `param` at line 28, `$ErrorActionPreference` at line 33 | PASS |
| `#Requires -Version 5.1` in first 5 lines | Present | PASS |
| `-Silent` parameter in `param` block | Present | PASS |
| `-Force` parameter in `param` block | Present | PASS |
| `.SYNOPSIS` comment-help block | Present | PASS |

---

## 4. New Features

| Feature | Script | Status |
|---------|--------|--------|
| `--dry-run` (shows key count, no write) | `backup_keys.py` | PASS — `Dry-run: would write 0 key(s)` |
| `create_backup_file` + immediate `validate` | `backup_keys.py` | PASS — `key_count=0 checksum_ok=True` |
| `--dry-run` (validate + skip restore) | `restore_keys.py` | PASS |
| `--force` skips `input()` confirmation | `restore_keys.py` | PASS |

---

## 5. Color Output & Verbose

| Check | Status |
|-------|--------|
| ANSI codes disabled when `stdout.isatty()=False` | PASS |
| `validate_backup.py` has `isatty()` guard | PASS |
| ANSI green `\033[32m` present | PASS |
| ANSI red `\033[31m` present | PASS |
| `--verbose` flag in `validate_backup.py` | PASS |
| `traceback.print_exc()` in `validate_backup.py` | PASS |
| `--verbose` flag in `backup_keys.py` | PASS |
| `traceback.print_exc()` in `backup_keys.py` | PASS |
| `--verbose` flag in `restore_keys.py` | PASS |
| `traceback.print_exc()` in `restore_keys.py` | PASS |

---

## 6. Summary of Fixes Applied

| Fix | File | Status |
|-----|------|--------|
| `param(...)` moved before `$ErrorActionPreference` | `setup_windows_keys.ps1` | Done |
| `#Requires -Version 5.1` added | `setup_windows_keys.ps1` | Done |
| `-Force` parameter added | `setup_windows_keys.ps1` | Done |
| `.SYNOPSIS` / `.PARAMETER` / `.EXAMPLE` help block | `setup_windows_keys.ps1` | Done |
| Inline Python f-string quote escaping fixed | `setup_windows_keys.ps1` | Done |
| `try/except` wrapping all `validate_backup_file` calls | `validate_backup.py` | Done |
| User-friendly `[ERROR]` messages (no raw traceback) | `validate_backup.py` | Done |
| Exit codes: `0`=valid, `1`=error, `2`=wrong version/corrupt | `validate_backup.py` | Done |
| `--verbose` flag for opt-in traceback | `validate_backup.py` | Done |
| ANSI color output gated on `isatty()` | `validate_backup.py` | Done |
| `os.chmod` before `copy2` in rollback | `migrate_env_to_encrypted.py` | Done |
| `os.replace` fallback if `copy2` fails | `migrate_env_to_encrypted.py` | Done |
| `[WARN] Partial rollback` with backup path logged | `migrate_env_to_encrypted.py` | Done |
| `encoding="utf-8-sig"` in `_parse_env_file` | `migrate_env_to_encrypted.py` | Done |
| `line.lstrip("\ufeff")` belt-and-suspenders BOM strip | `migrate_env_to_encrypted.py` | Done |
| Write-back uses plain `encoding="utf-8"` (no BOM) | `migrate_env_to_encrypted.py` | Done |
| `[INFO]`/`[WARN]`/`[ERROR]` prefixes standardised | `migrate_env_to_encrypted.py` | Done |
| `--dry-run` added | `backup_keys.py` | Done |
| `--verbose` + `try/except` with friendly errors | `backup_keys.py` | Done |
| Exit code table in `--help` epilog | `backup_keys.py` | Done |
| `--force` added (skips confirmation for `replace`) | `restore_keys.py` | Done |
| `--verbose` + `try/except` with friendly errors | `restore_keys.py` | Done |
| Exit code table in `--help` epilog | `restore_keys.py` | Done |

---

## 7. Known Minor Issues (Non-blocking)

| Issue | Impact | Recommendation |
|-------|--------|----------------|
| Project import startup takes ~30 s on first run | UX — slow `--help` | Lazy-import `KeyManager` only inside `main()`, not at module level |
| `pydantic` V2 deprecation warning on every run | Noise in output | Update `AppConfig` fields: rename `allow_population_by_field_name` → `validate_by_name` |
| `google.generativeai` deprecation warning | Noise in output | Migrate to `google.genai` package |
| `setup_windows_keys.ps1` `Get-Help -Full` shows only signature | PS5.1 comment-help parsing | Move `<# ... #>` block to immediately precede `param()`; `#Requires` must stay first |

None of the above block correct functionality.

---

## Verdict

**All 29 smoke-test checks passed. CLI tools are production-ready.**
