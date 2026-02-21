"""Компонент отображения истории рефлексий задачи."""

from typing import Any, Dict, List, Optional

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False


def render_reflection(
    count: Optional[int],
    details: Optional[List[Dict[str, Any]]] = None,
) -> None:
    """
    Рендерит счётчик циклов рефлексии и, при наличии, детали итераций.
    Сейчас details не приходит из API — показываем placeholder.
    """
    if not STREAMLIT_AVAILABLE:
        return
    st.subheader("Циклы рефлексии")
    c = count if count is not None else 0
    st.metric("Циклов рефлексии", c)
    if details and isinstance(details, list) and len(details) > 0:
        for i, d in enumerate(details):
            desc = d.get("description", str(d)) if isinstance(d, dict) else str(d)
            st.markdown(f"- **Итерация {i + 1}:** {desc}")
    else:
        st.caption("Детали рефлексий пока недоступны в API")
