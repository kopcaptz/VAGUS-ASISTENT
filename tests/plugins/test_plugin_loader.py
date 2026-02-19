"""Tests for plugin loaders."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from vagus.plugins.loader import (
    DependencyResolutionError,
    GitLoader,
    LocalLoader,
    PyPILoader,
)


def _write_test_plugin(
    plugin_dir: Path,
    plugin_name: str,
    module_name: str,
    dependencies: list[str] | None = None,
) -> None:
    plugin_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "name": plugin_name,
        "version": "1.0.0",
        "author": "Tests",
        "description": "Loader test plugin",
        "dependencies": dependencies or [],
        "python_version": ">=3.10",
        "vagus_version": ">=0.1.0",
        "entry_point": f"{module_name}:PluginEntry",
        "hooks": [],
        "permissions": [],
    }
    (plugin_dir / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (plugin_dir / f"{module_name}.py").write_text(
        "class PluginEntry:\n"
        "    def ping(self):\n"
        "        return 'pong'\n",
        encoding="utf-8",
    )


def test_local_loader_loads_plugin_from_directory(tmp_path: Path):
    plugin_dir = tmp_path / "local_plugin"
    _write_test_plugin(plugin_dir, plugin_name="local_plugin", module_name="local_entry")

    loaded = LocalLoader().load(plugin_dir)
    assert loaded.manifest.name == "local_plugin"
    assert loaded.entry_point.__name__ == "PluginEntry"


def test_local_loader_checks_dependencies(tmp_path: Path):
    plugin_dir = tmp_path / "broken_plugin"
    _write_test_plugin(
        plugin_dir,
        plugin_name="broken_plugin",
        module_name="broken_entry",
        dependencies=["dependency_that_should_not_exist_123456>=1.0.0"],
    )

    with pytest.raises(DependencyResolutionError):
        LocalLoader().load(plugin_dir)


def test_git_loader_delegates_to_local_loader(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    source_plugin = tmp_path / "git_source_plugin"
    _write_test_plugin(source_plugin, plugin_name="git_plugin", module_name="git_entry")

    loader = GitLoader()
    captured: dict[str, list[str]] = {}

    def fake_run(command: list[str]) -> None:
        captured["command"] = command
        target_dir = Path(command[-1])
        shutil.copytree(source_plugin, target_dir, dirs_exist_ok=True)

    monkeypatch.setattr(loader, "_run_command", fake_run)

    loaded = loader.load("vagus-ai/git-plugin")
    assert loaded.manifest.name == "git_plugin"
    assert captured["command"][:2] == ["git", "clone"]
    assert captured["command"][-2] == "https://github.com/vagus-ai/git-plugin.git"


def test_pypi_loader_installs_and_loads_plugin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    loader = PyPILoader()
    captured: dict[str, list[str]] = {}

    def fake_run(command: list[str]) -> None:
        captured["command"] = command
        target_dir = Path(command[command.index("--target") + 1])
        plugin_root = target_dir / "pypi_loaded_plugin"
        _write_test_plugin(
            plugin_root,
            plugin_name="pypi_plugin",
            module_name="pypi_entry",
        )

    monkeypatch.setattr(loader, "_run_command", fake_run)

    loaded = loader.load("pypi-plugin-demo", version="1.0.0")
    assert loaded.manifest.name == "pypi_plugin"
    assert captured["command"][0].endswith("python") or "python" in captured["command"][0]
    assert "pip" in captured["command"]
