"""Basic plugin template."""


class Plugin:
    """Minimal plugin entry point."""

    def on_message_received(self, message: dict) -> dict:
        updated = dict(message)
        updated["plugin"] = "test-plugin"
        return updated
