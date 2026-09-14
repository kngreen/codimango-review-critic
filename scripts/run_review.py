#!/usr/bin/env python3
"""Stateful review lifecycle controller.

This controller owns phase order and manifest writes. It does not fetch task data
or spawn agents itself; harness adapters provide attested run records and command
entries. Every state transition is fail-closed and atomic.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

from contract import (
    ContractError,
    FULL_SHA,
    PHASE_ORDER,
    load_json,
    sha256_file,
    utc_now,
    validate_bundle,
    validate_phases,
    write_json,
)


def atomic_write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        import json

        handle.write(json.dumps(value, indent=2, sort_keys=True) + "\n")
        temp = Path(handle.name)
    os.replace(temp, path)


def preflight_or_die(bundle: Path, scratch: Path, receipt: Path) -> dict:
    if not receipt.is_file():
        raise ContractError(
            "sandbox-attested preflight receipt is required; run reviewctl.py preflight first"
        )
    value = load_json(receipt)
    if value.get("verdict") != "PASS" or value.get("scratch_root") != str(
        scratch.resolve()
    ):
        raise ContractError("existing preflight receipt does not match scratch root")
    if value.get("sandbox_backend") not in {"systemd", "unshare", "sandbox-exec"}:
        raise ContractError("existing preflight receipt lacks sandbox attestation")
    head, tree, count = validate_bundle(bundle)
    if (
        value.get("bundle_commit") != head
        or value.get("bundle_tree") != tree
        or value.get("runtime_file_count") != count
    ):
        raise ContractError("existing preflight receipt does not match current bundle")
    return value


def append_phase(manifest: dict, name: str, artifact: Path | None = None) -> None:
    phases = manifest.setdefault("phases", [])
    expected = PHASE_ORDER[len(phases)] if len(phases) < len(PHASE_ORDER) else None
    if name != expected:
        raise ContractError(f"PHASE ORDER REJECTED: expected {expected}, got {name}")
    event = {
        "name": name,
        "sequence": len(phases) + 1,
        "timestamp": utc_now(),
        "task_id": str(manifest["task"]["id"]),
    }
    if artifact is not None:
        event["artifact_path"] = str(artifact.resolve())
        event["artifact_sha256"] = sha256_file(artifact)
    phases.append(event)


def seal_blind_pass(manifest: dict, artifact: Path) -> None:
    append_phase(manifest, "blind_sealed", artifact)


def fetch_history(manifest: dict) -> None:
    names = [phase["name"] for phase in manifest.get("phases", [])]
    if not names or names[-1] != "blind_sealed":
        raise ContractError("PHASE ORDER REJECTED: history requires sealed blind pass")
    append_phase(manifest, "history_started")


def cmd_bootstrap(args: argparse.Namespace) -> None:
    scratch = args.scratch_root.resolve()
    receipt = args.preflight_receipt.resolve()
    pre = preflight_or_die(args.bundle.resolve(), scratch, receipt)
    unresolved_repo = scratch / "_unresolved_task_repo"
    unresolved_repo.mkdir(exist_ok=True)
    manifest = {
        "schema_version": 2,
        "dispatcher_session_id": args.dispatcher_session_id,
        "task": {"id": args.task_id},
        "bundle": {
            "commit": pre["bundle_commit"],
            "tree": pre["bundle_tree"],
            "preflight_receipt_path": str(receipt),
            "preflight_receipt_sha256": sha256_file(receipt),
        },
        "scratch_root": str(scratch),
        "task_repo_root": str(unresolved_repo),
        "runs": [],
        "phases": [],
        "conditions": {},
        "final": {},
        "publisher": {},
        "context": {
            "allowed_identifiers": [args.task_id],
            "allowed_path_prefixes": list(args.allow_path),
            "allowed_repositories": ["UNRESOLVED"],
        },
    }
    append_phase(manifest, "preflight")
    atomic_write(args.manifest, manifest)
    print(f"REVIEW BOOTSTRAPPED task={args.task_id} preflight={receipt}")


def cmd_freeze_identity(args: argparse.Namespace) -> None:
    manifest = load_json(args.manifest)
    if [phase.get("name") for phase in manifest.get("phases", [])] != ["preflight"]:
        raise ContractError("identity freeze requires exactly one preflight phase")
    for name, value in (
        ("head_sha", args.head_sha),
        ("validation_sha", args.validation_sha),
        ("inspected_sha", args.inspected_sha),
    ):
        if FULL_SHA.fullmatch(value) is None:
            raise ContractError(f"{name} must be a full SHA")
    if args.review_job_sha and FULL_SHA.fullmatch(args.review_job_sha) is None:
        raise ContractError("review_job_sha must be a full SHA")
    manifest["task"] = {
        "id": str(manifest["task"]["id"]),
        "repo": args.repo,
        "track": args.track,
        "variant": args.variant,
        "base_track": args.base_track,
        "head_sha": args.head_sha,
        "validation_sha": args.validation_sha,
        "review_job_sha": args.review_job_sha,
        "inspected_sha": args.inspected_sha,
    }
    manifest["task_repo_root"] = (
        str(args.task_repo_root.resolve()) if args.task_repo_root else None
    )
    manifest["context"] = {
        "allowed_identifiers": [
            str(manifest["task"]["id"]),
            args.head_sha,
            args.validation_sha,
            args.inspected_sha,
        ]
        + ([args.review_job_sha] if args.review_job_sha else [])
        + list(args.allow_identifier),
        "allowed_path_prefixes": list(args.allow_path),
        "allowed_repositories": [args.repo],
    }
    append_phase(manifest, "identity_frozen")
    atomic_write(args.manifest, manifest)
    print(f"IDENTITY FROZEN task={manifest['task']['id']} sha={args.validation_sha}")


def cmd_record_run(args: argparse.Namespace) -> None:
    manifest = load_json(args.manifest)
    run = load_json(args.run_record)
    manifest.setdefault("runs", []).append(run)
    atomic_write(args.manifest, manifest)
    print(f"RUN RECORDED role={run.get('role')} session={run.get('session_id')}")


def cmd_phase(args: argparse.Namespace) -> None:
    manifest = load_json(args.manifest)
    if args.name == "blind_sealed":
        if args.artifact is None:
            raise ContractError("blind_sealed requires --artifact")
        seal_blind_pass(manifest, args.artifact)
    elif args.name == "history_started":
        fetch_history(manifest)
    else:
        append_phase(manifest, args.name, args.artifact)
    atomic_write(args.manifest, manifest)
    print(f"PHASE RECORDED name={args.name}")


def cmd_set_conditions(args: argparse.Namespace) -> None:
    manifest = load_json(args.manifest)
    manifest["conditions"] = {
        "path": str(args.conditions.resolve()),
        "sha256": sha256_file(args.conditions),
    }
    atomic_write(args.manifest, manifest)
    print(f"CONDITIONS RECORDED path={args.conditions.resolve()}")


def cmd_set_final(args: argparse.Namespace) -> None:
    manifest = load_json(args.manifest)
    paths = {
        "review": args.review,
        "live_payload": args.live_payload,
        "evidence": args.evidence,
        "findings": args.findings,
        "evidence_ledger": args.ledger,
        "command_audit": args.command_audit,
    }
    manifest["final"] = {
        "owner_session_id": args.critic_session_id,
        **{
            name: {"path": str(path.resolve()), "sha256": sha256_file(path)}
            for name, path in paths.items()
        },
    }
    manifest["publisher"] = {
        "source_path": str(args.review.resolve()),
        "source_sha256": sha256_file(args.review),
        "published_path": None,
        "published_sha256": None,
    }
    atomic_write(args.manifest, manifest)
    print(
        f"FINAL FILES RECORDED count={len(paths)} review_sha256={sha256_file(args.review)}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    bootstrap = sub.add_parser("bootstrap")
    bootstrap.add_argument("--bundle", required=True, type=Path)
    bootstrap.add_argument("--scratch-root", required=True, type=Path)
    bootstrap.add_argument("--preflight-receipt", required=True, type=Path)
    bootstrap.add_argument("--manifest", required=True, type=Path)
    bootstrap.add_argument("--dispatcher-session-id", required=True)
    bootstrap.add_argument("--task-id", required=True)
    bootstrap.add_argument(
        "--allow-path",
        action="append",
        default=["SKILL.md", "README.md", "references", "scripts", "schema"],
    )

    freeze = sub.add_parser("freeze-identity")
    freeze.add_argument("--manifest", required=True, type=Path)
    freeze.add_argument("--repo", required=True)
    freeze.add_argument("--track", required=True)
    freeze.add_argument("--variant", required=True)
    freeze.add_argument("--base-track", default="")
    freeze.add_argument("--head-sha", required=True)
    freeze.add_argument("--validation-sha", required=True)
    freeze.add_argument("--review-job-sha")
    freeze.add_argument("--inspected-sha", required=True)
    freeze.add_argument("--task-repo-root", type=Path)
    freeze.add_argument(
        "--allow-path",
        action="append",
        default=["SKILL.md", "README.md", "references", "scripts", "schema"],
    )
    freeze.add_argument("--allow-identifier", action="append", default=[])

    record = sub.add_parser("record-run")
    record.add_argument("--manifest", required=True, type=Path)
    record.add_argument("--run-record", required=True, type=Path)

    phase = sub.add_parser("phase")
    phase.add_argument("--manifest", required=True, type=Path)
    phase.add_argument("--name", required=True, choices=PHASE_ORDER)
    phase.add_argument("--artifact", type=Path)

    conditions = sub.add_parser("set-conditions")
    conditions.add_argument("--manifest", required=True, type=Path)
    conditions.add_argument("--conditions", required=True, type=Path)

    final = sub.add_parser("set-final")
    final.add_argument("--manifest", required=True, type=Path)
    final.add_argument("--critic-session-id", required=True)
    final.add_argument("--review", required=True, type=Path)
    final.add_argument("--live-payload", required=True, type=Path)
    final.add_argument("--evidence", required=True, type=Path)
    final.add_argument("--findings", required=True, type=Path)
    final.add_argument("--ledger", required=True, type=Path)
    final.add_argument("--command-audit", required=True, type=Path)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        if args.command == "bootstrap":
            cmd_bootstrap(args)
        elif args.command == "freeze-identity":
            cmd_freeze_identity(args)
        elif args.command == "record-run":
            cmd_record_run(args)
        elif args.command == "phase":
            cmd_phase(args)
        elif args.command == "set-conditions":
            cmd_set_conditions(args)
        elif args.command == "set-final":
            cmd_set_final(args)
        return 0
    except (ContractError, OSError, ValueError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
