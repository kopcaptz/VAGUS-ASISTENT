"""Tests for load testing helper scripts."""

import json
import sys

import pytest

from load_testing import api_load_test, cli_load_test, websocket_load_test


def test_api_load_test_report_generation(tmp_path):
    payload = {
        "scenario": "api_load_test",
        "users": 100,
        "target_rps": 1000,
    }
    report_path = api_load_test.write_report(output_dir=str(tmp_path), payload=payload)
    assert report_path.exists()
    parsed = json.loads(report_path.read_text(encoding="utf-8"))
    assert parsed["scenario"] == "api_load_test"


@pytest.mark.asyncio
async def test_websocket_load_test_runner_returns_summary():
    summary = await websocket_load_test.run_load(
        uri="ws://localhost:8000/api/v1/tasks/ws/test",
        concurrent_users=2,
        duration_seconds=1,
    )
    assert summary["scenario"] == "websocket_long_running_connections"
    assert summary["concurrent_users"] == 2
    assert "success_count" in summary


@pytest.mark.asyncio
async def test_cli_load_test_runner_returns_summary():
    summary = await cli_load_test.run_load(
        command=f"{sys.executable} -c \"print('ok')\"",
        concurrent_users=2,
        requests_per_user=1,
    )
    assert summary["scenario"] == "cli_load_test"
    assert summary["total_requests"] == 2
    assert summary["success_count"] >= 1
