"""
Load test: Redis Streams latency.
Measures publish_event latency, consumer group read latency, DLQ size.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from load_testing.metrics_collector import percentile
from load_testing.report_generator import (
    ensure_reports_dir,
    generate_plots,
    write_load_test_report_json,
)


async def measure_redis_streams_latency(
    redis_url: str = "redis://localhost:6379/0",
    stream_name: str = "vagus:events:stream",
    num_events: int = 100,
) -> dict:
    """
    Measure Redis Streams publish latency, read latency, DLQ count, stream length.

    Returns:
        Dict with publish_latency_p50_ms, publish_latency_p99_ms, read_latency_ms,
        dlq_count, stream_length, publish_latencies list.
    """
    try:
        import redis.asyncio as redis
    except ImportError:
        return {"error": "redis package not installed"}

    result: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario": "redis_streams_latency",
        "redis_url": redis_url[:50] + "..." if len(redis_url) > 50 else redis_url,
        "stream_name": stream_name,
        "num_events": num_events,
        "publish_latencies_ms": [],
        "publish_latency_p50_ms": None,
        "publish_latency_p99_ms": None,
        "read_latency_ms": None,
        "dlq_count": 0,
        "stream_length_before": None,
        "stream_length_after": None,
    }

    rd = redis.from_url(redis_url, decode_responses=True)
    dlq_name = f"{stream_name}_dlq"
    test_group = "load_test_group"
    test_consumer = "load_test_consumer"

    try:
        # Stream length before
        result["stream_length_before"] = await rd.xlen(stream_name)
        result["dlq_count"] = await rd.xlen(dlq_name)

        # Create consumer group if not exists (use 0 to read from start for test)
        try:
            await rd.xgroup_create(stream_name, test_group, id="0", mkstream=True)
        except Exception as e:
            if "BUSYGROUP" not in str(e) and "already exists" not in str(e).lower():
                result["group_error"] = str(e)

        # Publish N events and measure latency
        publish_times_ms: list[float] = []
        for i in range(num_events):
            payload = {"event": "load_test", "task_id": f"lt_{i}", "ts": time.time()}
            fields = {"event": "load_test", "task_id": f"lt_{i}", "data": json.dumps(payload), "ts": str(time.time())}
            t0 = time.perf_counter()
            await rd.xadd(stream_name, fields, id="*", maxlen=10000, approximate=True)
            t1 = time.perf_counter()
            publish_times_ms.append((t1 - t0) * 1000)

        result["publish_latencies_ms"] = publish_times_ms
        result["publish_latency_p50_ms"] = round(percentile(publish_times_ms, 50), 2)
        result["publish_latency_p99_ms"] = round(percentile(publish_times_ms, 99), 2)

        # Consumer group read: measure time to read N messages
        read_count = 0
        t0 = time.perf_counter()
        while read_count < num_events:
            messages = await rd.xreadgroup(
                groupname=test_group,
                consumername=test_consumer,
                streams={stream_name: ">"},
                count=min(100, num_events - read_count),
                block=2000,
            )
            if not messages:
                break
            for _, msgs in messages:
                read_count += len(msgs)
                for msg_id, _ in msgs:
                    await rd.xack(stream_name, test_group, msg_id)
        t1 = time.perf_counter()
        result["read_latency_ms"] = round((t1 - t0) * 1000, 2)
        result["messages_read"] = read_count

        result["stream_length_after"] = await rd.xlen(stream_name)
        result["dlq_count"] = await rd.xlen(dlq_name)
        result["redis_publish_latencies_ms"] = publish_times_ms  # for report_generator

        # Cleanup consumer group (optional - leave for debugging)
        # await rd.xgroup_destroy(stream_name, test_group)
    finally:
        await rd.aclose()

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Redis Streams latency load test")
    parser.add_argument("--redis-url", default="redis://localhost:6379/0")
    parser.add_argument("--stream", default="vagus:events:stream")
    parser.add_argument("--num-events", type=int, default=100)
    parser.add_argument("--output", default="load_testing/reports")
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()

    report = asyncio.run(measure_redis_streams_latency(
        redis_url=args.redis_url,
        stream_name=args.stream,
        num_events=args.num_events,
    ))

    if "error" in report:
        print(f"Error: {report['error']}")
        return 1

    out = ensure_reports_dir(args.output)
    write_load_test_report_json(report, output_dir=out, prefix="redis_streams_latency")
    if not args.no_plots:
        generate_plots(report, output_dir=out)

    print(f"Publish p50: {report['publish_latency_p50_ms']}ms, p99: {report['publish_latency_p99_ms']}ms")
    print(f"Read latency: {report['read_latency_ms']}ms")
    print(f"Stream length: {report['stream_length_after']}, DLQ: {report['dlq_count']}")
    print(f"Report saved to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
