"""
Process memory profiler with lightweight leak detection.
"""

from __future__ import annotations

import asyncio
import gc
import os
import time
from collections import Counter, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from vagus.layer0.logging import get_logger

try:
    import resource

    _RESOURCE_AVAILABLE = True
except ImportError:  # pragma: no cover - platform dependent
    resource = None  # type: ignore[assignment]
    _RESOURCE_AVAILABLE = False

try:
    import psutil

    _PSUTIL_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    psutil = None  # type: ignore[assignment]
    _PSUTIL_AVAILABLE = False


@dataclass(frozen=True)
class MemoryLeakPolicy:
    threshold_mb: float = 100.0
    window_seconds: int = 300


class MemoryProfiler:
    """Runtime memory profiler for admin observability endpoints."""

    def __init__(
        self,
        *,
        leak_policy: Optional[MemoryLeakPolicy] = None,
        history_limit: int = 1024,
    ):
        self.logger = get_logger("monitoring.memory_profiler")
        self.leak_policy = leak_policy or MemoryLeakPolicy()
        self.history_limit = max(32, int(history_limit))
        self._history: deque[dict[str, Any]] = deque(maxlen=self.history_limit)
        self._monitor_task: Optional[asyncio.Task] = None
        self._last_alert_at: float = 0.0
        self._resource_warning_logged = False

    @staticmethod
    def _read_windows_process_memory_mb() -> float:
        """
        Возвращает WorkingSetSize на Windows через WinAPI.
        """
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = PROCESS_MEMORY_COUNTERS()
            counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            process_handle = ctypes.windll.kernel32.GetCurrentProcess()
            success = ctypes.windll.psapi.GetProcessMemoryInfo(
                process_handle,
                ctypes.byref(counters),
                counters.cb,
            )
            if success:
                return float(counters.WorkingSetSize) / 1024.0 / 1024.0
        except Exception:
            return 0.0
        return 0.0

    def _read_process_memory_mb(self) -> float:
        """
        Возвращает RSS процесса в MB.
        """
        if _PSUTIL_AVAILABLE and psutil is not None:
            try:
                process = psutil.Process()
                return float(process.memory_info().rss) / 1024.0 / 1024.0
            except Exception:
                pass

        status_path = "/proc/self/status"
        try:
            with open(status_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("VmRSS:"):
                        parts = line.split()
                        if len(parts) >= 2:
                            kb = float(parts[1])
                            return kb / 1024.0
        except Exception:
            pass

        # Fallback для сред без /proc
        if _RESOURCE_AVAILABLE and resource is not None:
            usage = resource.getrusage(resource.RUSAGE_SELF)
            rss = float(usage.ru_maxrss)
            if rss > 1024 * 1024:
                # bytes-like units
                return rss / 1024.0 / 1024.0
            # KB-like units
            return rss / 1024.0

        if os.name == "nt":
            windows_memory = self._read_windows_process_memory_mb()
            if windows_memory > 0:
                return windows_memory

        if not self._resource_warning_logged:
            self._resource_warning_logged = True
            self.logger.warning(
                "resource module not available on this platform, memory metrics are degraded"
            )
        return 0.0

    def _top_object_types(self, *, limit: int = 10) -> list[dict[str, Any]]:
        try:
            type_counter = Counter(type(obj).__name__ for obj in gc.get_objects())
        except Exception:
            return []
        top = type_counter.most_common(max(1, int(limit)))
        return [{"type": type_name, "count": count} for type_name, count in top]

    def _compute_leak_signal(self, now_monotonic: float, current_mb: float) -> dict[str, Any]:
        window_seconds = int(self.leak_policy.window_seconds)
        threshold_mb = float(self.leak_policy.threshold_mb)
        baseline = None

        for snapshot in self._history:
            snap_ts = float(snapshot.get("monotonic_ts", 0.0))
            if now_monotonic - snap_ts <= window_seconds:
                baseline = snapshot
                break
        if baseline is None and self._history:
            baseline = self._history[0]

        baseline_mb = float(baseline.get("process_memory_mb", current_mb)) if baseline else current_mb
        growth_mb = current_mb - baseline_mb
        leak_detected = growth_mb > threshold_mb
        return {
            "detected": leak_detected,
            "growth_mb": round(growth_mb, 2),
            "threshold_mb": threshold_mb,
            "window_seconds": window_seconds,
            "baseline_memory_mb": round(baseline_mb, 2),
        }

    def collect_snapshot(self) -> dict[str, Any]:
        """
        Собирает текущую snapshot памяти и сохраняет её в историю.
        """
        now_monotonic = time.monotonic()
        now_iso = datetime.now(timezone.utc).isoformat()
        process_memory_mb = self._read_process_memory_mb()
        gc_count = gc.get_count()
        gc_stats = gc.get_stats()
        object_count = len(gc.get_objects())
        leak = self._compute_leak_signal(now_monotonic, process_memory_mb)

        snapshot = {
            "timestamp": now_iso,
            "monotonic_ts": now_monotonic,
            "process_memory_mb": round(process_memory_mb, 2),
            "python_object_count": int(object_count),
            "gc_count": {
                "gen0": int(gc_count[0]) if len(gc_count) > 0 else 0,
                "gen1": int(gc_count[1]) if len(gc_count) > 1 else 0,
                "gen2": int(gc_count[2]) if len(gc_count) > 2 else 0,
            },
            "gc_stats": gc_stats,
            "top_object_types": self._top_object_types(limit=10),
            "leak_signal": leak,
        }
        self._history.append(snapshot)

        # Чтобы не спамить логами, ограничиваем alert-логирование.
        if leak["detected"] and (now_monotonic - self._last_alert_at) >= 30.0:
            self._last_alert_at = now_monotonic
            self.logger.warning(
                "Potential memory leak detected: +%sMB in %ss (threshold=%sMB)",
                leak["growth_mb"],
                leak["window_seconds"],
                leak["threshold_mb"],
            )
        return snapshot

    async def start(self, *, interval_seconds: int = 30) -> None:
        """Запускает регулярный мониторинг памяти."""
        if self._monitor_task is not None and not self._monitor_task.done():
            return

        interval = max(1, int(interval_seconds))

        async def _run() -> None:
            while True:
                self.collect_snapshot()
                await asyncio.sleep(interval)

        self._monitor_task = asyncio.create_task(_run(), name="vagus-memory-profiler")
        self.logger.info("Memory profiler started (interval=%ss)", interval)

    async def stop(self) -> None:
        """Останавливает background мониторинг."""
        if self._monitor_task is None:
            return
        self._monitor_task.cancel()
        await asyncio.gather(self._monitor_task, return_exceptions=True)
        self._monitor_task = None
        self.logger.info("Memory profiler stopped")

    def get_stats(self, *, refresh: bool = True, history_limit: int = 60) -> dict[str, Any]:
        """
        Возвращает последнюю snapshot и историю для анализа тренда.
        """
        if refresh or not self._history:
            current = self.collect_snapshot()
        else:
            current = self._history[-1]

        tail_count = max(1, int(history_limit))
        history_tail = list(self._history)[-tail_count:]
        return {
            "current": current,
            "history": history_tail,
            "history_size": len(self._history),
            "leak_policy": {
                "threshold_mb": self.leak_policy.threshold_mb,
                "window_seconds": self.leak_policy.window_seconds,
            },
            "monitoring_active": self._monitor_task is not None and not self._monitor_task.done(),
        }

