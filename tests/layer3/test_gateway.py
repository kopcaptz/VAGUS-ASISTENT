"""Тесты Channel Gateway."""

import pytest
import httpx
from vagus.layer3.channels.gateway import ChannelGateway


def test_gateway_init():
    gw = ChannelGateway(api_url="http://localhost:8000", api_key="test-key")
    assert gw.api_url == "http://localhost:8000"
    assert gw.timeout == 120


def test_gateway_strips_trailing_slash():
    gw = ChannelGateway(api_url="http://localhost:8000/", api_key="key")
    assert gw.api_url == "http://localhost:8000"


@pytest.mark.asyncio
async def test_gateway_headers():
    """Проверяет формирование заголовков с токеном."""
    gw = ChannelGateway(api_url="http://localhost:8000", api_key="my-token")
    async with httpx.AsyncClient() as client:
        headers = await gw._auth_headers(client)
        assert headers["Authorization"] == "Bearer my-token"


def test_gateway_custom_timeout():
    gw = ChannelGateway(api_url="http://localhost:8000", api_key="k", timeout=60)
    assert gw.timeout == 60
