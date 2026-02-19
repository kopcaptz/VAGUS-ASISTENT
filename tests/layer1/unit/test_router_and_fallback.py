"""Unit-тесты router/fallback/strategy компонентов Layer 1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from vagus.layer0.config import ConfigManager
from vagus.layer1.balancing import QualityStrategy, StrategyManager
from vagus.layer1.fallback.fallback_chain import FallbackChain
from vagus.layer1.fallback.fallback_handler import FallbackHandler
from vagus.layer1.fallback.retry_manager import RetryManager
from vagus.layer1.router.llm_router import LLMRouter
from vagus.layer1.router.request_handler import RequestHandler
from vagus.layer1.router.response_builder import ResponseBuilder
from vagus.layer1.router.router_manager import RouterManager


class DummyProvider:
    """Минимальный провайдер для тестов маршрутизации."""

    def __init__(
        self,
        name: str,
        *,
        model: str = "dummy-model",
        available: bool = True,
        fail: bool = False,
        chunks: list[dict[str, Any]] | None = None,
        cost: float = 0.01,
    ):
        self.name = name
        self.model = model
        self._available = available
        self._fail = fail
        self._chunks = chunks or [{"content": "ok", "done": True}]
        self._cost = cost

    def is_available(self) -> bool:
        return self._available

    async def request(self, prompt: str, stream: bool = False, **kwargs):
        if self._fail:
            raise RuntimeError(f"{self.name} failed")
        for chunk in self._chunks:
            yield chunk

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return self._cost


@dataclass
class AvailabilityProvider:
    """Обёртка для provider_getter в FallbackHandler тестах."""

    available: bool = True

    def is_available(self) -> bool:
        return self.available


@pytest.mark.asyncio
async def test_request_handler_and_response_builder():
    handler = RequestHandler()
    req = handler.parse(
        "  hello  ",
        temperature=5.0,
        max_tokens=500000,
        priority="unexpected",
        metadata={"x": 1},
    )
    assert req.prompt == "hello"
    assert req.temperature == 2
    assert req.max_tokens == 100000
    assert req.priority == "normal"
    assert req.metadata == {"x": 1}

    with pytest.raises(ValueError):
        handler.parse("")

    async def _gen():
        yield {"content": "A", "done": False}
        yield {"content": "B", "done": True, "provider": "stub", "model": "m"}

    content, meta = await ResponseBuilder.collect_stream(_gen())
    assert content == "AB"
    assert meta["provider"] == "stub"
    assert ResponseBuilder.build_chunk("x", done=True)["done"] is True


def test_quality_strategy_and_strategy_manager():
    quality = QualityStrategy()
    assert quality.select_provider({"a": {"quality": 0.1}, "b": {"quality": 0.9}}, {}) == "b"
    with pytest.raises(ValueError):
        quality.select_provider({}, {})

    manager = StrategyManager()
    assert {"cost", "latency", "quality", "hybrid"} <= set(manager.list_strategies())
    manager.set_default("cost")
    assert manager.get_strategy().__class__.__name__ == "CostStrategy"
    with pytest.raises(KeyError):
        manager.set_default("unknown")


@pytest.mark.asyncio
async def test_retry_manager_retries_then_success(monkeypatch):
    import vagus.layer1.fallback.retry_manager as retry_module

    attempts = {"n": 0}

    async def _fake_sleep(_seconds: float):
        return None

    async def _op():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise ValueError("temporary")
        return "ok"

    monkeypatch.setattr(retry_module.asyncio, "sleep", _fake_sleep)
    rm = RetryManager(max_retries=3, base_delay=0.01)
    result = await rm.execute_with_retry(_op)
    assert result == "ok"
    assert attempts["n"] == 3


@pytest.mark.asyncio
async def test_retry_manager_raises_after_exhaust(monkeypatch):
    import vagus.layer1.fallback.retry_manager as retry_module

    async def _fake_sleep(_seconds: float):
        return None

    async def _op():
        raise RuntimeError("boom")

    monkeypatch.setattr(retry_module.asyncio, "sleep", _fake_sleep)
    rm = RetryManager(max_retries=2, base_delay=0.01)
    with pytest.raises(RuntimeError):
        await rm.execute_with_retry(_op)


@pytest.mark.asyncio
async def test_fallback_handler_switches_provider_on_failure():
    handler = FallbackHandler(max_retries=1, base_delay=0.0)
    providers = {"p1": AvailabilityProvider(True), "p2": AvailabilityProvider(True)}

    async def request_func(provider_id: str):
        if provider_id == "p1":
            raise RuntimeError("p1 error")
        return f"ok:{provider_id}"

    result, provider_id = await handler.execute(
        provider_ids=["p1", "p2"],
        request_func=request_func,
        provider_getter=lambda pid: providers[pid],
    )
    assert result == "ok:p2"
    assert provider_id == "p2"


@pytest.mark.asyncio
async def test_fallback_handler_raises_when_all_unavailable():
    handler = FallbackHandler(max_retries=1, base_delay=0.0)
    providers = {"p1": AvailabilityProvider(False)}

    async def request_func(provider_id: str):
        return f"ok:{provider_id}"

    with pytest.raises(RuntimeError):
        await handler.execute(
            provider_ids=["p1"],
            request_func=request_func,
            provider_getter=lambda pid: providers[pid],
        )


@pytest.mark.asyncio
async def test_llm_router_initialize_accepts_app_config(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-deepseek")

    config = ConfigManager(
        config_path="configs/vagus.yaml.example",
        enable_hot_reload=False,
    ).get_config()
    router = LLMRouter(enable_cache=False, enable_budgeting=False, enable_monitoring=False)
    await router.initialize(config)

    assert router._initialized is True
    assert {"openai", "anthropic", "deepseek"} <= set(router._providers.keys())


@pytest.mark.asyncio
async def test_llm_router_cache_hit_short_circuit():
    router = LLMRouter(enable_cache=True, enable_budgeting=False, enable_monitoring=False)
    await router.cache.set("cached prompt", "cached answer", model="default", priority="normal")

    chunks = [c async for c in router.route_request("cached prompt", stream=True)]
    assert chunks[-1]["done"] is True
    assert "cached answer" in chunks[-1]["content"]


@pytest.mark.asyncio
async def test_llm_router_fallback_success_and_stats():
    router = LLMRouter(enable_cache=True, enable_budgeting=False, enable_monitoring=False)
    router._providers = {
        "p1": DummyProvider("p1", fail=True),
        "p2": DummyProvider(
            "p2",
            chunks=[
                {"content": "hello ", "done": False},
                {"content": "world", "done": True},
            ],
            cost=0.123,
        ),
    }
    router._fallback_chain = FallbackChain(provider_ids=["p1", "p2"])

    class _PickP1:
        def select_provider(self, providers: dict[str, Any], request_context: dict[str, Any]) -> str:
            return "p1"

    router.strategy_manager.get_strategy = lambda name=None: _PickP1()  # type: ignore[assignment]

    chunks = [c async for c in router.route_request("prompt-1", stream=True)]
    content = "".join(c.get("content", "") for c in chunks)
    assert content == "hello world"

    stats = router.get_stats()
    assert stats["requests"] == 1
    assert stats["total_cost"] > 0

    cached = await router.cache.get("prompt-1", model="default", priority="normal")
    assert cached == "hello world"


@pytest.mark.asyncio
async def test_llm_router_raises_when_no_available_providers():
    router = LLMRouter(enable_cache=False, enable_budgeting=False, enable_monitoring=False)
    router._providers = {"p1": DummyProvider("p1", available=False)}

    with pytest.raises(RuntimeError):
        _ = [c async for c in router.route_request("no providers", stream=True)]


def test_router_manager_stats_and_callback_registration():
    class _DummyRouter:
        def get_stats(self):
            return {"requests": 7}

    class _DummyConfig:
        def __init__(self):
            self.callbacks = []

        def register_callback(self, cb):
            self.callbacks.append(cb)

    cfg = _DummyConfig()
    manager = RouterManager(router=_DummyRouter(), config_manager=cfg)
    assert manager.get_stats()["requests"] == 7

    cb = lambda _cfg: None
    manager.register_config_callback(cb)
    assert cfg.callbacks == [cb]
