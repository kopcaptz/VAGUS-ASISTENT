"""Template generator for new plugins."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Literal

TemplateName = Literal["basic", "webhook", "llm", "ui"]


class PluginTemplateError(RuntimeError):
    """Raised when plugin template generation fails."""


class PluginTemplateGenerator:
    """Creates plugin skeletons for common use-cases."""

    VALID_NAME_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_-]*$")

    def __init__(self, destination_root: str | Path = ".") -> None:
        self.destination_root = Path(destination_root).expanduser().resolve()

    def create(self, name: str, template: TemplateName = "basic") -> Path:
        plugin_name = self._validate_name(name)
        template_name = self._validate_template(template)
        plugin_dir = self.destination_root / plugin_name
        if plugin_dir.exists():
            raise PluginTemplateError(f"Plugin directory already exists: {plugin_dir}")
        plugin_dir.mkdir(parents=True, exist_ok=False)

        manifest = self._build_manifest(plugin_name, template_name)
        (plugin_dir / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=True, indent=2),
            encoding="utf-8",
        )
        (plugin_dir / "plugin.py").write_text(
            self._build_plugin_code(plugin_name, template_name),
            encoding="utf-8",
        )
        (plugin_dir / "README.md").write_text(
            self._build_readme(plugin_name, template_name),
            encoding="utf-8",
        )

        extra_files = self._build_extra_files(template_name)
        for file_name, content in extra_files.items():
            (plugin_dir / file_name).write_text(content, encoding="utf-8")

        return plugin_dir

    def _build_manifest(self, plugin_name: str, template: TemplateName) -> dict:
        hook_name = {
            "basic": "on_message_received",
            "webhook": "on_message_received",
            "llm": "post_task_execution",
            "ui": "on_config_changed",
        }[template]
        callback_name = {
            "basic": "Plugin.on_message_received",
            "webhook": "Plugin.on_message_received",
            "llm": "Plugin.post_task_execution",
            "ui": "Plugin.on_config_changed",
        }[template]

        return {
            "name": plugin_name,
            "version": "1.0.0",
            "author": "Plugin Author",
            "description": f"{template} template for Vagus plugin",
            "dependencies": [],
            "python_version": ">=3.10",
            "vagus_version": ">=0.1.0",
            "entry_point": "plugin:Plugin",
            "hooks": [
                {
                    "name": hook_name,
                    "priority": 50,
                    "callback": callback_name,
                    "is_async": False,
                }
            ],
            "permissions": [],
            "runtime_permissions": {
                "level": "READ",
                "filesystem": {"read": ["./data"], "write": []},
                "network": [],
                "environment_variables": [],
                "max_memory_mb": 256,
                "max_execution_time_seconds": 30,
            },
        }

    def _build_plugin_code(self, plugin_name: str, template: TemplateName) -> str:
        if template == "basic":
            return (
                '"""Basic plugin template."""\n\n\n'
                "class Plugin:\n"
                "    \"\"\"Minimal plugin entry point.\"\"\"\n\n"
                "    def on_message_received(self, message: dict) -> dict:\n"
                "        updated = dict(message)\n"
                f'        updated[\"plugin\"] = \"{plugin_name}\"\n'
                "        return updated\n"
            )
        if template == "webhook":
            return (
                '"""Webhook plugin template."""\n\n\n'
                "class Plugin:\n"
                "    def on_message_received(self, message: dict) -> dict:\n"
                "        payload = dict(message)\n"
                "        payload.setdefault(\"webhooks\", []).append(\"example-webhook\")\n"
                "        return payload\n"
            )
        if template == "llm":
            return (
                '"""LLM integration plugin template."""\n\n\n'
                "class Plugin:\n"
                "    def post_task_execution(self, task: dict, result: dict) -> dict:\n"
                "        enriched = dict(result)\n"
                "        enriched.setdefault(\"llm_annotations\", []).append(\"generated\")\n"
                "        return enriched\n"
            )
        return (
            '"""UI plugin template."""\n\n\n'
            "class Plugin:\n"
            "    def on_config_changed(self, config: dict) -> dict:\n"
            "        updated = dict(config)\n"
            "        updated.setdefault(\"ui\", {})[\"plugin_enabled\"] = True\n"
            "        return updated\n"
        )

    def _build_readme(self, plugin_name: str, template: TemplateName) -> str:
        return (
            f"# {plugin_name}\n\n"
            f"Generated from `{template}` plugin template.\n\n"
            "## Files\n\n"
            "- `manifest.json` — plugin metadata\n"
            "- `plugin.py` — plugin implementation\n"
        )

    def _build_extra_files(self, template: TemplateName) -> dict[str, str]:
        if template == "webhook":
            return {
                "webhook_config.json": json.dumps(
                    {"endpoint": "https://example.com/webhook", "secret": "change-me"},
                    ensure_ascii=True,
                    indent=2,
                )
            }
        if template == "llm":
            return {
                "llm_config.json": json.dumps(
                    {"provider": "openai", "model": "gpt-4o-mini"},
                    ensure_ascii=True,
                    indent=2,
                )
            }
        if template == "ui":
            return {"ui_schema.json": json.dumps({"type": "object", "properties": {}}, indent=2)}
        return {}

    def _validate_name(self, name: str) -> str:
        candidate = (name or "").strip()
        if not self.VALID_NAME_PATTERN.match(candidate):
            raise PluginTemplateError(
                "Plugin name must start with a letter and contain only letters, digits, '_' and '-'"
            )
        return candidate

    def _validate_template(self, template: str) -> TemplateName:
        allowed: set[str] = {"basic", "webhook", "llm", "ui"}
        if template not in allowed:
            raise PluginTemplateError(f"Unknown template '{template}'. Allowed: {sorted(allowed)}")
        return template  # type: ignore[return-value]


def create_plugin_template(
    name: str,
    *,
    template: TemplateName = "basic",
    destination_root: str | Path = ".",
) -> Path:
    """Convenience function for generating plugin template."""
    generator = PluginTemplateGenerator(destination_root=destination_root)
    return generator.create(name=name, template=template)
