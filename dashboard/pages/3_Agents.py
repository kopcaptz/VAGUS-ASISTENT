"""Страница информации об агентах."""

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False

if STREAMLIT_AVAILABLE:
    try:
        from dashboard.utils.api_client import VagusAPIClient
        from dashboard.utils.auth import attach_unauthorized_handler, get_token, require_login
    except ModuleNotFoundError:
        from utils.api_client import VagusAPIClient
        from utils.auth import attach_unauthorized_handler, get_token, require_login

    require_login()

    st.title("Агенты")

    client = attach_unauthorized_handler(VagusAPIClient(token=get_token()))

    try:
        agents = client.get_agents()
        if agents:
            for agent in agents:
                with st.expander(f"**{agent['name']}** — {'Доступен' if agent['is_available'] else 'Недоступен'}"):
                    st.write(f"**Описание:** {agent.get('description', 'N/A')}")
                    st.write(f"**Типы задач:** {', '.join(agent.get('task_types', []))}")
                    st.write(f"**Статус:** {'Активен' if agent['is_available'] else 'Неактивен'}")
        else:
            st.info("Нет зарегистрированных агентов")
    except Exception as e:
        st.error(f"Не удалось загрузить агентов: {e}")
