"""Restore encrypted API key backup into current key store.

Exit codes:
    0  Restore completed successfully (or dry-run passed).
    1  Unexpected error during restore.
    2  Backup file is invalid or cannot be decrypted.
"""

from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vagus.security import KeyManager  # noqa: E402
from vagus.security.key_backup import restore_backup_file, validate_backup_file  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Restore API keys from an encrypted Vagus backup (.vkb) file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes:\n"
            "  0  Restore successful (or dry-run validated)\n"
            "  1  Unexpected error\n"
            "  2  Backup invalid or cannot be decrypted\n"
        ),
    )
    parser.add_argument("backup_file", help="Path to .vkb backup file")
    parser.add_argument(
        "--strategy",
        choices=["merge", "replace"],
        default="merge",
        help="Restore strategy: 'merge' keeps existing keys and adds new ones, 'replace' overwrites all (default: merge)",
    )
    parser.add_argument("--password", default=None, help="Optional backup password")
    parser.add_argument("--dry-run", action="store_true", help="Validate and preview without writing any changes")
    parser.add_argument("--force", action="store_true", help="Skip confirmation prompt when using --strategy=replace")
    parser.add_argument("--verbose", action="store_true", help="Show full traceback on error")
    args = parser.parse_args()

    backup_path = Path(args.backup_file).expanduser()

    if not backup_path.exists():
        print(f"[ERROR] Backup file not found: {backup_path}")
        return 1

    try:
        manager = KeyManager()
        validation = validate_backup_file(
            key_manager=manager, backup_path=backup_path, password=args.password
        )
    except ValueError as exc:
        if args.verbose:
            traceback.print_exc()
        print(f"[ERROR] Backup validation failed: {exc}")
        return 2
    except Exception as exc:  # noqa: BLE001
        if args.verbose:
            traceback.print_exc()
        print(f"[ERROR] Unexpected error reading backup: {exc}")
        return 1

    status = "[OK]" if validation["valid"] else "[ERROR]"
    print(
        f"{status} Backup validation: valid={validation['valid']} "
        f"key_count={validation['key_count_actual']} "
        f"checksum_ok={validation['checksum_ok']}"
    )

    if not validation["valid"]:
        print("[ERROR] Backup is invalid — aborting restore.")
        return 2

    if args.dry_run:
        print("[INFO] Dry-run mode: restore skipped. Backup looks good.")
        return 0

    if args.strategy == "replace" and not args.force:
        answer = input("WARNING: --strategy=replace will overwrite ALL current keys. Continue? [y/N]: ").strip().lower()
        if answer not in {"y", "yes"}:
            print("[INFO] Restore cancelled.")
            return 0

    try:
        result = restore_backup_file(
            key_manager=manager,
            backup_path=backup_path,
            strategy=args.strategy,
            password=args.password,
        )
    except Exception as exc:  # noqa: BLE001
        if args.verbose:
            traceback.print_exc()
        print(f"[ERROR] Restore failed: {exc}")
        return 1

    print(f"[INFO] Restored {result['restored_count']} key(s) with strategy='{result['strategy']}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
