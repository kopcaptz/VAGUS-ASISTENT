"""Plugins management dashboard page."""

from __future__ import annotations

from typing import Any

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False

from dashboard.utils.plugins import (
    build_dependency_edges,
    filter_marketplace_plugins,
    format_plugin_logs,
    summarize_installed_plugins,
)
from vagus.plugins.analytics import PluginAnalytics
from vagus.plugins.dependencies import PluginDependencyResolver
from vagus.plugins.marketplace import MarketplaceClient
from vagus.plugins.registry import PluginRegistry


def _collect_installed_plugins(registry: PluginRegistry) -> list[dict[str, Any]]:
    plugins = registry.list_plugins()
    return [
        {
            "name": plugin.name,
            "version": plugin.manifest.version,
            "enabled": plugin.state.state.value == "ENABLED",
            "state": plugin.state.state.value,
            "author": plugin.manifest.author,
            "description": plugin.manifest.description,
        }
        for plugin in plugins
    ]


if STREAMLIT_AVAILABLE:
    st.title("Plugins")
    st.caption("Управление установленными плагинами и интеграция с marketplace")

    registry = PluginRegistry()
    marketplace_client = MarketplaceClient()
    analytics = PluginAnalytics()

    installed_plugins = _collect_installed_plugins(registry)
    summary = summarize_installed_plugins(installed_plugins)

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Всего", summary["total"])
    col2.metric("Включено", summary["enabled"])
    col3.metric("Отключено", summary["disabled"])
    col4.metric("Ошибки", summary["with_errors"])

    st.markdown("---")
    st.subheader("Установленные плагины")
    if installed_plugins:
        st.dataframe(installed_plugins, use_container_width=True, hide_index=True)
    else:
        st.info("Установленные плагины не найдены.")

    st.markdown("---")
    st.subheader("Marketplace")
    query = st.text_input("Поиск плагинов", value="")
    category = st.text_input("Категория (опционально)", value="")
    limit = st.slider("Лимит", min_value=5, max_value=50, value=20)

    marketplace_results = marketplace_client.search_plugins(
        query=query,
        category=category or None,
        limit=int(limit),
    )
    filtered_results = filter_marketplace_plugins(
        marketplace_results,
        query=query,
        category=category or None,
    )
    if filtered_results:
        st.dataframe(filtered_results, use_container_width=True, hide_index=True)
    else:
        st.info("Плагины не найдены.")

    st.markdown("---")
    st.subheader("Граф зависимостей")
    resolver = PluginDependencyResolver()
    for plugin in registry.list_plugins():
        resolver.add_plugin(
            plugin.name,
            plugin.manifest.version,
            dependencies=plugin.manifest.dependencies,
        )
    graph_edges = build_dependency_edges(resolver.dependency_graph())
    if graph_edges:
        st.dataframe(graph_edges, use_container_width=True, hide_index=True)
    else:
        st.info("Граф зависимостей пуст.")

    st.markdown("---")
    st.subheader("Аналитика")
    dashboard_payload = analytics.get_dashboard_data()
    st.json(dashboard_payload)

    st.markdown("---")
    st.subheader("Логи плагинов")
    sample_logs = [
        {"timestamp": "-", "plugin": "system", "level": "INFO", "message": "Plugin dashboard opened"}
    ]
    st.code("\n".join(format_plugin_logs(sample_logs)))
