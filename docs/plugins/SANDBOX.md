# Sandbox Execution Details

## Overview

`SandboxEngine` executes plugin callbacks with layered restrictions:

- timeout enforcement (`asyncio.timeout`),
- memory ceilings (`resource.setrlimit` when available),
- filesystem path restrictions (`open` guard),
- network whitelist restrictions (`socket` guards),
- process creation blocking (`subprocess`/`os.system` guards).

## Effective limits

Execution limits are computed as:

- `effective_memory_mb = min(global_sandbox_limit, plugin.max_memory_mb)`
- `effective_timeout = min(global_timeout, plugin.max_execution_time_seconds)`

This ensures per-plugin limits can be stricter than global defaults.

## Filesystem policy

Global `plugins.sandbox.filesystem_whitelist` is treated as read-only safe roots.
Plugin write access is only allowed when:

1. plugin has `WRITE` (or higher) permission level,
2. target path is in plugin `filesystem.write`,
3. path is still inside global whitelist.

## Network policy

Network access is allowed only when:

1. plugin permission level is `NETWORK` (or `SYSTEM`),
2. host is in plugin `network` allow-list,
3. host is in global sandbox network whitelist (if configured).

## Process policy

Process creation is denied unless plugin runs with `SYSTEM` level.
Attempts are audited and raise `SecurityViolationError`.

## Limitations

Current implementation focuses on practical, low-overhead isolation in-process.
For hostile multi-tenant environments, extend this with stronger OS-level isolation:

- separate worker process/container per plugin,
- seccomp/AppArmor profiles,
- cgroup memory and CPU quotas,
- read-only mount namespaces.
