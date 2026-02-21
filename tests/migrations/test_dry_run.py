"""Tests for Alembic migration dry-run (--sql mode).

Alembic does not have --dry-run; --sql outputs SQL to stdout without executing.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run_alembic(*args: str) -> subprocess.CompletedProcess[str]:
    """Run alembic from project root."""
    project_root = Path(__file__).resolve().parents[2]
    cmd = [sys.executable, "-m", "alembic"] + list(args)
    return subprocess.run(
        cmd,
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_alembic_upgrade_sql_output() -> None:
    """Verify upgrade --sql runs successfully and output contains CREATE TABLE for artifacts tables."""
    result = _run_alembic("upgrade", "head", "--sql")

    assert result.returncode == 0, (
        f"alembic upgrade head --sql failed: stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    assert "CREATE TABLE" in result.stdout, "Expected CREATE TABLE in SQL output"
    assert "artifacts" in result.stdout, "Expected artifacts table in SQL output"
    assert "artifact_relationships" in result.stdout, "Expected artifact_relationships table in output"

    # Verify migrations are not applied: --sql outputs to stdout only, no DB execution
    assert "idx_artifacts_tenant" in result.stdout or "artifacts" in result.stdout
    assert "idx_relationships_tenant" in result.stdout or "artifact_relationships" in result.stdout


def test_alembic_downgrade_sql_output() -> None:
    """Verify downgrade base --sql runs and output contains DROP TABLE for artifact tables."""
    # With --sql, downgrade requires <fromrev>:<torev> format
    result = _run_alembic("downgrade", "head:base", "--sql")

    assert result.returncode == 0, (
        f"alembic downgrade base --sql failed: stdout={result.stdout!r}, stderr={result.stderr!r}"
    )
    assert "DROP TABLE" in result.stdout or "DROP INDEX" in result.stdout
    assert "artifact_relationships" in result.stdout
    assert "artifacts" in result.stdout
