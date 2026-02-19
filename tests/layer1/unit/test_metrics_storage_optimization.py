"""Tests for SQLite query/index optimizations in MetricsStorage."""

from datetime import datetime, timedelta
import sqlite3

from vagus.layer1.monitoring.metrics_storage import MetricsStorage


def test_metrics_storage_creates_indexes_for_frequent_queries(tmp_path):
    db_path = tmp_path / "metrics.db"
    storage = MetricsStorage(str(db_path))

    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='index'
            """
        ).fetchall()
    index_names = {row[0] for row in rows}
    assert "idx_metrics_timestamp" in index_names
    assert "idx_metrics_provider" in index_names

    storage.insert(trace_id="t1", provider="openai", model="gpt-4o", success=True, e2e_ms=10.0)
    storage.insert(trace_id="t2", provider="anthropic", model="claude", success=True, e2e_ms=20.0)
    recent = storage.get_recent_requests(limit=1)
    assert len(recent) == 1
    assert recent[0]["trace_id"] in {"t1", "t2"}


def test_metrics_storage_creates_audit_timestamp_index_if_audit_table_exists(tmp_path):
    db_path = tmp_path / "metrics_with_audit.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS audit_log (timestamp TEXT NOT NULL)")
    storage = MetricsStorage(str(db_path))

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='index' AND name='idx_audit_log_timestamp'
            LIMIT 1
            """
        ).fetchone()
    assert row is not None
    assert storage is not None


def test_cleanup_old_triggers_vacuum_when_rows_deleted(tmp_path, monkeypatch):
    storage = MetricsStorage(str(tmp_path / "metrics.db"), vacuum_interval_seconds=60)
    storage.insert(trace_id="old-trace", provider="openai", model="gpt-4o", success=True, e2e_ms=10.0)

    old_ts = (datetime.utcnow() - timedelta(days=45)).isoformat()
    with sqlite3.connect(storage.db_path) as conn:
        conn.execute(
            "UPDATE request_metrics SET timestamp = ? WHERE trace_id = ?",
            (old_ts, "old-trace"),
        )

    called = {"count": 0}

    def _fake_vacuum(force: bool = False):
        called["count"] += 1
        return True

    monkeypatch.setattr(storage, "vacuum", _fake_vacuum)
    deleted = storage.cleanup_old(retention_days=30)
    assert deleted == 1
    assert called["count"] == 1
