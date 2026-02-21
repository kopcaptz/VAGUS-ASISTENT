"""Smoke tests for Monitoring dashboard page."""

from pathlib import Path


def test_monitoring_page_exists():
    page_path = Path("dashboard/pages/2_Monitoring.py")
    assert page_path.exists()


def test_monitoring_page_has_synaptic_graph():
    content = Path("dashboard/pages/2_Monitoring.py").read_text(encoding="utf-8")
    assert "fetch_graph_data" in content or "artifact_graph" in content
    assert "Граф синаптических связей" in content


def test_monitoring_page_has_redis_section():
    content = Path("dashboard/pages/2_Monitoring.py").read_text(encoding="utf-8")
    assert "Redis" in content
    assert "fetch_redis_metrics" in content or "redis_monitor" in content


def test_monitoring_page_has_postgres_section():
    content = Path("dashboard/pages/2_Monitoring.py").read_text(encoding="utf-8")
    assert "PostgreSQL" in content or "postgres" in content.lower()
    assert "fetch_postgres_metrics" in content or "postgres_monitor" in content


def test_monitoring_page_has_synaptic_metrics():
    content = Path("dashboard/pages/2_Monitoring.py").read_text(encoding="utf-8")
    assert "get_monitoring_synaptic" in content or "synaptic" in content.lower()
    assert "Метрики обучения" in content
