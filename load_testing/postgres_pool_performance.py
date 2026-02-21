"""
Load test: PostgreSQL pool performance.
1000 parallel requests to ArtifactKnowledgeBasePG, pool stats, deadlock detection.
"""
from __future__ import annotations

import argparse
import asyncio
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure src is in path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from load_testing.metrics_collector import percentile
from load_testing.report_generator import (
    ensure_reports_dir,
    generate_plots,
    write_load_test_report_json,
)


async def test_postgres_pool_performance(
    postgres_url: str = "postgresql+asyncpg://vagus:vagus_password@localhost:5432/vagus_db",
    num_requests: int = 1000,
    concurrency: int = 50,
    min_size: int = 2,
    max_size: int = 20,
) -> dict:
    """
    Run num_requests parallel write_artifact calls with semaphore-limited concurrency.

    Returns:
        Dict with total_time_s, requests_per_sec, latency_p50_ms, latency_p99_ms,
        error_count, deadlock_count, pool_size_after, postgres_latencies_ms.
    """
    try:
        from vagus.layer2.memory.artifact_kb_pg import ArtifactKnowledgeBasePG
    except ImportError:
        return {"error": "vagus package not available"}

    result: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario": "postgres_pool_performance",
        "num_requests": num_requests,
        "concurrency": concurrency,
        "latencies_ms": [],
        "total_time_s": None,
        "requests_per_sec": None,
        "latency_p50_ms": None,
        "latency_p99_ms": None,
        "error_count": 0,
        "deadlock_count": 0,
        "pool_size_after": None,
        "postgres_latencies_ms": [],  # for report_generator
    }

    kb = ArtifactKnowledgeBasePG(
        postgres_url,
        min_size=min_size,
        max_size=max_size,
    )

    sem = asyncio.Semaphore(concurrency)
    latencies: list[float] = []
    errors = 0
    deadlocks = 0

    async def do_write(i: int) -> None:
        nonlocal errors, deadlocks
        async with sem:
            t0 = time.perf_counter()
            try:
                plan_id = f"load_test_{i % 100}"
                key = f"key_{uuid.uuid4().hex[:8]}"
                await kb.write_artifact(
                    content=f"Load test content {i}",
                    artifact_type="load_test",
                    source="postgres_pool_performance",
                    tenant_id="default",
                    plan_id=plan_id,
                    key=key,
                )
            except Exception as e:
                errors += 1
                err_str = str(e).lower()
                if "deadlock" in err_str or "could not obtain lock" in err_str:
                    deadlocks += 1
                return
            finally:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                latencies.append(elapsed_ms)

    start = time.perf_counter()
    await asyncio.gather(*[do_write(i) for i in range(num_requests)])
    total_time = time.perf_counter() - start

    await kb.close()

    result["latencies_ms"] = latencies
    result["postgres_latencies_ms"] = latencies
    result["total_time_s"] = round(total_time, 2)
    result["requests_per_sec"] = round(len(latencies) / total_time, 2) if total_time > 0 else 0
    result["latency_p50_ms"] = round(percentile(latencies, 50), 2) if latencies else None
    result["latency_p99_ms"] = round(percentile(latencies, 99), 2) if latencies else None
    result["error_count"] = errors
    result["deadlock_count"] = deadlocks
    result["success_count"] = len(latencies)

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="PostgreSQL pool performance load test")
    parser.add_argument(
        "--postgres-url",
        default="postgresql+asyncpg://vagus:vagus_password@localhost:5432/vagus_db",
    )
    parser.add_argument("--num-requests", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--max-size", type=int, default=20)
    parser.add_argument("--output", default="load_testing/reports")
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()

    report = asyncio.run(test_postgres_pool_performance(
        postgres_url=args.postgres_url,
        num_requests=args.num_requests,
        concurrency=args.concurrency,
        max_size=args.max_size,
    ))

    if "error" in report:
        print(f"Error: {report['error']}")
        return 1

    out = ensure_reports_dir(args.output)
    write_load_test_report_json(report, output_dir=out, prefix="postgres_pool_performance")
    if not args.no_plots:
        generate_plots(report, output_dir=out)

    print(f"Total: {report['total_time_s']}s, RPS: {report['requests_per_sec']}")
    print(f"Latency p50: {report['latency_p50_ms']}ms, p99: {report['latency_p99_ms']}ms")
    print(f"Errors: {report['error_count']}, Deadlocks: {report['deadlock_count']}")
    print(f"Report saved to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
