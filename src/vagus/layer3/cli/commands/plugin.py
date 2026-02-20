"""
Plugin management commands: create/install/list/enable/disable/uninstall.
"""

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

try:
    import typer
except ImportError:
    typer = None  # type: ignore[assignment]

from vagus.plugins.core.models import LoadedPlugin, PluginLifecycleState
from vagus.plugins.loader import GitLoader, LocalLoader, PluginLoaderError
from vagus.plugins.marketplace import MarketplaceClient
from vagus.plugins.registry import PluginRegistry
from vagus.plugins.tools import PluginTemplateError, PluginTemplateGenerator

from ..utils.output import print_error, print_info, print_success, print_table

PLUGIN_INSTALL_ROOT = Path.home() / ".vagus" / "plugins"
PLUGIN_STATE_FILE = PLUGIN_INSTALL_ROOT / "registry.json"


def _ensure_storage() -> None:
    PLUGIN_INSTALL_ROOT.mkdir(parents=True, exist_ok=True)


def _load_plugin_state() -> dict[str, Any]:
    if not PLUGIN_STATE_FILE.exists():
        return {"plugins": {}}

    try:
        payload = json.loads(PLUGIN_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"plugins": {}}

    if not isinstance(payload, dict):
        return {"plugins": {}}

    plugins_payload = payload.get("plugins")
    if not isinstance(plugins_payload, dict):
        return {"plugins": {}}

    return {"plugins": plugins_payload}


def _save_plugin_state(payload: dict[str, Any]) -> None:
    _ensure_storage()
    PLUGIN_STATE_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _is_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme.lower() in {"http", "https"}


def _is_git_source(value: str) -> bool:
    source = value.strip()
    if source.startswith("git@"):
        return True

    if source.endswith(".git"):
        return True

    parsed = urlparse(source)
    if parsed.scheme.lower() in {"http", "https"} and "github.com" in parsed.netloc.lower():
        path_parts = [part for part in parsed.path.split("/") if part]
        if len(path_parts) >= 2 and not source.lower().endswith((".zip", ".tar", ".tar.gz", ".tgz")):
            return True

    if parsed.scheme:
        return False

    if source.count("/") == 1 and not source.startswith((".", "~")):
        return True

    return False


def _locate_plugin_root(search_root: Path) -> Path:
    root_manifest = search_root / "manifest.json"
    if root_manifest.exists():
        return search_root

    manifests = sorted(search_root.rglob("manifest.json"), key=lambda item: len(item.parts))
    if not manifests:
        raise PluginLoaderError(f"manifest.json not found in extracted plugin source: {search_root}")
    return manifests[0].parent


def _download_and_extract_plugin_from_url(source_url: str) -> tuple[Path, Path]:
    temp_root = Path(tempfile.mkdtemp(prefix="vagus_plugin_url_"))
    download_name = Path(urlparse(source_url).path).name or "plugin_download.bin"
    download_path = temp_root / download_name

    try:
        with urlopen(source_url, timeout=30) as response:
            content = response.read()
    except Exception as exc:
        raise PluginLoaderError(f"Failed to download plugin from URL '{source_url}': {exc}") from exc

    download_path.write_bytes(content)

    extract_dir = temp_root / "extracted"
    extract_dir.mkdir(parents=True, exist_ok=True)

    if zipfile.is_zipfile(download_path):
        with zipfile.ZipFile(download_path) as archive:
            archive.extractall(extract_dir)
        return _locate_plugin_root(extract_dir), temp_root

    if tarfile.is_tarfile(download_path):
        with tarfile.open(download_path) as archive:
            archive.extractall(extract_dir)
        return _locate_plugin_root(extract_dir), temp_root

    raise PluginLoaderError(
        f"Unsupported plugin artifact from URL '{source_url}'. Expected zip/tar archive or git source."
    )


def _resolve_loaded_source_dir(loaded: LoadedPlugin) -> Path:
    if not loaded.source:
        raise PluginLoaderError(f"Loader did not provide source path for plugin '{loaded.name}'")
    return Path(loaded.source).expanduser().resolve()


def _load_plugin_from_marketplace(plugin_id: str, version: Optional[str]) -> tuple[LoadedPlugin, Path, Path]:
    client = MarketplaceClient()
    details = client.get_plugin_details(plugin_id)
    if not details:
        raise PluginLoaderError(f"Plugin '{plugin_id}' not found in marketplace")

    download_url = ""
    if version:
        versions = client.get_plugin_versions(plugin_id)
        for item in versions:
            if str(item.get("version", "")).strip() == version:
                download_url = str(item.get("download_url", "")).strip()
                break
        if not download_url:
            raise PluginLoaderError(
                f"Plugin '{plugin_id}' does not have requested version '{version}' in marketplace"
            )
    else:
        download_url = str(details.get("download_url", "")).strip()

    if not download_url:
        raise PluginLoaderError(f"Marketplace plugin '{plugin_id}' has no download URL")

    if _is_git_source(download_url):
        loaded = GitLoader().load(download_url, ref=version)
        source_dir = _resolve_loaded_source_dir(loaded)
        return loaded, source_dir, source_dir

    plugin_root, temp_root = _download_and_extract_plugin_from_url(download_url)
    loaded = LocalLoader().load(plugin_root)
    return loaded, plugin_root, temp_root


