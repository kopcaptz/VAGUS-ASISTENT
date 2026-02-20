"""Plugins management dashboard page."""

from __future__ import annotations

import json
from typing import Any

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False

from dashboard.utils.plugins import format_plugin_logs, summarize_installed_plugins

if STREAMLIT_AVAILABLE:
    import streamlit.components.v1 as components

    from dashboard.utils.api_client import VagusAPIClient
    from dashboard.utils.auth import get_token, require_login


def _safe_json_dumps(payload: Any) -> str:
    return json.dumps(payload if isinstance(payload, dict) else {}, ensure_ascii=False, indent=2)


def _dependency_graph_to_dot(edges: list[dict[str, str]]) -> str:
    lines = ["digraph plugin_dependencies {"]
    for edge in edges:
        source = str(edge.get("source", ""))
        target = str(edge.get("target", ""))
        if not source:
            continue
        if not target or target == source:
            lines.append(f'  "{source}";')
            continue
        lines.append(f'  "{source}" -> "{target}";')
    lines.append("}")
    return "\n".join(lines)


def _dependency_graph_html(
    plugin_name: str,
    edges: list[dict[str, str]],
    conflicts: dict[str, list[str]],
    health_checks: list[dict[str, Any]],
) -> str:
    nodes: dict[str, dict[str, Any]] = {}
    conflict_nodes = set(conflicts.keys())
    health_by_name = {
        str(item.get("dependency_name", "")): item for item in health_checks if isinstance(item, dict)
    }

    def ensure_node(node_id: str) -> None:
        if node_id in nodes:
            return
        if node_id == plugin_name:
            color = "#4F81BD"
            title = f"{node_id} (plugin)"
        elif node_id in conflict_nodes:
            color = "#E74C3C"
            title = f"{node_id} (conflict)"
        else:
            status = str(health_by_name.get(node_id, {}).get("status", "ok"))
            if status == "missing":
                color = "#F39C12"
            elif status == "conflict":
                color = "#E74C3C"
            else:
                color = "#2ECC71"
            title = f"{node_id} ({status})"
        nodes[node_id] = {"id": node_id, "label": node_id, "title": title, "color": color}

    edge_rows: list[dict[str, str]] = []
    for edge in edges:
        source = str(edge.get("source", "")).strip()
        target = str(edge.get("target", "")).strip()
        if not source:
            continue
        ensure_node(source)
        if target and target != source:
            ensure_node(target)
            edge_rows.append({"from": source, "to": target, "arrows": "to"})
        else:
            ensure_node(source)

    for dependency_name in conflict_nodes:
        ensure_node(dependency_name)

    node_payload = json.dumps(list(nodes.values()), ensure_ascii=False)
    edge_payload = json.dumps(edge_rows, ensure_ascii=False)
    return f"""
<div style="display:grid;grid-template-columns:3fr 1fr;gap:12px;">
  <div id="dep-network" style="height:420px;border:1px solid #ddd;border-radius:6px;"></div>
  <div id="dep-info" style="height:420px;overflow:auto;border:1px solid #ddd;border-radius:6px;padding:8px;font-family:Arial,sans-serif;font-size:13px;">
    <b>Dependency graph</b><br/>
    Click node to inspect details.
  </div>
</div>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<script>
const nodes = new vis.DataSet({node_payload});
const edges = new vis.DataSet({edge_payload});
const container = document.getElementById("dep-network");
const info = document.getElementById("dep-info");
const network = new vis.Network(container, {{nodes, edges}}, {{
  physics: {{stabilization: false}},
  interaction: {{hover: true, dragNodes: true, zoomView: true}},
  nodes: {{shape: "dot", size: 18, font: {{color: "#222"}}}},
  edges: {{smooth: true}}
}});
network.on("click", function(params) {{
  if (!params.nodes || params.nodes.length === 0) return;
  const nodeId = params.nodes[0];
  const node = nodes.get(nodeId);
  info.innerHTML = `<b>${{node.label}}</b><br/><br/>${{node.title || ""}}`;
}});
</script>
"""


