"""
Report generator for load tests: CSV, JSON, and plots.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPORTS_DIR = Path(__file__).parent / "reports"


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def ensure_reports_dir(output_dir: Path | str | None) -> Path:
    """Ensure reports directory exists."""
    path = Path(output_dir) if output_dir else REPORTS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_parallel_tasks_csv(
    tasks: list[dict[str, Any]],
    output_dir: Path | str | None = None,
) -> Path:
    """Write parallel tasks results to CSV."""
    out = ensure_reports_dir(output_dir)
    path = out / f"parallel_tasks_{_timestamp()}.csv"
    columns = ["task_id", "status", "duration_sec", "created_at", "error"]
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        w.writeheader()
        for t in tasks:
            row = {c: t.get(c, "") for c in columns}
            w.writerow(row)
    return path


def write_load_test_report_json(
    report: dict[str, Any],
    output_dir: Path | str | None = None,
    prefix: str = "load_test_report",
) -> Path:
    """Write full load test report to JSON."""
    out = ensure_reports_dir(output_dir)
    path = out / f"{prefix}_{_timestamp()}.json"

    def _serialize(obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, dict):
            return {k: _serialize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [_serialize(x) for x in obj]
        return obj

    path.write_text(
        json.dumps(_serialize(report), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def generate_plots(
    report: dict[str, Any],
    output_dir: Path | str | None = None,
) -> list[Path]:
    """
    Generate performance plots. Uses plotly if available, else matplotlib.
    Returns list of saved file paths.
    """
    out = ensure_reports_dir(output_dir)
    paths: list[Path] = []

    try:
        import plotly.graph_objects as go
        has_plotly = True
    except ImportError:
        has_plotly = False

    if not has_plotly:
        try:
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            has_matplotlib = True
        except ImportError:
            has_matplotlib = False
    else:
        has_matplotlib = False

    if not has_plotly and not has_matplotlib:
        return paths

    # Task duration distribution
    durations = report.get("task_durations_sec") or []
    if durations:
        if has_plotly:
            fig = go.Figure(data=[go.Histogram(x=durations, nbinsx=30)])
            fig.update_layout(
                title="Task Duration Distribution",
                xaxis_title="Duration (sec)",
                yaxis_title="Count",
            )
            p = out / f"task_duration_hist_{_timestamp()}.html"
            fig.write_html(str(p))
            paths.append(p)
        elif has_matplotlib:
            import matplotlib.pyplot as plt
            plt.figure()
            plt.hist(durations, bins=30, edgecolor="black", alpha=0.7)
            plt.xlabel("Duration (sec)")
            plt.ylabel("Count")
            plt.title("Task Duration Distribution")
            p = out / f"task_duration_hist_{_timestamp()}.png"
            plt.savefig(p)
            plt.close()
            paths.append(p)

    # Redis latency (if present)
    publish_latencies = report.get("redis_publish_latencies_ms") or []
    if publish_latencies:
        if has_plotly:
            fig = go.Figure(data=[go.Box(y=publish_latencies, name="Publish latency (ms)")])
            fig.update_layout(title="Redis Streams Publish Latency")
            p = out / f"redis_latency_{_timestamp()}.html"
            fig.write_html(str(p))
            paths.append(p)
        elif has_matplotlib:
            import matplotlib.pyplot as plt
            plt.figure()
            plt.boxplot(publish_latencies)
            plt.ylabel("ms")
            plt.title("Redis Streams Publish Latency")
            p = out / f"redis_latency_{_timestamp()}.png"
            plt.savefig(p)
            plt.close()
            paths.append(p)

    # PostgreSQL latency (if present)
    pg_latencies = report.get("postgres_latencies_ms") or []
    if pg_latencies:
        if has_plotly:
            fig = go.Figure(data=[go.Histogram(x=pg_latencies, nbinsx=30)])
            fig.update_layout(
                title="PostgreSQL Request Latency Distribution",
                xaxis_title="Latency (ms)",
                yaxis_title="Count",
            )
            p = out / f"postgres_latency_{_timestamp()}.html"
            fig.write_html(str(p))
            paths.append(p)
        elif has_matplotlib:
            import matplotlib.pyplot as plt
            plt.figure()
            plt.hist(pg_latencies, bins=30, edgecolor="black", alpha=0.7)
            plt.xlabel("Latency (ms)")
            plt.ylabel("Count")
            plt.title("PostgreSQL Request Latency Distribution")
            p = out / f"postgres_latency_{_timestamp()}.png"
            plt.savefig(p)
            plt.close()
            paths.append(p)

    return paths
