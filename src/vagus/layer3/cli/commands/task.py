"""
CLI task commands: create, status, list.
"""

import time

import typer
from rich.console import Console

from ..utils.api_client import CLIApiClient
from ..utils.output import print_task_detail, print_task_table

app = typer.Typer()
console = Console()


@app.command("create")
def create_task(
    prompt: str = typer.Argument(..., help="Task prompt"),
    task_type: str = typer.Option("default", "--type", "-t", help="Task type: default, research, code, analysis"),
    wait: bool = typer.Option(True, "--wait/--no-wait", help="Wait for task completion"),
):
    """Create and execute a new task."""
    client = CLIApiClient()

    with console.status("[bold green]Creating task..."):
        try:
            response = client.create_task(prompt=prompt, task_type=task_type)
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            raise typer.Exit(code=1)

    task_id = response["task_id"]
    console.print(f"[green]Task created:[/green] [bold]{task_id}[/bold]")

    if wait:
        console.print("[yellow]Waiting for result...[/yellow]")
        for _ in range(240):  # up to 2 minutes
            time.sleep(0.5)
            try:
                status_data = client.get_task_status(task_id)
            except Exception as e:
                console.print(f"[red]Error polling status:[/red] {e}")
                raise typer.Exit(code=1)

            status = status_data.get("status", "unknown")
            if status == "completed":
                console.print("\n[bold green]Task completed![/bold green]")
                result = status_data.get("result", {})
                if isinstance(result, dict):
                    console.print(result.get("content", str(result)))
                else:
                    console.print(str(result))
                break
            elif status == "failed":
                console.print(f"\n[bold red]Task failed:[/bold red] {status_data.get('error')}")
                raise typer.Exit(code=1)
        else:
            console.print("[yellow]Timeout waiting for task completion.[/yellow]")


@app.command("status")
def get_status(task_id: str = typer.Argument(..., help="Task ID")):
    """Get task status."""
    client = CLIApiClient()
    try:
        data = client.get_task_status(task_id)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)
    print_task_detail(data)


@app.command("list")
def list_tasks(limit: int = typer.Option(10, "--limit", "-n", help="Number of tasks to show")):
    """Show recent tasks."""
    client = CLIApiClient()
    try:
        tasks = client.list_tasks(limit=limit)
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)
    if not tasks:
        console.print("[yellow]No tasks found.[/yellow]")
    else:
        print_task_table(tasks)
