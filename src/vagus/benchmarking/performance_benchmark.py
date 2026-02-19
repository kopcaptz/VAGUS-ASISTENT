"""
Performance benchmarking scenarios for key subsystems.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Callable, Optional

from vagus.layer0.logging import get_logger


@dataclass(frozen=True)
class BenchmarkScenarioResult:
    name: str
    iterations: int
    p50_ms: float
    p95_ms: float
    avg_ms: float
    min_ms: float
    max_ms: float
    metadata: dict[str, Any]


class PerformanceBenchmarkRunner:
    """Runs benchmark scenarios and persists results for trend analysis."""

    def __init__(self, *, output_dir: str = "benchmark_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.logger = get_logger("benchmarking.performance")

    @staticmethod
    def _quantile(values: list[float], quantile: float) -> float:
        if not values:
            return 0.0
        sorted_values = sorted(values)
        idx = min(len(sorted_values) - 1, max(0, int(round((len(sorted_values) - 1) * quantile))))
        return float(sorted_values[idx])

    def _summarize(self, name: str, samples_ms: list[float], *, metadata: Optional[dict[str, Any]] = None):
        if not samples_ms:
            samples_ms = [0.0]
        return BenchmarkScenarioResult(
            name=name,
            iterations=len(samples_ms),
            p50_ms=round(self._quantile(samples_ms, 0.50), 3),
            p95_ms=round(self._quantile(samples_ms, 0.95), 3),
            avg_ms=round(mean(samples_ms), 3),
            min_ms=round(min(samples_ms), 3),
            max_ms=round(max(samples_ms), 3),
            metadata=metadata or {},
        )

    async def benchmark_provider_latency(
        self,
        *,
        provider: Any,
        prompt: str,
        iterations: int = 5,
    ) -> BenchmarkScenarioResult:
        samples = []
        for _ in range(max(1, int(iterations))):
            started = time.perf_counter()
            gen = provider.request(prompt=prompt, stream=False)
            async for chunk in gen:
                if isinstance(chunk, dict) and chunk.get("done"):
                    break
            samples.append((time.perf_counter() - started) * 1000.0)
        return self._summarize(
            "provider_latency",
            samples,
            metadata={"provider": getattr(provider, "name", "unknown"), "model": getattr(provider, "model", "")},
        )

    async def benchmark_agent_execution(
        self,
        *,
        orchestrator: Any,
        task_type: str = "default",
        iterations: int = 5,
    ) -> BenchmarkScenarioResult:
        samples = []
        for idx in range(max(1, int(iterations))):
            started = time.perf_counter()
            await orchestrator.execute_task(
                task_id=f"bench-{task_type}-{idx}",
                prompt=f"Benchmark task #{idx}",
                task_type=task_type,
            )
            samples.append((time.perf_counter() - started) * 1000.0)
        return self._summarize(
            "agent_execution",
            samples,
            metadata={"task_type": task_type},
        )

    async def benchmark_cache_hit_miss(
        self,
        *,
        cache_service: Any,
        iterations: int = 100,
    ) -> BenchmarkScenarioResult:
        hit_samples: list[float] = []
        miss_samples: list[float] = []
        sample_count = max(1, int(iterations))

        for idx in range(sample_count):
            key = f"bench-cache-{idx}"
            await cache_service.set(key, {"value": idx})
            started_hit = time.perf_counter()
            await cache_service.get(key)
            hit_samples.append((time.perf_counter() - started_hit) * 1000.0)

            started_miss = time.perf_counter()
            await cache_service.get(f"{key}-miss")
            miss_samples.append((time.perf_counter() - started_miss) * 1000.0)

        combined = hit_samples + miss_samples
        return self._summarize(
            "cache_hit_miss",
            combined,
            metadata={
                "hit_avg_ms": round(mean(hit_samples), 3),
                "miss_avg_ms": round(mean(miss_samples), 3),
            },
        )

    def benchmark_database_queries(
        self,
        *,
        metrics_storage: Any,
        iterations: int = 100,
    ) -> BenchmarkScenarioResult:
        samples: list[float] = []
        sample_count = max(1, int(iterations))
        for idx in range(sample_count):
            started = time.perf_counter()
            metrics_storage.get_recent_requests(limit=10)
            metrics_storage.get_top_providers(limit=5)
            metrics_storage.get_stats(retention_days=30)
            samples.append((time.perf_counter() - started) * 1000.0)
        return self._summarize("database_queries", samples, metadata={"query_bundle_count": 3})

    def save_results(
        self,
        *,
        suite_name: str,
        scenario_results: list[BenchmarkScenarioResult],
        extra: Optional[dict[str, Any]] = None,
    ) -> Path:
        payload = {
            "suite_name": suite_name,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "scenarios": [result.__dict__ for result in scenario_results],
            "extra": extra or {},
        }
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        output_path = self.output_dir / f"{suite_name}_{ts}.json"
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.logger.info("Benchmark results saved to %s", output_path)
        return output_path

    @staticmethod
    def compare_results(current: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
        baseline_by_name = {
            item.get("name"): item for item in baseline.get("scenarios", []) if isinstance(item, dict)
        }
        comparison: dict[str, Any] = {}
        for item in current.get("scenarios", []):
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if name not in baseline_by_name:
                continue
            baseline_item = baseline_by_name[name]
            current_avg = float(item.get("avg_ms", 0.0))
            baseline_avg = float(baseline_item.get("avg_ms", 0.0))
            delta = current_avg - baseline_avg
            comparison[str(name)] = {
                "current_avg_ms": round(current_avg, 3),
                "baseline_avg_ms": round(baseline_avg, 3),
                "delta_ms": round(delta, 3),
                "regression": delta > 0.0,
            }
        return comparison


def _fingerprint_sources(source_paths: list[str]) -> str:
    hasher = hashlib.sha256()
    for source_path in sorted(source_paths):
        path = Path(source_path)
        if not path.exists():
            continue
        if path.is_file():
            stat = path.stat()
            hasher.update(f"{path}:{stat.st_mtime_ns}:{stat.st_size}".encode("utf-8"))
        elif path.is_dir():
            for child in sorted(path.rglob("*.py")):
                stat = child.stat()
                hasher.update(f"{child}:{stat.st_mtime_ns}:{stat.st_size}".encode("utf-8"))
    return hasher.hexdigest()


async def auto_run_if_sources_changed(
    *,
    source_paths: list[str],
    state_file: str,
    benchmark_coro: Callable[[], Any],
) -> dict[str, Any]:
    """
    Автоматически запускает benchmark при изменении исходников.
    """
    state_path = Path(state_file)
    current_fingerprint = _fingerprint_sources(source_paths)
    previous_fingerprint = ""
    if state_path.exists():
        try:
            previous_fingerprint = json.loads(state_path.read_text(encoding="utf-8")).get("fingerprint", "")
        except Exception:
            previous_fingerprint = ""

    if current_fingerprint == previous_fingerprint:
        return {"executed": False, "reason": "no_source_changes"}

    result = benchmark_coro()
    if asyncio.iscoroutine(result):
        result = await result

    state_payload = {
        "fingerprint": current_fingerprint,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"executed": True, "result": result}

