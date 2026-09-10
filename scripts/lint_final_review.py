#!/usr/bin/env python3
"""Compatibility wrapper for the shared final-review language contract."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from contract import ContractError, load_json, validate_language


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("review", type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--max-words", type=int, default=None)
    args = parser.parse_args()
    try:
        lexical, whitespace, identifiers = validate_language(
            args.review, load_json(args.manifest), args.max_words
        )
        print(
            f"FINAL REVIEW LANGUAGE OK lexical={lexical} whitespace={whitespace} "
            f"identifiers={identifiers}"
        )
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print("FINAL REVIEW REJECTED", file=sys.stderr)
        print(f"- {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
