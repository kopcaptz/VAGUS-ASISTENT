"""Tests for plugin signature verification."""

from __future__ import annotations

from pathlib import Path

import pytest

from vagus.plugins.security.signatures import PluginSignatureVerifier, TrustStore


def test_ed25519_sign_and_verify_manifest():
    verifier = PluginSignatureVerifier()
    private_key, public_key = verifier.generate_ed25519_keypair()
    payload = b'{"name":"demo"}'
    signature = verifier.sign_manifest_ed25519(payload, private_key)
    assert verifier.verify_manifest_ed25519(payload, signature, public_key.encode("utf-8")) is True


def test_ed25519_verify_fails_with_wrong_key():
    verifier = PluginSignatureVerifier()
    private_key, _ = verifier.generate_ed25519_keypair()
    _, other_public = verifier.generate_ed25519_keypair()

    payload = b'{"name":"demo"}'
    signature = verifier.sign_manifest_ed25519(payload, private_key)
    assert verifier.verify_manifest_ed25519(payload, signature, other_public.encode("utf-8")) is False


def test_trust_store_loads_keys_from_directory(tmp_path: Path):
    _, public_key = PluginSignatureVerifier.generate_ed25519_keypair()
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    (keys_dir / "plugin_a.pem").write_text(public_key, encoding="utf-8")

    store = TrustStore()
    loaded = store.load_from_directory(keys_dir)
    assert loaded == 1
    assert store.has_key("plugin_a") is True


def test_verify_manifest_file_uses_trust_store(tmp_path: Path):
    verifier = PluginSignatureVerifier()
    private_key, public_key = verifier.generate_ed25519_keypair()
    verifier.trust_store.add_key("plugin_a", public_key)

    manifest = tmp_path / "manifest.json"
    manifest.write_text('{"name":"plugin_a"}', encoding="utf-8")
    signature = verifier.sign_manifest_ed25519(manifest.read_bytes(), private_key)
    signature_file = tmp_path / "manifest.sig"
    signature_file.write_text(verifier.encode_signature(signature), encoding="utf-8")

    assert verifier.verify_manifest_file(manifest, signature_file, key_id="plugin_a") is True


def test_gpg_verification_invokes_subprocess(monkeypatch: pytest.MonkeyPatch):
    verifier = PluginSignatureVerifier()
    captured: dict[str, list[str]] = {}

    def fake_run(command, check, capture_output, text):  # noqa: ANN001
        captured["command"] = command
        class Result:  # pragma: no cover - simple stub
            returncode = 0
        return Result()

    monkeypatch.setattr("vagus.plugins.security.signatures.subprocess.run", fake_run)

    assert verifier.verify_marketplace_gpg("artifact.sig", "artifact.tar.gz") is True
    assert captured["command"][:2] == ["gpg", "--verify"]
