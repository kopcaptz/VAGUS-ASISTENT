"""Dashboard integration registry for plugin-provided pages and widgets."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass
class PluginDashboardPage:
    plugin_name: str
    route: str
    title: str
    render: Callable[..., Any]


@dataclass
class PluginDashboardWidget:
    plugin_name: str
    target_page: str
    name: str
    render: Callable[..., Any]


class DashboardPluginIntegration:
    """Registry of plugin dashboard pages and widgets."""

    def __init__(self) -> None:
        self._pages: dict[str, PluginDashboardPage] = {}
        self._widgets: list[PluginDashboardWidget] = []

    def register_page(
        self,
        *,
        plugin_name: str,
        route: str,
        title: str,
        render: Callable[..., Any],
    ) -> None:
        key = route.strip().lower()
        self._pages[key] = PluginDashboardPage(
            plugin_name=plugin_name,
            route=route,
            title=title,
            render=render,
        )

    def register_widget(
        self,
        *,
        plugin_name: str,
        target_page: str,
        name: str,
        render: Callable[..., Any],
    ) -> None:
        self._widgets.append(
            PluginDashboardWidget(
                plugin_name=plugin_name,
                target_page=target_page,
                name=name,
                render=render,
            )
        )

    def list_pages(self) -> list[PluginDashboardPage]:
        return sorted(self._pages.values(), key=lambda item: item.route)

    def list_widgets(self, *, target_page: Optional[str] = None) -> list[PluginDashboardWidget]:
        if target_page is None:
            return list(self._widgets)
        desired = target_page.strip().lower()
        return [widget for widget in self._widgets if widget.target_page.strip().lower() == desired]

    def discover_from_plugin(self, plugin_name: str, plugin_runtime: Any) -> None:
        """Discover dashboard page/widget extension points from plugin runtime object."""
        target = self._resolve_runtime_target(plugin_runtime)

        pages_provider = getattr(target, "get_dashboard_pages", None)
        if callable(pages_provider):
            try:
                pages = pages_provider()
            except Exception:
                pages = []
            if isinstance(pages, list):
                for item in pages:
                    if not isinstance(item, dict):
                        continue
                    render = item.get("render")
                    if not callable(render):
                        continue
                    route = str(item.get("route", "")).strip()
                    title = str(item.get("title", route)).strip()
                    if route:
                        self.register_page(
                            plugin_name=plugin_name,
                            route=route,
                            title=title,
                            render=render,
                        )

        widgets_provider = getattr(target, "get_dashboard_widgets", None)
        if callable(widgets_provider):
            try:
                widgets = widgets_provider()
            except Exception:
                widgets = []
            if isinstance(widgets, list):
                for item in widgets:
                    if not isinstance(item, dict):
                        continue
                    render = item.get("render")
                    if not callable(render):
                        continue
                    target_page = str(item.get("target_page", "")).strip()
                    name = str(item.get("name", "widget")).strip()
                    if target_page:
                        self.register_widget(
                            plugin_name=plugin_name,
                            target_page=target_page,
                            name=name,
                            render=render,
                        )

    def clear(self) -> None:
        self._pages.clear()
        self._widgets.clear()

    @staticmethod
    def _resolve_runtime_target(plugin_runtime: Any) -> Any:
        if inspect.isclass(plugin_runtime):
            try:
                return plugin_runtime()
            except Exception:
                return plugin_runtime
        return plugin_runtime


_dashboard_integration_singleton: Optional[DashboardPluginIntegration] = None


def get_dashboard_plugin_integration() -> DashboardPluginIntegration:
    global _dashboard_integration_singleton
    if _dashboard_integration_singleton is None:
        _dashboard_integration_singleton = DashboardPluginIntegration()
    return _dashboard_integration_singleton
