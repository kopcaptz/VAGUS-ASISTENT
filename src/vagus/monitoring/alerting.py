"""
Alerting service with YAML-configurable rules and notification channels.
"""

from __future__ import annotations

import json
import smtplib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from typing import Any, Dict, Iterable, List, Optional
from urllib import error, request

import yaml


@dataclass
class AlertRules:
    high_error_rate_percent_5m: float = 5.0
    high_latency_p95_seconds: float = 5.0
    circuit_breaker_open_minutes: float = 5.0
    disk_free_percent_min: float = 10.0


@dataclass
class TelegramChannelConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""


@dataclass
class EmailChannelConfig:
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 587
    username: str = ""
    password: str = ""
    from_email: str = ""
    to_emails: List[str] = field(default_factory=list)
    use_tls: bool = True


@dataclass
class WebhookChannelConfig:
    enabled: bool = False
    url: str = ""
    timeout_seconds: float = 5.0


@dataclass
class AlertingConfig:
    rules: AlertRules = field(default_factory=AlertRules)
    telegram: TelegramChannelConfig = field(default_factory=TelegramChannelConfig)
    email: EmailChannelConfig = field(default_factory=EmailChannelConfig)
    webhook: WebhookChannelConfig = field(default_factory=WebhookChannelConfig)


@dataclass
class AlertSnapshot:
    error_rate_percent_5m: float
    latency_p95_seconds: float
    circuit_breaker_open_minutes: float
    disk_free_percent: float
    llm_providers: Dict[str, bool]


@dataclass
class AlertEvent:
    rule: str
    severity: str
    message: str
    timestamp: str
    details: Dict[str, Any]


def _to_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    if isinstance(value, int):
        return value != 0
    return default


def _to_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    result: List[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            result.append(item.strip())
    return result


def load_alerting_config_from_yaml(path: str) -> AlertingConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        data = {}

    rules_data = data.get("rules", {})
    if not isinstance(rules_data, dict):
        rules_data = {}
    rules = AlertRules(
        high_error_rate_percent_5m=_to_float(rules_data.get("high_error_rate_percent_5m"), 5.0),
        high_latency_p95_seconds=_to_float(rules_data.get("high_latency_p95_seconds"), 5.0),
        circuit_breaker_open_minutes=_to_float(
            rules_data.get("circuit_breaker_open_minutes"),
            5.0,
        ),
        disk_free_percent_min=_to_float(rules_data.get("disk_free_percent_min"), 10.0),
    )

    channels_data = data.get("channels", {})
    if not isinstance(channels_data, dict):
        channels_data = {}

    telegram_data = channels_data.get("telegram", {})
    if not isinstance(telegram_data, dict):
        telegram_data = {}
    telegram = TelegramChannelConfig(
        enabled=_to_bool(telegram_data.get("enabled"), False),
        bot_token=str(telegram_data.get("bot_token", "")),
        chat_id=str(telegram_data.get("chat_id", "")),
    )

    email_data = channels_data.get("email", {})
    if not isinstance(email_data, dict):
        email_data = {}
    email = EmailChannelConfig(
        enabled=_to_bool(email_data.get("enabled"), False),
        smtp_host=str(email_data.get("smtp_host", "")),
        smtp_port=_to_int(email_data.get("smtp_port"), 587),
        username=str(email_data.get("username", "")),
        password=str(email_data.get("password", "")),
        from_email=str(email_data.get("from_email", "")),
        to_emails=_to_string_list(email_data.get("to_emails")),
        use_tls=_to_bool(email_data.get("use_tls"), True),
    )

    webhook_data = channels_data.get("webhook", {})
    if not isinstance(webhook_data, dict):
        webhook_data = {}
    webhook = WebhookChannelConfig(
        enabled=_to_bool(webhook_data.get("enabled"), False),
        url=str(webhook_data.get("url", "")),
        timeout_seconds=_to_float(webhook_data.get("timeout_seconds"), 5.0),
    )

    return AlertingConfig(
        rules=rules,
        telegram=telegram,
        email=email,
        webhook=webhook,
    )


def evaluate_alert_rules(snapshot: AlertSnapshot, rules: AlertRules) -> List[AlertEvent]:
    alerts: List[AlertEvent] = []
    now = datetime.now(timezone.utc).isoformat()

    if snapshot.error_rate_percent_5m > rules.high_error_rate_percent_5m:
        alerts.append(
            AlertEvent(
                rule="high_error_rate",
                severity="critical",
                message=(
                    f"High error rate detected: {snapshot.error_rate_percent_5m:.2f}% "
                    f"(threshold={rules.high_error_rate_percent_5m:.2f}%)"
                ),
                timestamp=now,
                details={"error_rate_percent_5m": snapshot.error_rate_percent_5m},
            )
        )

    if snapshot.latency_p95_seconds > rules.high_latency_p95_seconds:
        alerts.append(
            AlertEvent(
                rule="high_latency",
                severity="critical",
                message=(
                    f"High latency detected: p95={snapshot.latency_p95_seconds:.2f}s "
                    f"(threshold={rules.high_latency_p95_seconds:.2f}s)"
                ),
                timestamp=now,
                details={"latency_p95_seconds": snapshot.latency_p95_seconds},
            )
        )

    if snapshot.circuit_breaker_open_minutes > rules.circuit_breaker_open_minutes:
        alerts.append(
            AlertEvent(
                rule="circuit_breaker_open_too_long",
                severity="warning",
                message=(
                    "Circuit breaker remained open too long: "
                    f"{snapshot.circuit_breaker_open_minutes:.2f} min "
                    f"(threshold={rules.circuit_breaker_open_minutes:.2f} min)"
                ),
                timestamp=now,
                details={
                    "circuit_breaker_open_minutes": snapshot.circuit_breaker_open_minutes
                },
            )
        )

    if snapshot.disk_free_percent < rules.disk_free_percent_min:
        alerts.append(
            AlertEvent(
                rule="low_disk_space",
                severity="critical",
                message=(
                    f"Low disk space: free={snapshot.disk_free_percent:.2f}% "
                    f"(threshold={rules.disk_free_percent_min:.2f}%)"
                ),
                timestamp=now,
                details={"disk_free_percent": snapshot.disk_free_percent},
            )
        )

    down_providers = sorted([name for name, ok in snapshot.llm_providers.items() if not ok])
    if down_providers:
        alerts.append(
            AlertEvent(
                rule="llm_provider_down",
                severity="critical",
                message=f"LLM providers unavailable: {', '.join(down_providers)}",
                timestamp=now,
                details={"down_providers": down_providers},
            )
        )

    return alerts


class _Notifier:
    def send(self, alert: AlertEvent) -> None:
        raise NotImplementedError


class TelegramNotifier(_Notifier):
    def __init__(self, config: TelegramChannelConfig):
        self.config = config

    def send(self, alert: AlertEvent) -> None:
        if not self.config.enabled:
            return
        if not self.config.bot_token or not self.config.chat_id:
            raise ValueError("Telegram channel is enabled but bot_token/chat_id are missing")

        url = f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
        body = json.dumps(
            {
                "chat_id": self.config.chat_id,
                "text": f"[{alert.severity}] {alert.message}",
            }
        ).encode("utf-8")
        req = request.Request(
            url,
            method="POST",
            headers={"Content-Type": "application/json"},
            data=body,
        )
        with request.urlopen(req, timeout=5):
            pass


class EmailNotifier(_Notifier):
    def __init__(self, config: EmailChannelConfig):
        self.config = config

    def send(self, alert: AlertEvent) -> None:
        if not self.config.enabled:
            return
        if not self.config.smtp_host or not self.config.from_email or not self.config.to_emails:
            raise ValueError("Email channel is enabled but SMTP/from/to config is incomplete")

        message = EmailMessage()
        message["Subject"] = f"[Vagus][{alert.severity}] {alert.rule}"
        message["From"] = self.config.from_email
        message["To"] = ", ".join(self.config.to_emails)
        message.set_content(f"{alert.message}\n\nDetails:\n{json.dumps(alert.details, indent=2)}")

        with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port, timeout=10) as smtp:
            if self.config.use_tls:
                smtp.starttls()
            if self.config.username:
                smtp.login(self.config.username, self.config.password)
            smtp.send_message(message)


