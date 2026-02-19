"""
CLI приложение — точка входа для консольных команд.
Инициализация Typer приложения и регистрация групп команд.
"""

import typer
from rich.console import Console

from .commands import agent, task
from .utils.config import get_config_path, save_config

app = typer.Typer(
    name="vagus",
    help="Vagus Asistent — CLI для управления задачами и агентами",
)
console = Console()


@app.command()
def login(
    api_url: str = typer.Option("http://localhost:8000", "--url", "-u", help="URL API"),
    api_key: str = typer.Option(..., "--token", "-t", prompt="API Token (access_token)", help="JWT access token"),
):
    """Сохраняет API URL и токен в ~/.vagus/config.json."""
    save_config(api_url=api_url, api_key=api_key)
    path = get_config_path()
    console.print(f"[green]Конфигурация сохранена в[/green] {path}")
    console.print("[dim]Используйте access_token из POST /api/v1/auth/token[/dim]")


app.add_typer(task.task_app, name="task")
app.add_typer(agent.agent_app, name="agent")


def main() -> None:
    """Точка входа CLI."""
    app()


if __name__ == "__main__":
    main()