def _hot_reload_live_updates_html(ws_base_url: str, token: str) -> str:
    ws_url = f"{ws_base_url.rstrip('/')}/api/v1/plugins/ws/updates?token={token}"
    ws_url_payload = json.dumps(ws_url)
    return f"""
<div style="border:1px solid #ddd;border-radius:6px;padding:8px;font-family:Arial,sans-serif;">
  <b>Live plugin events (WebSocket)</b>
  <div id="ws-status" style="margin-top:6px;color:#666;">Connecting...</div>
  <div id="ws-events" style="margin-top:8px;max-height:280px;overflow:auto;background:#fafafa;padding:8px;border-radius:4px;"></div>
</div>
<script>
const wsUrl = {ws_url_payload};
const statusEl = document.getElementById("ws-status");
const eventsEl = document.getElementById("ws-events");
let socket = null;

function appendEvent(entry) {{
  const row = document.createElement("div");
  row.style.padding = "4px 0";
  row.style.borderBottom = "1px solid #eee";
  const ts = entry.timestamp || new Date().toISOString();
  const kind = entry.type || "event";
  row.textContent = `[${{ts}}] ${{kind}}: ${{JSON.stringify(entry.payload || {{}})}}`;
  eventsEl.prepend(row);
  while (eventsEl.children.length > 120) {{
    eventsEl.removeChild(eventsEl.lastChild);
  }}
}}

function maybeNotify(entry) {{
  const payload = entry.payload || {{}};
  const eventType = payload.event_type || entry.type || "";
  if (!["plugin_reload_failed", "plugin_alert", "manual_reload"].includes(eventType)) return;
  if (!("Notification" in window)) return;
  if (Notification.permission === "granted") {{
    const title = "Vagus Plugin Event";
    const body = `${{eventType}}: ${{JSON.stringify(payload)}}`;
    new Notification(title, {{ body }});
  }}
}}

function connect() {{
  socket = new WebSocket(wsUrl);
  socket.onopen = () => {{
    statusEl.textContent = "Connected";
    statusEl.style.color = "#2ecc71";
    if ("Notification" in window && Notification.permission === "default") {{
      Notification.requestPermission().catch(() => {{}});
    }}
  }};
  socket.onmessage = (event) => {{
    try {{
      const payload = JSON.parse(event.data);
      appendEvent(payload);
      maybeNotify(payload);
    }} catch (e) {{
      appendEvent({{ type: "raw_message", payload: {{ data: event.data }} }});
    }}
  }};
  socket.onclose = () => {{
    statusEl.textContent = "Disconnected. Reconnecting...";
    statusEl.style.color = "#e67e22";
    setTimeout(connect, 1500);
  }};
  socket.onerror = () => {{
    statusEl.textContent = "Socket error";
    statusEl.style.color = "#e74c3c";
  }};
}}

connect();
</script>
"""


