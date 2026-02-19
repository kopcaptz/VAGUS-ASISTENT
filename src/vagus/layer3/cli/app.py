"""
Root Typer CLI application for Vagus Asistent.
Usage: python -m vagus [command]
"""

import typer

from .commands import admin, agent, task
from .utils.config import save_config

app = typer.Typer(
    name="vagus",
    help="Vagus Asistent — multi-layer AI agent system",
    add_completion=True,
)

app.add_typer(task.app, name="task", help="Task management")
app.add_typer(agent.app, name="agent", help="Agent information")
app.add_typer(admin.app, name="admin", help="System administration")


@app.command()
def login(
    api_url: str = typer.Option("http://localhost:8000", help="API server URL"),
    username: str = typer.Option(..., prompt=True, help="Username"),
    password: str = typer.Option(..., prompt=True, hide_input=True, help="Password"),
):
    """Authenticate and save credentials."""
    from .utils.api_client import CLIApiClient

    client = CLIApiClient(api_url=api_url)
    try:
        tokens = client.login(username=username, password=password)
        save_config({
            "api_url": api_url,
            "api_key": tokens["access_token"],
        })
        typer.echo("Credentials saved.")
    except Exception as e:
        typer.echo(f"Login failed: {e}", err=True)
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
