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
    from dashboard.utils.api_client import VagusAPIClient
    from dashboard.utils.auth import is_logged_in, set_token
    from vagus.plugins.integration import get_dashboard_plugin_integration

    st.set_page_config(
        page_title="Vagus Asistent",
        page_icon="🤖",
        layout="wide",
    )

    st.title("🤖 Vagus Asistent Dashboard")

    if is_logged_in():
        st.success("Вы авторизованы")
        dashboard_integration = get_dashboard_plugin_integration()
        plugin_pages = dashboard_integration.list_pages()
        st.markdown(
            "Используйте меню слева для навигации:\n"
            "- **Tasks** — создание и просмотр задач\n"
            "- **Monitoring** — метрики системы\n"
            "- **Agents** — информация об агентах\n"
            "- **Settings** — настройки\n"
            "- **Performance** — realtime performance dashboard\n"
            "- **Circuit Breakers** — состояние и reset CB\n"
            "- **Error Analytics** — классификация ошибок\n"
            "- **Plugins** — управление плагинами"
        )
        if plugin_pages:
            st.markdown("### Plugin routes")
            for page in plugin_pages:
                st.write(f"- `{page.route}` — {page.title} ({page.plugin_name})")
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
