"""Digital signature utilities for plugin verification."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from pathlib import Path
import subprocess
from typing import Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    PublicFormat,
    load_pem_private_key,
    load_pem_public_key,
)


class SignatureError(RuntimeError):
    """Base signature verification exception."""


@dataclass
class TrustStore:
    """In-memory trust store for plugin signature public keys."""

    keys: dict[str, str] = field(default_factory=dict)

    def add_key(self, key_id: str, public_key_pem: str) -> None:
        self.keys[key_id] = public_key_pem.strip()

    def remove_key(self, key_id: str) -> None:
        self.keys.pop(key_id, None)

    def get_key(self, key_id: str) -> Optional[str]:
        return self.keys.get(key_id)

    def has_key(self, key_id: str) -> bool:
        return key_id in self.keys

    def load_from_directory(self, path: str | Path) -> int:
        root = Path(path).expanduser().resolve()
        if not root.exists():
            return 0

        loaded = 0
        for key_file in sorted(root.glob("*.pem")):
            key_id = key_file.stem
            self.add_key(key_id, key_file.read_text(encoding="utf-8"))
            loaded += 1
        return loaded


class PluginSignatureVerifier:
    """Verifier for manifest signatures (Ed25519) and marketplace GPG signatures."""

    def __init__(
        self,
        trust_store: Optional[TrustStore] = None,
        trusted_keys: Optional[dict[str, str]] = None,
    ) -> None:
        self.trust_store = trust_store or TrustStore()
        if trusted_keys:
            for key_id, key in trusted_keys.items():
                self.trust_store.add_key(key_id, key)

    def verify_manifest_file(
        self,
        manifest_path: str | Path,
        signature_path: str | Path,
        key_id: str,
    ) -> bool:
        manifest_file = Path(manifest_path).expanduser().resolve()
        signature_file = Path(signature_path).expanduser().resolve()
        public_key_pem = self.trust_store.get_key(key_id)
        if not public_key_pem:
            return False

        manifest_bytes = manifest_file.read_bytes()
        signature_bytes = self._load_signature(signature_file)
        return self.verify_manifest_ed25519(
            manifest_bytes=manifest_bytes,
            signature=signature_bytes,
            public_key_pem=public_key_pem.encode("utf-8"),
        )

    def verify_manifest_ed25519(
        self,
        manifest_bytes: bytes,
        signature: bytes,
        public_key_pem: bytes,
    ) -> bool:
        try:
            public_key = load_pem_public_key(public_key_pem)
            if not isinstance(public_key, Ed25519PublicKey):
                return False
            public_key.verify(signature, manifest_bytes)
            return True
        except (InvalidSignature, ValueError, TypeError):
            return False

    def verify_marketplace_gpg(
        self,
        signature_path: str | Path,
        artifact_path: str | Path,
        *,
        keyring_path: Optional[str | Path] = None,
    ) -> bool:
        command = ["gpg", "--verify", str(signature_path), str(artifact_path)]
        if keyring_path:
            keyring = Path(keyring_path).expanduser().resolve()
            command = [
                "gpg",
                "--no-default-keyring",
                "--keyring",
                str(keyring),
                "--verify",
                str(signature_path),
                str(artifact_path),
            ]

        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
            return True
        except (subprocess.CalledProcessError, FileNotFoundError):
            return False

    @staticmethod
    def generate_ed25519_keypair() -> tuple[str, str]:
        """Generate PEM encoded private/public key pair."""
        private_key = Ed25519PrivateKey.generate()
        private_pem = private_key.private_bytes(
            encoding=Encoding.PEM,
            format=PrivateFormat.PKCS8,
            encryption_algorithm=NoEncryption(),
        ).decode("utf-8")
        public_pem = private_key.public_key().public_bytes(
            encoding=Encoding.PEM,
            format=PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")
        return private_pem, public_pem

    @staticmethod
    def sign_manifest_ed25519(manifest_bytes: bytes, private_key_pem: str | bytes) -> bytes:
        private_key_data = (
            private_key_pem.encode("utf-8")
            if isinstance(private_key_pem, str)
            else private_key_pem
        )
        private_key = load_pem_private_key(private_key_data, password=None)
        if not isinstance(private_key, Ed25519PrivateKey):
            raise SignatureError("Provided private key is not Ed25519")
        return private_key.sign(manifest_bytes)

    @staticmethod
    def encode_signature(signature: bytes) -> str:
        return base64.b64encode(signature).decode("utf-8")

    @staticmethod
    def decode_signature(signature_payload: str | bytes) -> bytes:
        raw = signature_payload.encode("utf-8") if isinstance(signature_payload, str) else signature_payload
        try:
            return base64.b64decode(raw, validate=True)
        except Exception:
            return raw

    def _load_signature(self, signature_file: Path) -> bytes:
        payload = signature_file.read_bytes().strip()
        return self.decode_signature(payload)
