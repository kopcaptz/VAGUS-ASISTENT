# Plugin Integration Guide

## Agent System (Layer 2)

`TaskOrchestrator` now supports plugin hooks:

- `pre_task_execution(task)` — mutate task payload before agent selection.
- `post_task_execution(task, result)` — transform successful result.
- `on_error(task, error)` — react to orchestration errors.

Plugins can inject additional steps by returning:

```python
{
  "task_id": "...",
  "prompt": "...",
  "task_type": "...",
  "metadata": {...},
  "additional_steps": ["validate sources", "add custom audit trail"]
}
```

## LLM Router (Layer 1)

`LLMRouter` supports plugin hooks:

- `pre_llm_call(call_context)`
- `post_llm_call(call_context, response_payload)`
- `on_llm_error(call_context, error)`

Plugins can also register custom providers via:

- `llm_providers` mapping,
- `get_llm_providers()`,
- `register_llm_providers(registry)`.

## Dashboard

Dashboard plugin integration registry allows:

- dynamic pages (`get_dashboard_pages`),
- widgets (`get_dashboard_widgets`),
- widgets on existing pages (e.g. Performance page).

## CLI

Plugins can contribute commands dynamically:

- `get_cli_commands()` -> `vagus plugin <plugin_name> <command>`
- `get_cli_subcommands()` -> add subcommands to `task/agent/admin`.

## Telegram

Plugins can add:

- message handlers (`handle_telegram_message`),
- inline buttons (`get_telegram_buttons`).

Handlers are dispatched through `TelegramPluginIntegration`.
