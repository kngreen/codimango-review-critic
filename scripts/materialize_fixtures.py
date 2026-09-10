#!/usr/bin/env python3
"""Materialize path- and digest-bound acceptance fixtures."""

from __future__ import annotations

import argparse
import copy
import shutil
from pathlib import Path

from contract import write_json
from contract_test import Fixture


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        shutil.rmtree(args.output)
    args.output.mkdir(parents=True)
    fixture = Fixture(args.output / "files")
    write_json(args.output / "run_good.json", fixture.manifest)
    rewrite = copy.deepcopy(fixture.manifest)
    rewrite["publisher"]["published_sha256"] = "9" * 64
    write_json(args.output / "run_parent_rewrite.json", rewrite)
    history = copy.deepcopy(fixture.manifest)
    history["phases"][3], history["phases"][4] = (
        history["phases"][4],
        history["phases"][3],
    )
    write_json(args.output / "history_before_blind.json", history)
    print(f"FIXTURES MATERIALIZED path={args.output} count=3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
