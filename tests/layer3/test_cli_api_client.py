"""Тесты CLI API-клиента."""

from unittest.mock import patch

import pytest
from vagus.layer3.cli.utils.api_client import CLIApiClient
from vagus.layer3.security.request_signing import (
    HEADER_CLIENT_ID,
    HEADER_SIGNATURE,
    HEADER_TIMESTAMP,
)


def test_cli_client_init_defaults():
    with patch("vagus.layer3.cli.utils.api_client.load_config", return_value={
        "api_url": "http://localhost:8000",
        "api_key": "test-key",
        "enable_request_signing": True,
    }), patch(
        "vagus.layer3.cli.utils.api_client.load_or_create_client_credentials",
        return_value={"client_id": "cid", "client_secret": "sec"},
    ):
        client = CLIApiClient()
        assert client.api_url == "http://localhost:8000"
        assert client.api_key == "test-key"
        assert client.enable_request_signing is True


def test_cli_client_custom_url():
    with patch("vagus.layer3.cli.utils.api_client.load_config", return_value={
        "enable_request_signing": False
    }):
        client = CLIApiClient(api_url="http://custom:9000", api_key="key")
        assert client.api_url == "http://custom:9000"


def test_cli_client_headers_with_key():
    with patch("vagus.layer3.cli.utils.api_client.load_config", return_value={
        "enable_request_signing": False
    }):
        client = CLIApiClient(api_url="http://test", api_key="bearer-tok")
    assert client._headers["Authorization"] == "Bearer bearer-tok"


def test_cli_client_headers_no_key():
    with patch("vagus.layer3.cli.utils.api_client.load_config", return_value={
        "enable_request_signing": False
    }):
        client = CLIApiClient(api_url="http://test", api_key="")
    assert "Authorization" not in client._headers


def test_cli_client_signing_headers_present_when_enabled():
    with patch("vagus.layer3.cli.utils.api_client.load_config", return_value={
        "enable_request_signing": True
    }), patch(
        "vagus.layer3.cli.utils.api_client.load_or_create_client_credentials",
        return_value={"client_id": "cid", "client_secret": "sec"},
    ):
        client = CLIApiClient(api_url="http://localhost:8000", api_key="")
        headers = client._build_request_headers(
            method="GET",
            path="/api/v1/status",
            body_bytes=b"",
            cli_command="admin.status",
            cli_arguments=None,
        )
        assert headers[HEADER_CLIENT_ID] == "cid"
        assert HEADER_TIMESTAMP in headers
        assert HEADER_SIGNATURE in headers


def test_cli_client_signing_disabled_skips_signature_headers():
    with patch("vagus.layer3.cli.utils.api_client.load_config", return_value={
        "enable_request_signing": False
    }):
        client = CLIApiClient(api_url="http://localhost:8000", api_key="")
        headers = client._build_request_headers(
            method="GET",
            path="/api/v1/status",
            body_bytes=b"",
            cli_command="admin.status",
            cli_arguments=None,
        )
        assert HEADER_CLIENT_ID not in headers
        assert HEADER_TIMESTAMP not in headers
        assert HEADER_SIGNATURE not in headers
