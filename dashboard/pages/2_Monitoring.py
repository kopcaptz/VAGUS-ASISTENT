"""Страница мониторинга системы."""

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False

if STREAMLIT_AVAILABLE:
    from dashboard.utils.api_client import VagusAPIClient
    from dashboard.utils.auth import get_token, require_login
    from dashboard.utils.charts import extract_metrics

    require_login()

    st.title("Мониторинг")

    client = VagusAPIClient(token=get_token())

    try:
        status = client.get_system_status()
        metrics = extract_metrics(status)

        col1, col2, col3 = st.columns(3)
        col1.metric("Агентов", metrics["agents"])
        col2.metric("Активных задач", metrics["active_tasks"])
        col3.metric("Uptime", metrics["uptime"])

        col4, col5, col6 = st.columns(3)
        col4.metric("Запросов", metrics["requests"])
        col5.metric("Общая стоимость", metrics["total_cost"])
        col6.metric("Cache Hit Rate", f"{metrics['cache_hit_rate']:.1f}%")

        st.markdown("---")
        st.subheader("Layer 1 Stats")
        l1 = status.get("layer1_stats", {})
        if l1:
            st.json(l1)
        else:
            st.info("Нет данных Layer 1")

    except Exception as e:
        st.error(f"Не удалось загрузить статус: {e}")

    if st.button("Обновить"):
        st.rerun()
