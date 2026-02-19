"""
Страница «Настройки» — API URL, пользователи, экспорт/импорт конфигурации.
"""

import json

import streamlit as st

from utils.api_client import VagusAPIClient

st.set_page_config(page_title="Настройки — Vagus", page_icon="⚙️", layout="wide")

if not st.session_state.get("authenticated"):
    st.warning("Пожалуйста, войдите в систему на главной странице.")
    st.stop()

st.title("⚙️ Настройки")
st.divider()

client = VagusAPIClient()

# ── 1. API URL ───────────────────────────────────────────────────────────────

st.subheader("🌐 Настройки подключения")

current_url = st.session_state.get("api_url", "http://localhost:8000")
new_url = st.text_input("API URL", value=current_url)

if new_url != current_url:
    st.session_state["api_url"] = new_url
    st.success(f"API URL обновлён: `{new_url}`")
    st.rerun()

st.divider()

# ── 2. Управление пользователями ─────────────────────────────────────────────

st.subheader("👥 Пользователи")

try:
    users = client.get_users()
except Exception:
    users = []

if users:
    header_cols = st.columns([3, 3, 2, 2])
    header_cols[0].markdown("**Имя**")
    header_cols[1].markdown("**Email**")
    header_cols[2].markdown("**Роль**")
    header_cols[3].markdown("**Статус**")

    for user in users:
        cols = st.columns([3, 3, 2, 2])
        cols[0].write(user.get("username", "—"))
        cols[1].write(user.get("email", "—"))
        cols[2].write(user.get("role", "—"))
        active = user.get("active", True)
        cols[3].write("🟢 Активен" if active else "🔴 Неактивен")
else:
    st.info(
        "Список пользователей недоступен. "
        "API не поддерживает эндпоинт или нет данных."
    )

st.divider()

# ── 3. Экспорт / импорт конфигурации ────────────────────────────────────────

st.subheader("📦 Конфигурация")

tab_export, tab_import = st.tabs(["Экспорт", "Импорт"])

with tab_export:
    st.markdown("Скачайте текущую конфигурацию системы в формате JSON.")
    if st.button("Загрузить конфигурацию из API"):
        try:
            config = client.get_config()
            st.session_state["current_config"] = config
            st.success("Конфигурация загружена.")
        except Exception as exc:
            st.error(f"Ошибка загрузки конфигурации: {exc}")

    config_data = st.session_state.get("current_config")
    if config_data:
        config_json = json.dumps(config_data, indent=2, ensure_ascii=False)
        st.download_button(
            label="⬇️ Скачать JSON",
            data=config_json,
            file_name="vagus_config.json",
            mime="application/json",
            use_container_width=True,
        )
        with st.expander("Просмотр конфигурации"):
            st.json(config_data)

with tab_import:
    st.markdown("Загрузите JSON-файл конфигурации для применения.")
    uploaded = st.file_uploader(
        "Выберите JSON-файл",
        type=["json"],
        key="config_upload",
    )
    if uploaded is not None:
        try:
            new_config = json.loads(uploaded.read().decode("utf-8"))
            st.json(new_config)

            if st.button("✅ Применить конфигурацию", type="primary"):
                try:
                    result = client.update_config(new_config)
                    st.success("Конфигурация успешно применена!")
                    st.json(result)
                except Exception as exc:
                    st.error(f"Ошибка применения: {exc}")
        except json.JSONDecodeError:
            st.error("Файл не является валидным JSON.")

st.divider()

# ── 4. Информация о сессии ───────────────────────────────────────────────────

st.subheader("ℹ️ Сессия")
st.caption(f"Пользователь: **{st.session_state.get('username', '—')}**")
st.caption(f"API URL: `{st.session_state.get('api_url', '—')}`")
st.caption(f"JWT: `{'***' + st.session_state.get('jwt_token', '')[-8:] if st.session_state.get('jwt_token') else '—'}`")