if STREAMLIT_AVAILABLE:
    require_login()
    st.title("Plugins")
    st.caption("Управление плагинами и marketplace через API")

    token_value = get_token()
    client = VagusAPIClient(token=token_value)

    try:
        installed_plugins = client.get_plugins()
    except Exception as exc:
        st.error(f"Не удалось получить список плагинов: {exc}")
        st.stop()

    tabs = st.tabs(["Installed", "Marketplace", "Trending", "Hot Reload"])

    with tabs[0]:
        summary = summarize_installed_plugins(installed_plugins)
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Всего", summary["total"])
        col2.metric("Включено", summary["enabled"])
        col3.metric("Отключено", summary["disabled"])
        col4.metric("Ошибки", summary["with_errors"])

        try:
            stats_payload = client.get_plugin_statistics()
        except Exception as exc:
            stats_payload = {}
            st.warning(f"Не удалось загрузить статистику плагинов: {exc}")

        stats_summary = stats_payload.get("summary", {}) if isinstance(stats_payload, dict) else {}
        if isinstance(stats_summary, dict) and stats_summary:
            stat_col1, stat_col2, stat_col3 = st.columns(3)
            stat_col1.metric("Installed total", int(stats_summary.get("installed_total", 0)))
            stat_col2.metric("Enabled total", int(stats_summary.get("enabled_total", 0)))
            stat_col3.metric(
                "Marketplace offline",
                "yes" if bool(stats_summary.get("marketplace_offline_mode", False)) else "no",
            )

        st.markdown("---")
        st.subheader("Установить плагин (source)")
        with st.form("plugin_install_form"):
            source = st.text_input(
                "Путь / URL / Marketplace ID",
                value="",
                help="Например: ./test-plugin или user/repo или marketplace-id",
            )
            version = st.text_input("Версия (опционально)", value="")
            install_submit = st.form_submit_button("Установить")
        if install_submit:
            if not source.strip():
                st.error("Укажите источник плагина.")
            else:
                try:
                    client.install_plugin(source.strip(), version=version.strip() or None)
                    st.success("Плагин установлен.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Ошибка установки плагина: {exc}")

        st.markdown("---")
        st.subheader("Установленные плагины")
        if not installed_plugins:
            st.info("Установленные плагины не найдены.")
        else:
            st.dataframe(installed_plugins, use_container_width=True, hide_index=True)
            st.caption("Выберите плагин ниже для управления состоянием и конфигурацией.")

            plugin_names = [str(plugin.get("name", "")) for plugin in installed_plugins if plugin.get("name")]

            st.markdown("---")
            st.subheader("Bulk dependency management")
            bulk_targets = st.multiselect(
                "Плагины для массового обновления зависимостей",
                options=plugin_names,
                key="bulk_dep_targets",
            )
            bulk_updates_text = st.text_area(
                "Dependency updates JSON (применяется ко всем выбранным плагинам)",
                value='{"example-dep": "==1.2.3"}',
                key="bulk_dependency_updates_json",
            )
            bulk_col1, bulk_col2, bulk_col3 = st.columns(3)
            bulk_pin_versions = bulk_col1.checkbox(
                "Pin versions",
                value=True,
                key="bulk_dependency_pin_versions",
            )
            bulk_dry_run = bulk_col2.checkbox(
                "Dry run",
                value=False,
                key="bulk_dependency_dry_run",
            )
            bulk_allow_conflicts = bulk_col3.checkbox(
                "Allow conflicts",
                value=False,
                key="bulk_dependency_allow_conflicts",
            )
            bulk_rollback = st.checkbox(
                "Rollback on error",
                value=True,
                key="bulk_dependency_rollback",
            )
            if st.button("Запустить bulk dependency update", key="run_bulk_dependency_update"):
                if not bulk_targets:
                    st.error("Выберите хотя бы один плагин для bulk update.")
                else:
                    try:
                        updates_payload = json.loads(bulk_updates_text or "{}")
                        if not isinstance(updates_payload, dict):
                            raise ValueError("updates JSON должен быть объектом")
                    except Exception as exc:
                        st.error(f"Некорректный updates JSON: {exc}")
                        updates_payload = None

                    if updates_payload is not None:
                        operations = [
                            {
                                "plugin_name": plugin_name,
                                "updates": updates_payload,
                                "pin_versions": bulk_pin_versions,
                            }
                            for plugin_name in bulk_targets
                        ]
                        try:
                            bulk_result = client.bulk_update_plugin_dependencies(
                                operations=operations,
                                dry_run=bulk_dry_run,
                                rollback_on_error=bulk_rollback,
                                allow_conflicts=bulk_allow_conflicts,
                                export_lock=True,
                            )
                            st.json(bulk_result)
                            if bulk_result.get("errors"):
                                st.error("Bulk update завершился с ошибками.")
                            else:
                                st.success("Bulk dependency update завершен.")
                                if not bulk_dry_run:
                                    st.rerun()
                        except Exception as exc:
                            st.error(f"Bulk update failed: {exc}")

            for plugin in installed_plugins:
                plugin_name = str(plugin.get("name", "unknown"))
                status_label = str(plugin.get("status", "UNKNOWN"))
                with st.expander(f"{plugin_name} ({status_label})", expanded=False):
                    st.write(str(plugin.get("description", "")))
                    st.caption(
                        f"Автор: {plugin.get('author', 'unknown')} | Версия: {plugin.get('version', '-')}"
                    )

                    controls_col1, controls_col2 = st.columns(2)
                    if bool(plugin.get("enabled", False)):
                        if controls_col1.button("Disable", key=f"disable_{plugin_name}"):
                            try:
                                client.disable_plugin(plugin_name)
                                st.success(f"Плагин {plugin_name} отключен.")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Не удалось отключить плагин: {exc}")
                    else:
                        if controls_col1.button("Enable", key=f"enable_{plugin_name}"):
                            try:
                                client.enable_plugin(plugin_name)
                                st.success(f"Плагин {plugin_name} включен.")
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Не удалось включить плагин: {exc}")

                    if controls_col2.button("Uninstall", key=f"uninstall_{plugin_name}"):
                        try:
                            client.uninstall_plugin(plugin_name)
                            st.success(f"Плагин {plugin_name} удален.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Не удалось удалить плагин: {exc}")

                    plugin_tabs = st.tabs(["Configuration", "Dependencies"])

                    with plugin_tabs[0]:
                        try:
                            config_payload = client.get_plugin_config(plugin_name)
                        except Exception as exc:
                            st.warning(f"Не удалось загрузить конфигурацию: {exc}")
                            config_payload = {"settings": {}, "secrets": {}, "ui_schema": {}}

                        with st.form(f"config_form_{plugin_name}"):
                            settings_text = st.text_area(
                                "settings (JSON)",
                                value=_safe_json_dumps(config_payload.get("settings", {})),
                                key=f"settings_{plugin_name}",
                            )
                            secrets_text = st.text_area(
                                "secrets (JSON)",
                                value=_safe_json_dumps(config_payload.get("secrets", {})),
                                key=f"secrets_{plugin_name}",
                            )
                            schema_text = st.text_area(
                                "ui_schema (JSON)",
                                value=_safe_json_dumps(config_payload.get("ui_schema", {})),
                                key=f"schema_{plugin_name}",
                            )
                            config_submit = st.form_submit_button("Сохранить конфигурацию")
                            if config_submit:
                                settings_payload = None
                                secrets_payload = None
                                schema_payload = None
                                try:
                                    settings_payload = json.loads(settings_text or "{}")
                                    secrets_payload = json.loads(secrets_text or "{}")
                                    schema_payload = json.loads(schema_text or "{}")
                                except json.JSONDecodeError as exc:
                                    st.error(f"Некорректный JSON в конфигурации: {exc}")
                                if (
                                    settings_payload is not None
                                    and secrets_payload is not None
                                    and schema_payload is not None
                                ):
                                    try:
                                        client.update_plugin_config(
                                            plugin_name,
                                            settings=settings_payload,
                                            secrets=secrets_payload,
                                            ui_schema=schema_payload,
                                        )
                                        st.success("Конфигурация обновлена.")
                                        st.rerun()
                                    except Exception as exc:
                                        st.error(f"Не удалось сохранить конфигурацию: {exc}")

                    with plugin_tabs[1]:
                        dependency_payload: dict[str, Any] = {}
                        conflicts_payload: dict[str, Any] = {}
                        try:
                            dependency_payload = client.get_plugin_dependencies(plugin_name)
                            conflicts_payload = client.get_plugin_dependency_conflicts(plugin_name)
                        except Exception as exc:
                            st.error(f"Не удалось получить dependency данные: {exc}")

                        dependencies = (
                            dependency_payload.get("dependencies", [])
                            if isinstance(dependency_payload, dict)
                            else []
                        )
                        conflicts = (
                            conflicts_payload.get("conflicts", {})
                            if isinstance(conflicts_payload, dict)
                            else {}
                        )
                        missing = (
                            conflicts_payload.get("missing_dependencies", [])
                            if isinstance(conflicts_payload, dict)
                            else []
                        )
                        health_checks = (
                            conflicts_payload.get("health_checks", [])
                            if isinstance(conflicts_payload, dict)
                            else []
                        )
                        edges = (
                            dependency_payload.get("edges", [])
                            if isinstance(dependency_payload, dict)
                            else []
                        )

                        dep_col1, dep_col2, dep_col3 = st.columns(3)
                        dep_col1.metric("Dependencies", len(dependencies) if isinstance(dependencies, list) else 0)
                        dep_col2.metric("Conflicts", len(conflicts) if isinstance(conflicts, dict) else 0)
                        dep_col3.metric("Missing", len(missing) if isinstance(missing, list) else 0)

                        if isinstance(edges, list) and edges:
                            components.html(
                                _dependency_graph_html(
                                    plugin_name=plugin_name,
                                    edges=edges,
                                    conflicts=conflicts if isinstance(conflicts, dict) else {},
                                    health_checks=health_checks if isinstance(health_checks, list) else [],
                                ),
                                height=460,
                                scrolling=False,
                            )
                            with st.expander("DOT fallback view", expanded=False):
                                st.graphviz_chart(_dependency_graph_to_dot(edges))
                        else:
                            st.info("Dependency graph пуст или недоступен.")

                        if isinstance(conflicts, dict) and conflicts:
                            st.warning("Обнаружены конфликты зависимостей")
                            st.json(conflicts_payload)
                        elif conflicts_payload:
                            st.success("Конфликты зависимостей не обнаружены")

                        resolve_col1, resolve_col2 = st.columns(2)
                        if resolve_col1.button(
                            "Auto-resolve conflicts",
                            key=f"resolve_deps_{plugin_name}",
                        ):
                            try:
                                resolve_result = client.resolve_plugin_dependencies(
                                    plugin_name,
                                    strategy="prefer-installed",
                                    dry_run=False,
                                    pin_versions=True,
                                    export_lock=True,
                                )
                                st.success("Авто-разрешение завершено.")
                                st.json(resolve_result)
                                st.rerun()
                            except Exception as exc:
                                st.error(f"Auto-resolve failed: {exc}")
                        if resolve_col2.button(
                            "Dry-run resolve",
                            key=f"resolve_deps_dry_{plugin_name}",
                        ):
                            try:
                                resolve_result = client.resolve_plugin_dependencies(
                                    plugin_name,
                                    strategy="prefer-installed",
                                    dry_run=True,
                                    pin_versions=True,
                                    export_lock=True,
                                )
                                st.json(resolve_result)
                            except Exception as exc:
                                st.error(f"Dry-run resolve failed: {exc}")

                        with st.form(f"manual_dep_update_form_{plugin_name}"):
                            updates_text = st.text_area(
                                "Manual dependency updates JSON",
                                value='{"example-dependency": ">=1.2.0"}',
                                key=f"manual_updates_{plugin_name}",
                            )
                            manual_pin_versions = st.checkbox(
                                "Pin versions",
                                value=False,
                                key=f"manual_pin_versions_{plugin_name}",
                            )
                            manual_dry_run = st.checkbox(
                                "Dry run",
                                value=False,
                                key=f"manual_dry_run_{plugin_name}",
                            )
                            manual_submit = st.form_submit_button("Apply manual dependency update")
                            if manual_submit:
                                updates_payload = None
                                try:
                                    updates_payload = json.loads(updates_text or "{}")
                                    if not isinstance(updates_payload, dict):
                                        raise ValueError("updates JSON должен быть объектом")
                                except Exception as exc:
                                    st.error(f"Некорректный JSON для updates: {exc}")

                                if updates_payload is not None:
                                    try:
                                        result = client.update_plugin_dependencies(
                                            plugin_name,
                                            updates=updates_payload,
                                            pin_versions=manual_pin_versions,
                                            dry_run=manual_dry_run,
                                            export_lock=True,
                                        )
                                        st.success("Dependency update выполнен.")
                                        st.json(result)
                                        if not manual_dry_run:
                                            st.rerun()
                                    except Exception as exc:
                                        st.error(f"Dependency update failed: {exc}")

                        lock_content = (
                            str(conflicts_payload.get("lock_content", ""))
                            if isinstance(conflicts_payload, dict)
                            else ""
                        )
                        st.download_button(
                            "Export requirements.txt",
                            data=lock_content,
                            file_name=f"{plugin_name}-requirements.txt",
                            mime="text/plain",
                            key=f"export_lock_{plugin_name}",
                        )
                        import_lock_text = st.text_area(
                            "Import dependency lock content",
                            value=lock_content,
                            key=f"import_lock_text_{plugin_name}",
                        )
                        if st.button("Import lock", key=f"import_lock_btn_{plugin_name}"):
                            if not import_lock_text.strip():
                                st.error("Lock content пустой.")
                            else:
                                try:
                                    import_result = client.update_plugin_dependencies(
                                        plugin_name,
                                        updates={},
                                        pin_versions=True,
                                        dry_run=False,
                                        export_lock=True,
                                        import_lock_content=import_lock_text,
                                    )
                                    st.success("Lock импортирован.")
                                    st.json(import_result)
                                    st.rerun()
                                except Exception as exc:
                                    st.error(f"Не удалось импортировать lock: {exc}")

    with tabs[1]:
        st.subheader("Marketplace")
        try:
            categories = client.marketplace_categories()
        except Exception as exc:
            categories = []
            st.warning(f"Не удалось получить категории marketplace: {exc}")

        with st.form("marketplace_search_form"):
            q = st.text_input("Поиск", value="")
            category_options = ["all"] + categories
            selected_category = st.selectbox("Категория", options=category_options)
            limit = st.slider("Лимит", min_value=1, max_value=50, value=20)
            search_submit = st.form_submit_button("Искать")

        if search_submit or "marketplace_results" not in st.session_state:
            try:
                st.session_state["marketplace_results"] = client.marketplace_search_plugins(
                    query=q.strip(),
                    category=None if selected_category == "all" else selected_category,
                    limit=limit,
                )
            except Exception as exc:
                st.session_state["marketplace_results"] = []
                st.error(f"Ошибка поиска marketplace: {exc}")

        results = st.session_state.get("marketplace_results", [])
        if not results:
            st.info("По вашему запросу плагины не найдены.")
        else:
            st.dataframe(results, use_container_width=True, hide_index=True)
            for item in results:
                plugin_id = str(item.get("plugin_id") or item.get("name") or "")
                if not plugin_id:
                    continue
                title = str(item.get("name") or plugin_id)
                rating = float(item.get("avg_rating") or 0.0)
                reviews = int(item.get("review_count") or 0)
                with st.expander(f"{title} — rating {rating:.1f} ({reviews} reviews)", expanded=False):
                    st.write(str(item.get("description", "")))
                    st.caption(
                        f"ID: {plugin_id} | Категория: {item.get('category', '-')}"
                        f" | Автор: {item.get('author', '-')}"
                    )
                    details_col, install_col = st.columns(2)
                    if details_col.button("Детали", key=f"marketplace_details_btn_{plugin_id}"):
                        st.session_state["marketplace_details_plugin"] = plugin_id
                    if install_col.button("Установить", key=f"marketplace_install_btn_{plugin_id}"):
                        try:
                            client.marketplace_install_plugin(plugin_id)
                            st.success(f"Плагин {plugin_id} установлен.")
                            st.rerun()
                        except Exception as exc:
                            st.error(f"Не удалось установить {plugin_id}: {exc}")

                    if st.session_state.get("marketplace_details_plugin") == plugin_id:
                        try:
                            details = client.marketplace_plugin_details(plugin_id)
                            st.json(details)
                        except Exception as exc:
                            st.error(f"Не удалось загрузить детали плагина: {exc}")

    with tabs[2]:
        st.subheader("Trending")
        try:
            trending_plugins = client.marketplace_trending_plugins(limit=20)
        except Exception as exc:
            trending_plugins = []
            st.warning(f"Не удалось получить trending plugins: {exc}")

        if not trending_plugins:
            st.info("Trending-плагины недоступны.")
        else:
            st.dataframe(trending_plugins, use_container_width=True, hide_index=True)
            chart_rows = [
                {
                    "plugin": str(item.get("name") or item.get("plugin_id") or ""),
                    "rating": float(item.get("avg_rating") or 0.0),
                    "reviews": int(item.get("review_count") or 0),
                }
                for item in trending_plugins
            ]
            st.bar_chart(chart_rows, x="plugin", y=["rating", "reviews"])

            for item in trending_plugins:
                plugin_id = str(item.get("plugin_id") or item.get("name") or "")
                if not plugin_id:
                    continue
                button_label = f"Установить {plugin_id}"
                if st.button(button_label, key=f"trending_install_{plugin_id}"):
                    try:
                        client.marketplace_install_plugin(plugin_id)
                        st.success(f"Плагин {plugin_id} установлен.")
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Не удалось установить {plugin_id}: {exc}")

    with tabs[3]:
        st.subheader("Hot Reload & Monitoring")

        status_payload: dict[str, Any] = {}
        try:
            status_payload = client.get_hot_reload_status()
        except Exception as exc:
            st.error(f"Не удалось получить hot-reload status: {exc}")

        action_col1, action_col2, action_col3 = st.columns(3)
        if action_col1.button("Refresh", key="hot_reload_refresh"):
            st.rerun()
        if action_col2.button("Enable hot-reload", key="hot_reload_enable_btn"):
            try:
                result = client.enable_hot_reload()
                st.success(result.get("message", "Hot-reload enabled"))
                st.rerun()
            except Exception as exc:
                st.error(f"Не удалось включить hot-reload: {exc}")
        if action_col3.button("Disable hot-reload", key="hot_reload_disable_btn"):
            try:
                result = client.disable_hot_reload()
                st.warning(result.get("message", "Hot-reload disabled"))
                st.rerun()
            except Exception as exc:
                st.error(f"Не удалось выключить hot-reload: {exc}")

        if status_payload:
            status_col1, status_col2, status_col3, status_col4 = st.columns(4)
            status_col1.metric("Enabled", "yes" if status_payload.get("enabled") else "no")
            status_col2.metric("Running", "yes" if status_payload.get("running") else "no")
            status_col3.metric("Events", int(status_payload.get("events_total", 0)))
            status_col4.metric(
                "Watchdog",
                "available" if status_payload.get("watchdog_available") else "missing",
            )

            st.caption(
                f"Watch dirs: {', '.join(status_payload.get('watch_directories', []))}"
                f" | debounce_ms: {status_payload.get('debounce_ms', 500)}"
            )

            plugin_health = (
                status_payload.get("plugin_health", [])
                if isinstance(status_payload.get("plugin_health"), list)
                else []
            )
            if plugin_health:
                st.markdown("#### Plugin health dashboard")
                st.dataframe(plugin_health, use_container_width=True, hide_index=True)
                st.bar_chart(
                    plugin_health,
                    x="name",
                    y=["max_memory_usage_mb", "average_execution_time_seconds", "error_rate"],
                )
            else:
                st.info("Health metrics пока недоступны.")

            performance_payload = (
                status_payload.get("performance", {})
                if isinstance(status_payload.get("performance"), dict)
                else {}
            )
            recommendations = (
                performance_payload.get("recommendations", [])
                if isinstance(performance_payload.get("recommendations"), list)
                else []
            )
            if recommendations:
                st.markdown("#### Performance recommendations")
                for recommendation in recommendations:
                    st.write(f"- {recommendation}")

            alerts_payload = (
                status_payload.get("alerts", [])
                if isinstance(status_payload.get("alerts"), list)
                else []
            )
            if alerts_payload:
                st.markdown("#### Alerts")
                st.dataframe(alerts_payload, use_container_width=True, hide_index=True)
            else:
                st.success("Активных алертов нет.")

            alerting_cfg = (
                status_payload.get("alerting", {})
                if isinstance(status_payload.get("alerting"), dict)
                else {}
            )
            st.caption(f"Alerting config snapshot: {alerting_cfg}")

        st.markdown("---")
        st.markdown("#### Hot-reload logs")
        log_filter_col1, log_filter_col2, log_filter_col3 = st.columns(3)
        selected_plugin_for_logs = log_filter_col1.selectbox(
            "Plugin filter",
            options=["all"] + [str(p.get("name", "")) for p in installed_plugins if p.get("name")],
            key="hot_reload_logs_plugin_filter",
        )
        event_type_filter = log_filter_col2.text_input(
            "Event type filter",
            value="",
            key="hot_reload_logs_event_filter",
        )
        logs_limit = log_filter_col3.slider(
            "Logs limit",
            min_value=10,
            max_value=500,
            value=120,
            key="hot_reload_logs_limit",
        )
        try:
            hot_reload_logs = client.get_hot_reload_logs(
                limit=logs_limit,
                plugin_name=None if selected_plugin_for_logs == "all" else selected_plugin_for_logs,
                event_type=event_type_filter.strip() or None,
            )
            if hot_reload_logs:
                st.dataframe(hot_reload_logs, use_container_width=True, hide_index=True)
                events_chart = []
                for item in hot_reload_logs:
                    if not isinstance(item, dict):
                        continue
                    events_chart.append(
                        {
                            "event_type": str(item.get("event_type", "unknown")),
                            "success": 1 if item.get("success") else 0,
                        }
                    )
                if events_chart:
                    st.bar_chart(events_chart, x="event_type", y="success")
            else:
                st.info("Hot-reload логи пока пустые.")
        except Exception as exc:
            st.error(f"Не удалось получить hot-reload logs: {exc}")

        st.markdown("---")
        st.markdown("#### Manual reload & history")
        reload_targets = [str(p.get("name", "")) for p in installed_plugins if p.get("name")]
        if reload_targets:
            reload_target = st.selectbox(
                "Plugin for manual reload",
                options=reload_targets,
                key="manual_reload_target",
            )
            reload_col1, reload_col2 = st.columns(2)
            if reload_col1.button("Reload now", key="reload_now_btn"):
                try:
                    reload_result = client.reload_plugin_now(reload_target)
                    if bool(reload_result.get("reloaded", False)):
                        st.success(reload_result.get("message", "Plugin reloaded"))
                    else:
                        st.error(reload_result.get("message", "Plugin reload failed"))
                    st.json(reload_result)
                    st.rerun()
                except Exception as exc:
                    st.error(f"Reload failed: {exc}")
            if reload_col2.button("Show reload history", key="reload_history_btn"):
                try:
                    history_payload = client.get_plugin_reload_history(reload_target, limit=200)
                    st.json(history_payload)
                except Exception as exc:
                    st.error(f"Не удалось получить reload history: {exc}")
        else:
            st.info("Нет установленных плагинов для ручного reload.")

        st.markdown("---")
        st.markdown("#### Real-time updates (WebSocket)")
        components.html(
            _hot_reload_live_updates_html(
                ws_base_url=client.websocket_root_url,
                token=token_value,
            ),
            height=380,
            scrolling=False,
        )

    st.markdown("---")
    st.subheader("Логи плагинов")
    log_rows = [
        {"timestamp": "-", "plugin": "system", "level": "INFO", "message": "Plugins page loaded via API"}
    ]
    st.code("\n".join(format_plugin_logs(log_rows)))
