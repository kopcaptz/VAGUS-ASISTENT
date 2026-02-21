"""Компонент отображения оценки качества задачи."""

from typing import Optional

try:
    import streamlit as st

    STREAMLIT_AVAILABLE = True
except ImportError:
    STREAMLIT_AVAILABLE = False


def render_quality_score(score: Optional[float]) -> None:
    """
    Рендерит оценку качества: прогресс-бар (0–1) и числовой показатель.
    История оценок при отсутствии данных: "Нет данных".
    """
    if not STREAMLIT_AVAILABLE:
        return
    st.subheader("Оценка качества")
    value = score if score is not None else 0.0
    value = max(0.0, min(1.0, float(value)))
    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric("Оценка качества", f"{value * 100:.0f}%")
    with col2:
        st.progress(value)
    st.caption("История оценок")
    st.info("Нет данных")
