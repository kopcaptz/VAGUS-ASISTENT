"""
Команды backup/restore API ключей: vagus backup create/list/validate/restore.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import typer
except ImportError:
    typer = None  # type: ignore[assignment]

from ..utils.output import print_error, print_info, print_success, print_table

DEFAULT_BACKUP_DIR = "~/.vagus/backups"

if typer is not None:
    app = typer.Typer(help="Backup и restore API ключей")
else:
    app = None  # type: ignore[assignment]


def _cli_context():
    from vagus.logging import generate_trace_id, logging_context

    return logging_context(trace_id=generate_trace_id(), component="cli")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _resolve_output_path(output: Optional[str]) -> Path:
    if output:
        candidate = Path(output).expanduser()
        if candidate.suffix.lower() == ".vkb":
            return candidate
        return candidate / f"keys_backup_{_utc_stamp()}.vkb"
    return Path(DEFAULT_BACKUP_DIR).expanduser() / f"keys_backup_{_utc_stamp()}.vkb"


def _resolve_backup_dir(output: Optional[str]) -> Path:
    if output:
        candidate = Path(output).expanduser()
        if candidate.suffix.lower() == ".vkb":
            return candidate.parent
        return candidate
    return Path(DEFAULT_BACKUP_DIR).expanduser()


def _emit_json(payload: Any) -> None:
    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    if typer is None:
        print(text)
        return
    typer.echo(text)


if typer is not None:

    @app.command("create")
    def create_backup(
        password: Optional[str] = typer.Option(None, "--password", help="Доп. пароль шифрования backup"),
        output: Optional[str] = typer.Option(
            None,
            "--output",
            "-o",
            help="Путь к backup-файлу .vkb или директория для записи",
        ),
        validate: bool = typer.Option(True, "--validate/--no-validate", help="Проверить backup после создания"),
        as_json: bool = typer.Option(False, "--json", help="Вывести результат в JSON"),
    ):
        """Создать зашифрованный backup ключей."""
        with _cli_context():
            from vagus.security import KeyManager
            from vagus.security.key_backup import create_backup_file, validate_backup_file

            backup_path = _resolve_output_path(output)
            manager = KeyManager()
            try:
                created = create_backup_file(
                    key_manager=manager,
                    backup_path=backup_path,
                    password=password,
                )
                result: dict[str, Any] = {"backup_path": str(created), "validated": False}
                if validate:
                    validation = validate_backup_file(
                        key_manager=manager,
                        backup_path=created,
                        password=password,
                    )
                    result["validated"] = bool(validation.get("valid", False))
                    result["validation"] = validation

                if as_json:
                    _emit_json(result)
                    return

                print_success(f"Backup создан: {created}")
                if validate:
                    if bool(result.get("validated", False)):
                        print_success("Проверка backup прошла успешно.")
                    else:
                        print_error("Проверка backup не прошла.")
                        raise typer.Exit(code=2)
            except Exception as exc:
                print_error(f"Ошибка создания backup: {exc}")
                raise typer.Exit(code=1)

    @app.command("list")
    def list_backups(
        output: Optional[str] = typer.Option(
            None,
            "--output",
            "-o",
            help="Директория backup-файлов (или файл, тогда берется его директория)",
        ),
        as_json: bool = typer.Option(False, "--json", help="Вывести сырые JSON данные"),
    ):
        """Показать список backup-файлов."""
        with _cli_context():
            backup_dir = _resolve_backup_dir(output)
            files = sorted(
                backup_dir.glob("*.vkb"),
                key=lambda item: item.stat().st_mtime,
                reverse=True,
            ) if backup_dir.exists() else []

            payload = []
            for item in files:
                stat = item.stat()
                payload.append(
                    {
                        "filename": item.name,
                        "path": str(item),
                        "size_bytes": stat.st_size,
                        "modified_at": datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ).isoformat(),
                    }
                )

            if as_json:
                _emit_json(payload)
                return

            if not payload:
                print_info(f"Backup-файлы не найдены в: {backup_dir}")
                return

            rows = [
                [
                    str(row["filename"]),
                    str(row["size_bytes"]),
                    str(row["modified_at"]),
                    str(row["path"]),
                ]
                for row in payload
            ]
            print_table("Backups", ["Filename", "Size (bytes)", "Modified (UTC)", "Path"], rows)

    @app.command("validate")
    def validate_backup(
        backup_file: str = typer.Argument(..., help="Путь к backup-файлу .vkb"),
        password: Optional[str] = typer.Option(None, "--password", help="Доп. пароль шифрования backup"),
        as_json: bool = typer.Option(False, "--json", help="Вывести сырые JSON данные"),
    ):
        """Проверить backup-файл."""
        with _cli_context():
            from vagus.security import KeyManager
            from vagus.security.key_backup import validate_backup_file

            manager = KeyManager()
            backup_path = Path(backup_file).expanduser()
            if not backup_path.exists():
                print_error(f"Файл не найден: {backup_path}")
                raise typer.Exit(code=1)

            try:
                result = validate_backup_file(
                    key_manager=manager,
                    backup_path=backup_path,
                    password=password,
                )
                if as_json:
                    _emit_json(result)
                    return

                if bool(result.get("valid", False)):
                    print_success(
                        f"Backup валиден: checksum_ok={result.get('checksum_ok')} "
                        f"key_count={result.get('key_count_actual')}"
                    )
                    return
                print_error("Backup невалиден.")
                raise typer.Exit(code=2)
            except Exception as exc:
                print_error(f"Ошибка проверки backup: {exc}")
                raise typer.Exit(code=1)

    @app.command("restore")
    def restore_backup(
        backup_file: str = typer.Argument(..., help="Путь к backup-файлу .vkb"),
        password: Optional[str] = typer.Option(None, "--password", help="Доп. пароль шифрования backup"),
        strategy: str = typer.Option("merge", "--strategy", help="Стратегия: merge или replace"),
        as_json: bool = typer.Option(False, "--json", help="Вывести сырые JSON данные"),
        force: bool = typer.Option(False, "--force", help="Пропустить подтверждение"),
    ):
        """Восстановить ключи из backup-файла."""
        with _cli_context():
            from vagus.security import KeyManager
            from vagus.security.key_backup import restore_backup_file

            backup_path = Path(backup_file).expanduser()
            if not backup_path.exists():
                print_error(f"Файл не найден: {backup_path}")
                raise typer.Exit(code=1)

            strategy_normalized = strategy.strip().lower()
            if strategy_normalized not in {"merge", "replace"}:
                print_error("Некорректная стратегия. Используйте: merge или replace.")
                raise typer.Exit(code=1)

            if not force:
                confirmed = typer.confirm(
                    f"Восстановить ключи из {backup_path} со стратегией '{strategy_normalized}'?",
                    default=False,
                )
                if not confirmed:
                    print_info("Операция отменена.")
                    raise typer.Exit(code=0)

            manager = KeyManager()
            try:
                result = restore_backup_file(
                    key_manager=manager,
                    backup_path=backup_path,
                    strategy=strategy_normalized,
                    password=password,
                )
                if as_json:
                    _emit_json(result)
                    return
                print_success(
                    f"Восстановление завершено: restored_count={result.get('restored_count')} "
                    f"strategy={result.get('strategy')}"
                )
            except Exception as exc:
                print_error(f"Ошибка восстановления backup: {exc}")
                raise typer.Exit(code=1)

