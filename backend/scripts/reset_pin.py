#!/usr/bin/env python
"""CLI script for admin PIN management.

P1-1: Replaces removed /peek-pin endpoint.
Use this script to view/reset PINs from command line.

Usage:
    python -m backend.scripts.reset_pin --role operator
    python -m backend.scripts.reset_pin --role operator --new-pin 1234567
    python -m backend.scripts.reset_pin --list
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))

from services.db import DEFAULT_PINS, get_pin_row, init_db, pin_from_b64, update_pin


def list_pins() -> None:
    """List all roles with their SHA-256 hashes (not plaintext)."""
    init_db()
    print("=== PIN Roles (SHA-256 hashes only) ===")
    for role in sorted(DEFAULT_PINS.keys()):
        row = get_pin_row(role)
        if row:
            print(f"  {role:12s} → {row['pin_sha256'][:16]}...")
        else:
            print(f"  {role:12s} → NOT FOUND")


def view_pin(role: str) -> None:
    """View plaintext PIN (WARNING: terminal exposure)."""
    init_db()
    row = get_pin_row(role)
    if not row:
        print(f"ERROR: Role '{role}' not found", file=sys.stderr)
        sys.exit(1)
    pin = pin_from_b64(str(row["pin_b64"]))
    print(f"=== PIN for '{role}' ===")
    print(f"PIN: {pin}")
    print("WARNING: PIN visible in terminal history!")


def reset_pin(role: str, new_pin: str) -> None:
    """Reset PIN for a role."""
    if len(new_pin) != 7 or not new_pin.isdigit():
        print("ERROR: PIN must be exactly 7 digits", file=sys.stderr)
        sys.exit(1)
    init_db()
    update_pin(role, new_pin)
    print(f"OK: PIN reset for '{role}'")


def main() -> None:
    parser = argparse.ArgumentParser(description="Admin PIN management (P1-1 replacement for /peek-pin)")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list", action="store_true", help="List all roles (SHA-256 only)")
    group.add_argument("--role", type=str, help="View or reset PIN for role")
    parser.add_argument("--new-pin", type=str, help="New 7-digit PIN (required with --role for reset)")

    args = parser.parse_args()

    if args.list:
        list_pins()
    elif args.role:
        if args.new_pin:
            reset_pin(args.role, args.new_pin)
        else:
            view_pin(args.role)


if __name__ == "__main__":
    main()
