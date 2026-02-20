"""Validate encrypted API key backup file integrity and decryptability.

Exit codes:
    0  Backup is valid and decryptable.
    1  I/O error, crypto failure, or wrong password.
    2  Incompatible backup version or corrupted structure.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from vagus.security import KeyManager  # noqa: E402
from vagus.security.key_backup import validate_backup_file  # noqa: E402


def _fmt_ok(msg: str) -> str:
    if sys.stdout.isatty():
        return f"\033[32m[OK]\033[0m {msg}"
    return f"[OK] {msg}"


def _fmt_err(msg: str) -> str:
    if sys.stdout.isatty():
        return f"\033[31m[ERROR]\033[0m {msg}"
    return f"[ERROR] {msg}"


def _fmt_warn(msg: str) -> str:
    if sys.stdout.isatty():
        return f"\033[33m[WARN]\033[0m {msg}"
    return f"[WARN] {msg}"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate a Vagus encrypted key backup (.vkb) file.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes:\n"
            "  0  Backup valid\n"
            "  1  I/O or crypto error\n"
            "  2  Incompatible version or corrupted structure\n"
        ),
    )
    parser.add_argument("backup_file", help="Path to .vkb backup file")
    parser.add_argument("--password", default=None, help="Optional backup password")
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Print full result as JSON (machine-readable)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show full traceback on error instead of a summary",
    )
    args = parser.parse_args()

    backup_path = Path(args.backup_file).expanduser()

    if not backup_path.exists():
        print(_fmt_err(f"File not found: {backup_path}"))
        return 1

    try:
        manager = KeyManager()
        result = validate_backup_file(
            key_manager=manager,
            backup_path=backup_path,
            password=args.password,
        )
    except FileNotFoundError as exc:
        print(_fmt_err(f"File not found: {exc}"))
        return 1
    except ValueError as exc:
        msg = str(exc)
        if args.verbose:
            traceback.print_exc()
        if "version" in msg.lower():
            print(_fmt_err(f"Incompatible backup version: {msg}"))
            print(_fmt_warn("This backup was created by a different Vagus version."))
            return 2
        print(_fmt_err(f"Backup validation failed: {msg}"))
        return 2
    except Exception as exc:  # noqa: BLE001
        if args.verbose:
            traceback.print_exc()
        print(_fmt_err(f"Unexpected error during validation: {exc}"))
        return 1

    if args.json_output:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        status = _fmt_ok("Backup is VALID") if result["valid"] else _fmt_err("Backup is INVALID")
        print(status)
        print(f"  decryption_ok   = {result['decryption_ok']}")
        print(f"  checksum_ok     = {result['checksum_ok']}")
        print(f"  key_count       = {result['key_count_actual']}")
        if not result["valid"]:
            print(_fmt_warn("Checksum mismatch — backup may be corrupted or tampered."))

    return 0 if result["valid"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
