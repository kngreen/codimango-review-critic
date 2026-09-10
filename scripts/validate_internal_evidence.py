#!/usr/bin/env python3
"""Validate complete evidence and finding ledgers."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from contract import ContractError, load_json, validate_evidence


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--findings", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = validate_evidence(
            load_json(args.ledger), load_json(args.findings), load_json(args.manifest)
        )
        print(
            "EVIDENCE LEDGER OK "
            + " ".join(f"{key}={value}" for key, value in result.items())
        )
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(f"EVIDENCE REJECTED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
