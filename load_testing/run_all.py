"""
Run all load tests sequentially and generate combined report.
"""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from load_testing.parallel_tasks import run_100_parallel_tasks
from load_testing.redis_streams_latency import measure_redis_streams_latency
from load_testing.postgres_pool_performance import test_postgres_pool_performance
from load_testing.report_generator import (
    ensure_reports_dir,
    generate_plots,
    write_load_test_report_json,
)


async def run_all(
    base_url: str = "http://localhost:8000",
    redis_url: str = "redis://localhost:6379/0",
    postgres_url: str = "postgresql+asyncpg://vagus:vagus_password@localhost:5432/vagus_db",
    num_tasks: int = 100,
    num_events: int = 100,
    num_pg_requests: int = 1000,
    output_dir: str = "load_testing/reports",
    skip_parallel: bool = False,
    skip_redis: bool = False,
    skip_postgres: bool = False,
) -> dict:
    """Run all load tests and return combined report."""
    combined: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario": "run_all",
        "results": {},
        "summary": {},
    }

    out = ensure_reports_dir(output_dir)

    if not skip_parallel:
        print("Running parallel_tasks...")
        try:
            pt = await run_100_parallel_tasks(
                base_url=base_url,
                num_tasks=num_tasks,
                redis_url=redis_url,
            )
            combined["results"]["parallel_tasks"] = pt
            combined["summary"]["parallel_tasks"] = {
                "completed": pt.get("completed", 0),
                "failed": pt.get("failed", 0),
                "duration_p50": pt.get("duration_p50_sec"),
            }
        except Exception as e:
            combined["results"]["parallel_tasks"] = {"error": str(e)}
            combined["summary"]["parallel_tasks"] = {"error": str(e)}
        print("  Done.")

    if not skip_redis:
        print("Running redis_streams_latency...")
        try:
            rs = await measure_redis_streams_latency(
                redis_url=redis_url,
                num_events=num_events,
            )
            combined["results"]["redis_streams"] = rs
            if "error" not in rs:
                combined["summary"]["redis_streams"] = {
                    "publish_p50_ms": rs.get("publish_latency_p50_ms"),
                    "read_latency_ms": rs.get("read_latency_ms"),
                }
            else:
                combined["summary"]["redis_streams"] = {"error": rs["error"]}
        except Exception as e:
            combined["results"]["redis_streams"] = {"error": str(e)}
            combined["summary"]["redis_streams"] = {"error": str(e)}
        print("  Done.")

    if not skip_postgres:
        print("Running postgres_pool_performance...")
        try:
            pg = await test_postgres_pool_performance(
                postgres_url=postgres_url,
                num_requests=num_pg_requests,
            )
            combined["results"]["postgres_pool"] = pg
            if "error" not in pg:
                combined["summary"]["postgres_pool"] = {
                    "rps": pg.get("requests_per_sec"),
                    "latency_p50_ms": pg.get("latency_p50_ms"),
                    "error_count": pg.get("error_count", 0),
                }
            else:
                combined["summary"]["postgres_pool"] = {"error": pg["error"]}
        except Exception as e:
            combined["results"]["postgres_pool"] = {"error": str(e)}
            combined["summary"]["postgres_pool"] = {"error": str(e)}
        print("  Done.")

    write_load_test_report_json(combined, output_dir=out, prefix="run_all")
    for name, data in combined["results"].items():
        if isinstance(data, dict) and "error" not in data:
            generate_plots(data, output_dir=out)

    print(f"\nCombined report saved to {out}")
    return combined


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all load tests")
    parser.add_argument("--url", default="http://localhost:8000")
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument("--postgres-url", default="postgresql+asyncpg://vagus:vagus_password@localhost:5432/vagus_db")
    parser.add_argument("--tasks", type=int, default=100)
    parser.add_argument("--redis-events", type=int, default=100)
    parser.add_argument("--pg-requests", type=int, default=1000)
    parser.add_argument("--output", default="load_testing/reports")
    parser.add_argument("--skip-parallel", action="store_true")
    parser.add_argument("--skip-redis", action="store_true")
    parser.add_argument("--skip-postgres", action="store_true")
    args = parser.parse_args()

    asyncio.run(run_all(
        base_url=args.url,
        redis_url=args.redis_url,
        postgres_url=args.postgres_url,
        num_tasks=args.tasks,
        num_events=args.redis_events,
        num_pg_requests=args.pg_requests,
        output_dir=args.output,
        skip_parallel=args.skip_parallel,
        skip_redis=args.skip_redis,
        skip_postgres=args.skip_postgres,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
