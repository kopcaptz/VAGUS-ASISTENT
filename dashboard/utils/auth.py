"""
Authentication helpers for the Streamlit Dashboard.
"""

import streamlit as st


def is_authenticated() -> bool:
    """Checks whether the user has a valid access token in session."""
    return bool(st.session_state.get("access_token"))


def require_login():
    """Redirects to the main page if the user is not authenticated."""
    if not is_authenticated():
        st.warning("Please log in on the main page first.")
        st.stop()


def logout():
    """Clears authentication state."""
    st.session_state.pop("access_token", None)
    st.session_state.pop("refresh_token", None)
