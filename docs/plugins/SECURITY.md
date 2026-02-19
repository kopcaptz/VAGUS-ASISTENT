# Plugin Security Model

## Threat model

Plugin code is considered untrusted by default. Security controls aim to reduce risk of:

- arbitrary command execution,
- unrestricted filesystem access,
- data exfiltration over network,
- unauthorized environment secret access,
- dependency supply-chain abuse.

## Permission model

Runtime permissions are declared via `PluginPermissions`:

- `level`: `NONE | READ | WRITE | NETWORK | SYSTEM`
- `filesystem.read[]` and `filesystem.write[]`
- `network[]` domain allow-list
- `environment_variables[]` allow-list
- `max_memory_mb`
- `max_execution_time_seconds`

`SYSTEM` is trusted mode and bypasses restrictions. For third-party plugins it should be avoided.

## Security manager

`SecurityManager` performs runtime checks and emits audit events for every sensitive operation:

- filesystem reads/writes,
- network access attempts,
- environment variable reads,
- process creation attempts.

Denied operations raise `SecurityViolationError`.

## Secure loading

`SecurePluginLoader` adds controls on top of standard loading:

1. manifest signature verification (optional/required),
2. dependency vetting (allow-list + max dependency count),
3. static code scan for banned imports/calls (e.g. `os.system`, `subprocess.Popen`, `ctypes`),
4. quarantine of suspicious plugins.

## Digital signatures

`PluginSignatureVerifier` supports:

- Ed25519 verification for `manifest.json`,
- GPG verification for marketplace artifacts.

Trusted public keys are stored in `TrustStore`.

## Monitoring and auto-disable

`PluginMonitor` tracks:

- execution time,
- memory usage,
- error rate,
- security violation count.

Plugins are automatically disabled when limits or security thresholds are exceeded.
