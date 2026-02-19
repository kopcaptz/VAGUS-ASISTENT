"""Marketplace demo plugin."""


class MarketplaceDemoPlugin:
    """Example plugin for marketplace publication demos."""

    def on_message_received(self, message: dict) -> dict:
        updated = dict(message)
        tags = list(updated.get("tags", []))
        tags.append("marketplace-demo")
        updated["tags"] = tags
        return updated
