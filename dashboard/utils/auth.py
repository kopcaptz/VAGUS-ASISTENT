"""
Управление аутентификацией в Streamlit session_state.
Токен также сохраняется в локальный файл .admin_session для персистентности при F5.
"""

import base64
import json
import time
from pathlib import Path
from typing import Any

# dashboard/utils/auth.py -> project root = parent.parent.parent
_SESSION_FILE = Path(__file__).resolve().parent.parent.parent / ".admin_session"

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


def _load_persisted_token() -> str:
    """Читает токен из файла .admin_session."""
    try:
        if _SESSION_FILE.exists():
            data = _SESSION_FILE.read_text(encoding="utf-8").strip()
            return data if data else ""
    except Exception:
        pass
    return ""


def _save_persisted_token(token: str) -> None:
    """Сохраняет токен в файл .admin_session."""
    try:
        _SESSION_FILE.write_text(token.strip(), encoding="utf-8")
        _SESSION_FILE.chmod(0o600)
    except Exception:
        pass


def _clear_persisted_token() -> None:
    """Удаляет файл .admin_session."""
    try:
        if _SESSION_FILE.exists():
            _SESSION_FILE.unlink()
    except Exception:
        pass


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
        token = _load_persisted_token()
        if token:
            st.session_state["access_token"] = token
        else:
            return False
    if _is_token_expired(token):
        st.session_state.pop("access_token", None)
        _clear_persisted_token()
        return False
    return True


def get_token() -> str:
    """Возвращает текущий access_token."""
    if not STREAMLIT_AVAILABLE:
        return ""
    return st.session_state.get("access_token", "")


def set_token(token: str) -> None:
    """Сохраняет access_token в session_state и в файл .admin_session."""
    if STREAMLIT_AVAILABLE:
        st.session_state["access_token"] = token
        _save_persisted_token(token)


def logout() -> None:
    """Выход из системы: очищает session_state и удаляет .admin_session."""
    if STREAMLIT_AVAILABLE:
        st.session_state.pop("access_token", None)
        _clear_persisted_token()


def _render_login_form() -> None:
    """Отображает форму входа (логин, пароль)."""
    try:
        from dashboard.utils.api_client import VagusAPIClient
    except ModuleNotFoundError:
        from utils.api_client import VagusAPIClient

    st.markdown("### Вход в систему")
    with st.form("login_form"):
        username = st.text_input("Логин")
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


def require_login() -> None:
    """Проверяет авторизацию; при отсутствии — показывает форму входа."""
    if not STREAMLIT_AVAILABLE:
        return
    if not is_logged_in():
        st.warning("Сессия отсутствует или истекла. Войдите в систему ниже.")
        _render_login_form()
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
    """Обрабатывает 401: очищает сессию и показывает форму входа."""
    if not STREAMLIT_AVAILABLE:
        return False
    if not _is_unauthorized_error(exc):
        return False
    logout()
    st.warning("Сессия истекла или недействительна. Войдите снова.")
    _render_login_form()
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
