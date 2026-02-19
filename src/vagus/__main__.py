"""
Entry point for: python -m vagus
Delegates to the Typer CLI application.
"""

from vagus.layer3.cli.app import app

if __name__ == "__main__":
    app()
