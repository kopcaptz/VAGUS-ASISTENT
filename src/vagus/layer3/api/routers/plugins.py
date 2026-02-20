"""
Plugin management router for dashboard/API clients.
"""

from __future__ import annotations

import asyncio
import json
import re
import importlib.util
from collections import deque
from datetime import datetime, timezone
from importlib import metadata as importlib_metadata
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect, status
from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.version import InvalidVersion, Version

from vagus.monitoring.alerting import (
    AlertEvent,
    AlertRules,
    AlertingConfig,
    AlertingService,
    EmailChannelConfig,
    TelegramChannelConfig,
    WebhookChannelConfig,
)
from vagus.plugins.analytics import PluginAnalytics
from vagus.plugins.core.models import PluginLifecycleState
from vagus.plugins.dependencies import DependencyResolutionError, PluginDependencyResolver
from vagus.plugins.hot_reload import HotReloadConfig, HotReloadManager, WATCHDOG_AVAILABLE
from vagus.plugins.manager import PluginManager, PluginManagerError, PluginNotFoundError
from vagus.plugins.marketplace import MarketplaceClient
from vagus.plugins.monitoring import PluginMonitor

from ..auth import decode_access_token
from ..dependencies import get_current_admin
from ..models import (
    BulkDependencyUpdateRequest,
    BulkDependencyUpdateResponse,
    HotReloadLogEntry,
    HotReloadStatusResponse,
    HotReloadToggleResponse,
    MarketplaceInstallRequest,
    MarketplacePluginDetailResponse,
    MarketplacePluginSummary,
    PluginConfigResponse,
    PluginConfigUpdateRequest,
    PluginDependencyConflictsResponse,
    PluginDependencyResolveRequest,
    PluginDependencyResponse,
    PluginDependencyUpdateRequest,
    PluginDependencyUpdateResponse,
    PluginDeleteResponse,
    PluginInfoResponse,
    PluginInstallRequest,
    PluginReloadHistoryResponse,
    PluginReloadNowResponse,
    PluginStatisticsResponse,
)

router = APIRouter(prefix="/plugins", tags=["Plugins"])


def _get_plugin_manager(request: Request) -> PluginManager:
    manager = getattr(request.app.state, "plugin_manager", None)
    if isinstance(manager, PluginManager):
        return manager

    manager = PluginManager()
    request.app.state.plugin_manager = manager
    return manager


def _get_marketplace_client(request: Request) -> MarketplaceClient:
    client = getattr(request.app.state, "marketplace_client", None)
    if isinstance(client, MarketplaceClient):
        return client

    runtime_config = getattr(request.app.state, "runtime_config", {})
    plugins_cfg = runtime_config.get("plugins", {}) if isinstance(runtime_config, dict) else {}
    marketplace_cfg = plugins_cfg.get("marketplace", {}) if isinstance(plugins_cfg, dict) else {}

    url = str(marketplace_cfg.get("url", "https://plugins.vagus.ai"))
    cache_ttl_hours_raw = marketplace_cfg.get("cache_ttl_hours", 24)
    timeout_raw = marketplace_cfg.get("timeout_seconds", 10)
    offline_mode_raw = marketplace_cfg.get("offline_mode", False)

    try:
        cache_ttl_hours = max(1, int(cache_ttl_hours_raw))
    except (TypeError, ValueError):
        cache_ttl_hours = 24

    try:
        timeout_seconds = max(1, int(timeout_raw))
    except (TypeError, ValueError):
        timeout_seconds = 10

    client = MarketplaceClient(
        url=url,
        cache_ttl_hours=cache_ttl_hours,
        timeout_seconds=timeout_seconds,
        offline_mode=bool(offline_mode_raw),
    )
    request.app.state.marketplace_client = client
    return client


def _get_plugin_analytics(request: Request) -> PluginAnalytics:
    analytics = getattr(request.app.state, "plugin_analytics", None)
    if isinstance(analytics, PluginAnalytics):
        return analytics
    analytics = PluginAnalytics()
    request.app.state.plugin_analytics = analytics
    return analytics


def _get_plugin_event_bus(app) -> deque[dict[str, Any]]:
    bus = getattr(app.state, "plugin_realtime_events", None)
    if isinstance(bus, deque):
        return bus
    initialized: deque[dict[str, Any]] = deque(maxlen=2000)
    app.state.plugin_realtime_events = initialized
    app.state.plugin_realtime_seq = 0
    return initialized


