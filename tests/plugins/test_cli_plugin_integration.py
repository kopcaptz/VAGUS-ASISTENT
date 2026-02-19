"""Tests for dynamic CLI integration from plugins."""

from __future__ import annotations

from typer.testing import CliRunner

from vagus.layer3.cli.app import create_app
from vagus.plugins.core.models import LoadedPlugin, PluginManifest
from vagus.plugins.integration import CLIPluginIntegration
from vagus.plugins.registry import PluginRegistry


def test_cli_integration_register_and_attach_plugin_commands():
    import typer

    integration = CLIPluginIntegration()
    root = typer.Typer()

    plugin_group = typer.Typer()
    root.add_typer(plugin_group, name="plugin")

    def ping():
        print("pong-from-plugin")

    integration.register_plugin_command(
        plugin_name="demo",
        command_name="ping",
        callback=ping,
        help_text="Ping command",
    )
    integration.attach_to_plugin_typer(plugin_group)

    runner = CliRunner()
    result = runner.invoke(root, ["plugin", "demo", "ping"])
    assert result.exit_code == 0
    assert "pong-from-plugin" in result.output


def test_cli_integration_attach_namespace_subcommands():
    import typer

    integration = CLIPluginIntegration()
    root = typer.Typer()
    task_app = typer.Typer()
    root.add_typer(task_app, name="task")

    def extra():
        print("extra-subcommand")

    integration.register_namespace_subcommand(
        namespace="task",
        command_name="extra",
        callback=extra,
        help_text="Extra command",
    )
    integration.attach_namespace_subcommands({"task": task_app})

    runner = CliRunner()
    result = runner.invoke(root, ["task", "extra"])
    assert result.exit_code == 0
    assert "extra-subcommand" in result.output


def test_cli_integration_discover_from_plugin_runtime():
    integration = CLIPluginIntegration()

    class PluginRuntime:
        def get_cli_commands(self):
            return [{"name": "hello", "callback": lambda: print("hello-cli"), "help": "hello"}]

    integration.discover_from_plugin("demo", PluginRuntime())
    assert "demo" in integration._plugin_commands  # pylint: disable=protected-access
    assert integration._plugin_commands["demo"][0].command_name == "hello"  # pylint: disable=protected-access


def test_create_app_exposes_dynamic_plugin_command_from_registry():
    registry = PluginRegistry()
    registry.clear()

    class PluginRuntime:
        def get_cli_commands(self):
            def ping():
                print("dynamic-ping")

            return [{"name": "ping", "callback": ping, "help": "dynamic ping"}]

    loaded = LoadedPlugin(
        manifest=PluginManifest(
            name="dynamic_cli_plugin",
            version="1.0.0",
            author="tests",
            description="dynamic cli plugin",
            dependencies=[],
            python_version=">=3.10",
            vagus_version=">=0.1.0",
            entry_point="plugin:PluginRuntime",
            hooks=[],
            permissions=[],
        ),
        entry_point=PluginRuntime,
    )
    registry.register(loaded)

    app = create_app()
    runner = CliRunner()
    result = runner.invoke(app, ["plugin", "dynamic_cli_plugin", "ping"])
    assert result.exit_code == 0
    assert "dynamic-ping" in result.output

    registry.clear()
