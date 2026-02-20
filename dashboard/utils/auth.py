"""
Управление аутентификацией в Streamlit session_state.
"""

import base64
import json
import time
from typing import Any

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False


def _decode_jwt_payload(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {}
        payload_b64 = parts[1]
        padding = "=" * (-len(payload_b64) % 4)
        decoded = base64.urlsafe_b64decode(payload_b64 + padding)
        data = json.loads(decoded.decode("utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _is_token_expired(token: str, leeway_seconds: int = 30) -> bool:
    payload = _decode_jwt_payload(token)
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        return True
    return (float(exp) - float(leeway_seconds)) <= time.time()


def is_logged_in() -> bool:
    """Проверяет, аутентифицирован ли пользователь."""
    if not STREAMLIT_AVAILABLE:
        return False
    token = st.session_state.get("access_token", "")
    if not token:
        return False
    if _is_token_expired(token):
        st.session_state.pop("access_token", None)
        return False
    return True


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
        st.warning("Сессия отсутствует или истекла. Пожалуйста, войдите снова на главной странице.")
        st.stop()


def _is_unauthorized_error(exc: Exception) -> bool:
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code == 401:
        return True

    text = str(exc)
    if "401" in text:
        return True
    if "Could not validate credentials" in text:
        return True
    return False


def handle_unauthorized_error(exc: Exception) -> bool:
    """Обрабатывает 401: очищает сессию и останавливает страницу."""
    if not STREAMLIT_AVAILABLE:
        return False
    if not _is_unauthorized_error(exc):
        return False
    logout()
    st.warning("Сессия истекла или недействительна. Войдите снова на главной странице.")
    st.stop()
    return True


def attach_unauthorized_handler(client: Any) -> Any:
    """
    Оборачивает API-клиент, чтобы автоматически обрабатывать 401
    во всех методах клиента.
    """

    class _UnauthorizedAwareClient:
        def __init__(self, wrapped: Any):
            self._wrapped = wrapped

        def __getattr__(self, name: str) -> Any:
            attr = getattr(self._wrapped, name)
            if not callable(attr):
                return attr

            def _wrapped_call(*args: Any, **kwargs: Any) -> Any:
                try:
                    return attr(*args, **kwargs)
                except Exception as exc:
                    handle_unauthorized_error(exc)
                    raise

            return _wrapped_call

    return _UnauthorizedAwareClient(client)
