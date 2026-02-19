"""
Управление аутентификацией в Streamlit session_state.
"""

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False


def is_logged_in() -> bool:
    """Проверяет, аутентифицирован ли пользователь."""
    if not STREAMLIT_AVAILABLE:
        return False
    return bool(st.session_state.get("access_token"))


def get_token() -> str:
    """Возвращает текущий access_token."""
    if not STREAMLIT_AVAILABLE:
        return ""
    return st.session_state.get("access_token", "")


def set_token(token: str) -> None:
    """Сохраняет access_token."""
    if STREAMLIT_AVAILABLE:
        st.session_state["access_token"] = token


def logout() -> None:
    """Выход из системы."""
    if STREAMLIT_AVAILABLE:
        st.session_state.pop("access_token", None)


def require_login() -> None:
    """Перенаправляет на страницу входа если не аутентифицирован."""
    if not STREAMLIT_AVAILABLE:
        return
    if not is_logged_in():
        st.warning("Пожалуйста, войдите в систему на главной странице.")
        st.stop()
