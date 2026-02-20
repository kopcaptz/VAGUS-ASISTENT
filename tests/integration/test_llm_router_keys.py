"""Integration tests for LLM router + key manager interactions."""

from __future__ import annotations

import pytest

from vagus.layer1.providers.base_provider import LLMProvider
from vagus.layer1.router.llm_router import LLMRouter
from vagus.security import KeyManager


class _DummyProvider(LLMProvider):
    async def request(self, prompt: str, stream: bool = False, **kwargs):
        yield {"content": "ok", "done": True}

    def calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        return 0.0


@pytest.mark.asyncio
async def test_router_marks_key_as_used(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    KeyManager.reset_instance_for_tests()
    km = KeyManager()
    km.add_key(name="openai", key_type="openai", value="sk-test-1234567890")

    router = LLMRouter(enable_cache=False, enable_budgeting=False, enable_monitoring=False)
    router._providers = {"openai": _DummyProvider(name="openai", model="gpt-4o-mini", api_key="dummy")}

    async def _exec(**kwargs):
        result = await kwargs["request_func"]("openai")
        return result, "openai"

    monkeypatch.setattr(router.fallback_handler, "execute", _exec)

    output = []
    async for chunk in router.route_request("hello", stream=True):
        output.append(chunk)
    assert output

    entry = km.list_keys().get("openai")
    assert entry is not None
    assert entry.get("last_used_at") is not None


@pytest.mark.asyncio
async def test_refresh_provider_after_key_update(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    KeyManager.reset_instance_for_tests()
    km = KeyManager()
    km.add_key(name="openai", key_type="openai", value="sk-old-1234567890")

    router = LLMRouter(enable_cache=False, enable_budgeting=False, enable_monitoring=False)
    router._initialized = True
    router._providers = {"openai": _DummyProvider(name="openai", model="gpt-4o-mini", api_key="x")}

    def _create(provider_id: str, model: str, api_key=None, **kwargs):
        return _DummyProvider(name=provider_id, model=model, api_key=router.provider_factory._resolve_api_key(provider_id, api_key))

    monkeypatch.setattr(router.provider_factory, "create", _create)
    km.update_key(name="openai", value="sk-new-1234567890")

    refreshed = await router.refresh_provider("openai")
    assert refreshed is True
    assert router._providers["openai"].api_key == "sk-new-1234567890"
