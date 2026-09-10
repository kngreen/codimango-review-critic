#!/usr/bin/env python3
"""Render a structured payload for the current live Codimango form."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from contract import ContractError, load_json, render_live_payload, write_json


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", required=True, type=Path)
    parser.add_argument("--findings", required=True, type=Path)
    parser.add_argument("--conditions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        payload = render_live_payload(
            load_json(args.data), load_json(args.findings), load_json(args.conditions)
        )
        write_json(args.output, payload)
        print(f"LIVE PAYLOAD RENDERED fields={len(payload)} path={args.output}")
        return 0
    except (ContractError, OSError, ValueError, KeyError) as exc:
        print(f"LIVE PAYLOAD REJECTED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
