from __future__ import annotations

import sys

import pytest

import vagus.security.dpapi_wrapper as dpapi_wrapper

pytestmark = [
    pytest.mark.windows,
    pytest.mark.skipif(sys.platform != "win32", reason="Windows-only DPAPI test"),
]


def test_dpapi_roundtrip_if_available() -> None:
    if not dpapi_wrapper.is_dpapi_available():
        pytest.skip("DPAPI unavailable")
    source = b"vagus-dpapi-test"
    protected = dpapi_wrapper.protect_data(source)
    assert protected.startswith(b"DPAPIv1")
    restored = dpapi_wrapper.unprotect_data(protected)
    assert restored == source
