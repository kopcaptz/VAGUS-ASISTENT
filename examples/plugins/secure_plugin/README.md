# Secure Plugin Example

This example shows a plugin with explicit runtime permissions and signature metadata.

## Files

- `manifest.json` — includes `runtime_permissions` and signature fields.
- `plugin.py` — safe hook implementation (`pre_task_execution`).

## Notes

- For production, sign `manifest.json` with Ed25519 and place signature into `manifest.sig`.
- Load plugin with `SecurePluginLoader` and `require_signatures=true`.
