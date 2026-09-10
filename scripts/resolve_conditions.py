#!/usr/bin/env python3
"""Resolve Agentic, Validation Override, and iOS conditions fail-closed."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from contract import (
    ContractError,
    load_json,
    resolve_conditions,
    validate_conditions,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("metadata", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        source = load_json(args.metadata)
        result = resolve_conditions(source)
        validate_conditions(
            result, str(source.get("task_id", "")), source.get("task_sha")
        )
        write_json(args.output, result)
        recovered = result["agentic"].get("source")
        if recovered and recovered != "api":
            print(f"AGENTIC RECOVERED source={recovered}")
        print(
            "CONDITIONS OK "
            + " ".join(
                f"{key}={result[key]['state']}"
                for key in ("agentic", "validation_override", "ios")
            )
        )
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(f"CONDITION REJECTED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
