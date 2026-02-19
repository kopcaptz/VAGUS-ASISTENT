"""
WebSocket load testing helper.

Scenario:
  - Long-running WS connections
  - Up to 100 concurrent users
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import websockets  # type: ignore

    WEBSOCKETS_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency
    websockets = None
    WEBSOCKETS_AVAILABLE = False


def write_report(*, output_dir: str, payload: dict[str, Any]) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    report_path = path / "websocket_load_test_report.json"
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_path


async def _run_one_connection(uri: str, duration_seconds: int) -> dict[str, Any]:
    started = time.perf_counter()
    if not WEBSOCKETS_AVAILABLE:
        await asyncio.sleep(0.001)
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return {
            "connected": False,
            "reason": "websockets_package_not_installed",
            "elapsed_ms": round(elapsed_ms, 2),
        }

    try:
        async with websockets.connect(uri) as ws:  # type: ignore[attr-defined]
            end_ts = time.perf_counter() + max(1, duration_seconds)
            while time.perf_counter() < end_ts:
                await ws.send("ping")
                await asyncio.sleep(0.5)
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            return {
                "connected": True,
                "duration_seconds": duration_seconds,
                "elapsed_ms": round(elapsed_ms, 2),
            }
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return {
            "connected": False,
            "reason": str(exc),
            "elapsed_ms": round(elapsed_ms, 2),
        }


async def run_load(
    *,
    uri: str,
    concurrent_users: int = 100,
    duration_seconds: int = 30,
) -> dict[str, Any]:
    tasks = [
        asyncio.create_task(_run_one_connection(uri, duration_seconds))
        for _ in range(max(1, int(concurrent_users)))
    ]
    results = await asyncio.gather(*tasks)
    success_count = sum(1 for item in results if item.get("connected") is True)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario": "websocket_long_running_connections",
        "uri": uri,
        "concurrent_users": int(concurrent_users),
        "duration_seconds": int(duration_seconds),
        "success_count": int(success_count),
        "failure_count": int(len(results) - success_count),
        "websockets_available": WEBSOCKETS_AVAILABLE,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="WebSocket load test")
    parser.add_argument("--uri", default="ws://localhost:8000/api/v1/tasks/ws/test")
    parser.add_argument("--concurrent-users", type=int, default=100)
    parser.add_argument("--duration-seconds", type=int, default=30)
    parser.add_argument("--output-dir", default="load_testing/reports")
    args = parser.parse_args()

    result = asyncio.run(
        run_load(
            uri=args.uri,
            concurrent_users=args.concurrent_users,
            duration_seconds=args.duration_seconds,
        )
    )
    output_file = write_report(output_dir=args.output_dir, payload=result)
    print(f"WebSocket load report saved: {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