def _publish_plugin_event(app, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    bus = _get_plugin_event_bus(app)
    next_seq = int(getattr(app.state, "plugin_realtime_seq", 0)) + 1
    app.state.plugin_realtime_seq = next_seq
    event = {
        "seq": next_seq,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "type": event_type,
        "payload": payload,
    }
    bus.append(event)
    return event


def _ensure_alerting_service(app) -> AlertingService:
    existing = getattr(app.state, "plugin_alerting_service", None)
    if isinstance(existing, AlertingService):
        return existing

    runtime_config = getattr(app.state, "runtime_config", {})
    monitoring_cfg = runtime_config.get("monitoring", {}) if isinstance(runtime_config, dict) else {}
    alerting_cfg = monitoring_cfg.get("alerting", {}) if isinstance(monitoring_cfg, dict) else {}
    if not isinstance(alerting_cfg, dict):
        alerting_cfg = {}
    rules_cfg = alerting_cfg.get("rules", {}) if isinstance(alerting_cfg.get("rules"), dict) else {}
    channels_cfg = (
        alerting_cfg.get("channels", {}) if isinstance(alerting_cfg.get("channels"), dict) else {}
    )

    telegram_cfg = channels_cfg.get("telegram", {})
    if not isinstance(telegram_cfg, dict):
        telegram_cfg = {}
    email_cfg = channels_cfg.get("email", {})
    if not isinstance(email_cfg, dict):
        email_cfg = {}
    webhook_cfg = channels_cfg.get("webhook", {})
    if not isinstance(webhook_cfg, dict):
        webhook_cfg = {}

    def _safe_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _safe_int(value: Any, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    service = AlertingService(
        AlertingConfig(
            rules=AlertRules(
                high_error_rate_percent_5m=_safe_float(
                    rules_cfg.get("high_error_rate_percent_5m", 5.0), 5.0
                ),
                high_latency_p95_seconds=_safe_float(
                    rules_cfg.get("high_latency_p95_seconds", 5.0), 5.0
                ),
                circuit_breaker_open_minutes=_safe_float(
                    rules_cfg.get("circuit_breaker_open_minutes", 5.0), 5.0
                ),
                disk_free_percent_min=_safe_float(rules_cfg.get("disk_free_percent_min", 10.0), 10.0),
            ),
            telegram=TelegramChannelConfig(
                enabled=bool(telegram_cfg.get("enabled", False)),
                bot_token=str(telegram_cfg.get("bot_token", "")),
                chat_id=str(telegram_cfg.get("chat_id", "")),
            ),
            email=EmailChannelConfig(
                enabled=bool(email_cfg.get("enabled", False)),
                smtp_host=str(email_cfg.get("smtp_host", "")),
                smtp_port=_safe_int(email_cfg.get("smtp_port", 587), 587),
                username=str(email_cfg.get("username", "")),
                password=str(email_cfg.get("password", "")),
                from_email=str(email_cfg.get("from_email", "")),
                to_emails=[
                    str(item)
                    for item in (email_cfg.get("to_emails", []) if isinstance(email_cfg.get("to_emails"), list) else [])
                    if str(item).strip()
                ],
                use_tls=bool(email_cfg.get("use_tls", True)),
            ),
            webhook=WebhookChannelConfig(
                enabled=bool(webhook_cfg.get("enabled", False)),
                url=str(webhook_cfg.get("url", "")),
                timeout_seconds=_safe_float(webhook_cfg.get("timeout_seconds", 5.0), 5.0),
            ),
        )
    )
    app.state.plugin_alerting_service = service
    return service


def _record_plugin_alert(
    app,
    *,
    message: str,
    severity: str = "warning",
    plugin_name: Optional[str] = None,
) -> dict[str, Any]:
    alerts = getattr(app.state, "plugin_alert_events", None)
    if not isinstance(alerts, deque):
        alerts = deque(maxlen=1000)
        app.state.plugin_alert_events = alerts
    event = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "severity": severity,
        "plugin_name": plugin_name,
        "message": message,
    }
    alerts.append(event)
    try:
        service = _ensure_alerting_service(app)
        notification_result = service.notify(
            [
                AlertEvent(
                    rule="plugin_alert",
                    severity=severity,
                    message=message,
                    timestamp=event["timestamp"],
                    details={"plugin_name": plugin_name},
                )
            ]
        )
        event["notifications_sent"] = int(notification_result.get("sent", 0))
        errors = notification_result.get("errors", [])
        event["notification_errors"] = [str(item) for item in errors] if isinstance(errors, list) else []
    except Exception as exc:
        event["notifications_sent"] = 0
        event["notification_errors"] = [str(exc)]
    _publish_plugin_event(app, "plugin_alert", event)
    return event


def _get_plugin_monitor(request: Request) -> PluginMonitor:
    monitor = getattr(request.app.state, "plugin_monitor", None)
    if isinstance(monitor, PluginMonitor):
        return monitor
    monitor = PluginMonitor(
        alert_callback=lambda message: _record_plugin_alert(
            request.app,
            message=message,
            severity="warning",
        )
    )
    request.app.state.plugin_monitor = monitor
    return monitor


def _load_hot_reload_config(request: Request) -> HotReloadConfig:
    runtime_config = getattr(request.app.state, "runtime_config", {})
    plugins_cfg = runtime_config.get("plugins", {}) if isinstance(runtime_config, dict) else {}
    hot_reload_cfg = plugins_cfg.get("hot_reload", {}) if isinstance(plugins_cfg, dict) else {}
    if not isinstance(hot_reload_cfg, dict):
        hot_reload_cfg = {}

    watch_directories_raw = hot_reload_cfg.get("watch_directories", ["./plugins", "~/.vagus/plugins"])
    if isinstance(watch_directories_raw, list):
        watch_directories = [str(path).strip() for path in watch_directories_raw if str(path).strip()]
    else:
        watch_directories = ["./plugins", "~/.vagus/plugins"]
    if not watch_directories:
        watch_directories = ["./plugins", "~/.vagus/plugins"]

    debounce_ms_raw = hot_reload_cfg.get("debounce_ms", 500)
    try:
        debounce_ms = max(50, int(debounce_ms_raw))
    except (TypeError, ValueError):
        debounce_ms = 500

    enabled_raw = hot_reload_cfg.get("enabled", True)
    enabled = bool(enabled_raw)

    return HotReloadConfig(
        enabled=enabled,
        watch_directories=watch_directories,
        debounce_ms=debounce_ms,
    )


def _sync_hot_reload_runtime(manager: HotReloadManager, plugin_manager: PluginManager) -> None:
    installed_plugins = plugin_manager.list_plugins()
    desired_names = {str(item.get("name")) for item in installed_plugins if item.get("name")}

    # Remove stale plugins from registry and hook bindings.
    for loaded in list(manager.registry.list_plugins()):
        if loaded.name in desired_names:
            continue
        manager.registry.unregister(loaded.name)
        old_bindings = getattr(manager, "_plugin_hook_bindings", {}).pop(loaded.name, [])
        for hook_name, callback in old_bindings:
            manager.hook_system.unregister_hook(hook_name, callback)

    existing_bindings = set(getattr(manager, "_plugin_hook_bindings", {}).keys())
    for item in installed_plugins:
        plugin_name = str(item.get("name", "")).strip()
        plugin_path = str(item.get("path", "")).strip()
        if not plugin_name or not plugin_path:
            continue
        path = Path(plugin_path).expanduser()
        if not path.exists():
            continue
        try:
            loaded = plugin_manager.local_loader.load(path)
        except Exception:
            continue
        loaded.state.state = (
            PluginLifecycleState.ENABLED
            if bool(item.get("enabled", True))
            else PluginLifecycleState.DISABLED
        )
        manager.registry.register(loaded)
        should_bind_hooks = bool(item.get("enabled", True))
        if should_bind_hooks and loaded.name not in existing_bindings:
            try:
                manager.register_plugin(loaded)
                existing_bindings.add(loaded.name)
            except Exception:
                continue
        if not should_bind_hooks and loaded.name in existing_bindings:
            old_bindings = getattr(manager, "_plugin_hook_bindings", {}).pop(loaded.name, [])
            for hook_name, callback in old_bindings:
                manager.hook_system.unregister_hook(hook_name, callback)
            existing_bindings.discard(loaded.name)


def _get_hot_reload_manager(request: Request) -> HotReloadManager:
    existing = getattr(request.app.state, "hot_reload_manager", None)
    if isinstance(existing, HotReloadManager):
        _sync_hot_reload_runtime(existing, _get_plugin_manager(request))
        return existing

    config = _load_hot_reload_config(request)
    manager = HotReloadManager(config=config)

    def _event_listener(event: dict[str, Any]) -> None:
        _publish_plugin_event(request.app, "hot_reload_event", event)
        if str(event.get("event_type")) == "plugin_reload_failed":
            _record_plugin_alert(
                request.app,
                message=f"Hot-reload failed for plugin '{event.get('plugin_name', 'unknown')}'",
                severity="critical",
                plugin_name=str(event.get("plugin_name", "") or None),
            )

    manager.add_event_listener(_event_listener)
    request.app.state.hot_reload_manager = manager
    _sync_hot_reload_runtime(manager, _get_plugin_manager(request))
    if manager.config.enabled:
        manager.start()
    return manager


def _format_hot_reload_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp": str(event.get("timestamp", "")),
        "event_type": str(event.get("event_type", "unknown")),
        "plugin_name": (
            str(event.get("plugin_name")) if event.get("plugin_name") is not None else None
        ),
        "success": event.get("success"),
        "details": event.get("details", {}) if isinstance(event.get("details"), dict) else {},
    }


