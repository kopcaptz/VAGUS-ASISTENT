"""Windows DPAPI wrapper with explicit binary envelope.

Envelope format:
    magic (7 bytes): b"DPAPIv1"
    version (1 byte): 0x01
    payload: raw CryptProtectData bytes
"""

from __future__ import annotations

import ctypes
import logging
import sys
from ctypes import wintypes

logger = logging.getLogger(__name__)

DPAPI_MAGIC = b"DPAPIv1"
DPAPI_VERSION = 1


class DATA_BLOB(ctypes.Structure):
    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


class CRYPTPROTECT_PROMPTSTRUCT(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("dwPromptFlags", wintypes.DWORD),
        ("hwndApp", wintypes.HWND),
        ("szPrompt", wintypes.LPCWSTR),
    ]


def is_dpapi_available() -> bool:
    """Returns True when current platform can use Windows DPAPI."""
    return sys.platform == "win32"


def _build_envelope(payload: bytes) -> bytes:
    return DPAPI_MAGIC + bytes([DPAPI_VERSION]) + payload


def _parse_envelope(blob: bytes) -> bytes:
    if len(blob) < len(DPAPI_MAGIC) + 1:
        raise ValueError("DPAPI envelope is too short")
    if not blob.startswith(DPAPI_MAGIC):
        raise ValueError("Not a DPAPI envelope")
    version = blob[len(DPAPI_MAGIC)]
    if version != DPAPI_VERSION:
        raise ValueError(f"Unsupported DPAPI envelope version: {version}")
    return blob[len(DPAPI_MAGIC) + 1 :]


def _bytes_to_blob(data: bytes) -> tuple[DATA_BLOB, ctypes.Array[ctypes.c_byte]]:
    if not data:
        arr = (ctypes.c_byte * 1)()
        return DATA_BLOB(0, arr), arr
    arr = (ctypes.c_byte * len(data)).from_buffer_copy(data)
    return DATA_BLOB(len(data), arr), arr


def _blob_to_bytes(blob: DATA_BLOB) -> bytes:
    if blob.cbData == 0 or not blob.pbData:
        return b""
    return ctypes.string_at(blob.pbData, blob.cbData)


def protect_data(data: bytes) -> bytes:
    """Protects bytes with Windows DPAPI and wraps them in DPAPI envelope."""
    if not is_dpapi_available():
        raise RuntimeError("DPAPI is available only on Windows")

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    in_blob, _in_arr = _bytes_to_blob(data)
    out_blob = DATA_BLOB()
    prompt = CRYPTPROTECT_PROMPTSTRUCT(
        cbSize=ctypes.sizeof(CRYPTPROTECT_PROMPTSTRUCT),
        dwPromptFlags=0,
        hwndApp=None,
        szPrompt=None,
    )

    ok = crypt32.CryptProtectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        ctypes.byref(prompt),
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        error_code = ctypes.GetLastError()
        raise RuntimeError(f"CryptProtectData failed with code {error_code}")

    try:
        protected = _blob_to_bytes(out_blob)
        return _build_envelope(protected)
    finally:
        if out_blob.pbData:
            kernel32.LocalFree(out_blob.pbData)


def unprotect_data(blob: bytes) -> bytes:
    """Unwraps DPAPI envelope and decrypts bytes with Windows DPAPI."""
    if not is_dpapi_available():
        raise RuntimeError("DPAPI is available only on Windows")

    crypt32 = ctypes.windll.crypt32
    kernel32 = ctypes.windll.kernel32

    payload = _parse_envelope(blob)
    in_blob, _in_arr = _bytes_to_blob(payload)
    out_blob = DATA_BLOB()
    prompt = CRYPTPROTECT_PROMPTSTRUCT(
        cbSize=ctypes.sizeof(CRYPTPROTECT_PROMPTSTRUCT),
        dwPromptFlags=0,
        hwndApp=None,
        szPrompt=None,
    )

    ok = crypt32.CryptUnprotectData(
        ctypes.byref(in_blob),
        None,
        None,
        None,
        ctypes.byref(prompt),
        0,
        ctypes.byref(out_blob),
    )
    if not ok:
        error_code = ctypes.GetLastError()
        raise RuntimeError(f"CryptUnprotectData failed with code {error_code}")

    try:
        return _blob_to_bytes(out_blob)
    finally:
        if out_blob.pbData:
            kernel32.LocalFree(out_blob.pbData)
