"""
Команды управления API ключами: vagus keys list/health/validate.
"""

from __future__ import annotations

import json

try:
    import typer
except ImportError:
    typer = None  # type: ignore[assignment]

from ..utils.output import print_error, print_success, print_table

if typer is not None:
    app = typer.Typer(help="Управление API ключами")
else:
    app = None  # type: ignore[assignment]


def _cli_context():
    from vagus.logging import generate_trace_id, logging_context

    return logging_context(trace_id=generate_trace_id(), component="cli")


def _emit_json(payload) -> None:
    if typer is None:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
        return
    typer.echo(json.dumps(payload, ensure_ascii=False, indent=2, default=str))


if typer is not None:

    @app.command("list")
    def list_keys(
        as_json: bool = typer.Option(False, "--json", help="Вывести сырые JSON данные"),
    ):
        """Показать список API ключей."""
        with _cli_context():
            from ..utils.api_client import CLIApiClient

            client = CLIApiClient()
            try:
                keys = client.list_api_keys()
                if as_json:
                    _emit_json(keys)
                    return

                if not keys:
                    print_success("Ключи не найдены.")
                    return

                rows: list[list[str]] = []
                for row in keys:
                    rows.append(
                        [
                            str(row.get("name", "")),
                            str(row.get("type", "custom")),
                            str(row.get("status", "unknown")),
                            str(row.get("last_used_at", "")),
                            str(row.get("created_at", "")),
                            str(row.get("masked_value", "***")),
                        ]
                    )
                print_table(
                    "API Keys",
                    ["Name", "Type", "Status", "Last Used", "Created", "Masked"],
                    rows,
                )
            except Exception as exc:
                print_error(f"Ошибка получения ключей: {exc}")
                raise typer.Exit(code=1)

    @app.command("health")
    def keys_health(
        check: bool = typer.Option(False, "--check", help="Запустить online health-check"),
        as_json: bool = typer.Option(False, "--json", help="Вывести сырые JSON данные"),
    ):
        """Показать health API ключей."""
        with _cli_context():
            from ..utils.api_client import CLIApiClient

            client = CLIApiClient()
            try:
                payload = (
                    client.run_api_keys_health_check()
                    if check
                    else client.get_api_keys_health()
                )
                if as_json:
                    _emit_json(payload)
                    return

                total = int(payload.get("total_keys", 0))
                valid = int(payload.get("valid_keys", 0))
                invalid = int(payload.get("invalid_keys", 0))
                expiring = int(payload.get("expiring_soon", 0))
                rotation = bool(payload.get("rotation_required", False))

                print_success(
                    f"Health: total={total}, valid={valid}, invalid={invalid}, expiring<=7d={expiring}"
                )
                if rotation:
                    print_error("Rotation required: есть ключи, требующие ротации.")

                rows: list[list[str]] = []
                for item in payload.get("keys", []):
                    rows.append(
                        [
                            str(item.get("name", "")),
                            str(item.get("type", "custom")),
                            str(item.get("status", "unknown")),
                            str(item.get("expires_in_days", "")),
                            str(item.get("last_validation", "")),
                        ]
                    )
                if rows:
                    print_table(
                        "Keys Health",
                        ["Name", "Type", "Status", "Expires In Days", "Last Validation"],
                        rows,
                    )
            except Exception as exc:
                print_error(f"Ошибка получения health: {exc}")
                raise typer.Exit(code=1)

    @app.command("validate")
    def validate_key(
        key_name: str = typer.Argument(..., help="Имя ключа"),
        as_json: bool = typer.Option(False, "--json", help="Вывести сырые JSON данные"),
    ):
        """Провалидировать конкретный API ключ."""
        with _cli_context():
            from ..utils.api_client import CLIApiClient

            client = CLIApiClient()
            try:
                payload = client.validate_api_key(key_name)
                if as_json:
                    _emit_json(payload)
                    return

                if bool(payload.get("valid", False)):
                    print_success(f"Ключ '{key_name}' валиден.")
                    return
                print_error(f"Ключ '{key_name}' невалиден: {payload.get('error', 'unknown')}")
                raise typer.Exit(code=2)
            except Exception as exc:
                print_error(f"Ошибка валидации ключа: {exc}")
                raise typer.Exit(code=1)

