"""Tests for secure plugin loader."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from vagus.plugins.loader import (
    DependencyVettingError,
    SecurePluginLoader,
    SecurityScanError,
    SignatureValidationError,
)
from vagus.plugins.security import PluginSignatureVerifier


def _write_plugin(
    root: Path,
    name: str,
    *,
    dependencies: list[str] | None = None,
    code: str | None = None,
    signature_key_id: str | None = None,
) -> None:
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "name": name,
        "version": "1.0.0",
        "author": "Tests",
        "description": "Secure loader plugin",
        "dependencies": dependencies or [],
        "python_version": ">=3.10",
        "vagus_version": ">=0.1.0",
        "entry_point": "plugin:Entry",
        "hooks": [],
        "permissions": [],
        "signature_key_id": signature_key_id or name,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (root / "plugin.py").write_text(
        code
        or (
            "class Entry:\n"
            "    def run(self):\n"
            "        return 'ok'\n"
        ),
        encoding="utf-8",
    )


def test_secure_loader_loads_safe_plugin(tmp_path: Path):
    plugin_dir = tmp_path / "safe_plugin"
    _write_plugin(plugin_dir, "safe_plugin")
    loader = SecurePluginLoader(quarantine_dir=tmp_path / "quarantine")

    loaded = loader.load(plugin_dir)
    assert loaded.manifest.name == "safe_plugin"


def test_secure_loader_detects_banned_construct_and_quarantines(tmp_path: Path):
    plugin_dir = tmp_path / "danger_plugin"
    _write_plugin(
        plugin_dir,
        "danger_plugin",
        code=(
            "import os\n"
            "class Entry:\n"
            "    def run(self):\n"
            "        os.system('echo dangerous')\n"
        ),
    )
    quarantine = tmp_path / "quarantine"
    loader = SecurePluginLoader(quarantine_dir=quarantine)

    with pytest.raises(SecurityScanError):
        loader.load(plugin_dir)

    quarantined_items = list(quarantine.rglob("QUARANTINE_REASON.txt"))
    assert quarantined_items, "Expected quarantined plugin metadata file"


def test_secure_loader_rejects_non_allowlisted_dependency(tmp_path: Path):
    plugin_dir = tmp_path / "deps_plugin"
    _write_plugin(plugin_dir, "deps_plugin", dependencies=["numpy>=1.0.0"])
    loader = SecurePluginLoader(
        quarantine_dir=tmp_path / "quarantine",
        allowed_dependencies={"pytest"},
    )

    with pytest.raises(DependencyVettingError):
        loader.load(plugin_dir)


def test_secure_loader_requires_manifest_signature(tmp_path: Path):
    plugin_dir = tmp_path / "signed_required"
    _write_plugin(plugin_dir, "signed_required")
    loader = SecurePluginLoader(
        require_signatures=True,
        trusted_keys={},
        quarantine_dir=tmp_path / "quarantine",
    )

    with pytest.raises(SignatureValidationError):
        loader.load(plugin_dir)


def test_secure_loader_accepts_valid_manifest_signature(tmp_path: Path):
    plugin_dir = tmp_path / "signed_ok"
    _write_plugin(plugin_dir, "signed_ok")
    manifest_bytes = (plugin_dir / "manifest.json").read_bytes()

    private_key, public_key = PluginSignatureVerifier.generate_ed25519_keypair()
    signature = PluginSignatureVerifier.sign_manifest_ed25519(manifest_bytes, private_key)
    (plugin_dir / "manifest.sig").write_text(
        PluginSignatureVerifier.encode_signature(signature),
        encoding="utf-8",
    )

    loader = SecurePluginLoader(
        require_signatures=True,
        trusted_keys={"signed_ok": public_key},
        quarantine_dir=tmp_path / "quarantine",
    )
    loaded = loader.load(plugin_dir)
    assert loaded.manifest.name == "signed_ok"
