"""Performance dashboard: realtime and 24h history charts."""

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False

if STREAMLIT_AVAILABLE:
    from dashboard.utils.api_client import VagusAPIClient
    from dashboard.utils.auth import get_token, require_login
    from dashboard.utils.charts import append_history_snapshot, build_performance_snapshot
    from vagus.plugins.integration import get_dashboard_plugin_integration

    require_login()
    st.title("Performance")
    st.caption("Realtime telemetry + history window (24h)")

    client = VagusAPIClient(token=get_token())
    history = st.session_state.get("performance_history", [])

    try:
        metrics_text = client.get_prometheus_metrics()
        system_status = client.get_system_status()
        snapshot = build_performance_snapshot(metrics_text, system_status)
        history = append_history_snapshot(history, snapshot, window_hours=24)
        st.session_state["performance_history"] = history

        col1, col2, col3 = st.columns(3)
        col1.metric("Request latency (avg)", f"{snapshot['request_latency_ms']:.2f} ms")
        col2.metric("Error rate", f"{snapshot['error_rate_percent']:.2f}%")
        col3.metric("Active connections", int(snapshot["active_connections"]))

        col4, col5 = st.columns(2)
        col4.metric("Cache hit ratio", f"{snapshot['cache_hit_ratio_percent']:.2f}%")
        col5.metric("LLM provider costs", f"${snapshot['llm_provider_cost_usd']:.4f}")

        st.markdown("---")
        st.subheader("Plugin widgets")
        integration = get_dashboard_plugin_integration()
        widgets = integration.list_widgets(target_page="performance")
        if widgets:
            for widget in widgets:
                try:
                    widget_result = widget.render(snapshot=snapshot, history=history)
                except TypeError:
                    widget_result = widget.render(snapshot)
                except Exception as exc:
                    st.warning(f"Widget '{widget.name}' error: {exc}")
                    continue

                st.markdown(f"**{widget.name}** (`{widget.plugin_name}`)")
                if isinstance(widget_result, dict):
                    st.json(widget_result)
                else:
                    st.write(widget_result)
        else:
            st.info("Plugin widgets for Performance page are not registered.")

        st.markdown("---")
        st.subheader("24h trends")
        if len(history) >= 2:
            try:
                import pandas as pd

                chart_df = pd.DataFrame(history)
                chart_df["time"] = pd.to_datetime(chart_df["timestamp"], unit="s")
                chart_df = chart_df.set_index("time")

                st.line_chart(chart_df[["request_latency_ms"]], height=180)
                st.line_chart(chart_df[["error_rate_percent"]], height=180)
                st.line_chart(chart_df[["active_connections"]], height=180)
                st.line_chart(chart_df[["cache_hit_ratio_percent"]], height=180)
                st.line_chart(chart_df[["llm_provider_cost_usd"]], height=180)
            except ImportError:
                st.info("Install pandas for line charts (`pip install pandas`).")
                st.json(history[-30:])
        else:
            st.info("Not enough samples yet. Press refresh to accumulate history.")
    except Exception as exc:
        st.error(f"Failed to load performance telemetry: {exc}")

    if st.button("Refresh"):
        st.rerun()
