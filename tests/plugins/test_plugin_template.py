"""Tests for plugin template generator and CLI integration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vagus.layer3.cli.app import create_app
from vagus.plugins.tools import PluginTemplateError, PluginTemplateGenerator, create_plugin_template


def test_plugin_template_generator_creates_basic_template(tmp_path: Path):
    generator = PluginTemplateGenerator(destination_root=tmp_path)
    plugin_dir = generator.create(name="demo_plugin", template="basic")

    assert (plugin_dir / "manifest.json").exists()
    assert (plugin_dir / "plugin.py").exists()
    manifest = json.loads((plugin_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["name"] == "demo_plugin"


@pytest.mark.parametrize(
    "template,extra_file",
    [
        ("webhook", "webhook_config.json"),
        ("llm", "llm_config.json"),
        ("ui", "ui_schema.json"),
    ],
)
def test_plugin_template_generator_adds_template_specific_files(
    tmp_path: Path,
    template: str,
    extra_file: str,
):
    generator = PluginTemplateGenerator(destination_root=tmp_path)
    plugin_dir = generator.create(name=f"{template}_plugin", template=template)  # type: ignore[arg-type]
    assert (plugin_dir / extra_file).exists()


def test_plugin_template_generator_rejects_invalid_name(tmp_path: Path):
    generator = PluginTemplateGenerator(destination_root=tmp_path)
    with pytest.raises(PluginTemplateError):
        generator.create(name="123-invalid", template="basic")


def test_plugin_template_generator_rejects_existing_directory(tmp_path: Path):
    existing = tmp_path / "demo_plugin"
    existing.mkdir()
    generator = PluginTemplateGenerator(destination_root=tmp_path)
    with pytest.raises(PluginTemplateError):
        generator.create(name="demo_plugin", template="basic")


def test_create_plugin_template_helper(tmp_path: Path):
    plugin_dir = create_plugin_template("helper_plugin", destination_root=tmp_path, template="basic")
    assert plugin_dir.exists()


def test_cli_plugin_create_command(tmp_path: Path):
    app = create_app()
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["plugin", "create", "cli_plugin", "--template", "basic", "--destination", str(tmp_path)],
    )
    assert result.exit_code == 0
    assert (tmp_path / "cli_plugin" / "manifest.json").exists()
