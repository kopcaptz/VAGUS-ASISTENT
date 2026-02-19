"""Tests for dashboard plugin integration and config UI helpers."""

from __future__ import annotations

from dashboard.utils.plugins import (
    build_ui_form_fields,
    render_live_preview,
    validate_plugin_settings,
)
from vagus.plugins.integration import DashboardPluginIntegration


def test_build_ui_form_fields_from_schema():
    schema = {
        "properties": {
            "enabled": {"type": "boolean", "title": "Enabled"},
            "threshold": {"type": "number", "minimum": 0, "maximum": 10},
            "mode": {"type": "string", "enum": ["fast", "safe"]},
        },
        "required": ["enabled"],
    }
    settings = {"enabled": True, "threshold": 4}
    fields = build_ui_form_fields(schema, settings)
    assert len(fields) == 3
    assert any(field["name"] == "enabled" and field["required"] for field in fields)


def test_validate_plugin_settings_success():
    schema = {
        "properties": {
            "enabled": {"type": "boolean"},
            "threshold": {"type": "number", "minimum": 0, "maximum": 10},
            "mode": {"type": "string", "enum": ["fast", "safe"]},
        },
        "required": ["enabled", "mode"],
    }
    settings = {"enabled": True, "threshold": 5, "mode": "fast"}
    assert validate_plugin_settings(settings, schema) == []


def test_validate_plugin_settings_reports_errors():
    schema = {
        "properties": {
            "enabled": {"type": "boolean"},
            "threshold": {"type": "number", "minimum": 0, "maximum": 10},
        },
        "required": ["enabled"],
    }
    settings = {"enabled": "yes", "threshold": 999}
    errors = validate_plugin_settings(settings, schema)
    assert any("enabled" in err for err in errors)
    assert any("threshold" in err for err in errors)


def test_render_live_preview_returns_json():
    preview = render_live_preview({"mode": "fast", "enabled": True})
    assert '"mode": "fast"' in preview
    assert '"enabled": true' in preview.lower()


def test_dashboard_integration_registers_pages_and_widgets():
    integration = DashboardPluginIntegration()
    integration.register_page(
        plugin_name="demo",
        route="demo/analytics",
        title="Demo Analytics",
        render=lambda **_: {"ok": True},
    )
    integration.register_widget(
        plugin_name="demo",
        target_page="performance",
        name="Demo Widget",
        render=lambda **_: {"value": 1},
    )
    pages = integration.list_pages()
    widgets = integration.list_widgets(target_page="performance")
    assert pages[0].route == "demo/analytics"
    assert widgets[0].name == "Demo Widget"


def test_dashboard_integration_discovers_extension_points():
    integration = DashboardPluginIntegration()

    class PluginRuntime:
        def get_dashboard_pages(self):
            return [
                {
                    "route": "plugin/page",
                    "title": "Plugin Page",
                    "render": lambda **_: {"ok": True},
                }
            ]

        def get_dashboard_widgets(self):
            return [
                {
                    "target_page": "performance",
                    "name": "Plugin Widget",
                    "render": lambda **_: {"metric": 123},
                }
            ]

    integration.discover_from_plugin("plugin_demo", PluginRuntime())
    assert integration.list_pages()
    assert integration.list_widgets(target_page="performance")
