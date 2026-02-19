"""Unit-тесты стратегий балансировки."""
import pytest
from vagus.layer1.balancing import CostStrategy, HybridStrategy, LatencyStrategy


def test_cost_strategy():
    s = CostStrategy()
    providers = {
        "a": {"cost": 0.1},
        "b": {"cost": 0.05},
        "c": {"cost": 0.2},
    }
    assert s.select_provider(providers, {}) == "b"


def test_hybrid_strategy():
    s = HybridStrategy()
    providers = {
        "a": {"cost": 0.1, "latency": 100, "quality": 0.9},
        "b": {"cost": 0.05, "latency": 50, "quality": 0.7},
    }
    pid = s.select_provider(providers, {"priority": "normal"})
    assert pid in ("a", "b")


def test_latency_strategy():
    s = LatencyStrategy()
    providers = {
        "a": {"e2e_ms": 200},
        "b": {"e2e_ms": 50},
    }
    assert s.select_provider(providers, {}) == "b"
