"""Plugin loaders for local folders, Git repos and PyPI packages."""

from __future__ import annotations

import importlib
import importlib.metadata
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import types
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

from pydantic import ValidationError

from ..core.models import LoadedPlugin, PluginLifecycleState, PluginManifest, PluginState

try:
    from packaging.requirements import InvalidRequirement, Requirement
except Exception:  # pragma: no cover - fallback for very minimal environments
    InvalidRequirement = ValueError
    Requirement = None  # type: ignore[assignment]

try:
    from packaging.specifiers import InvalidSpecifier, SpecifierSet
except Exception:  # pragma: no cover
    InvalidSpecifier = ValueError
    SpecifierSet = None  # type: ignore[assignment]


class PluginLoaderError(RuntimeError):
    """Base exception for plugin loading errors."""


class ManifestValidationError(PluginLoaderError):
    """Raised when manifest.json is absent or invalid."""


class DependencyResolutionError(PluginLoaderError):
    """Raised when plugin dependencies cannot be satisfied."""


class EntryPointImportError(PluginLoaderError):
    """Raised when plugin entry point cannot be imported."""


class BasePluginLoader:
    """Shared helpers for all loader implementations."""

    def validate_manifest(self, plugin_dir: Path) -> PluginManifest:
        """Validate and parse plugin manifest.json."""
        manifest_path = plugin_dir / "manifest.json"
        if not manifest_path.exists():
            raise ManifestValidationError(f"manifest.json not found in '{plugin_dir}'")

        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ManifestValidationError(f"Invalid JSON in {manifest_path}: {exc}") from exc

        try:
            return PluginManifest.model_validate(payload)
        except ValidationError as exc:
            raise ManifestValidationError(f"Manifest validation failed: {exc}") from exc

    def check_dependencies(self, manifest: PluginManifest) -> None:
        """Check python/vagus version constraints and dependency availability."""
        self._check_python_version(manifest.python_version)
        self._check_vagus_version(manifest.vagus_version)

        missing: list[str] = []
        for dependency in manifest.dependencies:
            package_name = self._extract_package_name(dependency)
            if not self._is_package_available(package_name):
                missing.append(dependency)

        if missing:
            raise DependencyResolutionError(
                f"Missing dependencies for plugin '{manifest.name}': {', '.join(missing)}"
            )

    def import_entry_point(
        self,
        manifest: PluginManifest,
        search_paths: Sequence[Path],
    ) -> tuple[object, object]:
        """Import module/object declared by manifest entry point."""
        module_name, _, object_name = manifest.entry_point.partition(":")
        try:
            module = self._import_module_from_search_paths(module_name, search_paths)
        except Exception as exc:
            raise EntryPointImportError(
                f"Cannot import module '{module_name}' for plugin '{manifest.name}': {exc}"
            ) from exc

        if not object_name:
            return module, module

        if not hasattr(module, object_name):
            raise EntryPointImportError(
                f"Entry point object '{object_name}' was not found in module '{module_name}'"
            )

        return module, getattr(module, object_name)

    def _import_module_from_search_paths(self, module_name: str, search_paths: Sequence[Path]) -> object:
        module_parts = module_name.split(".")
        module_relative_path = Path(*module_parts)

        for root in search_paths:
            root_path = Path(root).expanduser().resolve()
            module_file = root_path / module_relative_path.with_suffix(".py")
            package_init = root_path / module_relative_path / "__init__.py"

            if module_file.exists():
                return self._load_module_from_file(module_name, module_file)

            if package_init.exists():
                return self._load_module_from_file(
                    module_name,
                    package_init,
                    is_package=True,
                )

        for path in search_paths:
            path_str = str(Path(path).expanduser().resolve())
            if path_str not in sys.path:
                sys.path.insert(0, path_str)
        return importlib.import_module(module_name)

    def _load_module_from_file(self, module_name: str, file_path: Path, *, is_package: bool = False) -> object:
        unique_module_name = (
            f"_vagus_plugin_{module_name.replace('.', '_')}_{uuid.uuid4().hex}"
        )

        source_text = file_path.read_text(encoding="utf-8")
        code = compile(source_text, str(file_path), "exec")

        module = types.ModuleType(unique_module_name)
        module.__file__ = str(file_path)
        if is_package:
            module.__package__ = unique_module_name
            module.__path__ = [str(file_path.parent)]  # type: ignore[attr-defined]
        else:
            module.__package__ = unique_module_name.rpartition(".")[0]

        sys.modules[unique_module_name] = module
        exec(code, module.__dict__)
        return module

    def _build_loaded_plugin(
        self,
        manifest: PluginManifest,
        module: object,
        entry_point: object,
        source: Path,
    ) -> LoadedPlugin:
        return LoadedPlugin(
            manifest=manifest,
            module=module,
            entry_point=entry_point,
            source=str(source),
            state=PluginState(
                state=PluginLifecycleState.LOADED,
                load_time=datetime.now(timezone.utc),
            ),
        )

    def _check_python_version(self, version_specifier: str) -> None:
        if SpecifierSet is None:
            return

        try:
            spec = SpecifierSet(version_specifier)
        except InvalidSpecifier as exc:
            raise DependencyResolutionError(
                f"Invalid python version specifier '{version_specifier}'"
            ) from exc

        current_python = (
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        )
        if current_python not in spec:
            raise DependencyResolutionError(
                f"Plugin requires Python '{version_specifier}', current version is {current_python}"
            )

    def _check_vagus_version(self, version_specifier: str) -> None:
        if SpecifierSet is None:
            return

        current_version = self._detect_vagus_version()
        if current_version is None:
            return

        try:
            spec = SpecifierSet(version_specifier)
        except InvalidSpecifier as exc:
            raise DependencyResolutionError(
                f"Invalid Vagus version specifier '{version_specifier}'"
            ) from exc

        if current_version not in spec:
            raise DependencyResolutionError(
                f"Plugin requires Vagus '{version_specifier}', current version is {current_version}"
            )

    def _detect_vagus_version(self) -> Optional[str]:
        try:
            return importlib.metadata.version("vagus")
        except importlib.metadata.PackageNotFoundError:
            pass
        except Exception:
            return None

        try:
            import vagus  # pylint: disable=import-outside-toplevel
        except Exception:
            return None

        version = getattr(vagus, "__version__", None)
        return str(version) if version else None

    def _extract_package_name(self, requirement: str) -> str:
        dependency = requirement.strip()
        if not dependency:
            raise DependencyResolutionError("Dependency declaration cannot be empty")

        if Requirement is not None:
            try:
                return Requirement(dependency).name
            except InvalidRequirement:
                pass

        match = re.match(r"^[A-Za-z0-9_.-]+", dependency)
        if not match:
            raise DependencyResolutionError(f"Cannot parse dependency declaration '{requirement}'")
        return match.group(0)

    def _is_package_available(self, package_name: str) -> bool:
        try:
            importlib.metadata.version(package_name)
            return True
        except importlib.metadata.PackageNotFoundError:
            pass
        except Exception:
            pass

        module_name = package_name.replace("-", "_")
        return importlib.util.find_spec(module_name) is not None


