"""Компонент визуализации плана выполнения задачи."""

from typing import Any, Dict, List, Optional

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False


def render_plan(plan: Optional[Dict[str, Any]]) -> None:
    """
    Рендерит план выполнения в Streamlit.
    Формат: {"plan_id", "steps": [{"step_id", "agent_type", "prompt", "depends_on", "artefact_key"}], "execution_mode"}
    """
    if not STREAMLIT_AVAILABLE or not plan:
        return
    steps = plan.get("steps")
    if not steps or not isinstance(steps, list):
        return
    st.subheader("План выполнения")
    plan_id = plan.get("plan_id", "")
    if plan_id:
        st.caption(f"Plan ID: {plan_id} | Режим: {plan.get('execution_mode', '—')}")
    rows = []
    for s in steps:
        if not isinstance(s, dict):
            continue
        step_id = s.get("step_id", "—")
        agent_type = s.get("agent_type", "—")
        prompt = s.get("prompt", "")
        prompt_short = (prompt[:60] + "…") if len(prompt) > 60 else prompt
        depends_on = s.get("depends_on", [])
        dep_str = ", ".join(depends_on) if isinstance(depends_on, list) else str(depends_on)
        artefact = s.get("artefact_key", "—")
        rows.append(
            {
                "Step ID": step_id,
                "Agent": agent_type,
                "Prompt": prompt_short,
                "Depends on": dep_str or "—",
                "Artefact": artefact,
            }
        )
    if rows:
        st.dataframe(
            rows,
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("Нет шагов в плане")
