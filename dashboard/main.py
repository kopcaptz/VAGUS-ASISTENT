"""
Streamlit Dashboard — main entry point.
Run: streamlit run dashboard/main.py
"""

import streamlit as st

from dashboard.utils.api_client import VagusAPIClient
from dashboard.utils.auth import is_authenticated, logout

st.set_page_config(
    page_title="Vagus Asistent",
    page_icon="🤖",
    layout="wide",
)

st.title("Vagus Asistent Dashboard")

if is_authenticated():
    st.success("Authenticated")
    if st.sidebar.button("Logout"):
        logout()
        st.rerun()
    st.sidebar.markdown("---")
    st.sidebar.markdown("Navigate using the pages in the sidebar.")
    st.markdown(
        "Welcome to the Vagus Asistent Dashboard. "
        "Use the sidebar to navigate to Tasks, Monitoring, Agents, or Settings."
    )
else:
    st.markdown("### Login")
    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

    if submitted:
        client = VagusAPIClient()
        if client.login(username, password):
            st.success("Login successful!")
            st.rerun()
        else:
            st.error("Invalid username or password.")
