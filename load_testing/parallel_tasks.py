"""
Load test: 100 parallel tasks via API.
Measures task duration, success rate, Synaptic buffering, Redis Streams latency.
"""
from __future__ import annotations

import argparse
import asyncio
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from load_testing.metrics_collector import collect_metrics, percentile
from load_testing.report_generator import (
    ensure_reports_dir,
    generate_plots,
    write_load_test_report_json,
    write_parallel_tasks_csv,
)


async def get_token(
    base_url: str,
    username: str = "admin",
    password: str = "testpassword",
) -> str:
    """Obtain JWT from /api/v1/auth/token."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{base_url.rstrip('/')}/api/v1/auth/token",
            json={"username": username, "password": password},
        )
        r.raise_for_status()
        data = r.json()
        return data["access_token"]


async def create_task(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    prompt: str,
    task_type: str = "default",
) -> dict:
    """Create task via POST /api/v1/tasks. Returns {task_id, status, created_at}."""
    r = await client.post(
        f"{base_url.rstrip('/')}/api/v1/tasks",
        headers={"Authorization": f"Bearer {token}"},
        json={"prompt": prompt, "task_type": task_type},
    )
    r.raise_for_status()
    data = r.json()
    return {
        "task_id": data["task_id"],
        "status": data.get("status", "pending"),
        "created_at": data.get("created_at", datetime.now(timezone.utc).isoformat()),
    }


async def poll_task_status(
    client: httpx.AsyncClient,
    base_url: str,
    token: str,
    task_id: str,
) -> dict:
    """Get task status via GET /api/v1/tasks/{id}."""
    r = await client.get(
        f"{base_url.rstrip('/')}/api/v1/tasks/{task_id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    r.raise_for_status()
    return r.json()


async def run_100_parallel_tasks(
    base_url: str = "http://localhost:8000",
    num_tasks: int = 100,
    auth: tuple[str, str] = ("admin", "testpassword"),
    poll_interval: float = 0.5,
    timeout_sec: float = 300,
    redis_url: str | None = None,
) -> dict:
    """
    Create num_tasks in parallel, poll until completed, collect metrics.

    Returns:
        Dict with task results, durations, metrics, monitoring data.
    """
    token = await get_token(base_url, auth[0], auth[1])
    headers = {"Authorization": f"Bearer {token}"}
    base = base_url.rstrip("/")

    # Create tasks in parallel
    created: list[dict] = []
    async with httpx.AsyncClient(timeout=30.0) as client:
        create_tasks = [
            create_task(client, base_url, token, f"Load test task {i}", "default")
            for i in range(num_tasks)
        ]
        results = await asyncio.gather(*create_tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                created.append({
                    "task_id": f"error_{i}",
                    "status": "failed",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "error": str(r),
                    "duration_sec": None,
                })
            else:
                created.append({
                    **r,
                    "error": None,
                    "duration_sec": None,
                })

    # Poll until all completed or timeout
    task_ids = [c["task_id"] for c in created if not c["task_id"].startswith("error_")]
    created_ts = {c["task_id"]: c["created_at"] for c in created}
    finished: dict[str, dict] = {}
    start_time = time.perf_counter()

    async with httpx.AsyncClient(timeout=10.0) as client:
        while task_ids and (time.perf_counter() - start_time) < timeout_sec:
            await asyncio.sleep(poll_interval)
            pending = [t for t in task_ids if t not in finished]
            if not pending:
                break

            tasks_to_poll = pending[:min(50, len(pending))]
            coros = [
                poll_task_status(client, base_url, token, tid)
                for tid in tasks_to_poll
            ]
            statuses = await asyncio.gather(*coros, return_exceptions=True)
            now = datetime.now(timezone.utc)
            for tid, resp in zip(tasks_to_poll, statuses):
                if isinstance(resp, Exception):
                    continue
                st = str(resp.get("status", "")).lower()
                if st in ("completed", "failed"):
                    created_at = created_ts.get(tid)
                    try:
                        from datetime import datetime as dt
                        if isinstance(created_at, str):
                            ct = dt.fromisoformat(created_at.replace("Z", "+00:00"))
                        else:
                            ct = created_at
                        delta = (now - ct).total_seconds()
                    except Exception:
                        delta = None
                    finished[tid] = {
                        "task_id": tid,
                        "status": st,
                        "error": resp.get("error"),
                        "duration_sec": delta,
                    }
                    task_ids = [t for t in task_ids if t != tid]

    # Merge results
    for c in created:
        tid = c["task_id"]
        if tid in finished:
            c["status"] = finished[tid]["status"]
            c["error"] = finished[tid].get("error")
            c["duration_sec"] = finished[tid].get("duration_sec")

    durations = [c["duration_sec"] for c in created if c.get("duration_sec") is not None]
    completed = sum(1 for c in created if str(c.get("status")).lower() == "completed")
    failed = sum(1 for c in created if str(c.get("status")).lower() == "failed")

    # Collect monitoring metrics
    metrics = await collect_metrics(base_url, redis_url=redis_url, token=token)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario": "parallel_tasks",
        "num_tasks": num_tasks,
        "completed": completed,
        "failed": failed,
        "timeout": num_tasks - completed - failed,
        "task_durations_sec": durations,
        "duration_p50_sec": percentile(durations, 50) if durations else None,
        "duration_p99_sec": percentile(durations, 99) if durations else None,
        "monitoring": metrics,
        "tasks": created,
    }

    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Load test: parallel tasks via API")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    parser.add_argument("--tasks", type=int, default=100, help="Number of parallel tasks")
    parser.add_argument("--output", default="load_testing/reports", help="Output directory")
    parser.add_argument("--username", default="admin")
    parser.add_argument("--password", default="testpassword")
    parser.add_argument("--redis-url", default=None, help="Redis URL for stream length")
    parser.add_argument("--no-plots", action="store_true", help="Skip plot generation")
    args = parser.parse_args()

    report = asyncio.run(run_100_parallel_tasks(
        base_url=args.url,
        num_tasks=args.tasks,
        auth=(args.username, args.password),
        redis_url=args.redis_url,
    ))

    out = ensure_reports_dir(args.output)
    write_parallel_tasks_csv(report.get("tasks", []), output_dir=out)
    write_load_test_report_json(report, output_dir=out, prefix="parallel_tasks")
    if not args.no_plots:
        generate_plots(report, output_dir=out)

    print(f"Completed: {report['completed']}, Failed: {report['failed']}")
    print(f"Duration p50: {report.get('duration_p50_sec')}s, p99: {report.get('duration_p99_sec')}s")
    print(f"Reports saved to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