def _load_plugin_for_install(source: str, version: Optional[str]) -> tuple[LoadedPlugin, Path, Optional[Path]]:
    candidate_path = Path(source).expanduser()
    local_loader = LocalLoader()

    if candidate_path.exists():
        loaded = local_loader.load(candidate_path)
        return loaded, candidate_path.resolve(), None

    if _is_git_source(source):
        loaded = GitLoader().load(source, ref=version)
        source_dir = _resolve_loaded_source_dir(loaded)
        return loaded, source_dir, source_dir

    if _is_url(source):
        plugin_root, temp_root = _download_and_extract_plugin_from_url(source)
        loaded = local_loader.load(plugin_root)
        return loaded, plugin_root, temp_root

    return _load_plugin_from_marketplace(source, version)


def _persist_installed_plugin(
    loaded_plugin: LoadedPlugin,
    source_dir: Path,
    install_origin: str,
) -> tuple[LoadedPlugin, Path]:
    _ensure_storage()

    install_dir = (PLUGIN_INSTALL_ROOT / loaded_plugin.name).resolve()
    source_dir = source_dir.expanduser().resolve()

    if install_dir != source_dir:
        if install_dir.exists():
            shutil.rmtree(install_dir)
        shutil.copytree(source_dir, install_dir)
    elif not install_dir.exists():
        raise PluginLoaderError(f"Plugin source path does not exist: {source_dir}")

    reloaded = LocalLoader().load(install_dir)
    reloaded.state.state = PluginLifecycleState.ENABLED

    state = _load_plugin_state()
    state_plugins = state.setdefault("plugins", {})
    state_plugins[reloaded.name] = {
        "path": str(install_dir),
        "enabled": True,
        "source": install_origin,
        "version": reloaded.manifest.version,
        "author": reloaded.manifest.author,
        "description": reloaded.manifest.description,
        "installed_at": datetime.now(timezone.utc).isoformat(),
    }
    _save_plugin_state(state)

    return reloaded, install_dir


def _load_runtime_registry() -> tuple[PluginRegistry, dict[str, Any], dict[str, str]]:
    state = _load_plugin_state()
    registry = PluginRegistry()
    registry.clear()
    loader = LocalLoader()
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
            loaded = loader.load(plugin_path)
            loaded.state.state = (
                PluginLifecycleState.ENABLED
                if bool(metadata.get("enabled", True))
                else PluginLifecycleState.DISABLED
            )
            registry.register(loaded)
        except Exception as exc:
            load_errors[plugin_name] = str(exc)

    return registry, state, load_errors


def _cleanup_temp_dir(temp_dir: Optional[Path]) -> None:
    if temp_dir is None:
        return
    temp_path = temp_dir.expanduser().resolve()
    if temp_path == PLUGIN_INSTALL_ROOT.resolve():
        return
    shutil.rmtree(temp_path, ignore_errors=True)


if typer is not None:
    app = typer.Typer(help="Управление плагинами")
else:
    app = None  # type: ignore[assignment]


