"""
Команды для работы с агентами: vagus agent list.
"""

try:
    import typer
except ImportError:
    typer = None  # type: ignore[assignment]

from vagus.logging import generate_trace_id, logging_context

from ..utils.api_client import CLIApiClient
from ..utils.output import print_error, print_table

if typer is not None:
    app = typer.Typer(help="Информация об агентах")
else:
    app = None  # type: ignore[assignment]


if typer is not None:

    @app.command("list")
    def list_agents():
        """Показать список доступных агентов."""
        with logging_context(trace_id=generate_trace_id(), component="cli"):
            client = CLIApiClient()
            try:
                agents = client.get_agents()
                rows = []
                for a in agents:
                    rows.append([
                        str(a.get("name", "")),
                        str(a.get("description", "")),
                        ", ".join(a.get("task_types", [])),
                        "Yes" if a.get("is_available") else "No",
                    ])
                print_table("Агенты", ["Name", "Description", "Task Types", "Available"], rows)
            except Exception as e:
                print_error(f"Ошибка: {e}")
                raise typer.Exit(code=1)
