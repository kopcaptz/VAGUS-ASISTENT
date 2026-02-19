"""Secure plugin loader with static analysis and signature checks."""

from __future__ import annotations

import ast
from datetime import datetime, timezone
from pathlib import Path
import shutil
from typing import Optional

from ..security.signatures import PluginSignatureVerifier
from .plugin_loader import LocalLoader, PluginLoaderError


class SecurityScanError(PluginLoaderError):
    """Raised when static code scan reports dangerous patterns."""


class DependencyVettingError(PluginLoaderError):
    """Raised when dependency vetting fails."""


class SignatureValidationError(PluginLoaderError):
    """Raised when manifest signature validation fails."""


class SecurePluginLoader(LocalLoader):
    """Extended local loader with security hardening checks."""

    def __init__(
        self,
        *,
        require_signatures: bool = False,
        trusted_keys: Optional[dict[str, str]] = None,
        allowed_dependencies: Optional[set[str]] = None,
        max_plugin_dependencies: int = 10,
        banned_imports: Optional[list[str]] = None,
        quarantine_dir: str | Path = ".vagus/quarantine/plugins",
    ) -> None:
        super().__init__()
        self.require_signatures = require_signatures
        self.allowed_dependencies = allowed_dependencies
        self.max_plugin_dependencies = max_plugin_dependencies
        self.banned_imports = banned_imports or ["os.system", "subprocess.Popen", "ctypes"]
        self.quarantine_dir = Path(quarantine_dir)
        self.signature_verifier = PluginSignatureVerifier(trusted_keys=trusted_keys or {})

    def load(self, plugin_path: str | Path):  # type: ignore[override]
        plugin_dir = Path(plugin_path).expanduser().resolve()
        if not plugin_dir.exists() or not plugin_dir.is_dir():
            raise PluginLoaderError(f"Plugin path does not exist or is not a directory: {plugin_dir}")

        manifest = self.validate_manifest(plugin_dir)
        self._validate_signature(plugin_dir, manifest.signature_key_id or manifest.name)
        self._vet_dependencies(manifest.dependencies)
        findings = self._scan_for_banned_constructs(plugin_dir)
        if findings:
            quarantine_location = self._quarantine(plugin_dir, ", ".join(findings))
            raise SecurityScanError(
                f"Plugin '{manifest.name}' contains banned constructs: {findings}. "
                f"Quarantined at: {quarantine_location}"
            )

        self.check_dependencies(manifest)
        module, entry_point = self.import_entry_point(
            manifest=manifest,
            search_paths=(plugin_dir, plugin_dir.parent),
        )
        return self._build_loaded_plugin(
            manifest=manifest,
            module=module,
            entry_point=entry_point,
            source=plugin_dir,
        )

    def _validate_signature(self, plugin_dir: Path, key_id: str) -> None:
        if not self.require_signatures:
            return

        manifest_path = plugin_dir / "manifest.json"
        signature_path = plugin_dir / "manifest.sig"
        if not signature_path.exists():
            quarantine_location = self._quarantine(plugin_dir, "missing manifest signature")
            raise SignatureValidationError(
                f"Missing manifest signature for '{plugin_dir}'. Quarantined at: {quarantine_location}"
            )

        is_valid = self.signature_verifier.verify_manifest_file(
            manifest_path=manifest_path,
            signature_path=signature_path,
            key_id=key_id,
        )
        if not is_valid:
            quarantine_location = self._quarantine(plugin_dir, "invalid manifest signature")
            raise SignatureValidationError(
                f"Invalid manifest signature for '{plugin_dir}'. Quarantined at: {quarantine_location}"
            )

    def _vet_dependencies(self, dependencies: list[str]) -> None:
        if len(dependencies) > self.max_plugin_dependencies:
            raise DependencyVettingError(
                f"Plugin has {len(dependencies)} dependencies; "
                f"maximum allowed is {self.max_plugin_dependencies}"
            )

        if not self.allowed_dependencies:
            return

        rejected: list[str] = []
        for dependency in dependencies:
            package_name = self._extract_package_name(dependency)
            if package_name not in self.allowed_dependencies:
                rejected.append(package_name)

        if rejected:
            raise DependencyVettingError(
                f"Dependencies are not allow-listed: {', '.join(sorted(set(rejected)))}"
            )

    def _scan_for_banned_constructs(self, plugin_dir: Path) -> list[str]:
        findings: set[str] = set()
        for source_file in plugin_dir.rglob("*.py"):
            source_text = source_file.read_text(encoding="utf-8")
            try:
                tree = ast.parse(source_text, filename=str(source_file))
            except SyntaxError:
                findings.add("syntax_error")
                continue

            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        self._record_if_banned(alias.name, findings)
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        full_name = f"{module}.{alias.name}".strip(".")
                        self._record_if_banned(full_name, findings)
                        self._record_if_banned(module, findings)
                elif isinstance(node, ast.Call):
                    call_name = self._resolve_call_name(node.func)
                    if call_name:
                        self._record_if_banned(call_name, findings)

        return sorted(findings)

    def _record_if_banned(self, symbol: str, findings: set[str]) -> None:
        candidate = (symbol or "").strip()
        if not candidate:
            return

        for banned in self.banned_imports:
            pattern = banned.strip()
            if not pattern:
                continue

            if candidate == pattern or candidate.startswith(f"{pattern}.") or pattern.startswith(
                f"{candidate}."
            ):
                findings.add(pattern)

    def _resolve_call_name(self, node: ast.AST) -> Optional[str]:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            prefix = self._resolve_call_name(node.value)
            if not prefix:
                return None
            return f"{prefix}.{node.attr}"
        return None

    def _quarantine(self, plugin_dir: Path, reason: str) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        destination = self.quarantine_dir / f"{plugin_dir.name}_{timestamp}"
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(plugin_dir, destination, dirs_exist_ok=True)
        (destination / "QUARANTINE_REASON.txt").write_text(reason, encoding="utf-8")
        return destination
