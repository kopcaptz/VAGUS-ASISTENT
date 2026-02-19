"""Тесты CLI API-клиента."""

from unittest.mock import patch

import pytest
from vagus.layer3.cli.utils.api_client import CLIApiClient


def test_cli_client_init_defaults():
    with patch("vagus.layer3.cli.utils.api_client.load_config", return_value={
        "api_url": "http://localhost:8000",
        "api_key": "test-key",
    }):
        client = CLIApiClient()
        assert client.api_url == "http://localhost:8000"
        assert client.api_key == "test-key"


def test_cli_client_custom_url():
    client = CLIApiClient(api_url="http://custom:9000", api_key="key")
    assert client.api_url == "http://custom:9000"


def test_cli_client_headers_with_key():
    client = CLIApiClient(api_url="http://test", api_key="bearer-tok")
    assert client._headers["Authorization"] == "Bearer bearer-tok"


def test_cli_client_headers_no_key():
    client = CLIApiClient(api_url="http://test", api_key="")
    assert "Authorization" not in client._headers
