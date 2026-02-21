"""Smoke tests for Tasks dashboard page."""

from pathlib import Path


def test_tasks_page_exists_and_has_expected_controls():
    page_path = Path("dashboard/pages/1_Tasks.py")
    assert page_path.exists()
    content = page_path.read_text(encoding="utf-8")
    assert "st.title" in content
    assert "create_task" in content
    assert "get_task_status" in content
    assert "list_tasks" in content


def test_tasks_page_has_plan_visualizer():
    content = Path("dashboard/pages/1_Tasks.py").read_text(encoding="utf-8")
    assert "plan_visualizer" in content or "render_plan" in content


def test_tasks_page_has_quality_gauge():
    content = Path("dashboard/pages/1_Tasks.py").read_text(encoding="utf-8")
    assert "quality_gauge" in content or "render_quality_score" in content


def test_tasks_page_has_reflection_history():
    content = Path("dashboard/pages/1_Tasks.py").read_text(encoding="utf-8")
    assert "reflection_history" in content or "render_reflection" in content


def test_tasks_page_has_goal_field():
    content = Path("dashboard/pages/1_Tasks.py").read_text(encoding="utf-8")
    assert "goal" in content


def test_tasks_page_has_websocket():
    content = Path("dashboard/pages/1_Tasks.py").read_text(encoding="utf-8")
    assert "websocket" in content.lower() or "WebSocket" in content
    assert "_task_events_ws_html" in content
