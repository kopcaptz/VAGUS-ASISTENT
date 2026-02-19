"""
Agents page — view registered agents and their capabilities.
"""

import streamlit as st

from dashboard.utils.api_client import VagusAPIClient
from dashboard.utils.auth import require_login

require_login()

st.title("Agents")

client = VagusAPIClient()

try:
    agents = client.get_agents()
    if not agents:
        st.info("No agents registered.")
    else:
        for agent in agents:
            with st.expander(f"{agent['name']} — {'Available' if agent['is_available'] else 'Unavailable'}"):
                st.markdown(f"**Description:** {agent.get('description', 'N/A')}")
                st.markdown(f"**Task Types:** {', '.join(agent.get('task_types', []))}")
except Exception as e:
    st.error(f"Could not load agents: {e}")
