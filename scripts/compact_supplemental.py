#!/usr/bin/env python3
"""Build and validate a bounded supplemental-output descriptor."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from contract import (
    ContractError,
    load_json,
    sha256_file,
    validate_supplemental,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task-sha", required=True)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        output = args.output.resolve()
        summary = args.summary.resolve()
        ledger_path = args.ledger.resolve()
        if output in {summary, ledger_path}:
            raise ContractError(
                "supplemental output must not alias summary or ledger input"
            )
        ledger = load_json(args.ledger)
        records = ledger.get("records") if isinstance(ledger, dict) else None
        if not isinstance(records, list):
            raise ContractError("supplemental ledger must contain records list")
        value = {
            "schema_version": 1,
            "task_id": args.task_id,
            "task_sha": args.task_sha,
            "complete": ledger.get("complete") is True,
            "total_records": len(records),
            "summary_path": str(args.summary.resolve()),
            "summary_sha256": sha256_file(args.summary),
            "ledger_path": str(args.ledger.resolve()),
            "ledger_sha256": sha256_file(args.ledger),
        }
        validate_supplemental(value, args.task_id, args.task_sha)
        write_json(args.output, value)
        print(
            f"SUPPLEMENTAL OUTPUT OK records={len(records)} summary_bytes={args.summary.stat().st_size}"
        )
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(f"SUPPLEMENTAL OUTPUT REJECTED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
