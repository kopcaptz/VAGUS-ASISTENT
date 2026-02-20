"""Migrate *_API_KEY values from env/.env into encrypted KeyManager storage."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vagus.security import KeyManager  # noqa: E402


API_KEY_RE = re.compile(r"^([A-Z0-9_]+)_API_KEY$")


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _parse_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    # utf-8-sig strips the UTF-8 BOM automatically; lstrip is belt-and-suspenders
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.lstrip("\ufeff")
        if "=" not in line or line.lstrip().startswith("#"):
            continue
        name, raw = line.split("=", 1)
        key = name.strip()
        value = raw.strip().strip("'").strip('"')
        if API_KEY_RE.match(key) and value:
            values[key] = value
    return values


def _write_env_without_keys(path: Path, remove_names: set[str]) -> None:
    if not path.exists():
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    lines_out: list[str] = []
    # Read with utf-8-sig so any existing BOM is consumed and not duplicated
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.lstrip("\ufeff")
        if "=" not in line:
            lines_out.append(line)
            continue
        name = line.split("=", 1)[0].strip()
        if name in remove_names:
            continue
        lines_out.append(line)
    # Write without BOM (plain utf-8)
    tmp.write_text("\n".join(lines_out) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _to_key_name(env_name: str) -> tuple[str, str]:
    m = API_KEY_RE.match(env_name)
    if not m:
        raise ValueError(f"Unsupported env var name: {env_name}")
    provider = m.group(1).lower()
    return provider, provider


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate *_API_KEY vars into encrypted key storage")
    parser.add_argument("--env-file", default=".env", help="Path to .env file (default: .env)")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="Show planned changes only")
    parser.add_argument("--apply", dest="dry_run", action="store_false", help="Apply migration changes")
    parser.add_argument("--force", action="store_true", help="Apply without interactive confirmation")
    parser.set_defaults(dry_run=True)
    args = parser.parse_args()

    env_path = Path(args.env_file).expanduser()
    file_values = _parse_env_file(env_path)
    runtime_values = {
        name: value
        for name, value in os.environ.items()
        if API_KEY_RE.match(name) and value
    }
    combined = dict(file_values)
    combined.update(runtime_values)

    if not combined:
        print("[INFO] No *_API_KEY entries found in env or .env")
        return 0

    print(f"[INFO] Discovered {len(combined)} API key variable(s):")
    for env_name in sorted(combined):
        print(f"       - {env_name}")

    if args.dry_run:
        print("[INFO] Dry-run mode: no changes applied.")
        return 0

    if not args.force:
        answer = input("Apply migration to encrypted storage? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print("[INFO] Migration cancelled.")
            return 1

    manager = KeyManager()
    pre_store = manager._load_store()  # noqa: SLF001
    env_backup_path: Path | None = None

    try:
        if env_path.exists():
            env_backup_path = env_path.with_name(f".env.backup_{_utc_stamp()}")
            shutil.copy2(env_path, env_backup_path)
            print(f"[INFO] Created .env backup: {env_backup_path}")

        store = manager._load_store()  # noqa: SLF001
        store_keys = store.get("keys", {}) if isinstance(store, dict) else {}
        if not isinstance(store_keys, dict):
            store_keys = {}

        migrated_names: set[str] = set()
        for env_name, value in sorted(combined.items()):
            key_name, key_type = _to_key_name(env_name)
            if key_name not in store_keys:
                manager.add_key(name=key_name, key_type=key_type, value=value)
                store_keys[key_name] = {}
            else:
                manager.update_key(name=key_name, value=value)
            migrated_names.add(env_name)

        _write_env_without_keys(env_path, migrated_names)
        print(f"[INFO] Migrated {len(migrated_names)} key(s) into encrypted storage.")
        return 0
    except Exception as exc:
        print(f"[ERROR] Migration failed: {exc}")
        # Roll back encrypted store first (always safe).
        manager._save_store(pre_store)  # noqa: SLF001
        # Attempt to restore .env from backup with escalating fallback strategies.
        if env_backup_path is not None and env_backup_path.exists():
            # Step 1: try to clear a possible read-only attribute on Windows/POSIX.
            try:
                os.chmod(env_path, 0o644)
            except OSError as chmod_err:
                print(f"[WARN] Could not clear read-only on .env: {chmod_err}")
            # Step 2: try a metadata-preserving copy.
            try:
                shutil.copy2(env_backup_path, env_path)
                print("[INFO] Rolled back .env from backup.")
            except OSError:
                # Step 3: fallback to atomic rename (same filesystem).
                try:
                    os.replace(env_backup_path, env_path)
                    print("[INFO] Rolled back .env via atomic replace.")
                except OSError as replace_err:
                    print(f"[WARN] Partial rollback — .env could not be restored: {replace_err}")
                    print(f"[WARN] Backup preserved at: {env_backup_path}")
                    print("[WARN] Restore manually: copy the backup file to .env")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
