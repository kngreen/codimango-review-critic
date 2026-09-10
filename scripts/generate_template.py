#!/usr/bin/env python3
"""Generate or verify the human-readable template from its JSON source."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from contract import ContractError, generate_template, load_review_format


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "references"
        / "output-template.md",
    )
    args = parser.parse_args()
    try:
        expected = generate_template(load_review_format())
        if args.write:
            args.output.write_text(expected, encoding="utf-8")
            print(f"TEMPLATE GENERATED path={args.output}")
        elif (
            not args.output.is_file()
            or args.output.read_text(encoding="utf-8") != expected
        ):
            raise ContractError("TEMPLATE DRIFT")
        else:
            print(f"TEMPLATE OK path={args.output}")
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
