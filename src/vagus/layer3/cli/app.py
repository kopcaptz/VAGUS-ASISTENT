"""
Корневое Typer-приложение: vagus.
"""

try:
    import typer
except ImportError:
    typer = None  # type: ignore[assignment]

from vagus.logging import generate_trace_id, logging_context

from .utils.config import save_config
from .utils.output import print_success


def create_app():
    """Создаёт Typer-приложение."""
    if typer is None:
        raise RuntimeError("typer not installed. pip install typer")

    app = typer.Typer(
        name="vagus",
        help="Vagus Asistent — многослойная агентная AI-система",
        add_completion=True,
    )

    from .commands.task import app as task_app
    from .commands.agent import app as agent_app
    from .commands.admin import app as admin_app

    if task_app is not None:
        app.add_typer(task_app, name="task", help="Управление задачами")
    if agent_app is not None:
        app.add_typer(agent_app, name="agent", help="Информация об агентах")
    if admin_app is not None:
        app.add_typer(admin_app, name="admin", help="Администрирование")

    @app.command()
    def login(
        api_url: str = typer.Option("http://localhost:8000", help="URL API сервера"),
        api_key: str = typer.Option(..., prompt=True, hide_input=True, help="API-ключ"),
    ):
        """Аутентификация и сохранение учётных данных."""
        with logging_context(trace_id=generate_trace_id(), component="cli"):
            save_config({"api_url": api_url, "api_key": api_key})
            print_success("Учётные данные сохранены.")

    return app


if typer is not None:
    app = create_app()

    def main():
        app()
else:

    def main():
        raise RuntimeError("typer not installed. pip install typer")


if __name__ == "__main__":
    main()
