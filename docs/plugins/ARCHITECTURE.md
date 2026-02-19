# Plugin Architecture (Vagus)

## Goals

Plugin system provides:

- package-based extension model (`manifest.json` + Python entry point),
- loading from local folders, Git repositories, and PyPI packages,
- safe execution boundaries (sandbox policy abstraction),
- hot-reload support without full application restart,
- hook-based extension points for task/message/config lifecycles.

## Directory Layout

```text
src/vagus/plugins/
├── core/           # Base Pydantic models
├── registry/       # Thread-safe singleton plugin registry
├── loader/         # Local/Git/PyPI plugin loaders
├── sandbox/        # Sandboxed execution abstraction
├── hooks/          # Hook registration and execution system
└── marketplace/    # Marketplace integration primitives
```

## Core Models

`src/vagus/plugins/core/models.py` defines:

- `PluginManifest` — plugin metadata and requirements.
- `PluginState` — lifecycle status (`LOADED/ENABLED/DISABLED/ERROR`) and diagnostics.
- `HookDefinition` — hook descriptor with priority (1-100), callback, async flag.
- `PluginConfig` — plugin runtime config payload (`settings/secrets/ui_schema`).
- `LoadedPlugin` — runtime aggregate object used by registry/loader.

## Loading Pipeline

All loaders follow the same flow:

1. validate `manifest.json`,
2. check Python/Vagus version constraints and dependencies,
3. import plugin `entry_point`,
4. return a `LoadedPlugin`.

Implemented loaders:

- `LocalLoader` — loads plugin from local directory.
- `GitLoader` — clones repository and delegates to `LocalLoader`.
- `PyPILoader` — installs package to isolated target dir and delegates to `LocalLoader`.

## Registry

`PluginRegistry` is a singleton with thread-safe operations:

- `register(plugin)`,
- `unregister(plugin_name)`,
- `get_plugin(name)`,
- `list_plugins(state=None)`,
- `get_hooks(hook_name)`.

## Hook System

`HookSystem` supports sync/async callbacks and strict priorities:

- `pre_task_execution(task)` -> can mutate task,
- `post_task_execution(task, result)` -> can transform result,
- `on_error(task, error)` -> error handlers,
- `on_message_received(message)` -> message preprocessing,
- `on_config_changed(config)` -> config reaction.

Callbacks with higher priority run first.

## Sandbox

`SandboxExecutor` currently enforces timeout-based execution boundaries and provides
an extension point for stronger OS-level isolation (process/container isolation,
memory cgroups, seccomp profiles) in subsequent iterations.

## Hot Reload

`LocalLoader.reload(...)` supports module reload for already loaded plugins. This
enables iterative plugin development without restarting the host application.

