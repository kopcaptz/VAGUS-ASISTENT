# Vagus Key Backup Format (v1)

## Binary layout

1. Magic bytes: `VAGUS_KEY_BACKUP_v1`
2. Newline separator (`\\n`)
3. Metadata JSON (single line, UTF-8)
4. Newline separator (`\\n`)
5. Encrypted payload bytes (AES-256-GCM)

## Metadata fields

- `version`: integer format version (`1`)
- `timestamp`: ISO-8601 UTC creation time
- `key_count`: number of keys in payload
- `checksum`: SHA-256 of decrypted JSON payload
- `has_password_layer`: whether additional password encryption is used
- `salt`: base64 KDF salt for outer encryption key
- `nonce`: base64 AES-GCM nonce for outer payload

## Encryption model

- Outer layer:
  - seed: KeyManager master key
  - KDF: PBKDF2-SHA256 (390000 iterations)
  - cipher: AES-256-GCM
- Optional inner password layer:
  - seed: user-provided password
  - KDF: PBKDF2-SHA256 (390000 iterations)
  - cipher: AES-256-GCM

## Validation rules

- Magic and version must match.
- Metadata must be valid JSON object.
- Decryption must succeed with current master key (and password if required).
- `checksum` must match decrypted payload bytes.
