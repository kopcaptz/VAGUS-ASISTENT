"""
Monitoring page — system metrics and performance.
"""

import streamlit as st

from dashboard.utils.api_client import VagusAPIClient
from dashboard.utils.auth import require_login
from dashboard.utils.charts import render_layer1_stats, render_metrics_row

require_login()

st.title("Monitoring")

client = VagusAPIClient()

try:
    status = client.get_system_status()

    st.subheader("System Overview")
    render_metrics_row(status)

    st.markdown("---")
    st.subheader("Layer 1 — LLM Router")
    render_layer1_stats(status.get("layer1_stats", {}))

except Exception as e:
    st.error(f"Could not load system status: {e}")

if st.button("Refresh"):
    st.rerun()
