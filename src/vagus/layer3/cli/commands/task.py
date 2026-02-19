"""
Команды для работы с задачами.
Создание, запуск, статус задач через CLI.
"""

import json
import time
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..utils.api_client import CLIApiClient
from ..utils.config import load_config

task_app = typer.Typer(help="Команды для работы с задачами")
console = Console()


def _require_config() -> None:
    """Проверяет наличие конфигурации."""
    config = load_config()
    if not config.get("api_url") or not config.get("api_key"):
        console.print("[red]Ошибка: выполните [bold]vagus login[/bold] для настройки API[/red]")
        raise typer.Exit(1)


@task_app.command("create")
def task_create(
    prompt: str = typer.Argument(..., help="Текст запроса для задачи"),
    task_type: str = typer.Option("default", "--type", "-t", help="Тип задачи"),
    wait: bool = typer.Option(False, "--wait/--no-wait", "-w/", help="Ожидать завершения и вывести результат"),
):
    """Создаёт задачу через API."""
    _require_config()
    client = CLIApiClient()
    try:
        result = client.create_task(prompt=prompt, task_type=task_type)
    except Exception as e:
        console.print(f"[red]Ошибка API: {e}[/red]")
        raise typer.Exit(1)

    task_id = result["task_id"]
    console.print(f"[green]Задача создана:[/green] {task_id}")
    console.print(f"  Статус: {result['status']}")
    console.print(f"  Проверить: {result['status_endpoint']}")

    if wait:
        console.print("\n[dim]Ожидание завершения...[/dim]")
        while True:
            time.sleep(0.5)
            try:
                status = client.get_task_status(task_id)
            except Exception as e:
                console.print(f"[red]Ошибка: {e}[/red]")
                raise typer.Exit(1)

            if status["status"] in ("completed", "failed"):
                if status["status"] == "completed":
                    res = status.get("result")
                    if res is not None:
                        content = json.dumps(res, ensure_ascii=False, indent=2) if isinstance(res, dict) else str(res)
                        console.print(Panel(content, title="Результат", border_style="green"))
                    else:
                        console.print("[green]Задача завершена[/green]")
                else:
                    console.print(f"[red]Ошибка: {status.get('error', 'Unknown')}[/red]")
                break
            console.print(f"  [dim]Статус: {status['status']}[/dim]")


@task_app.command("status")
def task_status(
    task_id: str = typer.Argument(..., help="Идентификатор задачи"),
):
    """Выводит статус задачи в виде таблицы."""
    _require_config()
    client = CLIApiClient()
    try:
        status = client.get_task_status(task_id)
    except Exception as e:
        console.print(f"[red]Ошибка API: {e}[/red]")
        raise typer.Exit(1)

    table = Table(title=f"Задача {task_id}")
    table.add_column("Поле", style="cyan")
    table.add_column("Значение", style="green")
    table.add_row("task_id", status["task_id"])
    table.add_row("status", status["status"])
    table.add_row("created_at", str(status["created_at"]))
    table.add_row("updated_at", str(status["updated_at"]))
    if status.get("error"):
        table.add_row("error", status["error"])
    if status.get("result") is not None:
        result_str = json.dumps(status["result"], ensure_ascii=False)
        if len(result_str) > 80:
            result_str = result_str[:77] + "..."
        table.add_row("result", result_str)
    console.print(table)


@task_app.command("list")
def task_list(
    limit: int = typer.Option(10, "--limit", "-l", help="Максимум задач в списке"),
):
    """Выводит список последних задач."""
    _require_config()
    client = CLIApiClient()
    try:
        tasks = client.list_tasks(limit=limit)
    except Exception as e:
        console.print(f"[red]Ошибка API: {e}[/red]")
        raise typer.Exit(1)

    if not tasks:
        console.print("[dim]Нет задач[/dim]")
        return

    table = Table(title="Последние задачи")
    table.add_column("task_id", style="cyan")
    table.add_column("status", style="green")
    table.add_column("prompt", style="white")
    table.add_column("created_at", style="dim")
    for t in tasks:
        prompt = t.get("prompt", "") or "-"
        if len(prompt) > 50:
            prompt = prompt[:47] + "..."
        table.add_row(t["task_id"], t["status"], prompt, str(t["created_at"]))

    console.print(table)
