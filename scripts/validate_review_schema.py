#!/usr/bin/env python3
"""Compatibility wrapper for the shared final-review schema contract."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from contract import ContractError, validate_final


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--conditions", required=True, type=Path)
    parser.add_argument("--findings", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = validate_final(
            args.review, args.template, args.conditions, args.findings, args.manifest
        )
        print("CANONICAL REVIEW SCHEMA OK")
        print(f"SECTIONS: {result['sections']}")
        print(f"FIELDS: {result['fields']}")
        print(f"WORDS: lexical={result['lexical']} whitespace={result['whitespace']}")
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print("CANONICAL REVIEW SCHEMA REJECTED", file=sys.stderr)
        print(f"- {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
