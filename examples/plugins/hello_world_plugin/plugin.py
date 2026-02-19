"""Example hello world plugin."""


class HelloWorldPlugin:
    """Simple plugin that prepends a greeting to incoming text message."""

    def on_message_received(self, message: dict) -> dict:
        updated = dict(message)
        text = str(updated.get("text", "")).strip()
        updated["text"] = f"Hello from plugin! {text}".strip()
        return updated
