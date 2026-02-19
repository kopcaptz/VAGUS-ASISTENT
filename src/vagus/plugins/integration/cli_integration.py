"""CLI integration registry for plugin-provided commands."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class PluginCLICommand:
    plugin_name: str
    command_name: str
    callback: Callable[..., Any]
    help_text: str = ""


@dataclass
class PluginCLISubcommand:
    namespace: str
    command_name: str
    callback: Callable[..., Any]
    help_text: str = ""


class CLIPluginIntegration:
    """Registry and binder for dynamic plugin CLI commands."""

    def __init__(self) -> None:
        self._plugin_commands: dict[str, list[PluginCLICommand]] = {}
        self._namespace_commands: dict[str, list[PluginCLISubcommand]] = {}
        self._attached_plugin_groups: set[str] = set()
        self._attached_namespace_commands: set[tuple[str, str]] = set()

    def register_plugin_command(
        self,
        *,
        plugin_name: str,
        command_name: str,
        callback: Callable[..., Any],
        help_text: str = "",
    ) -> None:
        commands = self._plugin_commands.setdefault(plugin_name, [])
        commands.append(
            PluginCLICommand(
                plugin_name=plugin_name,
                command_name=command_name,
                callback=callback,
                help_text=help_text,
            )
        )

    def register_namespace_subcommand(
        self,
        *,
        namespace: str,
        command_name: str,
        callback: Callable[..., Any],
        help_text: str = "",
    ) -> None:
        commands = self._namespace_commands.setdefault(namespace, [])
        commands.append(
            PluginCLISubcommand(
                namespace=namespace,
                command_name=command_name,
                callback=callback,
                help_text=help_text,
            )
        )

    def attach_to_plugin_typer(self, plugin_root_typer: Any) -> None:
        """Attach registered plugin command groups to `vagus plugin` typer."""
        try:
            import typer
        except ImportError:  # pragma: no cover
            return

        for plugin_name, commands in self._plugin_commands.items():
            if plugin_name in self._attached_plugin_groups:
                continue
            sub_app = typer.Typer(help=f"Команды плагина {plugin_name}")
            for command in commands:
                sub_app.command(name=command.command_name, help=command.help_text)(command.callback)
            plugin_root_typer.add_typer(sub_app, name=plugin_name, help=f"Команды плагина {plugin_name}")
            self._attached_plugin_groups.add(plugin_name)

    def attach_namespace_subcommands(self, namespaced_typers: dict[str, Any]) -> None:
        """Attach plugin-provided subcommands to existing CLI namespaces."""
        for namespace, commands in self._namespace_commands.items():
            namespace_typer = namespaced_typers.get(namespace)
            if namespace_typer is None:
                continue
            for command in commands:
                key = (namespace, command.command_name)
                if key in self._attached_namespace_commands:
                    continue
                namespace_typer.command(name=command.command_name, help=command.help_text)(command.callback)
                self._attached_namespace_commands.add(key)

    def discover_from_plugin(self, plugin_name: str, plugin_runtime: Any) -> None:
        target = self._resolve_runtime_target(plugin_runtime)

        commands_provider = getattr(target, "get_cli_commands", None)
        if callable(commands_provider):
            try:
                commands = commands_provider()
            except Exception:
                commands = []
            if isinstance(commands, list):
                for item in commands:
                    if not isinstance(item, dict):
                        continue
                    callback = item.get("callback")
                    name = str(item.get("name", "")).strip()
                    help_text = str(item.get("help", "")).strip()
                    if name and callable(callback):
                        self.register_plugin_command(
                            plugin_name=plugin_name,
                            command_name=name,
                            callback=callback,
                            help_text=help_text,
                        )

        namespace_provider = getattr(target, "get_cli_subcommands", None)
        if callable(namespace_provider):
            try:
                subcommands = namespace_provider()
            except Exception:
                subcommands = []
            if isinstance(subcommands, list):
                for item in subcommands:
                    if not isinstance(item, dict):
                        continue
                    callback = item.get("callback")
                    namespace = str(item.get("namespace", "")).strip()
                    name = str(item.get("name", "")).strip()
                    help_text = str(item.get("help", "")).strip()
                    if namespace and name and callable(callback):
                        self.register_namespace_subcommand(
                            namespace=namespace,
                            command_name=name,
                            callback=callback,
                            help_text=help_text,
                        )

    def discover_from_registry(self, plugin_registry: Any) -> None:
        if plugin_registry is None or not hasattr(plugin_registry, "list_plugins"):
            return
        for loaded_plugin in plugin_registry.list_plugins():
            runtime = loaded_plugin.entry_point
            self.discover_from_plugin(loaded_plugin.name, runtime)

    def clear(self) -> None:
        self._plugin_commands.clear()
        self._namespace_commands.clear()
        self._attached_plugin_groups.clear()
        self._attached_namespace_commands.clear()

    @staticmethod
    def _resolve_runtime_target(plugin_runtime: Any) -> Any:
        if inspect.isclass(plugin_runtime):
            try:
                return plugin_runtime()
            except Exception:
                return plugin_runtime
        return plugin_runtime


_cli_integration_singleton: Optional[CLIPluginIntegration] = None


def get_cli_plugin_integration() -> CLIPluginIntegration:
    global _cli_integration_singleton
    if _cli_integration_singleton is None:
        _cli_integration_singleton = CLIPluginIntegration()
    return _cli_integration_singleton
