"""
Команды администрирования: vagus admin status.
"""

try:
    import typer
except ImportError:
    typer = None  # type: ignore[assignment]

from ..utils.output import print_dict, print_error

if typer is not None:
    app = typer.Typer(help="Администрирование системы")
else:
    app = None  # type: ignore[assignment]


if typer is not None:

    @app.command("status")
    def system_status():
        """Показать статус системы."""
        from vagus.logging import generate_trace_id, logging_context

        with logging_context(trace_id=generate_trace_id(), component="cli"):
            from ..utils.api_client import CLIApiClient

            client = CLIApiClient()
            try:
                data = client.get_system_status()
                print_dict("Статус системы", data)
            except Exception as e:
                print_error(f"Ошибка: {e}")
                raise typer.Exit(code=1)
