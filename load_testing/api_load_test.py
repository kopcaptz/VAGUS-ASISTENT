"""
Locust-based HTTP load test scenarios for Vagus API.

Usage (headless example):
  locust -f load_testing/api_load_test.py --host http://localhost:8000 \
      --users 100 --spawn-rate 20 --run-time 5m --headless \
      --csv=load_testing/reports/api
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_USERS = 100
DEFAULT_TARGET_RPS = 1000

try:
    from locust import HttpUser, between, task, events  # type: ignore

    LOCUST_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    HttpUser = object
    LOCUST_AVAILABLE = False


def _build_report_payload(*, users: int, target_rps: int, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario": "api_load_test",
        "users": int(users),
        "target_rps": int(target_rps),
        "extra": extra or {},
    }


def write_report(*, output_dir: str, payload: dict[str, Any]) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    output_file = path / "api_load_test_report.json"
    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_file


if LOCUST_AVAILABLE:
    class VagusApiUser(HttpUser):
        wait_time = between(0.05, 0.2)

        @task(3)
        def health(self):
            self.client.get("/health", name="GET /health")

        @task(2)
        def metrics(self):
            self.client.get("/metrics", name="GET /metrics")

        @task(1)
        def status(self):
            self.client.get("/api/v1/status", name="GET /api/v1/status")


    @events.test_stop.add_listener
    def _on_test_stop(environment, **kwargs):  # pragma: no cover - integration with locust runtime
        users = getattr(environment.runner, "user_count", 0) if environment.runner else 0
        payload = _build_report_payload(
            users=users,
            target_rps=DEFAULT_TARGET_RPS,
            extra={"state": "finished"},
        )
        write_report(output_dir="load_testing/reports", payload=payload)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate API load-test report metadata")
    parser.add_argument("--users", type=int, default=DEFAULT_USERS)
    parser.add_argument("--target-rps", type=int, default=DEFAULT_TARGET_RPS)
    parser.add_argument("--output-dir", default="load_testing/reports")
    args = parser.parse_args()

    payload = _build_report_payload(
        users=args.users,
        target_rps=args.target_rps,
        extra={
            "locust_available": LOCUST_AVAILABLE,
            "note": "Run with Locust for real load execution",
        },
    )
    output_file = write_report(output_dir=args.output_dir, payload=payload)
    print(f"API load report saved: {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

