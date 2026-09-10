#!/usr/bin/env python3
"""Process-only mode cannot certify session isolation and therefore fails closed."""

from __future__ import annotations

import argparse
import sys


def main() -> int:
    argparse.ArgumentParser().parse_args()
    print(
        "PROCESS RUN RECORD REJECTED: isolation_unverified; use the Agentcloud control-plane adapter",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