def _build_plugin_health_rows(
    manager: PluginManager,
    monitor: PluginMonitor,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for plugin in manager.list_plugins():
        plugin_name = str(plugin.get("name", ""))
        metrics = monitor.get_metrics(plugin_name)
        executions = int(metrics.executions)
        errors = int(metrics.errors)
        avg_execution_time = float(metrics.average_execution_time_seconds)
        max_memory = float(metrics.max_memory_usage_mb)
        error_rate = float(metrics.error_rate) if executions > 0 else 0.0
        lifecycle_status = str(plugin.get("status", "UNKNOWN"))

        if lifecycle_status == "ERROR":
            if executions == 0:
                executions = 1
            if errors == 0:
                errors = 1
            error_rate = 1.0

        if not bool(plugin.get("enabled", True)):
            health_status = "DISABLED"
        elif lifecycle_status == "ERROR":
            health_status = "CRITICAL"
        elif error_rate >= monitor.max_error_rate:
            health_status = "CRITICAL"
        elif error_rate >= monitor.max_error_rate / 2:
            health_status = "DEGRADED"
        else:
            health_status = "HEALTHY"

        rows.append(
            {
                "name": plugin_name,
                "enabled": bool(plugin.get("enabled", True)),
                "lifecycle_status": lifecycle_status,
                "health_status": health_status,
                "executions": executions,
                "errors": errors,
                "error_rate": error_rate,
                "average_execution_time_seconds": avg_execution_time,
                "max_memory_usage_mb": max_memory,
                "last_error_message": metrics.last_error_message,
            }
        )
    return rows


def _build_performance_summary(plugin_health_rows: list[dict[str, Any]]) -> dict[str, Any]:
    ranked_by_memory = sorted(
        plugin_health_rows,
        key=lambda row: float(row.get("max_memory_usage_mb", 0.0)),
        reverse=True,
    )
    ranked_by_exec = sorted(
        plugin_health_rows,
        key=lambda row: float(row.get("average_execution_time_seconds", 0.0)),
        reverse=True,
    )
    ranked_by_error_rate = sorted(
        plugin_health_rows,
        key=lambda row: float(row.get("error_rate", 0.0)),
        reverse=True,
    )

    recommendations: list[str] = []
    if ranked_by_error_rate and float(ranked_by_error_rate[0].get("error_rate", 0.0)) > 0.3:
        recommendations.append(
            f"Investigate plugin '{ranked_by_error_rate[0].get('name')}' due to high error rate."
        )
    if ranked_by_exec and float(ranked_by_exec[0].get("average_execution_time_seconds", 0.0)) > 1.0:
        recommendations.append(
            f"Optimize execution path for plugin '{ranked_by_exec[0].get('name')}'."
        )
    if ranked_by_memory and float(ranked_by_memory[0].get("max_memory_usage_mb", 0.0)) > 256.0:
        recommendations.append(
            f"Consider reducing memory usage for plugin '{ranked_by_memory[0].get('name')}'."
        )

    return {
        "by_memory": ranked_by_memory[:10],
        "by_execution_time": ranked_by_exec[:10],
        "by_error_rate": ranked_by_error_rate[:10],
        "recommendations": recommendations,
    }


def _load_alerting_snapshot(request: Request) -> dict[str, Any]:
    runtime_config = getattr(request.app.state, "runtime_config", {})
    monitoring_cfg = runtime_config.get("monitoring", {}) if isinstance(runtime_config, dict) else {}
    alerting_cfg = monitoring_cfg.get("alerting", {}) if isinstance(monitoring_cfg, dict) else {}
    if not isinstance(alerting_cfg, dict):
        alerting_cfg = {}
    channels_cfg = alerting_cfg.get("channels", {}) if isinstance(alerting_cfg, dict) else {}
    if not isinstance(channels_cfg, dict):
        channels_cfg = {}
    return {
        "channels": {
            "email": bool((channels_cfg.get("email") or {}).get("enabled", False))
            if isinstance(channels_cfg.get("email"), dict)
            else False,
            "telegram": bool((channels_cfg.get("telegram") or {}).get("enabled", False))
            if isinstance(channels_cfg.get("telegram"), dict)
            else False,
            "webhook": bool((channels_cfg.get("webhook") or {}).get("enabled", False))
            if isinstance(channels_cfg.get("webhook"), dict)
            else False,
        },
        "escalation_policies": (
            alerting_cfg.get("escalation_policies", [])
            if isinstance(alerting_cfg.get("escalation_policies"), list)
            else []
        ),
    }


def _build_hot_reload_status_payload(request: Request) -> dict[str, Any]:
    manager = _get_hot_reload_manager(request)
    plugin_manager = _get_plugin_manager(request)
    monitor = _get_plugin_monitor(request)

    recent_logs = [_format_hot_reload_event(event) for event in manager.get_logs(limit=200)]
    plugin_health = _build_plugin_health_rows(plugin_manager, monitor)
    performance = _build_performance_summary(plugin_health)
    alerts_deque = getattr(request.app.state, "plugin_alert_events", deque(maxlen=1000))
    alerts = list(alerts_deque)[-100:]
    alerting = _load_alerting_snapshot(request)

    return {
        "enabled": bool(manager.config.enabled),
        "running": bool(manager.is_running),
        "watchdog_available": bool(WATCHDOG_AVAILABLE),
        "watch_directories": [str(path) for path in manager.config.watch_directories],
        "debounce_ms": int(manager.config.debounce_ms),
        "events_total": int(manager.events_total),
        "recent_logs": recent_logs,
        "plugin_health": plugin_health,
        "performance": performance,
        "alerts": alerts,
        "alerting": alerting,
    }


def _extract_ws_token(websocket: WebSocket) -> Optional[str]:
    token = websocket.query_params.get("token")
    if token:
        return token
    auth_header = websocket.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header.split(" ", 1)[1].strip()
    return None


def _build_ws_status_snapshot(app) -> dict[str, Any]:
    manager = getattr(app.state, "hot_reload_manager", None)
    alerts_deque = getattr(app.state, "plugin_alert_events", deque(maxlen=1000))
    if not isinstance(manager, HotReloadManager):
        return {
            "enabled": False,
            "running": False,
            "watchdog_available": bool(WATCHDOG_AVAILABLE),
            "events_total": 0,
            "alerts_total": len(alerts_deque),
        }
    return {
        "enabled": bool(manager.config.enabled),
        "running": bool(manager.is_running),
        "watchdog_available": bool(WATCHDOG_AVAILABLE),
        "events_total": int(manager.events_total),
        "alerts_total": len(alerts_deque),
    }


def _normalize_marketplace_summary(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "plugin_id": str(item.get("plugin_id") or item.get("name") or ""),
        "name": str(item.get("name") or item.get("plugin_id") or ""),
        "description": str(item.get("description") or ""),
        "category": str(item.get("category") or "general"),
        "author": str(item.get("author") or "unknown"),
        "latest_version": item.get("latest_version"),
        "download_url": item.get("download_url"),
        "avg_rating": float(item.get("avg_rating") or 0.0),
        "review_count": int(item.get("review_count") or 0),
    }


_DEPENDENCY_PATTERN = re.compile(r"^([A-Za-z][A-Za-z0-9_.-]*)(.*)$")
_SPECIFIER_PREFIXES = ("==", ">=", "<=", "!=", "~=", ">", "<")


def _split_dependency_entry(dependency: str) -> tuple[str, str]:
    text = dependency.strip()
    if not text:
        raise PluginManagerError("Dependency string must not be empty")
    match = _DEPENDENCY_PATTERN.match(text)
    if not match:
        raise PluginManagerError(f"Invalid dependency format: '{dependency}'")
    dependency_name = match.group(1)
    spec = (match.group(2) or "").strip()
    if spec:
        try:
            SpecifierSet(spec)
        except InvalidSpecifier as exc:
            raise PluginManagerError(
                f"Invalid dependency specifier '{spec}' in '{dependency}'"
            ) from exc
    return dependency_name, spec


def _normalize_update_spec(spec: str, *, pin_versions: bool) -> str:
    normalized = spec.strip()
    if not normalized:
        return ""
    if normalized.startswith("=") and not normalized.startswith("=="):
        normalized = f"=={normalized.lstrip('=')}"
    if pin_versions and not normalized.startswith(_SPECIFIER_PREFIXES):
        normalized = f"=={normalized}"
    elif not normalized.startswith(_SPECIFIER_PREFIXES) and normalized[:1].isdigit():
        normalized = f"=={normalized}"
    try:
        SpecifierSet(normalized)
    except InvalidSpecifier as exc:
        raise PluginManagerError(f"Invalid dependency version spec '{spec}'") from exc
    return normalized


def _dependency_map_to_list(mapping: dict[str, str]) -> list[str]:
    return [f"{dependency}{spec}" for dependency, spec in sorted(mapping.items())]


def _build_installed_plugin_index(manager: PluginManager) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for plugin in manager.list_plugins():
        name = str(plugin.get("name") or "").strip()
        if name:
            indexed[name] = plugin
    return indexed


def _read_plugin_manifest(manager: PluginManager, plugin_name: str) -> tuple[Path, dict[str, Any]]:
    plugin = manager.get_plugin(plugin_name)
    plugin_path = Path(str(plugin.get("path") or "")).expanduser().resolve()
    manifest_path = plugin_path / "manifest.json"
    if not manifest_path.exists():
        raise PluginManagerError(f"manifest.json not found for plugin '{plugin_name}'")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise PluginManagerError(f"Failed to read manifest for plugin '{plugin_name}': {exc}") from exc
    if not isinstance(manifest, dict):
        raise PluginManagerError(f"Invalid manifest format for plugin '{plugin_name}'")
    dependencies = manifest.get("dependencies")
    if dependencies is None:
        manifest["dependencies"] = []
    elif not isinstance(dependencies, list):
        raise PluginManagerError("Manifest dependencies must be a list")
    return manifest_path, manifest


def _write_plugin_manifest(manifest_path: Path, payload: dict[str, Any]) -> None:
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _dependency_map_from_lock(lock_content: str, *, pin_versions: bool) -> dict[str, str]:
    dependency_map: dict[str, str] = {}
    for raw_line in lock_content.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        cleaned = line.split("#", 1)[0].strip()
        if not cleaned:
            continue
        name, spec = _split_dependency_entry(cleaned)
        normalized_spec = _normalize_update_spec(spec, pin_versions=pin_versions) if spec else ""
        dependency_map[name] = normalized_spec
    return dependency_map


def _build_dependency_health(
    manager: PluginManager,
    dependencies: list[str],
) -> list[dict[str, Any]]:
    installed = _build_installed_plugin_index(manager)
    health_rows: list[dict[str, Any]] = []
    for dependency in dependencies:
        dependency_name, spec = _split_dependency_entry(dependency)
        installed_plugin = installed.get(dependency_name)
        installed_version: Optional[str] = None
        available = False
        compatible = False
        recommendation = "No action required"

        if installed_plugin is not None:
            installed_version = str(installed_plugin.get("version") or "")
            available = True
            if not spec:
                compatible = True
            else:
                try:
                    compatible = Version(installed_version) in SpecifierSet(spec)
                except (InvalidVersion, InvalidSpecifier):
                    compatible = False
        else:
            normalized_module = dependency_name.replace("-", "_")
            available = importlib.util.find_spec(normalized_module) is not None
            if available:
                try:
                    installed_version = importlib_metadata.version(dependency_name)
                except Exception:
                    installed_version = None
                if not spec:
                    compatible = True
                elif installed_version:
                    try:
                        compatible = Version(str(installed_version)) in SpecifierSet(spec)
                    except (InvalidVersion, InvalidSpecifier):
                        compatible = False
                else:
                    compatible = False
            else:
                compatible = False

        if not available:
            status = "missing"
            recommendation = f"Install '{dependency_name}' before enabling plugin."
        elif not compatible:
            status = "conflict"
            recommendation = (
                f"Align '{dependency_name}' to required spec '{spec}' "
                f"(currently '{installed_version or 'unknown'}')."
            )
        else:
            status = "ok"

        health_rows.append(
            {
                "dependency_name": dependency_name,
                "required_spec": spec,
                "installed_version": installed_version,
                "available": available,
                "compatible": compatible,
                "status": status,
                "recommendation": recommendation,
            }
        )
    return health_rows


def _collect_recommendations(
    conflicts: dict[str, list[str]],
    health_checks: list[dict[str, Any]],
) -> list[str]:
    recommendations: list[str] = []
    for dependency_name, specs in conflicts.items():
        filtered = [spec for spec in specs if spec and spec != "missing"]
        if filtered:
            recommendations.append(
                f"Resolve '{dependency_name}' with compatible spec: {', '.join(filtered)}"
            )
    for row in health_checks:
        status = str(row.get("status", ""))
        recommendation = str(row.get("recommendation", "")).strip()
        if status in {"missing", "conflict"} and recommendation:
            recommendations.append(recommendation)
    deduplicated = []
    seen: set[str] = set()
    for item in recommendations:
        if item in seen:
            continue
        seen.add(item)
        deduplicated.append(item)
    return deduplicated


def _build_lock_content(dependencies: list[str]) -> str:
    lines = sorted(dependencies)
    return ("\n".join(lines) + "\n") if lines else ""


def _write_lock_file(plugin_dir: Path, lock_content: str) -> Path:
    lock_path = (plugin_dir / "requirements.txt").resolve()
    lock_path.write_text(lock_content, encoding="utf-8")
    return lock_path


def _apply_dependency_update(
    manager: PluginManager,
    plugin_name: str,
    *,
    updates: dict[str, str],
    pin_versions: bool,
    dry_run: bool,
    export_lock: bool,
    import_lock_content: Optional[str] = None,
    allow_conflicts: bool = True,
) -> dict[str, Any]:
    manifest_path, manifest = _read_plugin_manifest(manager, plugin_name)
    plugin_dir = manifest_path.parent
    current_dependencies = manifest.get("dependencies", [])
    if not isinstance(current_dependencies, list):
        raise PluginManagerError("Manifest dependencies must be a list")

    current_map: dict[str, str] = {}
    for dependency in current_dependencies:
        dependency_name, spec = _split_dependency_entry(str(dependency))
        current_map[dependency_name] = spec

    applied_updates: dict[str, str] = {}
    if import_lock_content is not None and import_lock_content.strip():
        target_map = _dependency_map_from_lock(import_lock_content, pin_versions=pin_versions)
        applied_updates = {name: spec for name, spec in target_map.items()}
    else:
        if not updates:
            raise PluginManagerError("No dependency updates provided")
        target_map = dict(current_map)
        for dependency_name_raw, spec_raw in updates.items():
            dependency_name, _ = _split_dependency_entry(str(dependency_name_raw))
            normalized_spec = _normalize_update_spec(str(spec_raw), pin_versions=pin_versions)
            if not normalized_spec:
                target_map.pop(dependency_name, None)
                applied_updates[dependency_name] = ""
                continue
            _split_dependency_entry(f"{dependency_name}{normalized_spec}")
            target_map[dependency_name] = normalized_spec
            applied_updates[dependency_name] = normalized_spec

    updated_dependencies = _dependency_map_to_list(target_map)
    lock_content = _build_lock_content(updated_dependencies)
    lock_path = (plugin_dir / "requirements.txt").resolve()

    if not dry_run:
        manifest["dependencies"] = updated_dependencies
        _write_plugin_manifest(manifest_path, manifest)
        _write_lock_file(plugin_dir, lock_content)

    report = _build_dependency_report(
        manager,
        plugin_name,
        dependencies_override=updated_dependencies if dry_run else None,
    )
    conflicts = report.get("conflicts", {})
    missing_dependencies = report.get("missing_dependencies", [])
    health_checks = _build_dependency_health(manager, updated_dependencies)
    recommendations = _collect_recommendations(
        conflicts if isinstance(conflicts, dict) else {},
        health_checks,
    )

    if not allow_conflicts and isinstance(conflicts, dict) and conflicts:
        raise PluginManagerError(f"Dependency conflicts detected: {conflicts}")

    return {
        "plugin_name": plugin_name,
        "updated_dependencies": updated_dependencies,
        "applied_updates": applied_updates,
        "dry_run": dry_run,
        "conflicts": conflicts if isinstance(conflicts, dict) else {},
        "missing_dependencies": (
            missing_dependencies if isinstance(missing_dependencies, list) else []
        ),
        "health_checks": health_checks,
        "recommendations": recommendations,
        "lock_file_path": str(lock_path),
        "lock_content": lock_content if export_lock else None,
    }


def _build_dependency_report(
    manager: PluginManager,
    plugin_name: str,
    dependencies_override: Optional[list[str]] = None,
) -> dict[str, Any]:
    plugin_info = manager.get_plugin(plugin_name)
    if not plugin_info:
        raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")

    resolver = PluginDependencyResolver()
    direct_dependencies: list[str] = []

    installed_plugins = manager.list_plugins()
    for item in installed_plugins:
        plugin_path = str(item.get("path") or "").strip()
        if not plugin_path:
            continue
        path = Path(plugin_path).expanduser()
        if not path.exists():
            continue
        try:
            loaded = manager.local_loader.load(path)
        except Exception:
            continue
        dependencies = (
            list(dependencies_override)
            if dependencies_override is not None and loaded.name == plugin_name
            else loaded.manifest.dependencies
        )
        resolver.add_plugin(
            loaded.name,
            loaded.manifest.version,
            dependencies=dependencies,
        )
        if loaded.name == plugin_name:
            direct_dependencies = list(dependencies)

    graph = resolver.dependency_graph()
    if plugin_name not in graph:
        graph[plugin_name] = []

    conflicts = resolver.detect_conflicts()
    missing = sorted({dep for deps in graph.values() for dep in deps if dep not in graph})

    install_order: list[str] = []
    try:
        install_order = resolver.resolve([plugin_name])
    except DependencyResolutionError:
        # Keep report best-effort: graph/conflicts/missing are still useful for dashboard.
        install_order = [plugin_name]

    edges: list[dict[str, str]] = []
    for source, targets in graph.items():
        if not targets:
            edges.append({"source": source, "target": source})
            continue
        for target in targets:
            edges.append({"source": source, "target": target})

    return {
        "plugin_name": plugin_name,
        "dependencies": direct_dependencies,
        "install_order": install_order,
        "graph": graph,
        "edges": edges,
        "conflicts": conflicts,
        "missing_dependencies": missing,
    }


def _preflight_marketplace_conflicts(
    manager: PluginManager,
    marketplace_client: MarketplaceClient,
    plugin_id: str,
) -> dict[str, list[str]]:
    """
    Best-effort conflict check before install.
    Uses marketplace metadata if dependency list is available.
    """
    details = marketplace_client.get_plugin_details(plugin_id)
    dependencies_raw = details.get("dependencies", []) if isinstance(details, dict) else []
    dependencies = [str(item) for item in dependencies_raw if isinstance(item, str) and item.strip()]
    if not dependencies:
        return {}

    candidate_version = str(details.get("latest_version") or "0.0.0")
    resolver = PluginDependencyResolver()

    for item in manager.list_plugins():
        plugin_path = str(item.get("path") or "").strip()
        if not plugin_path:
            continue
        path = Path(plugin_path).expanduser()
        if not path.exists():
            continue
        try:
            loaded = manager.local_loader.load(path)
        except Exception:
            continue
        resolver.add_plugin(
            loaded.name,
            loaded.manifest.version,
            dependencies=loaded.manifest.dependencies,
        )

    resolver.add_plugin(plugin_id, candidate_version, dependencies=dependencies)
    conflicts = resolver.detect_conflicts()
    return {
        dependency: specs
        for dependency, specs in conflicts.items()
        if "missing" not in specs
    }


@router.get("", response_model=list[PluginInfoResponse])
async def list_plugins(
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> list[PluginInfoResponse]:
    """
    Возвращает список всех установленных плагинов.
    Доступно только admin-пользователю.
    """
    _ = current_admin
    manager = _get_plugin_manager(request)
    return [PluginInfoResponse.model_validate(item) for item in manager.list_plugins()]


@router.get("/marketplace/search", response_model=list[MarketplacePluginSummary])
async def marketplace_search(
    request: Request,
    q: str = Query(default="", description="Поисковый запрос"),
    category: Optional[str] = Query(default=None, description="Фильтр по категории"),
    limit: int = Query(default=20, ge=1, le=100, description="Лимит результатов"),
    current_admin: dict = Depends(get_current_admin),
) -> list[MarketplacePluginSummary]:
    """
    Поиск плагинов в marketplace.
    Использует встроенное кэширование клиента и fallback в offline mode.
    """
    _ = current_admin
    client = _get_marketplace_client(request)
    items = client.search_plugins(query=q, category=category, limit=limit)
    return [
        MarketplacePluginSummary.model_validate(_normalize_marketplace_summary(item))
        for item in items
        if isinstance(item, dict)
    ]


@router.get("/marketplace/categories", response_model=list[str])
async def marketplace_categories(
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> list[str]:
    """Возвращает список категорий marketplace."""
    _ = current_admin
    client = _get_marketplace_client(request)
    return client.get_categories()


@router.get("/marketplace/trending", response_model=list[MarketplacePluginSummary])
async def marketplace_trending(
    request: Request,
    limit: int = Query(default=10, ge=1, le=100),
    category: Optional[str] = Query(default=None),
    current_admin: dict = Depends(get_current_admin),
) -> list[MarketplacePluginSummary]:
    """Возвращает trending-плагины marketplace."""
    _ = current_admin
    client = _get_marketplace_client(request)
    items = client.get_trending_plugins(limit=limit, category=category)
    return [
        MarketplacePluginSummary.model_validate(_normalize_marketplace_summary(item))
        for item in items
        if isinstance(item, dict)
    ]


@router.get("/marketplace/{plugin_id}", response_model=MarketplacePluginDetailResponse)
async def marketplace_details(
    plugin_id: str,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> MarketplacePluginDetailResponse:
    """Возвращает детальную карточку плагина из marketplace."""
    _ = current_admin
    client = _get_marketplace_client(request)
    payload = client.get_plugin_details(plugin_id)
    if not payload:
        raise HTTPException(status_code=404, detail=f"Marketplace plugin '{plugin_id}' not found")

    normalized = _normalize_marketplace_summary(payload)
    normalized["metadata"] = payload.get("metadata", {}) if isinstance(payload.get("metadata"), dict) else {}
    normalized["versions"] = payload.get("versions", []) if isinstance(payload.get("versions"), list) else []
    normalized["reviews"] = payload.get("reviews", []) if isinstance(payload.get("reviews"), list) else []
    return MarketplacePluginDetailResponse.model_validate(normalized)


@router.post(
    "/marketplace/{plugin_id}/install",
    response_model=PluginInfoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def marketplace_install(
    plugin_id: str,
    request: Request,
    payload: Optional[MarketplaceInstallRequest] = None,
    current_admin: dict = Depends(get_current_admin),
) -> PluginInfoResponse:
    """
    Устанавливает плагин напрямую из marketplace по plugin_id.
    """
    _ = current_admin
    manager = _get_plugin_manager(request)
    marketplace_client = _get_marketplace_client(request)
    version = payload.version if payload is not None else None
    blocking_conflicts = _preflight_marketplace_conflicts(manager, marketplace_client, plugin_id)
    if blocking_conflicts:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Dependency conflicts detected before install",
                "conflicts": blocking_conflicts,
            },
        )
    try:
        installed = manager.install_plugin(
            plugin_id,
            version=version,
            marketplace_client=marketplace_client,
        )
        return PluginInfoResponse.model_validate(installed)
    except PluginManagerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/statistics", response_model=PluginStatisticsResponse)
async def plugin_statistics(
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> PluginStatisticsResponse:
    """
    Возвращает агрегированную статистику по установленным и marketplace-плагинам.
    """
    _ = current_admin
    manager = _get_plugin_manager(request)
    marketplace_client = _get_marketplace_client(request)
    analytics = _get_plugin_analytics(request)

    plugins = manager.list_plugins()
    enabled_count = sum(1 for plugin in plugins if bool(plugin.get("enabled")))
    error_count = sum(1 for plugin in plugins if str(plugin.get("status", "")).upper() == "ERROR")
    disabled_count = max(0, len(plugins) - enabled_count)

    trending_raw = marketplace_client.get_trending_plugins(limit=10)
    trending = [
        _normalize_marketplace_summary(item)
        for item in trending_raw
        if isinstance(item, dict)
    ]

    popularity = analytics.get_popularity(limit=10)
    if not popularity:
        popularity = [
            {
                "plugin_name": plugin.get("name", ""),
                "calls": 0,
                "success_rate": 0.0,
                "average_execution_time_seconds": 0.0,
                "category": "installed",
            }
            for plugin in plugins
        ]

    return PluginStatisticsResponse.model_validate({
        "summary": {
            "installed_total": len(plugins),
            "enabled_total": enabled_count,
            "disabled_total": disabled_count,
            "error_total": error_count,
            "marketplace_offline_mode": marketplace_client.offline_mode,
        },
        "popularity": popularity,
        "trending": trending,
    })


@router.get("/hot-reload/status", response_model=HotReloadStatusResponse)
async def hot_reload_status(
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> HotReloadStatusResponse:
    """
    Текущий статус hot-reload + мониторинг состояния плагинов.
    """
    _ = current_admin
    return HotReloadStatusResponse.model_validate(_build_hot_reload_status_payload(request))


@router.post("/hot-reload/enable", response_model=HotReloadToggleResponse)
async def hot_reload_enable(
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> HotReloadToggleResponse:
    """
    Включает hot-reload watcher для плагинов.
    """
    _ = current_admin
    manager = _get_hot_reload_manager(request)
    manager.config.enabled = True
    _sync_hot_reload_runtime(manager, _get_plugin_manager(request))
    started = manager.start()
    if started:
        message = "Hot-reload enabled"
    elif not WATCHDOG_AVAILABLE:
        message = "Watchdog is unavailable. Install watchdog to enable file watching."
    else:
        message = "Hot-reload enabled in config, but watcher could not be started."
    return HotReloadToggleResponse.model_validate({
        "enabled": bool(manager.config.enabled),
        "running": bool(manager.is_running),
        "watchdog_available": bool(WATCHDOG_AVAILABLE),
        "message": message,
    })


@router.post("/hot-reload/disable", response_model=HotReloadToggleResponse)
async def hot_reload_disable(
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> HotReloadToggleResponse:
    """
    Выключает hot-reload watcher для плагинов.
    """
    _ = current_admin
    manager = _get_hot_reload_manager(request)
    manager.config.enabled = False
    manager.stop()
    return HotReloadToggleResponse.model_validate({
        "enabled": bool(manager.config.enabled),
        "running": bool(manager.is_running),
        "watchdog_available": bool(WATCHDOG_AVAILABLE),
        "message": "Hot-reload disabled",
    })


@router.get("/hot-reload/logs", response_model=list[HotReloadLogEntry])
async def hot_reload_logs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    plugin_name: Optional[str] = Query(default=None),
    event_type: Optional[str] = Query(default=None),
    current_admin: dict = Depends(get_current_admin),
) -> list[HotReloadLogEntry]:
    """
    Логи hot-reload событий с фильтрацией.
    """
    _ = current_admin
    manager = _get_hot_reload_manager(request)
    rows = [_format_hot_reload_event(event) for event in manager.get_logs(limit=max(limit * 4, limit))]
    if plugin_name:
        rows = [row for row in rows if row.get("plugin_name") == plugin_name]
    if event_type:
        rows = [row for row in rows if row.get("event_type") == event_type]
    return [HotReloadLogEntry.model_validate(row) for row in rows[-limit:]]


@router.get("/{plugin_name}/reload-history", response_model=PluginReloadHistoryResponse)
async def plugin_reload_history(
    plugin_name: str,
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
    current_admin: dict = Depends(get_current_admin),
) -> PluginReloadHistoryResponse:
    """
    История событий reload по конкретному плагину.
    """
    _ = current_admin
    manager = _get_hot_reload_manager(request)
    plugin_manager = _get_plugin_manager(request)
    try:
        plugin_manager.get_plugin(plugin_name)
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    history = [_format_hot_reload_event(event) for event in manager.get_reload_history(plugin_name, limit=limit)]
    return PluginReloadHistoryResponse.model_validate(
        {"plugin_name": plugin_name, "history": history}
    )


@router.post("/{plugin_name}/reload-now", response_model=PluginReloadNowResponse)
async def plugin_reload_now(
    plugin_name: str,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> PluginReloadNowResponse:
    """
    Принудительно перезагружает плагин прямо сейчас.
    """
    _ = current_admin
    plugin_manager = _get_plugin_manager(request)
    monitor = _get_plugin_monitor(request)
    manager = _get_hot_reload_manager(request)
    try:
        plugin_manager.get_plugin(plugin_name)
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    _sync_hot_reload_runtime(manager, plugin_manager)
    reloaded = manager.reload_plugin(plugin_name)
    monitor.record_execution(
        plugin_name,
        execution_time_seconds=0.0,
        memory_usage_mb=0.0,
        failed=not reloaded,
        error_message="Manual reload failed" if not reloaded else None,
    )
    if not reloaded:
        _record_plugin_alert(
            request.app,
            message=f"Manual reload failed for plugin '{plugin_name}'",
            severity="critical",
            plugin_name=plugin_name,
        )
    _publish_plugin_event(
        request.app,
        "manual_reload",
        {"plugin_name": plugin_name, "reloaded": reloaded},
    )

    history = manager.get_reload_history(plugin_name, limit=1)
    event = _format_hot_reload_event(history[-1]) if history else None
    message = "Plugin reloaded successfully" if reloaded else "Plugin reload failed"
    return PluginReloadNowResponse.model_validate({
        "plugin_name": plugin_name,
        "reloaded": reloaded,
        "message": message,
        "event": event,
    })


@router.websocket("/ws/updates")
async def plugins_realtime_updates(websocket: WebSocket) -> None:
    """
    WebSocket stream for plugin hot-reload/monitoring events.
    Admin token is required in query param or Authorization header.
    """
    await websocket.accept()
    token = _extract_ws_token(websocket)
    payload = decode_access_token(token) if token else None
    if payload is None or payload.get("role") != "admin":
        await websocket.close(code=1008, reason="Admin token required")
        return

    bus = _get_plugin_event_bus(websocket.app)
    last_seq = 0
    since_raw = websocket.query_params.get("since")
    if since_raw:
        try:
            last_seq = max(0, int(since_raw))
        except (TypeError, ValueError):
            last_seq = 0

    await websocket.send_json(
        {
            "type": "connection_ack",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": {
                "role": payload.get("role"),
                "events_total": len(bus),
            },
        }
    )

    try:
        while True:
            pending = [event for event in list(bus) if int(event.get("seq", 0)) > last_seq]
            for event in pending:
                await websocket.send_json(event)
                last_seq = max(last_seq, int(event.get("seq", 0)))

            await websocket.send_json(
                {
                    "type": "status_snapshot",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "payload": _build_ws_status_snapshot(websocket.app),
                }
            )

            try:
                incoming = await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
                if incoming.strip().lower() in {"close", "stop"}:
                    await websocket.close(code=1000, reason="Client requested close")
                    return
            except asyncio.TimeoutError:
                continue
    except WebSocketDisconnect:
        return
    except Exception:
        try:
            await websocket.close(code=1011, reason="Internal plugin websocket error")
        except Exception:
            pass


@router.get("/{plugin_name}", response_model=PluginInfoResponse)
async def get_plugin(
    plugin_name: str,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> PluginInfoResponse:
    """
    Возвращает расширенную информацию о конкретном плагине.
    """
    _ = current_admin
    manager = _get_plugin_manager(request)
    try:
        return PluginInfoResponse.model_validate(manager.get_plugin(plugin_name))
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{plugin_name}/dependencies", response_model=PluginDependencyResponse)
async def plugin_dependencies(
    plugin_name: str,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> PluginDependencyResponse:
    """
    Возвращает dependency graph, install order и конфликты для плагина.
    """
    _ = current_admin
    manager = _get_plugin_manager(request)
    try:
        return PluginDependencyResponse.model_validate(_build_dependency_report(manager, plugin_name))
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PluginManagerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/{plugin_name}/dependencies/conflicts",
    response_model=PluginDependencyConflictsResponse,
)
async def plugin_dependency_conflicts(
    plugin_name: str,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> PluginDependencyConflictsResponse:
    """
    Возвращает только конфликтные зависимости + health-check и рекомендации.
    """
    _ = current_admin
    manager = _get_plugin_manager(request)
    try:
        manifest_path, manifest = _read_plugin_manifest(manager, plugin_name)
        dependencies_raw = manifest.get("dependencies", [])
        dependencies = [str(item) for item in dependencies_raw] if isinstance(dependencies_raw, list) else []
        report = _build_dependency_report(manager, plugin_name)
        health_checks = _build_dependency_health(manager, dependencies)
        conflicts = report.get("conflicts", {})
        recommendations = _collect_recommendations(
            conflicts if isinstance(conflicts, dict) else {},
            health_checks,
        )
        lock_content = _build_lock_content(dependencies)
        return PluginDependencyConflictsResponse.model_validate({
            "plugin_name": plugin_name,
            "conflicts": conflicts if isinstance(conflicts, dict) else {},
            "missing_dependencies": report.get("missing_dependencies", []),
            "health_checks": health_checks,
            "recommendations": recommendations,
            "lock_file_path": str((manifest_path.parent / "requirements.txt").resolve()),
            "lock_content": lock_content,
        })
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PluginManagerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{plugin_name}/dependencies/resolve",
    response_model=PluginDependencyUpdateResponse,
)
async def resolve_plugin_dependencies(
    plugin_name: str,
    payload: PluginDependencyResolveRequest,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> PluginDependencyUpdateResponse:
    """
    Автоматически разрешает конфликты зависимостей (стратегия prefer-installed).
    """
    _ = current_admin
    manager = _get_plugin_manager(request)
    strategy = (payload.strategy or "prefer-installed").strip().lower()
    if strategy not in {"prefer-installed", "prefer-required"}:
        raise HTTPException(status_code=400, detail="Unsupported resolve strategy")

    try:
        report = _build_dependency_report(manager, plugin_name)
        conflicts = report.get("conflicts", {})
        if not isinstance(conflicts, dict):
            conflicts = {}

        installed = _build_installed_plugin_index(manager)
        updates: dict[str, str] = {}
        for dependency_name, specs in conflicts.items():
            version_specs = [spec for spec in specs if spec and spec != "missing"]
            installed_version = str(installed.get(dependency_name, {}).get("version") or "").strip()
            if strategy == "prefer-installed" and installed_version:
                updates[dependency_name] = f"=={installed_version}"
                continue
            if version_specs:
                updates[dependency_name] = version_specs[0]
                continue
            if installed_version:
                updates[dependency_name] = f"=={installed_version}"

        if not updates:
            manifest_path, manifest = _read_plugin_manifest(manager, plugin_name)
            dependencies_raw = manifest.get("dependencies", [])
            dependencies = [str(item) for item in dependencies_raw] if isinstance(dependencies_raw, list) else []
            report = _build_dependency_report(manager, plugin_name)
            health_checks = _build_dependency_health(manager, dependencies)
            return PluginDependencyUpdateResponse.model_validate({
                "plugin_name": plugin_name,
                "updated_dependencies": dependencies,
                "applied_updates": {},
                "dry_run": True,
                "conflicts": report.get("conflicts", {}),
                "missing_dependencies": report.get("missing_dependencies", []),
                "health_checks": health_checks,
                "recommendations": _collect_recommendations(
                    report.get("conflicts", {}) if isinstance(report.get("conflicts"), dict) else {},
                    health_checks,
                ),
                "lock_file_path": str((manifest_path.parent / "requirements.txt").resolve()),
                "lock_content": _build_lock_content(dependencies) if payload.export_lock else None,
            })

        return PluginDependencyUpdateResponse.model_validate(_apply_dependency_update(
            manager,
            plugin_name,
            updates=updates,
            pin_versions=payload.pin_versions,
            dry_run=payload.dry_run,
            export_lock=payload.export_lock,
            allow_conflicts=True,
        ))
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PluginManagerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/{plugin_name}/dependencies/update",
    response_model=PluginDependencyUpdateResponse,
)
async def update_plugin_dependencies(
    plugin_name: str,
    payload: PluginDependencyUpdateRequest,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> PluginDependencyUpdateResponse:
    """
    Ручное обновление dependency spec + import/export lock файла.
    """
    _ = current_admin
    manager = _get_plugin_manager(request)
    try:
        return PluginDependencyUpdateResponse.model_validate(_apply_dependency_update(
            manager,
            plugin_name,
            updates=payload.updates,
            pin_versions=payload.pin_versions,
            dry_run=payload.dry_run,
            export_lock=payload.export_lock,
            import_lock_content=payload.import_lock_content,
            allow_conflicts=True,
        ))
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PluginManagerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/dependencies/bulk-update",
    response_model=BulkDependencyUpdateResponse,
)
async def bulk_update_plugin_dependencies(
    payload: BulkDependencyUpdateRequest,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> BulkDependencyUpdateResponse:
    """
    Массовое обновление зависимостей по нескольким плагинам.
    Поддерживает rollback при ошибке.
    """
    _ = current_admin
    manager = _get_plugin_manager(request)
    backups: dict[str, dict[str, Any]] = {}
    updated: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    rolled_back = False

    for operation in payload.operations:
        plugin_name = operation.plugin_name
        try:
            manifest_path, _ = _read_plugin_manifest(manager, plugin_name)
            plugin_dir = manifest_path.parent
            lock_path = (plugin_dir / "requirements.txt").resolve()
            if not payload.dry_run and plugin_name not in backups:
                backups[plugin_name] = {
                    "manifest_path": str(manifest_path),
                    "manifest_text": manifest_path.read_text(encoding="utf-8"),
                    "lock_path": str(lock_path),
                    "lock_exists": lock_path.exists(),
                    "lock_text": lock_path.read_text(encoding="utf-8") if lock_path.exists() else "",
                }

            result = _apply_dependency_update(
                manager,
                plugin_name,
                updates=operation.updates,
                pin_versions=operation.pin_versions,
                dry_run=payload.dry_run,
                export_lock=payload.export_lock,
                import_lock_content=operation.import_lock_content,
                allow_conflicts=payload.allow_conflicts,
            )
            updated.append(result)
        except Exception as exc:
            errors.append({"plugin_name": plugin_name, "error": str(exc)})
            if payload.rollback_on_error and not payload.dry_run:
                rolled_back = True
                for backup in backups.values():
                    manifest_path = Path(str(backup["manifest_path"]))
                    manifest_path.write_text(str(backup["manifest_text"]), encoding="utf-8")
                    lock_path = Path(str(backup["lock_path"]))
                    if bool(backup["lock_exists"]):
                        lock_path.write_text(str(backup["lock_text"]), encoding="utf-8")
                    else:
                        lock_path.unlink(missing_ok=True)
            break

    return BulkDependencyUpdateResponse.model_validate({
        "updated": updated,
        "errors": errors,
        "rolled_back": rolled_back,
    })


@router.post(
    "/install",
    response_model=PluginInfoResponse,
    status_code=status.HTTP_201_CREATED,
)
async def install_plugin(
    payload: PluginInstallRequest,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> PluginInfoResponse:
    """
    Устанавливает плагин из локального пути, URL или marketplace ID.
    """
    _ = current_admin
    manager = _get_plugin_manager(request)
    try:
        installed = manager.install_plugin(
            payload.source,
            version=payload.version,
            marketplace_client=_get_marketplace_client(request),
        )
        return PluginInfoResponse.model_validate(installed)
    except PluginManagerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{plugin_name}/enable", response_model=PluginInfoResponse)
async def enable_plugin(
    plugin_name: str,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> PluginInfoResponse:
    """
    Включает установленный плагин.
    """
    _ = current_admin
    manager = _get_plugin_manager(request)
    try:
        return PluginInfoResponse.model_validate(
            manager.set_plugin_enabled(plugin_name, enabled=True)
        )
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PluginManagerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{plugin_name}/disable", response_model=PluginInfoResponse)
async def disable_plugin(
    plugin_name: str,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> PluginInfoResponse:
    """
    Отключает установленный плагин.
    """
    _ = current_admin
    manager = _get_plugin_manager(request)
    try:
        return PluginInfoResponse.model_validate(
            manager.set_plugin_enabled(plugin_name, enabled=False)
        )
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PluginManagerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{plugin_name}", response_model=PluginDeleteResponse)
async def uninstall_plugin(
    plugin_name: str,
    request: Request,
    force: bool = False,
    current_admin: dict = Depends(get_current_admin),
) -> PluginDeleteResponse:
    """
    Удаляет установленный плагин.
    """
    _ = current_admin
    manager = _get_plugin_manager(request)
    try:
        manager.uninstall_plugin(plugin_name, force=force)
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PluginManagerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return PluginDeleteResponse(plugin_name=plugin_name)


@router.get("/{plugin_name}/config", response_model=PluginConfigResponse)
async def get_plugin_config(
    plugin_name: str,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> PluginConfigResponse:
    """
    Возвращает текущую конфигурацию плагина.
    """
    _ = current_admin
    manager = _get_plugin_manager(request)
    try:
        return PluginConfigResponse.model_validate(manager.get_plugin_config(plugin_name))
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PluginManagerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/{plugin_name}/config", response_model=PluginConfigResponse)
async def update_plugin_config(
    plugin_name: str,
    payload: PluginConfigUpdateRequest,
    request: Request,
    current_admin: dict = Depends(get_current_admin),
) -> PluginConfigResponse:
    """
    Обновляет конфигурацию плагина (settings/secrets/ui_schema).
    """
    _ = current_admin
    manager = _get_plugin_manager(request)
    try:
        return PluginConfigResponse.model_validate(manager.update_plugin_config(
            plugin_name,
            settings=payload.settings,
            secrets=payload.secrets,
            ui_schema=payload.ui_schema,
        ))
    except PluginNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PluginManagerError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
