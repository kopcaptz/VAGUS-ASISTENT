"""Circuit Breaker dashboard (real-time status + history)."""

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False

if STREAMLIT_AVAILABLE:
    import time

    from dashboard.utils.api_client import VagusAPIClient
    from dashboard.utils.auth import get_token, require_login
    from dashboard.utils.charts import (
        append_circuit_breaker_history,
        flatten_circuit_breaker_history,
    )

    require_login()
    st.title("Circuit Breakers")
    st.caption("Состояние, счётчики отказов, success rate и ручной reset")

    client = VagusAPIClient(token=get_token())
    local_history = st.session_state.get("circuit_breaker_history", [])

    try:
        payload = client.get_circuit_breakers()
        breakers = payload.get("breakers", []) if isinstance(payload, dict) else []

        state_counts = {"closed": 0, "open": 0, "half-open": 0}
        for item in breakers:
            state = str(item.get("state", "closed")).lower()
            if state not in state_counts:
                state = "closed"
            state_counts[state] += 1

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Всего breaker-ов", len(breakers))
        col2.metric("Closed", state_counts["closed"])
        col3.metric("Open", state_counts["open"])
        col4.metric("Half-open", state_counts["half-open"])

        st.markdown("---")
        st.subheader("Текущие состояния")
        if breakers:
            st.dataframe(
                breakers,
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("Circuit breakers ещё не созданы (нет fallback-событий).")

        states_snapshot = {
            "timestamp": time.time(),
            "states": {str(item["provider_id"]): str(item.get("state", "closed")) for item in breakers},
        }
        local_history = append_circuit_breaker_history(local_history, states_snapshot, window_hours=24)
        st.session_state["circuit_breaker_history"] = local_history

        st.markdown("---")
        st.subheader("Manual reset")
        provider_ids = [str(item.get("provider_id", "")) for item in breakers if item.get("provider_id")]
        if provider_ids:
            selected_provider = st.selectbox("Провайдер", provider_ids)
            if st.button("Reset selected circuit breaker", type="primary"):
                reset_result = client.reset_circuit_breaker(selected_provider)
                st.success(f"Reset выполнен: {reset_result.get('provider_id')}")
                st.rerun()
        else:
            st.info("Нет circuit breaker для ручного reset.")

        st.markdown("---")
        st.subheader("История состояний (24h)")
        rows = flatten_circuit_breaker_history(local_history)
        if rows:
            try:
                import pandas as pd

                df = pd.DataFrame(rows)
                df["time"] = pd.to_datetime(df["timestamp"], unit="s")
                for provider_id in sorted(df["provider_id"].unique()):
                    provider_df = (
                        df[df["provider_id"] == provider_id][["time", "state_numeric"]]
                        .set_index("time")
                        .sort_index()
                    )
                    st.caption(f"{provider_id}: 0=closed, 1=open, 2=half-open")
                    st.line_chart(provider_df, height=150)
            except ImportError:
                st.info("Install pandas for history charts (`pip install pandas`).")
                st.json(rows[-100:])
        else:
            st.info("Недостаточно данных для истории. Нажмите Refresh несколько раз.")

    except Exception as exc:
        st.error(f"Не удалось загрузить данные Circuit Breakers: {exc}")

    if st.button("Refresh"):
        st.rerun()
