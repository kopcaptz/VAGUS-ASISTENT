"""
Команды управления задачами: vagus task create/status/list.
"""

import sys
import time
from typing import Optional

try:
    import typer
except ImportError:
    typer = None  # type: ignore[assignment]

from ..utils.api_client import CLIApiClient
from ..utils.output import print_dict, print_error, print_info, print_success, print_table

if typer is not None:
    app = typer.Typer(help="Управление задачами")
else:
    app = None  # type: ignore[assignment]


def _get_app():
    if typer is None:
        raise RuntimeError("typer not installed. pip install typer")
    return app


if typer is not None:

    @app.command("create")
    def create_task(
        prompt: str = typer.Argument(..., help="Запрос для выполнения"),
        task_type: str = typer.Option("default", "--type", "-t", help="Тип задачи"),
        wait: bool = typer.Option(True, "--wait/--no-wait", help="Ожидать завершения"),
    ):
        """Создать и выполнить новую задачу."""
        client = CLIApiClient()
        try:
            response = client.create_task(prompt=prompt, task_type=task_type)
            task_id = response["task_id"]
            print_success(f"Задача создана: {task_id}")

            if wait:
                print_info("Ожидание результата...")
                for _ in range(120):
                    time.sleep(0.5)
                    status_data = client.get_task_status(task_id)
                    status = status_data.get("status", "")

                    if status == "completed":
                        print_success("Задача выполнена!")
                        result = status_data.get("result", {})
                        if isinstance(result, dict):
                            print(result.get("content", str(result)))
                        else:
                            print(str(result))
                        return
                    elif status == "failed":
                        print_error(f"Ошибка: {status_data.get('error')}")
                        raise typer.Exit(code=1)

                print_error("Таймаут ожидания")
                raise typer.Exit(code=1)
        except Exception as e:
            if isinstance(e, (SystemExit,)):
                raise
            print_error(f"Ошибка: {e}")
            raise typer.Exit(code=1)

    @app.command("status")
    def get_status(task_id: str = typer.Argument(..., help="ID задачи")):
        """Получить статус задачи."""
        client = CLIApiClient()
        try:
            data = client.get_task_status(task_id)
            print_dict(f"Задача {task_id}", data)
        except Exception as e:
            print_error(f"Ошибка: {e}")
            raise typer.Exit(code=1)

    @app.command("list")
    def list_tasks(
        limit: int = typer.Option(10, "--limit", "-n", help="Количество задач"),
    ):
        """Показать список последних задач."""
        client = CLIApiClient()
        try:
            tasks = client.list_tasks(limit=limit)
            rows = []
            for t in tasks:
                rows.append([
                    str(t.get("task_id", "")),
                    str(t.get("status", "")),
                    str(t.get("created_at", "")),
                ])
            print_table("Список задач", ["ID", "Статус", "Создана"], rows)
        except Exception as e:
            print_error(f"Ошибка: {e}")
            raise typer.Exit(code=1)
