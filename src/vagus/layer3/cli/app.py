"""
Корневое Typer-приложение: vagus.
"""

from importlib import import_module
try:
    import click
    import typer
    from typer.core import TyperGroup
except ImportError:
    click = None  # type: ignore[assignment]
    typer = None  # type: ignore[assignment]
    TyperGroup = None  # type: ignore[assignment]

from .utils.config import save_config
from .utils.output import print_success

LAZY_SUBCOMMANDS: dict[str, tuple[str, str, str]] = {
    "task": ("vagus.layer3.cli.commands.task", "app", "Управление задачами"),
    "agent": ("vagus.layer3.cli.commands.agent", "app", "Информация об агентах"),
    "admin": ("vagus.layer3.cli.commands.admin", "app", "Администрирование"),
    "keys": ("vagus.layer3.cli.commands.keys", "app", "Управление API ключами"),
    "backup": ("vagus.layer3.cli.commands.backup", "app", "Backup и restore ключей"),
    "plugin": ("vagus.layer3.cli.commands.plugin", "app", "Управление плагинами"),
}


class LazySubcommandGroup(TyperGroup):  # type: ignore[misc]
    """
    Click group с ленивой загрузкой Typer-подкоманд.
    Это позволяет не импортировать тяжёлые modules при `vagus --help`.
    """

    def list_commands(self, ctx: click.Context) -> list[str]:
        names = list(super().list_commands(ctx))
        for command_name in LAZY_SUBCOMMANDS:
            if command_name not in names:
                names.append(command_name)
        return sorted(names)

    def get_command(self, ctx: click.Context, cmd_name: str) -> click.Command | None:
        command = super().get_command(ctx, cmd_name)
        if command is not None:
            return command

        spec = LAZY_SUBCOMMANDS.get(cmd_name)
        if spec is None:
            return None

        module_path, attr_name, _ = spec
        try:
            module = import_module(module_path)
            sub_app = getattr(module, attr_name, None)
            if sub_app is None:
                return None
            from typer.main import get_command as typer_get_command

            lazy_command = typer_get_command(sub_app)
            lazy_command.name = cmd_name
            return lazy_command
        except Exception:
            return None

    def format_commands(self, ctx: click.Context, formatter: click.HelpFormatter) -> None:
        rows: list[tuple[str, str]] = []
        eager_command_names = list(super().list_commands(ctx))

        for command_name in eager_command_names:
            command = super().get_command(ctx, command_name)
            if command is None or command.hidden:
                continue
            rows.append((command_name, command.get_short_help_str(formatter.width)))

        for command_name in sorted(LAZY_SUBCOMMANDS):
            if command_name in eager_command_names:
                continue
            rows.append((command_name, LAZY_SUBCOMMANDS[command_name][2]))

        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)


def create_app():
    """Создаёт Typer-приложение."""
    if typer is None or click is None or TyperGroup is None:
        raise RuntimeError("typer not installed. pip install typer")

    app = typer.Typer(
        name="vagus",
        help="Vagus Asistent — многослойная агентная AI-система",
        add_completion=True,
        cls=LazySubcommandGroup,
    )

    @app.callback()
    def root_callback() -> None:
        """Корневой callback для режима multi-command."""
        return None

    @app.command()
    def login(
        api_url: str = typer.Option("http://localhost:8000", help="URL API сервера"),
        api_key: str = typer.Option(..., prompt=True, hide_input=True, help="API-ключ"),
    ):
        """Аутентификация и сохранение учётных данных."""
        from vagus.logging import generate_trace_id, logging_context

        with logging_context(trace_id=generate_trace_id(), component="cli"):
            save_config({"api_url": api_url, "api_key": api_key})
            print_success("Учётные данные сохранены.")

    return app


if typer is not None and click is not None and TyperGroup is not None:
    app = create_app()

    def main():
        app()
else:

    def main():
        raise RuntimeError("typer not installed. pip install typer")


if __name__ == "__main__":
    main()
