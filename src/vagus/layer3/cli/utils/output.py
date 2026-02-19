"""
Rich output formatting utilities for CLI.
"""

from typing import Any, Dict, List

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


def print_task_table(tasks: List[Dict[str, Any]]) -> None:
    """Prints a list of tasks as a rich table."""
    table = Table(title="Tasks")
    table.add_column("ID", style="cyan", no_wrap=True, max_width=36)
    table.add_column("Status", style="green")
    table.add_column("Created", style="white")

    for task in tasks:
        status = task.get("status", "unknown")
        style = {
            "pending": "yellow",
            "in_progress": "blue",
            "completed": "green",
            "failed": "red",
        }.get(status, "white")
        table.add_row(
            task.get("task_id", "?"),
            f"[{style}]{status}[/{style}]",
            task.get("created_at", "?"),
        )
    console.print(table)


def print_task_detail(task: Dict[str, Any]) -> None:
    """Prints detailed task info as a table."""
    table = Table(title=f"Task {task.get('task_id', '?')}")
    table.add_column("Field", style="cyan")
    table.add_column("Value", style="white")

    for key, value in task.items():
        table.add_row(str(key), str(value))
    console.print(table)


def print_agents(agents: List[Dict[str, Any]]) -> None:
    """Prints agent list as a table."""
    table = Table(title="Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Description", style="white")
    table.add_column("Task Types", style="green")
    table.add_column("Available", style="yellow")

    for agent in agents:
        table.add_row(
            agent.get("name", "?"),
            agent.get("description", ""),
            ", ".join(agent.get("task_types", [])),
            str(agent.get("is_available", False)),
        )
    console.print(table)


def print_status(status: Dict[str, Any]) -> None:
    """Prints system status as a panel."""
    lines = [
        f"Agents: {status.get('layer2_agents_count', 0)}",
        f"Active tasks: {status.get('active_tasks_count', 0)}",
        f"Uptime: {status.get('uptime_seconds', 0):.1f}s",
    ]
    layer1 = status.get("layer1_stats", {})
    if layer1:
        lines.append(f"L1 requests: {layer1.get('requests', 0)}")
        lines.append(f"L1 total cost: ${layer1.get('total_cost', 0):.4f}")

    console.print(Panel("\n".join(lines), title="System Status", border_style="green"))
