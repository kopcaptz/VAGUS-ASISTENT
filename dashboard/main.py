"""
Vagus Asistent — Web Dashboard (Streamlit).

Запуск:
    streamlit run dashboard/main.py
"""

import os

import streamlit as st

from utils.api_client import VagusAPIClient


# ── page config ──────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Vagus Asistent",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── defaults in session_state ────────────────────────────────────────────────

if "api_url" not in st.session_state:
    st.session_state["api_url"] = os.environ.get(
        "VAGUS_API_URL", "http://localhost:8000"
    )
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False


# ── styling ──────────────────────────────────────────────────────────────────

st.markdown(
    """
    <style>
    .block-container { padding-top: 2rem; }
    [data-testid="stSidebar"] { min-width: 260px; }
    .login-box {
        max-width: 420px;
        margin: 6rem auto;
        padding: 2.5rem;
        border-radius: 12px;
        border: 1px solid #e0e0e0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ── auth helpers ─────────────────────────────────────────────────────────────

def _show_login_form() -> None:
    """Отображает форму входа по центру экрана."""
    st.markdown('<div class="login-box">', unsafe_allow_html=True)
    st.markdown("## 🧠 Vagus Asistent")
    st.markdown("Войдите для доступа к панели управления")
    st.divider()

    with st.form("login_form"):
        username = st.text_input("Имя пользователя")
        password = st.text_input("Пароль", type="password")
        submitted = st.form_submit_button("Войти", use_container_width=True)

    if submitted:
        if not username or not password:
            st.error("Заполните все поля.")
            return
        client = VagusAPIClient()
        with st.spinner("Авторизация..."):
            ok = client.login(username, password)
        if ok:
            st.success("Вход выполнен!")
            st.rerun()
        else:
            st.error("Неверные учётные данные или API недоступен.")

    st.markdown("</div>", unsafe_allow_html=True)


def _show_sidebar() -> None:
    """Боковая панель для авторизованного пользователя."""
    with st.sidebar:
        st.markdown("### 🧠 Vagus Asistent")
        st.divider()
        user = st.session_state.get("username", "—")
        st.markdown(f"**Пользователь:** {user}")
        st.caption(f"API: `{st.session_state.get('api_url', '')}`")
        st.divider()

        st.page_link("main.py", label="Главная", icon="🏠")
        st.page_link("pages/1_Tasks.py", label="Задачи", icon="📝")
        st.page_link("pages/2_Monitoring.py", label="Мониторинг", icon="📊")
        st.page_link("pages/3_Agents.py", label="Агенты", icon="🤖")
        st.page_link("pages/4_Settings.py", label="Настройки", icon="⚙️")

        st.divider()
        if st.button("Выйти", use_container_width=True):
            VagusAPIClient().logout()
            st.rerun()


# ── main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    if not st.session_state.get("authenticated"):
        _show_login_form()
        return

    _show_sidebar()

    st.title("🏠 Главная")
    st.markdown(
        """
        Добро пожаловать в **Vagus Asistent Dashboard**.

        Используйте навигацию слева для доступа к разделам:

        | Раздел | Описание |
        |--------|----------|
        | 📝 **Задачи** | Создание и отслеживание задач |
        | 📊 **Мониторинг** | Метрики и графики системы |
        | 🤖 **Агенты** | Управление агентами |
        | ⚙️ **Настройки** | Конфигурация и пользователи |
        """
    )

    st.divider()

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Статус API", value="—", delta=None)
    with col2:
        st.metric(label="Активные агенты", value="—")
    with col3:
        st.metric(label="Задач сегодня", value="—")

    client = VagusAPIClient()
    try:
        status = client.get_system_status()
        with col1:
            st.metric(label="Статус API", value="Online", delta="ok")
        active = status.get("active_agents", "—")
        with col2:
            st.metric(label="Активные агенты", value=str(active))
        tasks_today = status.get("tasks_today", "—")
        with col3:
            st.metric(label="Задач сегодня", value=str(tasks_today))
    except Exception:
        with col1:
            st.metric(label="Статус API", value="Offline", delta="err")


if __name__ == "__main__":
    main()
else:
    main()
