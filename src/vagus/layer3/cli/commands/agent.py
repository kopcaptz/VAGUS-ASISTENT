"""
CLI agent commands: list.
"""

import typer
from rich.console import Console

from ..utils.api_client import CLIApiClient
from ..utils.output import print_agents

app = typer.Typer()
console = Console()


@app.command("list")
def list_agents():
    """Show available agents."""
    client = CLIApiClient()
    try:
        agents = client.get_agents()
    except Exception as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(code=1)
    if not agents:
        console.print("[yellow]No agents registered.[/yellow]")
    else:
        print_agents(agents)
