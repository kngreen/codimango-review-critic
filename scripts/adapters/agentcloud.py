#!/usr/bin/env python3
"""Build a run record only from Agentcloud control-plane metadata and journal output."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentcloud_attestation import attested_run_record
from contract import ContractError, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session-id", required=True)
    parser.add_argument("--run", type=int, required=True)
    parser.add_argument("--expected-role", required=True)
    parser.add_argument("--allow-running-critic", action="store_true")
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        record = attested_run_record(
            args.session_id,
            args.run,
            allow_running=args.allow_running_critic,
            expected_role=args.expected_role,
        )
        if args.allow_running_critic and record["role"] != "critic":
            raise ContractError("only the critic role may be attested while running")
        write_json(args.output, record)
        print(
            f"AGENTCLOUD RUN RECORD OK role={record['role']} "
            f"session={args.session_id} run={record['attested_run']}"
        )
        return 0
    except (ContractError, OSError, ValueError, KeyError) as exc:
        print(f"AGENTCLOUD RUN RECORD REJECTED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
