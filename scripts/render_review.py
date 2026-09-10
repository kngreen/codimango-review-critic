#!/usr/bin/env python3
"""Render the preferred Markdown review from structured data."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from contract import ContractError, load_json, render_review


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--findings", required=True, type=Path)
    parser.add_argument("--conditions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        text = render_review(
            load_json(args.data), load_json(args.findings), load_json(args.conditions)
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
        print(f"REVIEW RENDERED bytes={len(text.encode())} path={args.output}")
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(f"RENDER REJECTED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
