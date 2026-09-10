#!/usr/bin/env python3
"""Validate every delivery gate and write a critic-owned approval receipt."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from agentcloud_attestation import attested_run_record
from contract import (
    ContractError,
    ROOT,
    approval_receipt,
    load_json,
    parse_time,
    render_live_payload,
    render_review,
    require_file,
    sha256_file,
    validate_command_audit,
    validate_dag,
    validate_evidence,
    validate_final,
    validate_phases,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--conditions", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--live-payload", required=True, type=Path)
    parser.add_argument(
        "--template", type=Path, default=ROOT / "references" / "output-template.md"
    )
    parser.add_argument("--review-data", required=True, type=Path)
    parser.add_argument("--findings", required=True, type=Path)
    parser.add_argument("--ledger", required=True, type=Path)
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--command-audit", required=True, type=Path)
    parser.add_argument("--approval", required=True, type=Path)
    args = parser.parse_args()
    try:
        manifest = load_json(args.manifest)
        current_session = os.environ.get("AGENTCLOUD_SESSION_ID")
        critic_session = next(
            (
                run.get("session_id")
                for run in manifest.get("runs", [])
                if run.get("role") == "critic"
            ),
            None,
        )
        if not current_session or current_session != critic_session:
            raise ContractError(
                "isolation_unverified: finalizer is not running in the attested critic session"
            )
        validate_attested_runs(manifest, current_session)
        validate_dag_or_die(manifest)
        validate_evidence_or_die(args.ledger, args.findings, manifest)
        validate_final_or_die(args, manifest)
        validate_command_audit_or_die(args.command_audit, manifest)
        approval = approval_receipt(
            args.manifest,
            args.review,
            args.live_payload,
            args.evidence,
            args.findings,
            args.ledger,
            args.command_audit,
        )
        write_json(args.approval, approval)
        attestation = {
            "approval_sha256": sha256_file(args.approval),
            "run_manifest_sha256": approval["run_manifest"]["sha256"],
            "review_sha256": approval["files"]["review"]["sha256"],
            "live_payload_sha256": approval["files"]["live_payload"]["sha256"],
            "critic_session_id": approval["critic_session_id"],
        }
        print(
            f"FINALIZATION OK task={approval['task_id']} sha={approval['task_sha']} "
            f"review_sha256={approval['files']['review']['sha256']}"
        )
        print("FINALIZATION_RECEIPT=" + json.dumps(attestation, sort_keys=True))
        return 0
    except (ContractError, OSError, ValueError, KeyError) as exc:
        print(f"FINALIZATION REJECTED: {exc}", file=sys.stderr)
        return 2


def validate_attested_runs(manifest: dict, current_session: str) -> None:
    compared = (
        "role",
        "runner",
        "session_id",
        "parent_session_id",
        "workspace",
        "harness",
        "loaded_skill",
        "status",
        "skill_revision",
        "task_id",
        "task_sha",
        "output_path",
        "output_sha256",
        "output_task_id",
        "output_task_sha",
        "attestation_source",
        "attested_run",
    )
    for claimed in manifest.get("runs", []):
        allow_running = claimed.get("role") == "critic"
        if allow_running and claimed.get("session_id") != current_session:
            raise ContractError("critic run record does not match current session")
        derived = attested_run_record(
            claimed["session_id"],
            claimed.get("attested_run"),
            allow_running=allow_running,
            expected_role=claimed.get("role"),
        )
        differences = [key for key in compared if claimed.get(key) != derived.get(key)]
        if parse_time(claimed.get("started_at"), "claimed.started_at") != parse_time(
            derived.get("started_at"), "derived.started_at"
        ):
            differences.append("started_at")
        if claimed.get("ended_at") is None or derived.get("ended_at") is None:
            if claimed.get("ended_at") != derived.get("ended_at"):
                differences.append("ended_at")
        elif parse_time(claimed.get("ended_at"), "claimed.ended_at") != parse_time(
            derived.get("ended_at"), "derived.ended_at"
        ):
            differences.append("ended_at")
        if differences:
            raise ContractError(
                f"Agentcloud run attestation mismatch for {claimed.get('role')}: {differences}"
            )


def validate_dag_or_die(manifest: dict) -> None:
    validate_dag(manifest)
    validate_phases(manifest)


def validate_evidence_or_die(ledger: Path, findings: Path, manifest: dict) -> None:
    validate_evidence(load_json(ledger), load_json(findings), manifest)


def validate_final_or_die(args: argparse.Namespace, manifest: dict) -> None:
    frozen_conditions = manifest["conditions"]
    if Path(frozen_conditions["path"]).resolve() != args.conditions.resolve():
        raise ContractError("finalizer conditions path differs from frozen manifest")
    require_file(args.conditions, frozen_conditions["sha256"])
    expected = manifest["final"]
    for key, path in (
        ("review", args.review),
        ("live_payload", args.live_payload),
        ("findings", args.findings),
        ("evidence_ledger", args.ledger),
        ("evidence", args.evidence),
        ("command_audit", args.command_audit),
    ):
        if Path(expected[key]["path"]).resolve() != path.resolve():
            raise ContractError(f"manifest final path differs for {key}")
    validate_final(
        args.review, args.template, args.conditions, args.findings, args.manifest
    )
    review_data = load_json(args.review_data)
    findings = load_json(args.findings)
    conditions = load_json(args.conditions)
    rendered = render_review(review_data, findings, conditions)
    if args.review.read_text(encoding="utf-8") != rendered:
        raise ContractError("final review bytes differ from critic renderer output")
    expected_payload = render_live_payload(review_data, findings, conditions)
    if load_json(args.live_payload) != expected_payload:
        raise ContractError("live payload differs from pinned renderer output")


def validate_command_audit_or_die(audit: Path, manifest: dict) -> None:
    validate_command_audit(audit, manifest, ROOT / "schema" / "command-policy.json")


if __name__ == "__main__":
    raise SystemExit(main())
