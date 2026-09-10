#!/usr/bin/env python3
"""Publish only bytes approved by an attested critic-session finalizer."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agentcloud_attestation import tool_receipt
from contract import (
    ContractError,
    load_json,
    require_file,
    sha256_file,
    verify_identical_bytes,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--approval", required=True, type=Path)
    parser.add_argument("--critic-session-id", required=True)
    parser.add_argument("--run", required=True, type=int)
    parser.add_argument("--name", default="review")
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--destination", required=True, type=Path)
    args = parser.parse_args()
    try:
        approval = load_json(args.approval)
        if approval.get("verdict") != "PASS":
            raise ContractError("PUBLISH REJECTED: approval verdict is not PASS")
        if approval.get("critic_session_id") != args.critic_session_id:
            raise ContractError("PUBLISH REJECTED: critic session mismatch")
        approval_digest = sha256_file(args.approval)
        attested, run = tool_receipt(
            args.critic_session_id,
            "FINALIZATION_RECEIPT=",
            args.run,
            required_script="finalize_review.py",
        )
        expected = {
            "approval_sha256": approval_digest,
            "run_manifest_sha256": approval.get("run_manifest", {}).get("sha256"),
            "review_sha256": approval.get("files", {}).get("review", {}).get("sha256"),
            "live_payload_sha256": approval.get("files", {})
            .get("live_payload", {})
            .get("sha256"),
            "critic_session_id": args.critic_session_id,
        }
        if attested != expected:
            raise ContractError(
                "PUBLISH REJECTED: Agentcloud finalization receipt mismatch"
            )
        manifest_entry = approval.get("run_manifest", {})
        manifest_path = Path(str(manifest_entry.get("path", "")))
        require_file(manifest_path, manifest_entry.get("sha256"))
        digest = verify_identical_bytes(
            approval, args.name, args.source, args.destination
        )
        print(
            f"PUBLISH VERIFIED name={args.name} sha256={digest} "
            f"critic_session={args.critic_session_id} run={run} path={args.destination}"
        )
        return 0
    except (ContractError, OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
