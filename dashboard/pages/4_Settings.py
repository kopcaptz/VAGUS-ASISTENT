"""
Settings page — admin configuration.
"""

import streamlit as st

from dashboard.utils.auth import require_login

require_login()

st.title("Settings")

st.info("Settings management is coming in a future release.")

st.markdown("### Current Configuration")
st.markdown(
    "- **API URL:** `http://localhost:8000`\n"
    "- **Dashboard:** Streamlit\n"
    "- **Authentication:** JWT (access + refresh tokens)\n"
)