class WebhookNotifier(_Notifier):
    def __init__(self, config: WebhookChannelConfig):
        self.config = config

    def send(self, alert: AlertEvent) -> None:
        if not self.config.enabled:
            return
        if not self.config.url:
            raise ValueError("Webhook channel is enabled but URL is missing")

        payload = {
            "rule": alert.rule,
            "severity": alert.severity,
            "message": alert.message,
            "timestamp": alert.timestamp,
            "details": alert.details,
        }
        req = request.Request(
            self.config.url,
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload).encode("utf-8"),
        )
        with request.urlopen(req, timeout=self.config.timeout_seconds):
            pass


class AlertingService:
    def __init__(self, config: AlertingConfig):
        self.config = config
        self._notifiers: List[_Notifier] = [
            TelegramNotifier(config.telegram),
            EmailNotifier(config.email),
            WebhookNotifier(config.webhook),
        ]

    @classmethod
    def from_yaml(cls, path: str) -> "AlertingService":
        return cls(load_alerting_config_from_yaml(path))

    def evaluate(self, snapshot: AlertSnapshot) -> List[AlertEvent]:
        return evaluate_alert_rules(snapshot, self.config.rules)

    def notify(self, alerts: Iterable[AlertEvent]) -> Dict[str, Any]:
        sent = 0
        errors: List[str] = []
        for alert in alerts:
            for notifier in self._notifiers:
                try:
                    notifier.send(alert)
                    sent += 1
                except (ValueError, error.URLError, smtplib.SMTPException, TimeoutError) as exc:
                    errors.append(str(exc))
                except Exception as exc:
                    errors.append(str(exc))
        return {"sent": sent, "errors": errors}


__all__ = [
    "AlertRules",
    "AlertSnapshot",
    "AlertEvent",
    "AlertingConfig",
    "AlertingService",
    "EmailChannelConfig",
    "TelegramChannelConfig",
    "WebhookChannelConfig",
    "evaluate_alert_rules",
    "load_alerting_config_from_yaml",
]
