# Windows Setup for API Keys

## Prerequisites

- Python 3.10+
- Project dependencies installed (`cryptography` is required)

## Quick Setup

### Batch

```bat
scripts\setup_windows_keys.bat
```

### PowerShell

```powershell
.\scripts\setup_windows_keys.ps1
```

Use silent mode for automation:

- Batch: `scripts\\setup_windows_keys.bat --silent`
- PowerShell: `.\scripts\setup_windows_keys.ps1 -Silent`

## What setup does

- Validates Python environment
- Creates `~/.vagus` storage if needed
- Initializes master key using DPAPI on Windows when available
- Falls back to file-based master key if DPAPI is unavailable

## DPAPI Notes

- DPAPI ties encryption to Windows account context.
- Master key file uses DPAPI envelope format (`DPAPIv1`).
- Legacy plain/base64 master keys are migrated automatically.
- Plaintext backup of master key is not created.

## Troubleshooting

- `Python not found`: add Python to `PATH`.
- `Missing dependency: cryptography`: run `pip install -r requirements.txt`.
- DPAPI errors: confirm process is running under a normal user profile and retry.
- Recovery path: restore access via the same Windows user context (DPAPI-bound key), or provide `VAGUS_KEYS_MASTER_KEY` explicitly for controlled recovery.
