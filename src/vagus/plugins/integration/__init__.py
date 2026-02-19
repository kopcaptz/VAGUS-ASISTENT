"""Integration helpers for wiring plugins into app surfaces."""

from .dashboard_integration import (
    DashboardPluginIntegration,
    PluginDashboardPage,
    PluginDashboardWidget,
    get_dashboard_plugin_integration,
)
from .cli_integration import (
    CLIPluginIntegration,
    PluginCLICommand,
    PluginCLISubcommand,
    get_cli_plugin_integration,
)
from .telegram_integration import (
    TelegramPluginIntegration,
    PluginInlineButton,
    get_telegram_plugin_integration,
)

__all__ = [
    "DashboardPluginIntegration",
    "PluginDashboardPage",
    "PluginDashboardWidget",
    "get_dashboard_plugin_integration",
    "CLIPluginIntegration",
    "PluginCLICommand",
    "PluginCLISubcommand",
    "get_cli_plugin_integration",
    "TelegramPluginIntegration",
    "PluginInlineButton",
    "get_telegram_plugin_integration",
]
