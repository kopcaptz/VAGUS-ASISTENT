"""Send a test alert through Telegram channel configuration."""

from __future__ import annotations

import os
from datetime import datetime, timezone

from vagus.monitoring.alerting import AlertEvent, AlertingService


def main() -> int:
    service = AlertingService.from_yaml("configs/telegram_test.yaml")
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        print("SKIPPED: set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID to send a real test alert.")
        return 0

    service.config.telegram.bot_token = token
    service.config.telegram.chat_id = chat_id

    alert = AlertEvent(
        rule="telegram_test",
        severity="info",
        message="Vagus test alert: Telegram integration is working.",
        timestamp=datetime.now(timezone.utc).isoformat(),
        details={"source": "scripts/test_telegram_alert.py"},
    )
    result = service.notify([alert])
    if result.get("errors"):
        print(f"FAILED: {result['errors']}")
        return 1
    print(f"OK: sent={result.get('sent', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
