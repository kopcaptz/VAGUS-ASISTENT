"""
Форматирование вывода CLI (plain-text, без обязательной зависимости от rich).
"""

from typing import Any, Dict, List, Optional


def print_table(title: str, columns: List[str], rows: List[List[str]]) -> None:
    """Выводит таблицу. Использует rich если доступен, иначе plain-text."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title=title)
        for col in columns:
            table.add_column(col)
        for row in rows:
            table.add_row(*row)
        console.print(table)
    except ImportError:
        print(f"\n{title}")
        print("-" * 60)
        print(" | ".join(columns))
        print("-" * 60)
        for row in rows:
            print(" | ".join(row))
        print()


def print_dict(title: str, data: Dict[str, Any]) -> None:
    """Выводит словарь."""
    try:
        from rich.console import Console
        from rich.table import Table

        console = Console()
        table = Table(title=title)
        table.add_column("Field", style="cyan")
        table.add_column("Value", style="white")
        for k, v in data.items():
            table.add_row(str(k), str(v))
        console.print(table)
    except ImportError:
        print(f"\n{title}")
        for k, v in data.items():
            print(f"  {k}: {v}")


def print_success(msg: str) -> None:
    try:
        from rich.console import Console
        Console().print(f"[bold green]{msg}[/bold green]")
    except ImportError:
        print(msg)


def print_error(msg: str) -> None:
    try:
        from rich.console import Console
        Console().print(f"[bold red]{msg}[/bold red]")
    except ImportError:
        print(f"ERROR: {msg}")


def print_info(msg: str) -> None:
    try:
        from rich.console import Console
        Console().print(f"[yellow]{msg}[/yellow]")
    except ImportError:
        print(msg)