class LocalLoader(BasePluginLoader):
    """Loader for local plugin directories."""

    def load(self, plugin_path: str | Path) -> LoadedPlugin:
        plugin_dir = Path(plugin_path).expanduser().resolve()
        if not plugin_dir.exists() or not plugin_dir.is_dir():
            raise PluginLoaderError(f"Plugin path does not exist or is not a directory: {plugin_dir}")

        manifest = self.validate_manifest(plugin_dir)
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

    def reload(self, loaded_plugin: LoadedPlugin) -> LoadedPlugin:
        """Hot-reload already loaded plugin module."""
        if loaded_plugin.module is None:
            if not loaded_plugin.source:
                raise PluginLoaderError("Cannot reload plugin without module or source path")
            return self.load(loaded_plugin.source)

        try:
            module = importlib.reload(loaded_plugin.module)
        except Exception as exc:
            loaded_plugin.state.state = PluginLifecycleState.ERROR
            loaded_plugin.state.error_message = str(exc)
            raise PluginLoaderError(
                f"Failed to reload plugin '{loaded_plugin.name}': {exc}"
            ) from exc

        _, _, object_name = loaded_plugin.manifest.entry_point.partition(":")
        loaded_plugin.module = module
        loaded_plugin.entry_point = getattr(module, object_name) if object_name else module
        loaded_plugin.state.last_used = datetime.now(timezone.utc)
        loaded_plugin.state.state = PluginLifecycleState.LOADED
        loaded_plugin.state.error_message = None
        return loaded_plugin


class GitLoader(BasePluginLoader):
    """Loader for plugin sources from Git repositories."""

    def __init__(self, local_loader: Optional[LocalLoader] = None):
        self.local_loader = local_loader or LocalLoader()

    def load(self, repository: str, ref: Optional[str] = None) -> LoadedPlugin:
        target_dir = Path(tempfile.mkdtemp(prefix="vagus_plugin_git_"))
        repository_url = self._normalize_repository(repository)

        command = ["git", "clone", "--depth", "1"]
        if ref:
            command.extend(["--branch", ref])
        command.extend([repository_url, str(target_dir)])

        self._run_command(command)
        return self.local_loader.load(target_dir)

    def _normalize_repository(self, repository: str) -> str:
        normalized = repository.strip()
        if not normalized:
            raise PluginLoaderError("Repository must not be empty")

        if normalized.startswith(("https://", "http://", "git@", "ssh://")):
            return normalized

        if normalized.count("/") == 1:
            return f"https://github.com/{normalized}.git"

        return normalized

    def _run_command(self, command: list[str]) -> None:
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise PluginLoaderError(
                f"Command failed: {' '.join(command)}{f'. {stderr}' if stderr else ''}"
            ) from exc


class PyPILoader(BasePluginLoader):
    """Loader for plugins installed from PyPI packages."""

    def __init__(self, local_loader: Optional[LocalLoader] = None):
        self.local_loader = local_loader or LocalLoader()

    def load(self, package_name: str, version: Optional[str] = None) -> LoadedPlugin:
        target_dir = Path(tempfile.mkdtemp(prefix="vagus_plugin_pypi_"))
        package_spec = f"{package_name}=={version}" if version else package_name

        command = [
            sys.executable,
            "-m",
            "pip",
            "install",
            package_spec,
            "--target",
            str(target_dir),
            "--disable-pip-version-check",
            "--no-input",
        ]
        self._run_command(command)

        plugin_root = self._locate_plugin_root(target_dir)
        return self.local_loader.load(plugin_root)

    def _locate_plugin_root(self, search_root: Path) -> Path:
        manifests = sorted(
            search_root.rglob("manifest.json"),
            key=lambda item: len(item.parts),
        )
        if not manifests:
            raise ManifestValidationError(
                f"No manifest.json found after PyPI install in '{search_root}'"
            )
        return manifests[0].parent

    def _run_command(self, command: list[str]) -> None:
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or "").strip()
            raise PluginLoaderError(
                f"Command failed: {' '.join(command)}{f'. {stderr}' if stderr else ''}"
            ) from exc
