"""Страница настроек (admin only)."""

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False

if STREAMLIT_AVAILABLE:
    try:
        from dashboard.utils.auth import get_token, logout, require_login
    except ModuleNotFoundError:
        from utils.auth import get_token, logout, require_login

    require_login()

    st.title("Настройки")

    st.subheader("API Подключение")
    api_url = st.text_input("API URL", value="http://localhost:8000")
    st.info(f"Текущий токен: {'***' + get_token()[-8:] if get_token() else 'Не установлен'}")

    st.markdown("---")
    st.subheader("Аккаунт")
    if st.button("Выйти"):
        logout()
        st.success("Вы вышли из системы")
        st.rerun()
