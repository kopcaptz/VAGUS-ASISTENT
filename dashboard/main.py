"""
Vagus Asistent Dashboard — главная страница.
Запуск: streamlit run dashboard/main.py
"""

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False

if STREAMLIT_AVAILABLE:
    import time

    from dashboard.utils.api_client import VagusAPIClient
    from dashboard.utils.auth import get_token, is_logged_in, set_token

    st.set_page_config(
        page_title="Vagus Asistent",
        page_icon="🤖",
        layout="wide",
    )

    st.title("🤖 Vagus Asistent Dashboard")

    if is_logged_in():
        st.success("Вы авторизованы")
        token = get_token()
        if token:
            client = VagusAPIClient(token=token)
            try:
                payload = client.get_api_keys_health()
                total = int(payload.get("total_keys", 0))
                valid = int(payload.get("valid_keys", 0))
                invalid = int(payload.get("invalid_keys", 0))
                expiring = int(payload.get("expiring_soon", 0))
                severity = "green"
                if invalid > 0:
                    severity = "red"
                elif expiring > 0:
                    severity = "orange"
                st.markdown(f"### API Keys Status: :{severity}[{valid}/{total} valid]")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total Keys", total)
                col2.metric("Valid", valid)
                col3.metric("Invalid", invalid)
                col4.metric("Expiring <= 7d", expiring)
            except Exception:
                st.info("API Keys Status недоступен")

        auto_refresh = st.checkbox("Auto-refresh dashboard widget (30s)", value=True)
        if auto_refresh:
            st.caption("Widget auto-refreshes every 30 seconds.")
            time.sleep(30)
            st.rerun()
        st.markdown(
            "Используйте меню слева для навигации:\n"
            "- **Tasks** — создание и просмотр задач\n"
            "- **Monitoring** — метрики системы\n"
            "- **Agents** — информация об агентах\n"
            "- **Settings** — настройки\n"
            "- **Performance** — realtime performance dashboard\n"
            "- **Circuit Breakers** — состояние и reset CB\n"
            "- **Error Analytics** — классификация ошибок"
        )
    else:
        st.markdown("### Вход в систему")
        with st.form("login_form"):
            username = st.text_input("Логин", value="admin")
            password = st.text_input("Пароль", type="password")
            submitted = st.form_submit_button("Войти")

        if submitted:
            client = VagusAPIClient()
            if client.login(username, password):
                set_token(client._token)
                st.success("Успешный вход!")
                st.rerun()
            else:
                st.error("Неверный логин или пароль")
