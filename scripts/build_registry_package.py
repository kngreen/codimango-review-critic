#!/usr/bin/env python3
"""Build the exact flat file set accepted by the Skills SDK registry."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from contract import runtime_files, validate_bundle


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    bundle = args.bundle.resolve()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error("output directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    files = runtime_files(bundle) + [bundle / "references" / "bundle-lock.md"]
    for source in sorted(files):
        relative = source.relative_to(bundle)
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    commit, tree, count = validate_bundle(output)
    print(
        f"REGISTRY PACKAGE OK files={count + 1} commit={commit} tree={tree} path={output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
