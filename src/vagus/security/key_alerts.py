"""API key alert manager with throttling and escalation."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

from vagus.monitoring.alerting import AlertEvent, AlertingService
from vagus.security.key_backup import create_backup_file
from vagus.security.key_manager import KeyManager


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class KeyAlertConfig:
    enabled: bool = True
    interval_seconds: int = 21600
    expiring_days_threshold: int = 7
    throttle_seconds: int = 3600
    escalation_warnings: int = 3
    backup_enabled: bool = False
    backup_schedule: str = "0 2 * * *"
    backup_retention_days: int = 7
    backup_max_backups: int = 10
    backup_encryption_password: Optional[str] = None
    backup_dir: str = "~/.vagus/backups"


class KeyAlertManager:
    """Runs scheduled API key health checks and emits alerts."""

    def __init__(
        self,
        *,
        key_manager: Optional[KeyManager] = None,
        alerting_service: Optional[AlertingService] = None,
        config: Optional[KeyAlertConfig] = None,
    ) -> None:
        self.key_manager = key_manager or KeyManager()
        self.alerting_service = alerting_service
        self.config = config or KeyAlertConfig()
        self._task: Optional[asyncio.Task[None]] = None
        self._running = False
        self._last_sent_at: dict[tuple[str, str], datetime] = {}
        self._warning_streaks: dict[tuple[str, str], int] = {}
        self._next_backup_at: Optional[datetime] = None

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self) -> None:
        if not self.config.enabled or self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(), name="vagus-key-alerts")

    async def stop(self) -> None:
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def run_once(self) -> dict[str, Any]:
        alerts = self._build_alerts()
        if not alerts or self.alerting_service is None:
            return {"alerts": alerts, "sent": 0, "errors": []}
        notify_result = self.alerting_service.notify(alerts)
        return {"alerts": alerts, **notify_result}

    async def _run_loop(self) -> None:
        interval = max(60, int(self.config.interval_seconds))
        while self._running:
            try:
                await self.run_once()
                await self._maybe_run_scheduled_backup()
            except Exception:
                pass
            await asyncio.sleep(interval)

    async def _maybe_run_scheduled_backup(self) -> None:
        if not self.config.backup_enabled:
            return
        now = _utc_now()
        if self._next_backup_at is None:
            self._next_backup_at = self._compute_next_backup_time(now)
        if self._next_backup_at is None or now < self._next_backup_at:
            return
        try:
            backup_dir = Path(self.config.backup_dir).expanduser()
            filename = f"scheduled_keys_{now.strftime('%Y%m%d_%H%M%S')}.vkb"
            create_backup_file(
                key_manager=self.key_manager,
                backup_path=backup_dir / filename,
                password=self.config.backup_encryption_password,
            )
            self._cleanup_old_backups(backup_dir=backup_dir)
        except Exception as exc:
            if self.alerting_service is not None:
                self.alerting_service.notify(
                    [
                        AlertEvent(
                            rule="key_backup_failed",
                            severity="warning",
                            message=f"Scheduled key backup failed: {exc}",
                            timestamp=now.isoformat(),
                            details={"backup_dir": self.config.backup_dir},
                        )
                    ]
                )
        finally:
            self._next_backup_at = self._compute_next_backup_time(now)

    def _compute_next_backup_time(self, now: datetime) -> Optional[datetime]:
        schedule = (self.config.backup_schedule or "").strip().lower()
        if schedule == "daily":
            candidate = now.replace(hour=2, minute=0, second=0, microsecond=0)
            if candidate <= now:
                candidate = candidate + timedelta(days=1)
            return candidate
        if schedule == "weekly":
            # Sunday at 02:00 UTC.
            days_until_sun = (6 - now.weekday()) % 7
            candidate = now.replace(hour=2, minute=0, second=0, microsecond=0) + timedelta(days=days_until_sun)
            if candidate <= now:
                candidate = candidate + timedelta(days=7)
            return candidate

        parts = schedule.split()
        if len(parts) == 5:
            minute_str, hour_str = parts[0], parts[1]
            if minute_str.isdigit() and hour_str.isdigit():
                minute = int(minute_str)
                hour = int(hour_str)
                candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if candidate <= now:
                    candidate = candidate + timedelta(days=1)
                return candidate
        return now + timedelta(days=1)

    def _cleanup_old_backups(self, *, backup_dir: Path) -> None:
        if not backup_dir.exists():
            return
        now = _utc_now()
        files = sorted(backup_dir.glob("scheduled_keys_*.vkb"), key=lambda p: p.stat().st_mtime, reverse=True)
        retention_days = max(1, int(self.config.backup_retention_days))
        cutoff = now - timedelta(days=retention_days)
        for old in files:
            try:
                modified = datetime.fromtimestamp(old.stat().st_mtime, tz=timezone.utc)
            except Exception:
                continue
            if modified < cutoff:
                try:
                    old.unlink()
                except Exception:
                    continue

        files = sorted(backup_dir.glob("scheduled_keys_*.vkb"), key=lambda p: p.stat().st_mtime, reverse=True)
        keep_max = max(1, int(self.config.backup_max_backups))
        for old in files[keep_max:]:
            try:
                old.unlink()
            except Exception:
                continue

    def _build_alerts(self) -> list[AlertEvent]:
        health = self.key_manager.get_health_stats(days_ahead=self.config.expiring_days_threshold)
        now = _utc_now()
        alerts: list[AlertEvent] = []

        for row in health.get("keys", []):
            key_name = str(row.get("name", ""))
            status = str(row.get("status", "unknown"))
            expires_in_days = row.get("expires_in_days")

            if status == "invalid":
                event = self._make_alert(
                    now=now,
                    key_name=key_name,
                    rule="key_validation_failed",
                    severity="WARNING",
                    message=f"API key '{key_name}' failed validation",
                    details={"status": status},
                )
                if event is not None:
                    alerts.append(event)
            if isinstance(expires_in_days, int) and expires_in_days <= self.config.expiring_days_threshold:
                sev = "CRITICAL" if expires_in_days < 0 else "WARNING"
                event = self._make_alert(
                    now=now,
                    key_name=key_name,
                    rule="key_expiring",
                    severity=sev,
                    message=f"API key '{key_name}' expires in {expires_in_days} day(s)",
                    details={"expires_in_days": expires_in_days},
                )
                if event is not None:
                    alerts.append(event)

        if bool(health.get("rotation_required")):
            event = self._make_alert(
                now=now,
                key_name="all",
                rule="key_rotation_required",
                severity="INFO",
                message="API key rotation is required (invalid or expiring keys detected)",
                details={
                    "invalid_keys": int(health.get("invalid_keys", 0)),
                    "expiring_soon": int(health.get("expiring_soon", 0)),
                },
            )
            if event is not None:
                alerts.append(event)

        return alerts

    def _make_alert(
        self,
        *,
        now: datetime,
        key_name: str,
        rule: str,
        severity: str,
        message: str,
        details: dict[str, Any],
    ) -> Optional[AlertEvent]:
        identity = (rule, key_name)
        prev_sent = self._last_sent_at.get(identity)
        if prev_sent is not None and (now - prev_sent).total_seconds() < int(self.config.throttle_seconds):
            return None

        if severity == "WARNING":
            streak = self._warning_streaks.get(identity, 0) + 1
            self._warning_streaks[identity] = streak
            if streak >= int(self.config.escalation_warnings):
                severity = "CRITICAL"
                message = f"{message} (escalated after {streak} warnings)"
        else:
            self._warning_streaks[identity] = 0

        self._last_sent_at[identity] = now
        return AlertEvent(
            rule=rule,
            severity=severity.lower(),
            message=message,
            timestamp=now.isoformat(),
            details=details,
        )
