"""Tests for quality_gauge component."""

from unittest.mock import patch

import pytest


def test_render_quality_score_imports_without_error():
    """Компонент импортируется без ошибок."""
    from dashboard.components.quality_gauge import render_quality_score

    assert callable(render_quality_score)


def test_render_quality_score_calls_streamlit():
    """render_quality_score вызывает st.metric и st.progress."""
    from unittest.mock import MagicMock

    from dashboard.components.quality_gauge import render_quality_score

    mock_col1 = MagicMock()
    mock_col2 = MagicMock()
    with patch("dashboard.components.quality_gauge.st") as mock_st:
        mock_st.STREAMLIT_AVAILABLE = True
        mock_st.columns.return_value = [mock_col1, mock_col2]
        render_quality_score(0.85)
        mock_st.subheader.assert_called_once_with("Оценка качества")
        mock_st.columns.assert_called_once_with([1, 2])
        mock_st.progress.assert_called_once_with(0.85)


def test_render_quality_score_none_uses_zero():
    """render_quality_score с None использует 0."""
    from unittest.mock import MagicMock

    from dashboard.components.quality_gauge import render_quality_score

    mock_col1 = MagicMock()
    mock_col2 = MagicMock()
    with patch("dashboard.components.quality_gauge.st") as mock_st:
        mock_st.STREAMLIT_AVAILABLE = True
        mock_st.columns.return_value = [mock_col1, mock_col2]
        render_quality_score(None)
        mock_st.progress.assert_called_once_with(0.0)
