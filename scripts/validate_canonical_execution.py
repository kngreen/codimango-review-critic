#!/usr/bin/env python3
"""Compatibility wrapper for receipt-v2 and DAG validation."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from contract import ContractError, load_json, validate_dag, validate_phases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--receipt", "--manifest", dest="manifest", required=True, type=Path
    )
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task-sha", required=True)
    args = parser.parse_args()
    try:
        data = load_json(args.manifest)
        if str(data.get("task", {}).get("id")) != args.task_id:
            raise ContractError("task_id mismatch")
        if data.get("task", {}).get("validation_sha") != args.task_sha:
            raise ContractError("task_sha mismatch")
        result = validate_dag(data)
        events = validate_phases(data)
        print("CANONICAL REVIEW EXECUTION OK")
        print(f"TASK: {args.task_id} @ {args.task_sha}")
        print(f"PRIMARY DECISION RUNNER: {result['decision_runner']}")
        print(f"SUPPLEMENTAL RUNNER: review-trials-and-spec")
        print(f"PHASE EVENTS: {events}")
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print("CANONICAL REVIEW EXECUTION REJECTED", file=sys.stderr)
        print(f"- {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
