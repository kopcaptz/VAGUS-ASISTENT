"""Error analytics dashboard."""

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False

if STREAMLIT_AVAILABLE:
    try:
        from dashboard.utils.api_client import VagusAPIClient
        from dashboard.utils.auth import attach_unauthorized_handler, get_token, require_login
        from dashboard.utils.charts import extract_error_rates
    except ModuleNotFoundError:
        from utils.api_client import VagusAPIClient
        from utils.auth import attach_unauthorized_handler, get_token, require_login
        from utils.charts import extract_error_rates

    require_login()
    st.title("Error Analytics")
    st.caption("Классификация ошибок, источники и корреляции")

    client = attach_unauthorized_handler(VagusAPIClient(token=get_token()))
    window_minutes = st.selectbox("Окно анализа (минуты)", [15, 30, 60, 180, 360], index=2)
    top_limit = st.slider("Top error sources", min_value=3, max_value=25, value=10)

    try:
        snapshot = client.get_error_analytics(
            window_minutes=int(window_minutes),
            top_sources_limit=int(top_limit),
        )
        rates = extract_error_rates(snapshot)
        by_type = snapshot.get("error_rate_by_type", {})
        total_errors = int(by_type.get("total_errors", 0) or 0)
        counts = by_type.get("counts", {}) if isinstance(by_type, dict) else {}

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Всего ошибок", total_errors)
        col2.metric("Transient", int(counts.get("transient", 0) or 0))
        col3.metric("Permanent", int(counts.get("permanent", 0) or 0))
        col4.metric("Infrastructure", int(counts.get("infrastructure", 0) or 0))

        st.markdown("---")
        st.subheader("Error rate по типам (%)")
        try:
            import pandas as pd

            rate_df = pd.DataFrame(
                [
                    {"type": "transient", "rate_percent": rates["transient"]},
                    {"type": "permanent", "rate_percent": rates["permanent"]},
                    {"type": "infrastructure", "rate_percent": rates["infrastructure"]},
                ]
            ).set_index("type")
            st.bar_chart(rate_df)
        except ImportError:
            st.json(rates)

        st.markdown("---")
        st.subheader("Top error sources")
        top_sources = snapshot.get("top_error_sources", [])
        if top_sources:
            st.dataframe(top_sources, use_container_width=True, hide_index=True)
        else:
            st.info("Нет ошибок за выбранное окно.")

        st.markdown("---")
        st.subheader("Correlation snapshot")
        st.json(snapshot.get("correlation", {}))

        st.markdown("---")
        st.subheader("Recent errors")
        recent = snapshot.get("recent_events", [])
        if recent:
            st.dataframe(recent, use_container_width=True, hide_index=True)
        else:
            st.info("Нет recent events.")

    except Exception as exc:
        st.error(f"Не удалось загрузить error analytics: {exc}")

    if st.button("Refresh"):
        st.rerun()
