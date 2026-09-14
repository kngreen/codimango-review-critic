#!/usr/bin/env python3
"""Unified command-line entry point for review-critic controls."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from contract import (
    ContractError,
    load_json,
    preflight,
    resolve_conditions,
    seal_bundle,
    validate_command_audit,
    validate_dag,
    validate_evidence,
    validate_final,
    validate_phases,
    write_json,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    seal = sub.add_parser("seal-bundle")
    seal.add_argument("--bundle", type=Path, required=True)
    seal.add_argument("--write", action="store_true")

    check = sub.add_parser("preflight")
    check.add_argument("--bundle", type=Path, required=True)
    check.add_argument("--scratch-root", type=Path, required=True)
    check.add_argument("--receipt", type=Path, required=True)

    dag = sub.add_parser("validate-dag")
    dag.add_argument("manifest", type=Path)

    phases = sub.add_parser("validate-phases")
    phases.add_argument("manifest", type=Path)

    conditions = sub.add_parser("resolve-conditions")
    conditions.add_argument("metadata", type=Path)
    conditions.add_argument("--output", type=Path, required=True)

    evidence = sub.add_parser("validate-evidence")
    evidence.add_argument("--ledger", type=Path, required=True)
    evidence.add_argument("--findings", type=Path, required=True)
    evidence.add_argument("--manifest", type=Path, required=True)

    final = sub.add_parser("validate-final")
    final.add_argument("--review", type=Path, required=True)
    final.add_argument("--template", type=Path, required=True)
    final.add_argument("--conditions", type=Path, required=True)
    final.add_argument("--findings", type=Path, required=True)
    final.add_argument("--manifest", type=Path, required=True)

    audit = sub.add_parser("validate-command-audit")
    audit.add_argument("--audit", type=Path, required=True)
    audit.add_argument("--manifest", type=Path, required=True)
    audit.add_argument(
        "--policy",
        type=Path,
        default=Path(__file__).resolve().parent.parent
        / "schema"
        / "command-policy.json",
    )

    args = parser.parse_args()
    try:
        if args.command == "seal-bundle":
            value = seal_bundle(args.bundle.resolve())
            if args.write:
                target = args.bundle / "schema" / "bundle-lock.json"
                write_json(target, value)
                print(
                    f"BUNDLE SEALED files={len(value['runtime_files'])} path={target}"
                )
            else:
                import json

                print(json.dumps(value, indent=2, sort_keys=True))
        elif args.command == "preflight":
            value = preflight(
                args.bundle.resolve(),
                args.scratch_root.resolve(),
                args.receipt.resolve(),
            )
            try:
                from audit_exec import probe_sandbox

                sandbox_backend = probe_sandbox()
            except (ContractError, OSError, ValueError):
                args.receipt.unlink(missing_ok=True)
                raise
            value["sandbox_backend"] = sandbox_backend
            write_json(args.receipt, value)
            print(
                f"PREFLIGHT OK files={value['runtime_file_count']} commit={value['bundle_commit']} "
                f"tree={value['bundle_tree']} sandbox={sandbox_backend}"
            )
        elif args.command == "validate-dag":
            result = validate_dag(load_json(args.manifest))
            print(
                f"RUN DAG OK roles={result['roles']} decision_runner={result['decision_runner']}"
            )
        elif args.command == "validate-phases":
            count = validate_phases(load_json(args.manifest))
            print(f"PHASE ORDER OK events={count}")
        elif args.command == "resolve-conditions":
            value = resolve_conditions(load_json(args.metadata))
            write_json(args.output, value)
            recovered = value["agentic"].get("source")
            if recovered and recovered != "api":
                print(f"AGENTIC RECOVERED source={recovered}")
            print(
                "CONDITIONS OK "
                + " ".join(
                    f"{key}={value[key]['state']}"
                    for key in ("agentic", "validation_override", "ios")
                )
            )
        elif args.command == "validate-evidence":
            result = validate_evidence(
                load_json(args.ledger),
                load_json(args.findings),
                load_json(args.manifest),
            )
            print(
                "EVIDENCE LEDGER OK "
                + " ".join(f"{key}={value}" for key, value in result.items())
            )
        elif args.command == "validate-final":
            result = validate_final(
                args.review,
                args.template,
                args.conditions,
                args.findings,
                args.manifest,
            )
            print(
                f"FINAL REVIEW OK sections={result['sections']} fields={result['fields']} "
                f"lexical={result['lexical']} whitespace={result['whitespace']} identifiers={result['identifiers']}"
            )
        elif args.command == "validate-command-audit":
            count = validate_command_audit(
                args.audit, load_json(args.manifest), args.policy
            )
            print(f"READ-ONLY AUDIT OK commands={count}")
        return 0
    except (ContractError, OSError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
