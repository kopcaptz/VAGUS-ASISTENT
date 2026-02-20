"""Shared plugin management service for CLI and API layers."""

from __future__ import annotations

import json
import shutil
import tarfile
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlparse
from urllib.request import urlopen

from .core.models import LoadedPlugin, PluginLifecycleState
from .loader import GitLoader, LocalLoader, PluginLoaderError
from .marketplace import MarketplaceClient
from .registry import PluginRegistry

DEFAULT_PLUGIN_INSTALL_ROOT = Path.home() / ".vagus" / "plugins"


class PluginManagerError(RuntimeError):
    """Base exception for plugin management operations."""


class PluginNotFoundError(PluginManagerError):
    """Raised when plugin does not exist in local registry."""


class PluginManager:
    """High-level plugin manager backed by filesystem state."""

    def __init__(
        self,
        *,
        install_root: Optional[str | Path] = None,
        state_file: Optional[str | Path] = None,
    ) -> None:
        self.install_root = (
            Path(install_root).expanduser().resolve()
            if install_root is not None
            else DEFAULT_PLUGIN_INSTALL_ROOT.resolve()
        )
        self.state_file = (
            Path(state_file).expanduser().resolve()
            if state_file is not None
            else (self.install_root / "registry.json").resolve()
        )
        self.local_loader = LocalLoader()
        self.git_loader = GitLoader()

    def install_plugin(
        self,
        source: str,
        *,
        version: Optional[str] = None,
        marketplace_client: Optional[MarketplaceClient] = None,
    ) -> dict[str, Any]:
        """Install plugin from local path, URL, git source or marketplace id."""
        temp_dir: Optional[Path] = None
        try:
            loaded, source_dir, cleanup_dir = self._load_plugin_for_install(
                source,
                version,
                marketplace_client=marketplace_client,
            )
            temp_dir = cleanup_dir
            installed, _ = self._persist_installed_plugin(
                loaded_plugin=loaded,
                source_dir=source_dir,
                install_origin=source,
            )
            PluginRegistry().register(installed)
            return self.get_plugin(installed.name)
        except PluginManagerError:
            raise
        except Exception as exc:
            raise PluginManagerError(f"Failed to install plugin: {exc}") from exc
        finally:
            self._cleanup_temp_dir(temp_dir)

    def list_plugins(self, *, state_filter: Optional[PluginLifecycleState] = None) -> list[dict[str, Any]]:
        """List installed plugins with runtime status."""
        registry, state, load_errors = self._load_runtime_registry()
        plugins_payload = state.get("plugins", {})
        if not isinstance(plugins_payload, dict):
            plugins_payload = {}

        listed: list[dict[str, Any]] = []
        emitted: set[str] = set()
        loaded_plugins = registry.list_plugins(state=state_filter) if state_filter else registry.list_plugins()
        for plugin in loaded_plugins:
            emitted.add(plugin.name)
            listed.append(
                self._plugin_to_info(
                    plugin,
                    metadata=plugins_payload.get(plugin.name),
                    load_error=load_errors.get(plugin.name),
                )
            )

        for plugin_name, metadata in plugins_payload.items():
            if plugin_name in emitted:
                continue
            if not isinstance(metadata, dict):
                continue
            if state_filter is not None:
                expected_enabled = state_filter == PluginLifecycleState.ENABLED
                if bool(metadata.get("enabled", True)) != expected_enabled:
                    continue
            listed.append(
                {
                    "name": plugin_name,
                    "version": str(metadata.get("version", "unknown")),
                    "status": "ERROR" if plugin_name in load_errors else "UNKNOWN",
                    "enabled": bool(metadata.get("enabled", True)),
                    "author": str(metadata.get("author", "unknown")),
                    "description": str(
                        metadata.get("description")
                        or load_errors.get(plugin_name, "Plugin metadata exists but plugin not loaded")
                    ),
                    "source": str(metadata.get("source", "")),
                    "path": str(metadata.get("path", "")),
                    "installed_at": metadata.get("installed_at"),
                    "load_error": load_errors.get(plugin_name),
                }
            )

        listed.sort(key=lambda item: item["name"])
        return listed

    def get_plugin(self, plugin_name: str) -> dict[str, Any]:
        """Get plugin info by name."""
        for plugin in self.list_plugins():
            if plugin.get("name") == plugin_name:
                return plugin
        raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")

    def set_plugin_enabled(self, plugin_name: str, *, enabled: bool) -> dict[str, Any]:
        """Enable or disable plugin in persisted state and runtime registry."""
        registry, state, load_errors = self._load_runtime_registry()
        plugins_payload = state.get("plugins", {})
        if not isinstance(plugins_payload, dict) or plugin_name not in plugins_payload:
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")

        metadata = plugins_payload.get(plugin_name)
        if not isinstance(metadata, dict):
            raise PluginManagerError(f"Invalid metadata for plugin '{plugin_name}'")

        metadata["enabled"] = bool(enabled)
        self._save_plugin_state(state)

        plugin = registry.get_plugin(plugin_name)
        if plugin is not None:
            plugin.state.state = (
                PluginLifecycleState.ENABLED if enabled else PluginLifecycleState.DISABLED
            )
            registry.register(plugin)

        plugin_info = self.get_plugin(plugin_name)
        if plugin_name in load_errors:
            plugin_info["load_error"] = load_errors[plugin_name]
        return plugin_info

    def uninstall_plugin(self, plugin_name: str, *, force: bool = False) -> None:
        """Uninstall plugin and remove metadata entry."""
        registry, state, _ = self._load_runtime_registry()
        plugins_payload = state.get("plugins", {})
        if not isinstance(plugins_payload, dict) or plugin_name not in plugins_payload:
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")

        metadata = plugins_payload[plugin_name]
        plugin_path = Path(str(metadata.get("path", ""))).expanduser()

        if plugin_path.exists():
            try:
                shutil.rmtree(plugin_path)
            except Exception as exc:
                if not force:
                    raise PluginManagerError(f"Failed to remove plugin files: {exc}") from exc

        plugins_payload.pop(plugin_name, None)
        self._save_plugin_state(state)
        registry.unregister(plugin_name)

    def get_plugin_config(self, plugin_name: str) -> dict[str, Any]:
        """Get plugin config payload."""
        state = self._load_plugin_state()
        plugins_payload = state.get("plugins", {})
        if not isinstance(plugins_payload, dict):
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")

        metadata = plugins_payload.get(plugin_name)
        if not isinstance(metadata, dict):
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")

        config = metadata.get("config")
        if not isinstance(config, dict):
            return {"settings": {}, "secrets": {}, "ui_schema": {}}
        return {
            "settings": config.get("settings", {}) if isinstance(config.get("settings"), dict) else {},
            "secrets": config.get("secrets", {}) if isinstance(config.get("secrets"), dict) else {},
            "ui_schema": config.get("ui_schema", {}) if isinstance(config.get("ui_schema"), dict) else {},
        }

    def update_plugin_config(
        self,
        plugin_name: str,
        *,
        settings: Optional[dict[str, Any]] = None,
        secrets: Optional[dict[str, Any]] = None,
        ui_schema: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Update plugin config payload."""
        state = self._load_plugin_state()
        plugins_payload = state.get("plugins", {})
        if not isinstance(plugins_payload, dict):
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")

        metadata = plugins_payload.get(plugin_name)
        if not isinstance(metadata, dict):
            raise PluginNotFoundError(f"Plugin '{plugin_name}' not found")

        config = metadata.get("config")
        if not isinstance(config, dict):
            config = {"settings": {}, "secrets": {}, "ui_schema": {}}

        if settings is not None:
            config["settings"] = settings
        if secrets is not None:
            config["secrets"] = secrets
        if ui_schema is not None:
            config["ui_schema"] = ui_schema
        metadata["config"] = config
        self._save_plugin_state(state)

        plugin = PluginRegistry().get_plugin(plugin_name)
        if plugin is not None:
            plugin.config.settings = config.get("settings", {})
            plugin.config.secrets = config.get("secrets", {})
            plugin.config.ui_schema = config.get("ui_schema", {})

        return {
            "settings": config.get("settings", {}),
            "secrets": config.get("secrets", {}),
            "ui_schema": config.get("ui_schema", {}),
        }

    def _plugin_to_info(
        self,
        plugin: LoadedPlugin,
        *,
        metadata: Any,
        load_error: Optional[str],
    ) -> dict[str, Any]:
        metadata_dict = metadata if isinstance(metadata, dict) else {}
        enabled = (
            bool(metadata_dict.get("enabled", True))
            if metadata_dict
            else plugin.state.state == PluginLifecycleState.ENABLED
        )
        return {
            "name": plugin.name,
            "version": plugin.manifest.version,
            "status": plugin.state.state.value,
            "enabled": enabled,
            "author": plugin.manifest.author,
            "description": plugin.manifest.description,
            "source": str(metadata_dict.get("source", plugin.source or "")),
            "path": str(metadata_dict.get("path", plugin.source or "")),
            "installed_at": metadata_dict.get("installed_at"),
            "load_error": load_error,
        }

    def _ensure_storage(self) -> None:
        self.install_root.mkdir(parents=True, exist_ok=True)

    def _load_plugin_state(self) -> dict[str, Any]:
        if not self.state_file.exists():
            return {"plugins": {}}

        try:
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return {"plugins": {}}

        if not isinstance(payload, dict):
            return {"plugins": {}}

        plugins_payload = payload.get("plugins")
        if not isinstance(plugins_payload, dict):
            return {"plugins": {}}

        return {"plugins": plugins_payload}

    def _save_plugin_state(self, payload: dict[str, Any]) -> None:
        self._ensure_storage()
        self.state_file.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    @staticmethod
    def _is_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme.lower() in {"http", "https"}

    @staticmethod
    def _is_git_source(value: str) -> bool:
        source = value.strip()
        if source.startswith("git@"):
            return True

        if source.endswith(".git"):
            return True

        parsed = urlparse(source)
        if parsed.scheme.lower() in {"http", "https"} and "github.com" in parsed.netloc.lower():
            path_parts = [part for part in parsed.path.split("/") if part]
            if len(path_parts) >= 2 and not source.lower().endswith(
                (".zip", ".tar", ".tar.gz", ".tgz")
            ):
                return True

        if parsed.scheme:
            return False

        if source.count("/") == 1 and not source.startswith((".", "~")):
            return True

        return False

    @staticmethod
    def _locate_plugin_root(search_root: Path) -> Path:
        root_manifest = search_root / "manifest.json"
        if root_manifest.exists():
            return search_root

        manifests = sorted(search_root.rglob("manifest.json"), key=lambda item: len(item.parts))
        if not manifests:
            raise PluginLoaderError(f"manifest.json not found in extracted plugin source: {search_root}")
        return manifests[0].parent

    def _download_and_extract_plugin_from_url(self, source_url: str) -> tuple[Path, Path]:
        temp_root = Path(tempfile.mkdtemp(prefix="vagus_plugin_url_"))
        download_name = Path(urlparse(source_url).path).name or "plugin_download.bin"
        download_path = temp_root / download_name

        try:
            with urlopen(source_url, timeout=30) as response:
                content = response.read()
        except Exception as exc:
            raise PluginManagerError(f"Failed to download plugin from URL '{source_url}': {exc}") from exc

        download_path.write_bytes(content)

        extract_dir = temp_root / "extracted"
        extract_dir.mkdir(parents=True, exist_ok=True)

        if zipfile.is_zipfile(download_path):
            with zipfile.ZipFile(download_path) as archive:
                archive.extractall(extract_dir)
            return self._locate_plugin_root(extract_dir), temp_root

        if tarfile.is_tarfile(download_path):
            with tarfile.open(download_path) as archive:
                archive.extractall(extract_dir)
            return self._locate_plugin_root(extract_dir), temp_root

        raise PluginManagerError(
            f"Unsupported plugin artifact from URL '{source_url}'. Expected zip/tar archive or git source."
        )

    @staticmethod
    def _resolve_loaded_source_dir(loaded: LoadedPlugin) -> Path:
        if not loaded.source:
            raise PluginManagerError(f"Loader did not provide source path for plugin '{loaded.name}'")
        return Path(loaded.source).expanduser().resolve()

    def _load_plugin_from_marketplace(
        self,
        plugin_id: str,
        version: Optional[str],
        marketplace_client: Optional[MarketplaceClient] = None,
    ) -> tuple[LoadedPlugin, Path, Path]:
        client = marketplace_client or MarketplaceClient()
        details = client.get_plugin_details(plugin_id)
        if not details:
            raise PluginManagerError(f"Plugin '{plugin_id}' not found in marketplace")

        download_url = ""
        if version:
            versions = client.get_plugin_versions(plugin_id)
            for item in versions:
                if str(item.get("version", "")).strip() == version:
                    download_url = str(item.get("download_url", "")).strip()
                    break
            if not download_url:
                raise PluginManagerError(
                    f"Plugin '{plugin_id}' does not have requested version '{version}' in marketplace"
                )
        else:
            download_url = str(details.get("download_url", "")).strip()

        if not download_url:
            raise PluginManagerError(f"Marketplace plugin '{plugin_id}' has no download URL")

        if self._is_git_source(download_url):
            loaded = self.git_loader.load(download_url, ref=version)
            source_dir = self._resolve_loaded_source_dir(loaded)
            return loaded, source_dir, source_dir

        plugin_root, temp_root = self._download_and_extract_plugin_from_url(download_url)
        loaded = self.local_loader.load(plugin_root)
        return loaded, plugin_root, temp_root

    def _load_plugin_for_install(
        self,
        source: str,
        version: Optional[str],
        marketplace_client: Optional[MarketplaceClient] = None,
    ) -> tuple[LoadedPlugin, Path, Optional[Path]]:
        candidate_path = Path(source).expanduser()

        if candidate_path.exists():
            loaded = self.local_loader.load(candidate_path)
            return loaded, candidate_path.resolve(), None

        if self._is_git_source(source):
            loaded = self.git_loader.load(source, ref=version)
            source_dir = self._resolve_loaded_source_dir(loaded)
            return loaded, source_dir, source_dir

        if self._is_url(source):
            plugin_root, temp_root = self._download_and_extract_plugin_from_url(source)
            loaded = self.local_loader.load(plugin_root)
            return loaded, plugin_root, temp_root

        return self._load_plugin_from_marketplace(
            source,
            version,
            marketplace_client=marketplace_client,
        )

    def _persist_installed_plugin(
        self,
        *,
        loaded_plugin: LoadedPlugin,
        source_dir: Path,
        install_origin: str,
    ) -> tuple[LoadedPlugin, Path]:
        self._ensure_storage()

        install_dir = (self.install_root / loaded_plugin.name).resolve()
        source_dir = source_dir.expanduser().resolve()

        if install_dir != source_dir:
            if install_dir.exists():
                shutil.rmtree(install_dir)
            shutil.copytree(source_dir, install_dir)
        elif not install_dir.exists():
            raise PluginManagerError(f"Plugin source path does not exist: {source_dir}")

        reloaded = self.local_loader.load(install_dir)
        reloaded.state.state = PluginLifecycleState.ENABLED

        state = self._load_plugin_state()
        state_plugins = state.setdefault("plugins", {})
        state_plugins[reloaded.name] = {
            "path": str(install_dir),
            "enabled": True,
            "source": install_origin,
            "version": reloaded.manifest.version,
            "author": reloaded.manifest.author,
            "description": reloaded.manifest.description,
            "installed_at": datetime.now(timezone.utc).isoformat(),
            "config": {
                "settings": reloaded.config.settings,
                "secrets": reloaded.config.secrets,
                "ui_schema": reloaded.config.ui_schema,
            },
        }
        self._save_plugin_state(state)

        return reloaded, install_dir

    def _load_runtime_registry(self) -> tuple[PluginRegistry, dict[str, Any], dict[str, str]]:
        state = self._load_plugin_state()
        registry = PluginRegistry()
        registry.clear()
        load_errors: dict[str, str] = {}

        plugins_payload = state.get("plugins", {})
        if not isinstance(plugins_payload, dict):
            return registry, {"plugins": {}}, load_errors

        for plugin_name, metadata in plugins_payload.items():
            if not isinstance(metadata, dict):
                load_errors[plugin_name] = "Invalid plugin metadata format"
                continue

            plugin_path = Path(str(metadata.get("path", ""))).expanduser()
            if not plugin_path.exists():
                load_errors[plugin_name] = f"Plugin path not found: {plugin_path}"
                continue

            try:
                loaded = self.local_loader.load(plugin_path)
                loaded.state.state = (
                    PluginLifecycleState.ENABLED
                    if bool(metadata.get("enabled", True))
                    else PluginLifecycleState.DISABLED
                )

                config = metadata.get("config")
                if isinstance(config, dict):
                    settings = config.get("settings", {})
                    secrets = config.get("secrets", {})
                    ui_schema = config.get("ui_schema", {})
                    loaded.config.settings = settings if isinstance(settings, dict) else {}
                    loaded.config.secrets = secrets if isinstance(secrets, dict) else {}
                    loaded.config.ui_schema = ui_schema if isinstance(ui_schema, dict) else {}

                registry.register(loaded)
            except Exception as exc:
                load_errors[plugin_name] = str(exc)

        return registry, state, load_errors

    def _cleanup_temp_dir(self, temp_dir: Optional[Path]) -> None:
        if temp_dir is None:
            return
        temp_path = temp_dir.expanduser().resolve()
        if temp_path == self.install_root.resolve():
            return
        shutil.rmtree(temp_path, ignore_errors=True)
