"""Тесты Channel Gateway."""

import pytest
from vagus.layer3.channels.gateway import ChannelGateway


def test_gateway_init():
    gw = ChannelGateway(api_url="http://localhost:8000", api_key="test-key")
    assert gw.api_url == "http://localhost:8000"
    assert gw.timeout == 120


def test_gateway_strips_trailing_slash():
    gw = ChannelGateway(api_url="http://localhost:8000/", api_key="key")
    assert gw.api_url == "http://localhost:8000"


def test_gateway_headers():
    gw = ChannelGateway(api_url="http://localhost:8000", api_key="my-token")
    assert gw._headers["Authorization"] == "Bearer my-token"


def test_gateway_custom_timeout():
    gw = ChannelGateway(api_url="http://localhost:8000", api_key="k", timeout=60)
    assert gw.timeout == 60
