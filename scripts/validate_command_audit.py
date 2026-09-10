#!/usr/bin/env python3
"""Validate task-scoped, read-only command audit entries."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from contract import ContractError, ROOT, load_json, validate_command_audit


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument(
        "--policy", type=Path, default=ROOT / "schema" / "command-policy.json"
    )
    args = parser.parse_args()
    try:
        count = validate_command_audit(
            args.audit, load_json(args.manifest), args.policy
        )
        print(f"READ-ONLY AUDIT OK commands={count}")
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
