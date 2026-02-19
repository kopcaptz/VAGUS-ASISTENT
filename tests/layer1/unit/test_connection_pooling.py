"""Tests for provider HTTP connection pooling."""

import pytest

from vagus.layer1.providers.base import HTTPClientManager, LLMProvider
from vagus.layer1.providers.openai_provider import OpenAIProvider


@pytest.mark.asyncio
async def test_http_client_manager_returns_singleton_client():
    LLMProvider.configure_http_client_pool(
        max_connections=101,
        max_keepalive_connections=21,
        keepalive_expiry=6.0,
    )
    client1 = HTTPClientManager.get_client()
    client2 = HTTPClientManager.get_client()
    assert client1 is client2
    cfg = HTTPClientManager.current_config()
    assert cfg.max_connections == 101
    assert cfg.max_keepalive_connections == 21
    assert cfg.keepalive_expiry == 6.0
    await LLMProvider.close_shared_http_client()


@pytest.mark.asyncio
async def test_http_client_manager_recreates_client_on_reconfigure():
    LLMProvider.configure_http_client_pool(max_connections=100, max_keepalive_connections=20, keepalive_expiry=5.0)
    client1 = HTTPClientManager.get_client()
    LLMProvider.configure_http_client_pool(max_connections=200, max_keepalive_connections=50, keepalive_expiry=10.0)
    client2 = HTTPClientManager.get_client()
    assert client1 is not client2
    await LLMProvider.close_shared_http_client()


def test_openai_provider_uses_shared_http_client(monkeypatch):
    class _DummyOpenAIClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr("vagus.layer1.providers.openai_provider.OPENAI_AVAILABLE", True)
    monkeypatch.setattr(
        "vagus.layer1.providers.openai_provider.AsyncOpenAI",
        _DummyOpenAIClient,
        raising=False,
    )

    provider = OpenAIProvider(api_key="test-key")
    sdk_client = provider._get_client()
    assert isinstance(sdk_client, _DummyOpenAIClient)
    assert "http_client" in sdk_client.kwargs
    assert sdk_client.kwargs["http_client"] is HTTPClientManager.get_client()
