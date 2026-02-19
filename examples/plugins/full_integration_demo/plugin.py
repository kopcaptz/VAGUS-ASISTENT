"""Full integration demo plugin."""

from __future__ import annotations


class FullIntegrationDemoPlugin:
    """Example plugin exposing integration points for all application surfaces."""

    def pre_task_execution(self, task: dict) -> dict:
        updated = dict(task)
        metadata = dict(updated.get("metadata", {}))
        metadata["full_demo"] = True
        updated["metadata"] = metadata
        updated["additional_steps"] = ["plugin: validate payload", "plugin: enrich context"]
        return updated

    def post_task_execution(self, task: dict, result: dict) -> dict:
        updated = dict(result)
        updated["plugin_note"] = "processed by full_integration_demo"
        return updated

    def pre_llm_call(self, context: dict) -> dict:
        updated = dict(context)
        prompt = str(updated.get("prompt", ""))
        updated["prompt"] = f"{prompt}\n\n[Plugin context: full integration demo]"
        return updated

    def get_dashboard_pages(self):
        return [
            {
                "route": "demo/full-integration",
                "title": "Full Integration Demo",
                "render": lambda **_: {"message": "Demo page rendered"},
            }
        ]

    def get_dashboard_widgets(self):
        return [
            {
                "target_page": "performance",
                "name": "Demo Performance Widget",
                "render": lambda snapshot=None, **_: {
                    "metric": "latency_ms",
                    "value": (snapshot or {}).get("request_latency_ms", 0),
                },
            }
        ]

    def get_cli_commands(self):
        def ping():
            print("plugin pong")

        return [{"name": "ping", "callback": ping, "help": "Demo plugin ping command"}]

    async def handle_telegram_message(self, message_text: str, context: dict) -> str | None:
        if message_text.strip().lower().startswith("/demo"):
            return f"Demo reply for user {context.get('user_id', 'unknown')}"
        return None

    def get_telegram_buttons(self):
        async def handler(context: dict) -> str:
            return f"Inline demo action for chat {context.get('chat_id', 'unknown')}"

        return [
            {
                "text": "Demo Action",
                "callback_data": "demo_action",
                "handler": handler,
            }
        ]
