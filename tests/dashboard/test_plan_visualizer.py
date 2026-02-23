"""Tests for plan_visualizer component."""

from unittest.mock import MagicMock, patch

import pytest


def test_render_plan_imports_without_error():
    """Компонент импортируется без ошибок."""
    from dashboard.components.plan_visualizer import render_plan

    assert callable(render_plan)


def test_render_plan_with_empty_plan_does_not_raise():
    """render_plan с пустым планом не вызывает исключений."""
    from dashboard.components.plan_visualizer import render_plan

    with patch("streamlit.subheader") as mock_subheader, \
         patch("streamlit.dataframe") as mock_dataframe, \
         patch("streamlit.write") as mock_write:
        render_plan(None)
        render_plan({})
        render_plan({"steps": []})
        render_plan({"steps": None})


def test_render_plan_with_valid_plan_calls_streamlit():
    """render_plan с валидным планом вызывает st.subheader и st.dataframe."""
    from dashboard.components.plan_visualizer import render_plan

    plan = {
        "plan_id": "plan_1",
        "steps": [
            {
                "step_id": "s1",
                "agent_type": "coder",
                "prompt": "Write code",
                "depends_on": [],
                "artefact_key": "code",
            },
        ],
        "execution_mode": "sequential",
    }
    with patch("streamlit.subheader") as mock_subheader, \
         patch("streamlit.dataframe") as mock_dataframe, \
         patch("streamlit.write") as mock_write:
        render_plan(plan)
        mock_subheader.assert_called_once_with("План выполнения")
        mock_dataframe.assert_called_once()
        call_args = mock_dataframe.call_args[0][0]
        assert len(call_args) == 1
        assert call_args[0]["Step ID"] == "s1"
        assert call_args[0]["Agent"] == "coder"
