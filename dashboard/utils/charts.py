"""
Chart helpers for the Streamlit Dashboard.
"""

from typing import Any, Dict

import streamlit as st


def render_metrics_row(status: Dict[str, Any]) -> None:
    """Renders a row of st.metric cards for system status."""
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Agents", status.get("layer2_agents_count", 0))
    with col2:
        st.metric("Active Tasks", status.get("active_tasks_count", 0))
    with col3:
        uptime = status.get("uptime_seconds", 0)
        if uptime > 3600:
            label = f"{uptime / 3600:.1f}h"
        elif uptime > 60:
            label = f"{uptime / 60:.1f}m"
        else:
            label = f"{uptime:.0f}s"
        st.metric("Uptime", label)


def render_layer1_stats(stats: Dict[str, Any]) -> None:
    """Renders Layer 1 statistics."""
    if not stats:
        st.info("No Layer 1 statistics available.")
        return

    col1, col2 = st.columns(2)
    with col1:
        st.metric("Total Requests", stats.get("requests", 0))
    with col2:
        st.metric("Total Cost", f"${stats.get('total_cost', 0):.4f}")

    cache = stats.get("cache", {})
    if cache:
        st.subheader("Cache")
        c1, c2 = st.columns(2)
        with c1:
            st.metric("Cache Hits", cache.get("hits", 0))
        with c2:
            st.metric("Cache Misses", cache.get("misses", 0))
