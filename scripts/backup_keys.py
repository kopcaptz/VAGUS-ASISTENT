"""Create encrypted backup of API key store.

Exit codes:
    0  Backup created (and validated, if --validate was requested).
    1  Unexpected error during backup.
    2  Backup created but post-validation failed.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vagus.security import KeyManager  # noqa: E402
from vagus.security.key_backup import create_backup_file, validate_backup_file  # noqa: E402


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create an encrypted backup of the Vagus API key store.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes:\n"
            "  0  Backup created successfully\n"
            "  1  Unexpected error\n"
            "  2  Backup created but validation failed\n"
        ),
    )
    parser.add_argument("--output-dir", default="~/.vagus/backups", help="Backup output directory (default: ~/.vagus/backups)")
    parser.add_argument("--filename", default=None, help="Override backup filename (default: keys_backup_<timestamp>.vkb)")
    parser.add_argument("--password", default=None, help="Optional extra encryption password for the backup")
    parser.add_argument("--validate", action="store_true", help="Validate the created backup immediately after writing")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be backed up without writing")
    parser.add_argument("--verbose", action="store_true", help="Show full traceback on error")
    args = parser.parse_args()

    output_dir = Path(args.output_dir).expanduser()
    filename = args.filename or f"keys_backup_{_utc_stamp()}.vkb"
    backup_path = output_dir / filename

    try:
        manager = KeyManager()

        if args.dry_run:
            store = manager._load_store()  # noqa: SLF001
            key_count = len(store.get("keys", {})) if isinstance(store, dict) else 0
            print(f"[INFO] Dry-run: would write {key_count} key(s) to {backup_path}")
            return 0

        create_backup_file(key_manager=manager, backup_path=backup_path, password=args.password)
        print(f"[INFO] Backup created: {backup_path}")

        if args.validate:
            result = validate_backup_file(key_manager=manager, backup_path=backup_path, password=args.password)
            if result["valid"]:
                print(f"[OK]   Validation passed: checksum_ok={result['checksum_ok']} key_count={result['key_count_actual']}")
            else:
                print(f"[ERROR] Validation failed: checksum_ok={result['checksum_ok']}")
                return 2

        return 0
    except Exception as exc:  # noqa: BLE001
        if args.verbose:
            traceback.print_exc()
        print(f"[ERROR] Backup failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
