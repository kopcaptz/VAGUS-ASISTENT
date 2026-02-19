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
    build_ui_form_fields,
    filter_marketplace_plugins,
    format_plugin_logs,
    render_live_preview,
    summarize_installed_plugins,
    validate_plugin_settings,
)
from vagus.plugins.analytics import PluginAnalytics
from vagus.plugins.dependencies import PluginDependencyResolver
from vagus.plugins.integration import get_dashboard_plugin_integration
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
            "ui_schema": plugin.config.ui_schema,
            "settings": plugin.config.settings,
        }
        for plugin in plugins
    ]


if STREAMLIT_AVAILABLE:
    st.title("Plugins")
    st.caption("Управление установленными плагинами и интеграция с marketplace")

    registry = PluginRegistry()
    marketplace_client = MarketplaceClient()
    analytics = PluginAnalytics()
    dashboard_integration = get_dashboard_plugin_integration()
    dashboard_integration.clear()
    for loaded_plugin in registry.list_plugins():
        runtime = loaded_plugin.entry_point
        if isinstance(runtime, type):
            try:
                runtime = runtime()
            except Exception:
                pass
        dashboard_integration.discover_from_plugin(loaded_plugin.name, runtime)

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
    st.subheader("Plugin routes and widgets")
    pages = dashboard_integration.list_pages()
    widgets = dashboard_integration.list_widgets()
    if pages:
        st.markdown("**Dynamic routes:**")
        st.dataframe(
            [
                {"route": page.route, "title": page.title, "plugin": page.plugin_name}
                for page in pages
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Динамические plugin routes не зарегистрированы.")
    if widgets:
        st.markdown("**Widgets:**")
        st.dataframe(
            [
                {
                    "target_page": widget.target_page,
                    "name": widget.name,
                    "plugin": widget.plugin_name,
                }
                for widget in widgets
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Plugin widgets не зарегистрированы.")

    st.markdown("---")
    st.subheader("Конфигурация плагинов")
    loaded_plugins = {plugin.name: plugin for plugin in registry.list_plugins()}
    if loaded_plugins:
        for plugin_name, plugin in loaded_plugins.items():
            with st.expander(f"Настройки: {plugin_name}"):
                ui_schema = plugin.config.ui_schema or {}
                settings = dict(plugin.config.settings)
                fields = build_ui_form_fields(ui_schema, settings)
                if not fields:
                    st.info("ui_schema не задан — настройка недоступна.")
                    continue

                draft_settings = dict(settings)
                for field in fields:
                    key_prefix = f"{plugin_name}_{field['name']}"
                    field_type = field["type"]
                    if field_type == "boolean":
                        draft_settings[field["name"]] = st.checkbox(
                            field["title"],
                            value=bool(field["value"]),
                            help=field["description"],
                            key=f"{key_prefix}_bool",
                        )
                    elif field_type == "number":
                        default_value = field["value"] if isinstance(field["value"], (int, float)) else 0.0
                        min_value = field["minimum"] if isinstance(field["minimum"], (int, float)) else None
                        max_value = field["maximum"] if isinstance(field["maximum"], (int, float)) else None
                        draft_settings[field["name"]] = st.number_input(
                            field["title"],
                            value=float(default_value),
                            min_value=min_value,
                            max_value=max_value,
                            help=field["description"],
                            key=f"{key_prefix}_number",
                        )
                    elif field_type == "array":
                        default_array = field["value"] if isinstance(field["value"], list) else []
                        raw = st.text_area(
                            field["title"],
                            value="\n".join(str(item) for item in default_array),
                            help=field["description"],
                            key=f"{key_prefix}_array",
                        )
                        draft_settings[field["name"]] = [
                            line.strip()
                            for line in raw.splitlines()
                            if line.strip()
                        ]
                    elif field.get("enum"):
                        enum_values = [str(item) for item in field["enum"]]
                        current_value = str(field["value"]) if field["value"] in enum_values else enum_values[0]
                        draft_settings[field["name"]] = st.selectbox(
                            field["title"],
                            options=enum_values,
                            index=enum_values.index(current_value),
                            help=field["description"],
                            key=f"{key_prefix}_enum",
                        )
                    else:
                        draft_settings[field["name"]] = st.text_input(
                            field["title"],
                            value=str(field["value"] if field["value"] is not None else ""),
                            help=field["description"],
                            key=f"{key_prefix}_text",
                        )

                validation_errors = validate_plugin_settings(draft_settings, ui_schema)
                if validation_errors:
                    st.error("Ошибки валидации: " + "; ".join(validation_errors))
                else:
                    st.success("Конфигурация валидна")

                st.markdown("**Live preview**")
                st.code(render_live_preview(draft_settings), language="json")

                if st.button(f"Применить {plugin_name}", key=f"{plugin_name}_apply_config"):
                    if validation_errors:
                        st.error("Сначала исправьте ошибки валидации.")
                    else:
                        plugin.config.settings = draft_settings
                        st.success("Конфигурация обновлена.")
    else:
        st.info("Нет загруженных плагинов для конфигурации.")

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
