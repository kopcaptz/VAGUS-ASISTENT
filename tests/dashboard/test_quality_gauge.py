"""Tests for quality_gauge component."""

from unittest.mock import MagicMock, patch

import pytest


def test_render_quality_score_imports_without_error():
    """Компонент импортируется без ошибок."""
    from dashboard.components.quality_gauge import render_quality_score

    assert callable(render_quality_score)


def test_render_quality_score_calls_streamlit():
    """render_quality_score вызывает st.metric и st.progress."""
    from dashboard.components.quality_gauge import render_quality_score

    mock_col1 = MagicMock()
    mock_col2 = MagicMock()
    with patch("streamlit.columns") as mock_columns, \
         patch("streamlit.subheader") as mock_subheader, \
         patch("streamlit.progress") as mock_progress:
        mock_columns.return_value = [mock_col1, mock_col2]
        render_quality_score(0.85)
        mock_subheader.assert_called_once_with("Оценка качества")
        mock_columns.assert_called_once_with([1, 2])
        mock_progress.assert_called_once_with(0.85)


def test_render_quality_score_none_uses_zero():
    """render_quality_score с None использует 0."""
    from dashboard.components.quality_gauge import render_quality_score

    mock_col1 = MagicMock()
    mock_col2 = MagicMock()
    with patch("streamlit.columns") as mock_columns, \
         patch("streamlit.subheader") as mock_subheader, \
         patch("streamlit.progress") as mock_progress:
        mock_columns.return_value = [mock_col1, mock_col2]
        render_quality_score(None)
        mock_progress.assert_called_once_with(0.0)
