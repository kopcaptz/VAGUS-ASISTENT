"""
CLI load testing helper.

Runs a command concurrently and produces a JSON report.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def write_report(*, output_dir: str, payload: dict[str, Any]) -> Path:
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)
    output_file = path / "cli_load_test_report.json"
    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_file


async def _run_command(command: str) -> dict[str, Any]:
    started = time.perf_counter()
    proc = await asyncio.create_subprocess_exec(
        *shlex.split(command),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await proc.communicate()
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {
        "return_code": int(proc.returncode or 0),
        "elapsed_ms": round(elapsed_ms, 2),
        "stdout_size": len(stdout or b""),
        "stderr_size": len(stderr or b""),
    }


async def run_load(
    *,
    command: str,
    concurrent_users: int = 100,
    requests_per_user: int = 10,
) -> dict[str, Any]:
    total_runs = max(1, int(concurrent_users)) * max(1, int(requests_per_user))
    semaphore = asyncio.Semaphore(max(1, int(concurrent_users)))

    async def _run_one() -> dict[str, Any]:
        async with semaphore:
            return await _run_command(command)

    tasks = [asyncio.create_task(_run_one()) for _ in range(total_runs)]
    results = await asyncio.gather(*tasks)

    success_count = sum(1 for item in results if item["return_code"] == 0)
    elapsed_values = [float(item["elapsed_ms"]) for item in results]
    avg_elapsed = sum(elapsed_values) / len(elapsed_values)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario": "cli_load_test",
        "command": command,
        "concurrent_users": int(concurrent_users),
        "requests_per_user": int(requests_per_user),
        "total_requests": int(total_runs),
        "success_count": int(success_count),
        "failure_count": int(total_runs - success_count),
        "avg_elapsed_ms": round(avg_elapsed, 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="CLI load test")
    parser.add_argument("--command", default="python3 -m vagus --help")
    parser.add_argument("--concurrent-users", type=int, default=100)
    parser.add_argument("--requests-per-user", type=int, default=10)
    parser.add_argument("--output-dir", default="load_testing/reports")
    args = parser.parse_args()

    payload = asyncio.run(
        run_load(
            command=args.command,
            concurrent_users=args.concurrent_users,
            requests_per_user=args.requests_per_user,
        )
    )
    output_file = write_report(output_dir=args.output_dir, payload=payload)
    print(f"CLI load report saved: {output_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

