"""
Plugin management commands: vagus plugin create.
"""

from __future__ import annotations

try:
    import typer
except ImportError:
    typer = None  # type: ignore[assignment]

from vagus.plugins.tools import PluginTemplateError, PluginTemplateGenerator

from ..utils.output import print_error, print_success

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