if typer is not None:

    @app.command("create")
    def create_plugin(
        name: str = typer.Argument(..., help="Имя плагина"),
        template: str = typer.Option("basic", help="Шаблон: basic/webhook/llm/ui"),
        destination: str = typer.Option(".", help="Директория назначения"),
    ):
        """Создать новый плагин по шаблону."""
        generator = PluginTemplateGenerator(destination_root=destination)
        try:
            plugin_dir = generator.create(name=name, template=template)  # type: ignore[arg-type]
            print_success(f"Плагин создан: {plugin_dir}")
        except PluginTemplateError as exc:
            print_error(str(exc))
            raise typer.Exit(code=1)

    @app.command("install")
    def install_plugin(
        path_or_url: str = typer.Argument(..., help="Локальный путь, URL или marketplace ID"),
        version: Optional[str] = typer.Option(
            None,
            "--version",
            help="Версия (для git ref/marketplace версий)",
        ),
    ):
        """Установить плагин из локального пути, URL или marketplace."""
        registry = PluginRegistry()
        temp_dir: Optional[Path] = None
        try:
            loaded, source_dir, cleanup_dir = _load_plugin_for_install(path_or_url, version)
            temp_dir = cleanup_dir
            installed, install_dir = _persist_installed_plugin(
                loaded,
                source_dir,
                install_origin=path_or_url,
            )
            registry.register(installed)
            print_success(
                f"Плагин установлен: {installed.name} {installed.manifest.version} ({install_dir})"
            )
        except Exception as exc:
            print_error(f"Ошибка установки плагина: {exc}")
            raise typer.Exit(code=1)
        finally:
            _cleanup_temp_dir(temp_dir)

    @app.command("list")
    def list_plugins(
        enabled: bool = typer.Option(False, "--enabled", help="Показать только включенные"),
        disabled: bool = typer.Option(False, "--disabled", help="Показать только отключенные"),
        all_plugins: bool = typer.Option(False, "--all", help="Показать все плагины"),
    ):
        """Показать список установленных плагинов."""
        if enabled and disabled:
            print_error("Нельзя одновременно использовать --enabled и --disabled")
            raise typer.Exit(code=1)
        if all_plugins and (enabled or disabled):
            print_error("--all нельзя комбинировать с --enabled/--disabled")
            raise typer.Exit(code=1)

        registry, state, load_errors = _load_runtime_registry()
        plugins_payload = state.get("plugins", {})
        if not isinstance(plugins_payload, dict):
            plugins_payload = {}

        if enabled:
            loaded_plugins = registry.list_plugins(state=PluginLifecycleState.ENABLED)
        elif disabled:
            loaded_plugins = registry.list_plugins(state=PluginLifecycleState.DISABLED)
        else:
            loaded_plugins = registry.list_plugins()

        rows: list[list[str]] = []
        emitted: set[str] = set()

        for plugin in loaded_plugins:
            emitted.add(plugin.name)
            rows.append(
                [
                    plugin.name,
                    plugin.manifest.version,
                    plugin.state.state.value,
                    plugin.manifest.author,
                    plugin.manifest.description,
                ]
            )

        # Include persisted but currently unloadable plugins in list output.
        if not enabled and not disabled:
            for plugin_name, metadata in plugins_payload.items():
                if plugin_name in emitted:
                    continue
                if not isinstance(metadata, dict):
                    continue
                rows.append(
                    [
                        plugin_name,
                        str(metadata.get("version", "unknown")),
                        "ERROR" if plugin_name in load_errors else "UNKNOWN",
                        str(metadata.get("author", "unknown")),
                        str(
                            metadata.get("description")
                            or load_errors.get(plugin_name, "Plugin metadata exists but plugin not loaded")
                        ),
                    ]
                )

        if not rows:
            print_info("Установленные плагины не найдены.")
            return

        print_table(
            "Установленные плагины",
            ["Name", "Version", "Status", "Author", "Description"],
            rows,
        )

    @app.command("enable")
    def enable_plugin(
        plugin_name: str = typer.Argument(..., help="Имя плагина"),
    ):
        """Включить установленный плагин."""
        registry, state, load_errors = _load_runtime_registry()
        plugins_payload = state.get("plugins", {})
        if not isinstance(plugins_payload, dict) or plugin_name not in plugins_payload:
            print_error(f"Плагин '{plugin_name}' не найден")
            raise typer.Exit(code=1)

        plugins_payload[plugin_name]["enabled"] = True
        _save_plugin_state(state)

        plugin = registry.get_plugin(plugin_name)
        if plugin is not None:
            plugin.state.state = PluginLifecycleState.ENABLED
            registry.register(plugin)

        if plugin_name in load_errors:
            print_info(f"Плагин отмечен как включенный, но пока не загружается: {load_errors[plugin_name]}")
        print_success(f"Плагин включен: {plugin_name}")

    @app.command("disable")
    def disable_plugin(
        plugin_name: str = typer.Argument(..., help="Имя плагина"),
    ):
        """Отключить установленный плагин."""
        registry, state, load_errors = _load_runtime_registry()
        plugins_payload = state.get("plugins", {})
        if not isinstance(plugins_payload, dict) or plugin_name not in plugins_payload:
            print_error(f"Плагин '{plugin_name}' не найден")
            raise typer.Exit(code=1)

        plugins_payload[plugin_name]["enabled"] = False
        _save_plugin_state(state)

        plugin = registry.get_plugin(plugin_name)
        if plugin is not None:
            plugin.state.state = PluginLifecycleState.DISABLED
            registry.register(plugin)

        if plugin_name in load_errors:
            print_info(f"Плагин отмечен как отключенный, но пока не загружается: {load_errors[plugin_name]}")
        print_success(f"Плагин отключен: {plugin_name}")

    @app.command("uninstall")
    def uninstall_plugin(
        plugin_name: str = typer.Argument(..., help="Имя плагина"),
        force: bool = typer.Option(False, "--force", help="Игнорировать ошибки удаления файлов"),
    ):
        """Удалить плагин из системы."""
        registry, state, _ = _load_runtime_registry()
        plugins_payload = state.get("plugins", {})
        if not isinstance(plugins_payload, dict) or plugin_name not in plugins_payload:
            print_error(f"Плагин '{plugin_name}' не найден")
            raise typer.Exit(code=1)

        metadata = plugins_payload[plugin_name]
        plugin_path = Path(str(metadata.get("path", ""))).expanduser()

        if plugin_path.exists():
            try:
                shutil.rmtree(plugin_path)
            except Exception as exc:
                if not force:
                    print_error(f"Не удалось удалить файлы плагина: {exc}")
                    raise typer.Exit(code=1)
                print_info(f"Предупреждение: удаление файлов с --force: {exc}")

        plugins_payload.pop(plugin_name, None)
        _save_plugin_state(state)
        registry.unregister(plugin_name)
        print_success(f"Плагин удален: {plugin_name}")
