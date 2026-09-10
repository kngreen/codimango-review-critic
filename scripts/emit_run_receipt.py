#!/usr/bin/env python3
"""Emit a child-owned run receipt into the Agentcloud durable journal."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from contract import ContractError, sha256_file


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True)
    parser.add_argument("--runner", required=True)
    parser.add_argument(
        "--status", choices=("completed", "failed", "unavailable"), default="completed"
    )
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task-sha", required=True)
    parser.add_argument("--skill-revision", required=True)
    parser.add_argument("--output-path", type=Path)
    args = parser.parse_args()
    try:
        session_id = os.environ.get("AGENTCLOUD_SESSION_ID")
        if not session_id:
            raise ContractError("isolation_unverified: AGENTCLOUD_SESSION_ID is absent")
        if args.status == "completed" and args.output_path is None:
            raise ContractError("completed run receipt requires --output-path")
        if args.status != "completed" and args.output_path is not None:
            raise ContractError("failed/unavailable run receipt must not claim output")
        value = {
            "session_id": session_id,
            "role": args.role,
            "runner": args.runner,
            "status": args.status,
            "task_id": args.task_id,
            "task_sha": args.task_sha,
            "skill_revision": args.skill_revision,
            "output_path": (
                str(args.output_path.resolve()) if args.output_path else None
            ),
            "output_sha256": (
                sha256_file(args.output_path) if args.output_path else None
            ),
        }
        print("CODIMANGO_RUN_RECEIPT=" + json.dumps(value, sort_keys=True))
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(f"RUN RECEIPT REJECTED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
