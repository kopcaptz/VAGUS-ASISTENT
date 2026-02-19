"""
CLI admin commands: status.
"""

import typer
from rich.console import Console

from ..utils.api_client import CLIApiClient
from ..utils.output import print_status

app = typer.Typer()
console = Console()


@app.command("status")
def system_status():
    """Show system status and metrics."""
    client = CLIApiClient()
    try:
        data = client.get_system_status()
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)
    print_status(data)
