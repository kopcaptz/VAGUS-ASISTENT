"""API keys management dashboard page."""

from __future__ import annotations

import time
from typing import Any

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False

if STREAMLIT_AVAILABLE:
    from dashboard.utils.api_client import VagusAPIClient
    from dashboard.utils.auth import get_token, require_login


def mask_key(value: str) -> str:
    if not value:
        return "***"
    if len(value) <= 8:
        return "***"
    return f"***{value[-8:]}"


if STREAMLIT_AVAILABLE:
    def _render_status_pie_chart(items: list[dict[str, Any]]) -> None:
        if not items:
            st.info("No health data available.")
            return
        counts: dict[str, int] = {}
        for row in items:
            status = str(row.get("status", "unknown"))
            counts[status] = counts.get(status, 0) + 1
        chart_data = [{"status": status, "value": value} for status, value in counts.items()]
        st.vega_lite_chart(
            {"values": chart_data},
            {
                "mark": {"type": "arc", "outerRadius": 120},
                "encoding": {
                    "theta": {"field": "value", "type": "quantitative"},
                    "color": {"field": "status", "type": "nominal"},
                    "tooltip": [
                        {"field": "status", "type": "nominal"},
                        {"field": "value", "type": "quantitative"},
                    ],
                },
            },
            use_container_width=True,
        )

    require_login()
    st.title("API Keys")
    st.caption("Безопасное управление API ключами через backend API")

    token = get_token()
    client = VagusAPIClient(token=token)

    col_left, col_right = st.columns([1, 1])
    with col_left:
        auto_refresh = st.checkbox("Auto refresh", value=False)
    with col_right:
        if st.button("Refresh now"):
            st.rerun()

    st.subheader("Добавить ключ")
    with st.form("add_api_key_form"):
        key_name = st.text_input("Name", value="")
        key_type = st.selectbox("Type", options=["openai", "anthropic", "google", "deepseek", "openrouter", "custom"])
        key_value = st.text_input("Value", value="", type="password")
        expires_at = st.text_input("Expires at (ISO, optional)", value="")
        add_submit = st.form_submit_button("Add")
    if add_submit:
        if not key_name.strip() or not key_value.strip():
            st.error("Name и Value обязательны.")
        else:
            try:
                client.create_api_key(
                    name=key_name.strip(),
                    key_type=key_type.strip(),
                    value=key_value.strip(),
                    expires_at=expires_at.strip() or None,
                )
                st.success("Ключ добавлен.")
                st.rerun()
            except Exception as exc:
                st.error(f"Не удалось добавить ключ: {exc}")

    st.markdown("---")
    st.subheader("Список ключей")

    try:
        keys = client.list_api_keys()
    except Exception as exc:
        st.error(f"Не удалось загрузить список ключей: {exc}")
        st.stop()

    if not keys:
        st.info("Ключи пока не добавлены.")
    else:
        table_rows: list[dict[str, Any]] = []
        for item in keys:
            table_rows.append(
                {
                    "Name": item.get("name", ""),
                    "Type": item.get("type", ""),
                    "Status": item.get("status", ""),
                    "Last Used": item.get("last_used_at"),
                    "Masked": item.get("masked_value", "***"),
                }
            )
        st.dataframe(table_rows, use_container_width=True, hide_index=True)

        st.markdown("---")
        st.subheader("Действия")
        selected = st.selectbox("Выберите ключ", options=[str(x.get("name", "")) for x in keys])
        action_col1, action_col2, action_col3 = st.columns(3)

        with action_col1:
            if st.button("Validate"):
                try:
                    response = client.validate_api_key(selected)
                    if response.get("valid"):
                        st.success("Ключ валиден.")
                    else:
                        st.warning(f"Ключ невалиден: {response.get('error')}")
                except Exception as exc:
                    st.error(f"Ошибка валидации: {exc}")

        with action_col2:
            if st.button("Delete"):
                try:
                    client.delete_api_key(selected)
                    st.success("Ключ удалён.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Ошибка удаления: {exc}")

        with action_col3:
            selected_row = next((x for x in keys if x.get("name") == selected), {})
            masked_value = str(selected_row.get("masked_value") or "***")
            st.code(masked_value, language=None)
            st.caption("Copy: используйте кнопку копирования у code-блока.")

    st.markdown("---")
    st.subheader("Keys Health")
    health_col1, health_col2, health_col3 = st.columns([1, 1, 2])
    with health_col1:
        run_health_check = st.button("Run Health Check")
    with health_col2:
        health_refresh = st.button("Refresh Health")

    health_payload: dict[str, Any] = {}
    try:
        if run_health_check:
            health_payload = client.run_api_keys_health_check()
        else:
            health_payload = client.get_api_keys_health()
    except Exception as exc:
        st.error(f"Не удалось получить health: {exc}")

    if health_refresh:
        st.rerun()

    if health_payload:
        total_keys = int(health_payload.get("total_keys", 0))
        valid_keys = int(health_payload.get("valid_keys", 0))
        invalid_keys = int(health_payload.get("invalid_keys", 0))
        expiring_soon = int(health_payload.get("expiring_soon", 0))
        rotation_required = bool(health_payload.get("rotation_required", False))

        summary_col1, summary_col2, summary_col3, summary_col4 = st.columns(4)
        summary_col1.metric("Total", total_keys)
        summary_col2.metric("Valid", valid_keys)
        summary_col3.metric("Invalid", invalid_keys)
        summary_col4.metric("Expiring <= 7d", expiring_soon)
        if rotation_required:
            st.warning("Rotation required")
        else:
            st.success("Rotation not required")

        key_health_rows = health_payload.get("keys", [])
        if isinstance(key_health_rows, list):
            _render_status_pie_chart(key_health_rows)
            expiring_rows = [
                row for row in key_health_rows
                if isinstance(row.get("expires_in_days"), int)
            ]
            expiring_rows.sort(key=lambda x: int(x.get("expires_in_days", 99999)))
            st.caption("Expiring keys (sorted by days left)")
            st.dataframe(expiring_rows, use_container_width=True, hide_index=True)

    if auto_refresh:
        time.sleep(2)
        st.rerun()
