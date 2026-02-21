"""Tests for reflection_history component."""

from unittest.mock import patch

import pytest


def test_render_reflection_imports_without_error():
    """Компонент импортируется без ошибок."""
    from dashboard.components.reflection_history import render_reflection

    assert callable(render_reflection)


def test_render_reflection_calls_streamlit():
    """render_reflection вызывает st.metric."""
    from dashboard.components.reflection_history import render_reflection

    with patch("dashboard.components.reflection_history.st") as mock_st:
        mock_st.STREAMLIT_AVAILABLE = True
        render_reflection(2)
        mock_st.subheader.assert_called_once_with("Циклы рефлексии")
        mock_st.metric.assert_called_once_with("Циклов рефлексии", 2)


def test_render_reflection_none_uses_zero():
    """render_reflection с None использует 0."""
    from dashboard.components.reflection_history import render_reflection

    with patch("dashboard.components.reflection_history.st") as mock_st:
        mock_st.STREAMLIT_AVAILABLE = True
        render_reflection(None)
        mock_st.metric.assert_called_once_with("Циклов рефлексии", 0)
