#!/usr/bin/env python3
"""Directional contract tests for every implementation item."""

from __future__ import annotations

import argparse
import copy
import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from contract import (
    BASELINES,
    ContractError,
    generate_template,
    load_json,
    load_review_format,
    parse_review,
    preflight,
    render_live_payload,
    render_review,
    require_full_sha,
    resolve_conditions,
    seal_bundle,
    sha256_file,
    validate_command_audit,
    validate_conditions,
    validate_dag,
    validate_evidence,
    validate_final,
    validate_findings,
    validate_language,
    validate_phases,
    validate_release_lock,
    validate_supplemental,
    write_json,
)

ROOT = Path(__file__).resolve().parent.parent
BASELINE = "d79066618fb26f50c162d41199c8847ddf481372"
TASK_ID = "999001"
TASK_SHA = "a" * 40
HEAD_SHA = "b" * 40
INSPECTED_SHA = "c" * 40


def expect_failure(fn: Callable[[], Any], contains: str | None = None) -> str:
    try:
        fn()
    except (ContractError, OSError, ValueError, KeyError) as exc:
        text = str(exc)
        if contains is not None and contains not in text:
            raise AssertionError(
                f"failure {text!r} did not contain {contains!r}"
            ) from exc
        return text
    raise AssertionError("expected failure, but control accepted input")


def run(
    command: list[str], cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, capture_output=True, check=False)


def baseline_file(path: str, destination: Path) -> Path:
    fixture = ROOT / "tests" / "baseline" / "d790666" / path
    if fixture.is_file():
        shutil.copyfile(fixture, destination)
        return destination
    proc = run(["git", "-C", str(ROOT), "show", f"{BASELINE}:{path}"])
    if proc.returncode != 0:
        raise AssertionError(
            f"baseline fixture missing and git history unavailable: {path}: {proc.stderr}"
        )
    destination.write_text(proc.stdout, encoding="utf-8")
    return destination


def old_script(
    path: str, args: list[str], temp: Path
) -> subprocess.CompletedProcess[str]:
    script = baseline_file(path, temp / Path(path).name)
    return run([sys.executable, str(script), *args])


def timestamp(offset: int) -> str:
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return (base + timedelta(seconds=offset)).isoformat().replace("+00:00", "Z")


class Fixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.scratch = root / "scratch"
        self.repo = root / "task-repo"
        self.scratch.mkdir(parents=True)
        self.repo.mkdir()
        self.conditions_path = self.scratch / "conditions.json"
        self.findings_path = self.scratch / "findings.json"
        self.review_data_path = self.scratch / "review-data.json"
        self.review_path = self.scratch / "final-review.md"
        self.live_path = self.scratch / "live-form-payload.json"
        self.evidence_path = self.scratch / "evidence.md"
        self.ledger_path = self.scratch / "evidence-ledger.json"
        self.audit_path = self.scratch / "command-audit.jsonl"
        self.preflight_path = self.scratch / "preflight.json"
        self.blind_path = self.scratch / "blind.md"
        self.template_path = ROOT / "references" / "output-template.md"
        self.conditions = {
            "schema_version": 1,
            "task_id": TASK_ID,
            "task_sha": TASK_SHA,
            "agentic": {"state": "not_required", "reason": "not_run"},
            "validation_override": {
                "state": "not_required",
                "reason": "none",
                "reasons": [],
            },
            "ios": {"state": "not_required", "reason": "non-iOS"},
        }
        write_json(self.conditions_path, self.conditions)
        self.findings = {
            "schema_version": 1,
            "task_id": TASK_ID,
            "task_sha": TASK_SHA,
            "quality_verdict": "Accept",
            "decision": "Accept",
            "decision_reconciliation": "The quality verdict and operational decision both accept the current task.",
            "findings": [
                {
                    "id": "F1",
                    "finding": "One narrow coverage caveat remains.",
                    "status": "CONFIRMED",
                    "independent_evidence": ["current task evidence"],
                    "attribution": "current",
                    "severity": "Low",
                    "blocking": False,
                    "reviewer_contribution": "The reviewer identified the omitted edge case.",
                    "close_condition": "Add one behavioral assertion for the edge case.",
                }
            ],
        }
        write_json(self.findings_path, self.findings)
        self.review_data = {
            "schema_version": 1,
            "task_id": TASK_ID,
            "task_sha": TASK_SHA,
            "sections": {
                "quality": {
                    "Reviewer Agrees?": "Agree",
                    "Notes": "The task is sound with one narrow coverage caveat.",
                },
                "contamination": {
                    "Risk Level": "NOT VERIFIED",
                    "Reviewer Agrees?": "Partially",
                    "Notes": "NOT VERIFIED: the service is unavailable.",
                },
                "novelty": {
                    "Risk Level": "LOW",
                    "Reviewer Agrees?": "Agree",
                    "Notes": "The implementation requires task-specific repository reasoning.",
                },
                "tbr": {
                    "Reviewer Agrees?": "Agree",
                    "Disagreed Checks": "none",
                    "Notes": "No material disagreement.",
                },
                "human": {
                    "Realistic Scenario?": "3",
                    "Realistic Scenario Notes": "The task models a concrete engineering maintenance scenario.",
                    "Domain Expertise?": "2",
                    "Domain Expertise Notes": "The task requires framework knowledge beyond general coding.",
                    "Original?": "3",
                    "Original Notes": "The combination is specific despite familiar primitives.",
                    "Primary Language": "Python",
                    "Other Languages": "Bash",
                    "Additional Notes": "No additional caveat.",
                },
                "decision": {
                    "Reason": "Critical 0, High 0, Medium 0, Low 1. The remaining issue is non-blocking and has an observable close condition.",
                    "Follow-up needed?": "No",
                },
                "other": {
                    "Notes": "Strengths: coherent behavior. To fix: add one edge assertion. To notice: external lookup is unavailable."
                },
                "confidence": {
                    "Confidence (1-5)": "4 - Exact files and current evidence are available."
                },
            },
            "validation_overrides": [],
        }
        write_json(self.review_data_path, self.review_data)
        self.review_path.write_text(
            render_review(self.review_data, self.findings, self.conditions),
            encoding="utf-8",
        )
        write_json(
            self.live_path,
            render_live_payload(self.review_data, self.findings, self.conditions),
        )
        self.evidence_path.write_text("Current task evidence.\n", encoding="utf-8")
        self.blind_path.write_text("Blind current-state result.\n", encoding="utf-8")
        self.ledger = {
            "schema_version": 1,
            "task": {"id": TASK_ID, "sha": TASK_SHA},
            "pagination": {
                "jobs": {
                    "complete": True,
                    "total": 0,
                    "ids": [],
                    "pages": 0,
                    "next_cursor": None,
                },
                "trials": {
                    "complete": True,
                    "total": 0,
                    "ids": [],
                    "pages": 0,
                    "next_cursor": None,
                },
                "reviews": {
                    "complete": True,
                    "total": 0,
                    "ids": [],
                    "pages": 0,
                    "next_cursor": None,
                },
            },
            "jobs": [],
            "trials": [],
            "reviews": [],
            "history": {"complete": True, "count": 0, "review_ids": []},
            "baselines": {
                name: {
                    "status": (
                        "not_applicable"
                        if name in {"hot_vs_cold", "with_vs_without_skill"}
                        else "not_verified"
                    ),
                    "rationale": f"{name} is unavailable in this synthetic fixture.",
                }
                for name in BASELINES
            },
            "prior_findings": [],
            "finding_dispositions": {},
            "unresolved": ["Synthetic fixture has no live task data."],
            "ios": None,
            "supplemental": {},
        }
        write_json(self.ledger_path, self.ledger)
        self.audit_path.write_text(
            json.dumps(
                {
                    "timestamp": timestamp(3),
                    "phase_sequence": 4,
                    "task_id": TASK_ID,
                    "argv": ["python3", "--version"],
                    "cwd": str(self.scratch),
                    "writes": [],
                    "exit_code": 0,
                    "sandbox": "linux",
                    "resolved_executable": "/usr/bin/python3",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        self.preflight_path.write_text(
            json.dumps(
                {
                    "verdict": "PASS",
                    "bundle_commit": "d" * 40,
                    "bundle_tree": "e" * 40,
                    "scratch_root": str(self.scratch.resolve()),
                    "sandbox_backend": "systemd",
                    "timestamp": timestamp(0),
                },
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        self.outputs: dict[str, Path] = {}
        for role in ("critic", "canonical_primary", "supplemental"):
            workspace = self.scratch / f"workspace-{role}"
            workspace.mkdir()
            output = workspace / f"{role}.md"
            output.write_text(
                f"{role} output for task {TASK_ID} at {TASK_SHA}.\n", encoding="utf-8"
            )
            self.outputs[role] = output
        self.outputs["critic"] = self.evidence_path
        supplemental_workspace = self.scratch / "workspace-supplemental"
        supplemental_summary = supplemental_workspace / "summary.md"
        supplemental_summary.write_text(
            "Bounded supplemental summary.\n", encoding="utf-8"
        )
        supplemental_ledger = supplemental_workspace / "ledger.json"
        write_json(
            supplemental_ledger,
            {
                "complete": True,
                "task_id": TASK_ID,
                "task_sha": TASK_SHA,
                "records": [],
            },
        )
        supplemental_descriptor = supplemental_workspace / "supplemental-output.json"
        descriptor = {
            "schema_version": 1,
            "task_id": TASK_ID,
            "task_sha": TASK_SHA,
            "complete": True,
            "total_records": 0,
            "summary_path": str(supplemental_summary),
            "summary_sha256": sha256_file(supplemental_summary),
            "ledger_path": str(supplemental_ledger),
            "ledger_sha256": sha256_file(supplemental_ledger),
        }
        write_json(supplemental_descriptor, descriptor)
        self.outputs["supplemental"] = supplemental_descriptor
        self.ledger["supplemental"] = {
            "status": "completed",
            "descriptor_path": str(supplemental_descriptor.resolve()),
            "descriptor_sha256": sha256_file(supplemental_descriptor),
            "reason": None,
        }
        write_json(self.ledger_path, self.ledger)
        self.manifest = self.make_manifest()
        self.manifest_path = self.scratch / "run-manifest.json"
        write_json(self.manifest_path, self.manifest)

    def run_record(
        self,
        role: str,
        runner: str,
        session: str,
        parent: str,
        status: str = "completed",
    ) -> dict[str, Any]:
        output = self.outputs.get(role)
        if output is None:
            workspace = self.scratch / f"workspace-{role}"
            workspace.mkdir(exist_ok=True)
            output = workspace / f"{role}.md"
            output.write_text(f"{role} distinct output\n", encoding="utf-8")
            self.outputs[role] = output
        if role == "critic" and status == "completed":
            status = "finalizing"
        completed = status in {"completed", "finalizing"}
        return {
            "role": role,
            "runner": runner,
            "session_id": session,
            "parent_session_id": parent,
            "workspace": str(output.parent.resolve()),
            "harness": "native",
            "loaded_skill": {
                "canonical_primary": "aai-review-flow",
                "supplemental": "review-trials-and-spec",
                "ios": "aai-ios",
                "lh_addon": "aai-long-horizon",
            }.get(role),
            "status": status,
            "skill_revision": {
                "critic": "d" * 40,
                "canonical_primary": load_json(ROOT / "references" / "release-lock.md")[
                    "dependencies"
                ]["aai-review-flow"],
                "canonical_fallback": load_json(
                    ROOT / "references" / "release-lock.md"
                )["dependencies"]["team-aai-fbsource"],
                "supplemental": load_json(ROOT / "references" / "release-lock.md")[
                    "dependencies"
                ]["review-trials-and-spec"],
                "ios": load_json(ROOT / "references" / "release-lock.md")[
                    "dependencies"
                ]["aai-ios"],
                "lh_addon": load_json(ROOT / "references" / "release-lock.md")[
                    "dependencies"
                ]["aai-long-horizon"],
            }.get(role, "1" * 40),
            "task_id": TASK_ID,
            "task_sha": TASK_SHA,
            "started_at": timestamp(
                0 if role == "critic" else (3 if role == "canonical_fallback" else 2)
            ),
            "ended_at": None if status == "finalizing" else timestamp(3),
            "output_path": str(output.resolve()) if completed else None,
            "output_sha256": sha256_file(output) if completed else None,
            "output_task_id": TASK_ID if completed else None,
            "output_task_sha": TASK_SHA if completed else None,
            "attestation_source": "agentcloud",
            "attested_run": {
                "critic": 42,
                "canonical_primary": 43,
                "canonical_fallback": 45,
                "supplemental": 44,
                "lh_addon": 46,
                "ios": 47,
            }.get(role, 49),
        }

    def make_manifest(self) -> dict[str, Any]:
        runs = [
            self.run_record(
                "critic",
                "codimango-review-critic",
                "critic-session",
                "dispatcher-session",
            ),
            self.run_record(
                "canonical_primary",
                "aai-review-flow",
                "primary-session",
                "critic-session",
            ),
            self.run_record(
                "supplemental",
                "review-trials-and-spec",
                "supplemental-session",
                "critic-session",
            ),
        ]
        phases = []
        for index, name in enumerate(
            (
                "preflight",
                "identity_frozen",
                "blind_started",
                "blind_sealed",
                "history_started",
                "history_complete",
                "finalized",
            )
        ):
            value: dict[str, Any] = {
                "name": name,
                "sequence": index + 1,
                "timestamp": timestamp(index),
                "task_id": TASK_ID,
            }
            if name == "blind_sealed":
                value["artifact_path"] = str(self.blind_path)
                value["artifact_sha256"] = sha256_file(self.blind_path)
            phases.append(value)
        final = {
            "owner_session_id": "critic-session",
            "review": {
                "path": str(self.review_path.resolve()),
                "sha256": sha256_file(self.review_path),
            },
            "live_payload": {
                "path": str(self.live_path.resolve()),
                "sha256": sha256_file(self.live_path),
            },
            "evidence": {
                "path": str(self.evidence_path.resolve()),
                "sha256": sha256_file(self.evidence_path),
            },
            "findings": {
                "path": str(self.findings_path.resolve()),
                "sha256": sha256_file(self.findings_path),
            },
            "evidence_ledger": {
                "path": str(self.ledger_path.resolve()),
                "sha256": sha256_file(self.ledger_path),
            },
            "command_audit": {
                "path": str(self.audit_path.resolve()),
                "sha256": sha256_file(self.audit_path),
            },
        }
        return {
            "schema_version": 2,
            "dispatcher_session_id": "dispatcher-session",
            "task": {
                "id": TASK_ID,
                "repo": "codimango/example-repo",
                "track": "swe-bench-pro",
                "variant": "swe_bench_single_turn",
                "base_track": "swe",
                "head_sha": HEAD_SHA,
                "validation_sha": TASK_SHA,
                "review_job_sha": TASK_SHA,
                "inspected_sha": INSPECTED_SHA,
            },
            "bundle": {
                "commit": "d" * 40,
                "tree": "e" * 40,
                "preflight_receipt_path": str(self.preflight_path),
                "preflight_receipt_sha256": sha256_file(self.preflight_path),
            },
            "scratch_root": str(self.scratch),
            "task_repo_root": str(self.repo),
            "runs": runs,
            "phases": phases,
            "conditions": {
                "path": str(self.conditions_path),
                "sha256": sha256_file(self.conditions_path),
            },
            "final": final,
            "publisher": {
                "source_path": str(self.review_path.resolve()),
                "source_sha256": final["review"]["sha256"],
                "published_path": None,
                "published_sha256": None,
            },
            "context": {
                "allowed_identifiers": [TASK_ID, TASK_SHA, HEAD_SHA, INSPECTED_SHA],
                "allowed_path_prefixes": [
                    "README.md",
                    "SKILL.md",
                    "tests",
                    "scripts",
                    "schema",
                ],
                "allowed_repositories": ["codimango/example-repo"],
            },
        }

    def sync(self) -> None:
        write_json(self.conditions_path, self.conditions)
        write_json(self.findings_path, self.findings)
        write_json(self.review_data_path, self.review_data)
        self.review_path.write_text(
            render_review(self.review_data, self.findings, self.conditions),
            encoding="utf-8",
        )
        write_json(
            self.live_path,
            render_live_payload(self.review_data, self.findings, self.conditions),
        )
        write_json(self.ledger_path, self.ledger)
        self.manifest["conditions"] = {
            "path": str(self.conditions_path),
            "sha256": sha256_file(self.conditions_path),
        }
        self.manifest["final"]["review"] = {
            "path": str(self.review_path.resolve()),
            "sha256": sha256_file(self.review_path),
        }
        self.manifest["final"]["live_payload"] = {
            "path": str(self.live_path.resolve()),
            "sha256": sha256_file(self.live_path),
        }
        self.manifest["final"]["findings"] = {
            "path": str(self.findings_path.resolve()),
            "sha256": sha256_file(self.findings_path),
        }
        self.manifest["final"]["evidence_ledger"] = {
            "path": str(self.ledger_path.resolve()),
            "sha256": sha256_file(self.ledger_path),
        }
        self.manifest["publisher"]["source_path"] = str(self.review_path)
        self.manifest["publisher"]["source_sha256"] = sha256_file(self.review_path)
        write_json(self.manifest_path, self.manifest)


def make_clean_bundle(parent: Path) -> Path:
    target = parent / "bundle"
    shutil.copytree(
        ROOT, target, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc")
    )
    write_json(target / "references" / "bundle-lock.md", seal_bundle(target))
    for command in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "config", "user.email", "test@example.com"],
        ["git", "config", "user.name", "Contract Test"],
        ["git", "add", "."],
        ["git", "commit", "-q", "-m", "fixture"],
    ):
        proc = run(command, cwd=target)
        if proc.returncode != 0:
            raise AssertionError(proc.stderr)
    return target


def item_i1(temp: Path) -> int:
    bundle = make_clean_bundle(temp / "one")
    scratch = temp / "scratch-good"
    preflight(bundle, scratch, temp / "preflight.json")
    registry_bundle = make_clean_bundle(temp / "registry")
    shutil.rmtree(registry_bundle / ".git")
    registry_receipt = preflight(
        registry_bundle,
        temp / "scratch-registry",
        temp / "preflight-registry.json",
    )
    require_full_sha(registry_receipt["bundle_commit"], "registry bundle identity")
    # A baseline without preflight has no rejection point: old=0.
    tampered = make_clean_bundle(temp / "two")
    (tampered / "scripts" / "lint_final_review.py").write_text(
        "tampered\n", encoding="utf-8"
    )
    expect_failure(
        lambda: preflight(tampered, temp / "scratch-tampered", temp / "bad.json"),
        "digest mismatch",
    )
    missing = make_clean_bundle(temp / "three")
    (missing / "SKILL.md").unlink()
    expect_failure(
        lambda: preflight(missing, temp / "scratch-missing", temp / "missing.json"),
        "file set changed",
    )
    inside = make_clean_bundle(temp / "four")
    expect_failure(
        lambda: preflight(inside, inside / "scratch", temp / "inside.json"), "outside"
    )
    dirty = make_clean_bundle(temp / "five")
    (dirty / "README.md").write_text(
        "dirty but same lock fails first\n", encoding="utf-8"
    )
    expect_failure(
        lambda: preflight(dirty, temp / "scratch-dirty", temp / "dirty.json"),
        "tracked bundle files are dirty",
    )
    print("DIRECTION I1 STRICTER old=0 new=2")
    return 6


def legacy_wrong_fallback(temp: Path, fixture: Fixture) -> int:
    receipt = {
        "task_id": TASK_ID,
        "task_sha": TASK_SHA,
        "track": "swe-bench-pro",
        "variant": "swe_bench_single_turn",
        "primary_runner": "aai-review-flow",
        "primary_status": "failed",
        "primary_session_id": "primary",
        "primary_skill_revision": "revision",
        "primary_output_path": None,
        "fallback_runner": "team-aai:review-task-tbench-v2",
        "fallback_status": "completed",
        "fallback_reason": "primary failed",
        "fallback_session_id": "fallback",
        "fallback_skill_revision": "revision",
        "fallback_output_path": str(fixture.outputs["canonical_primary"]),
        "supplemental_runner": "review-trials-and-spec",
        "supplemental_status": "completed",
        "supplemental_session_id": "supplemental",
        "supplemental_skill_revision": "revision",
        "supplemental_output_path": str(fixture.outputs["supplemental"]),
    }
    path = temp / "legacy-receipt.json"
    write_json(path, receipt)
    proc = old_script(
        "scripts/validate_canonical_execution.py",
        ["--receipt", str(path), "--task-id", TASK_ID, "--task-sha", TASK_SHA],
        temp,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"baseline unexpectedly rejected wrong fallback: {proc.stderr}"
        )
    return proc.returncode


def failed_primary(record: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(record)
    value.update(
        {
            "status": "failed",
            "output_path": None,
            "output_sha256": None,
            "output_task_id": None,
            "output_task_sha": None,
        }
    )
    return value


def item_i2(temp: Path) -> int:
    f = Fixture(temp / "fixture")
    validate_dag(f.manifest)
    unavailable_supplemental = copy.deepcopy(f.manifest)
    unavailable_run = next(
        run for run in unavailable_supplemental["runs"] if run["role"] == "supplemental"
    )
    unavailable_run.update(
        {
            "status": "unavailable",
            "loaded_skill": None,
            "output_path": None,
            "output_sha256": None,
            "output_task_id": None,
            "output_task_sha": None,
        }
    )
    validate_dag(unavailable_supplemental)
    duplicate_session = copy.deepcopy(f.manifest)
    duplicate_session["runs"][2]["session_id"] = duplicate_session["runs"][1][
        "session_id"
    ]
    expect_failure(lambda: validate_dag(duplicate_session), "duplicate session")
    duplicate_output = copy.deepcopy(f.manifest)
    duplicate_output["runs"][2]["output_path"] = duplicate_output["runs"][1][
        "output_path"
    ]
    duplicate_output["runs"][2]["output_sha256"] = duplicate_output["runs"][1][
        "output_sha256"
    ]
    expect_failure(
        lambda: validate_dag(duplicate_output), "outside attested session workspace"
    )
    wrong = copy.deepcopy(f.manifest)
    wrong["runs"][1] = failed_primary(wrong["runs"][1])
    fallback = f.run_record(
        "canonical_fallback",
        "team-aai:review-task-tbench-v2",
        "fallback-session",
        "critic-session",
    )
    wrong["runs"].append(fallback)
    expect_failure(
        lambda: validate_dag(wrong),
        "expected fallback team-aai:review-task-swebench-v2",
    )
    old = legacy_wrong_fallback(temp, f)
    primary_plus_fallback = copy.deepcopy(f.manifest)
    primary_plus_fallback["runs"].append(fallback)
    expect_failure(lambda: validate_dag(primary_plus_fallback), "fallback present")
    long_horizon = copy.deepcopy(wrong)
    long_horizon["task"]["track"] = "long-horizon"
    long_horizon["task"]["variant"] = "long_horizon"
    long_horizon["task"]["base_track"] = "swe-bench"
    long_horizon["runs"][-1]["runner"] = "team-aai:review-task-swebench-v2"
    expect_failure(lambda: validate_dag(long_horizon), "lh-review-task")
    parent_rewrite = copy.deepcopy(f.manifest)
    parent_rewrite["publisher"]["published_sha256"] = "9" * 64
    expect_failure(lambda: validate_dag(parent_rewrite), "byte hash changed")
    output_identity = copy.deepcopy(f.manifest)
    output_identity["runs"][1]["output_task_id"] = "foreign"
    expect_failure(lambda: validate_dag(output_identity), "output identity")
    wrong_revision = copy.deepcopy(f.manifest)
    wrong_revision["runs"][1]["skill_revision"] = "0" * 40
    expect_failure(lambda: validate_dag(wrong_revision), "differs from release lock")
    bad_sha = copy.deepcopy(f.manifest)
    bad_sha["task"]["validation_sha"] = "short"
    expect_failure(lambda: validate_dag(bad_sha), "does not match")
    print(f"DIRECTION I2 STRICTER old={old} new=2")
    return 11


def item_i3(temp: Path) -> int:
    f = Fixture(temp / "fixture")
    validate_phases(f.manifest)
    reversed_manifest = copy.deepcopy(f.manifest)
    reversed_manifest["phases"][3], reversed_manifest["phases"][4] = (
        reversed_manifest["phases"][4],
        reversed_manifest["phases"][3],
    )
    expect_failure(
        lambda: validate_phases(reversed_manifest),
        "history_started before blind_sealed",
    )
    missing = copy.deepcopy(f.manifest)
    missing["phases"].pop()
    expect_failure(lambda: validate_phases(missing), "expected")
    bad_hash = copy.deepcopy(f.manifest)
    bad_hash["phases"][3]["artifact_sha256"] = "0" * 64
    expect_failure(lambda: validate_phases(bad_hash), "digest mismatch")
    sequence_order = copy.deepcopy(f.manifest)
    sequence_order["phases"][4]["sequence"] = 4
    expect_failure(lambda: validate_phases(sequence_order), "sequences")
    print("DIRECTION I3 STRICTER old=0 new=2")
    return 5


def item_i4(temp: Path) -> int:
    cases = 0

    def resolve(value: dict[str, Any]) -> dict[str, Any]:
        nonlocal cases
        cases += 1
        return resolve_conditions(value)

    base = {
        "task_id": TASK_ID,
        "task_sha": TASK_SHA,
        "track": "tbench",
        "validation_overrides": [],
        "agentic": {"state": "not_run"},
    }
    assert resolve(base)["agentic"]["state"] == "not_required"
    completed = copy.deepcopy(base)
    completed["agentic"] = {
        "state": "completed",
        "review_body": "report",
        "run_id": "1",
    }
    assert resolve(completed)["agentic"]["state"] == "required"
    xml = temp / "review.xml"
    xml.write_text("<review>Agentic Full-Task Review</review>\n")
    recovered = copy.deepcopy(base)
    recovered["agentic"] = {
        "state": "parse_error",
        "run_id": "run-1",
        "traversal": {
            "complete": True,
            "job_id": "job-1",
            "trial_ids": ["trial-1"],
            "artifacts": [{"path": str(xml.resolve()), "sha256": sha256_file(xml)}],
        },
    }
    assert resolve(recovered)["agentic"]["state"] == "required"
    empty_xml = temp / "empty-review.xml"
    empty_xml.write_text("")
    no_body = copy.deepcopy(base)
    no_body["agentic"] = {
        "state": "parse_error",
        "traversal": {
            "complete": True,
            "job_id": "job-2",
            "trial_ids": ["trial-2"],
            "artifacts": [
                {"path": str(empty_xml.resolve()), "sha256": sha256_file(empty_xml)}
            ],
        },
    }
    assert resolve(no_body)["agentic"]["state"] == "not_required"
    missing_artifact = copy.deepcopy(base)
    missing_artifact["agentic"] = {
        "state": "parse_error",
        "traversal": {
            "complete": True,
            "job_id": "job-3",
            "trial_ids": ["trial-3"],
            "artifacts": [
                {"path": str((temp / "missing.xml").resolve()), "sha256": "0" * 64}
            ],
        },
    }
    value = resolve(missing_artifact)
    expect_failure(
        lambda: validate_conditions(value, TASK_ID, TASK_SHA), "agentic unresolved"
    )
    incomplete = copy.deepcopy(base)
    incomplete["agentic"] = {"state": "parse_error", "traversal": {"complete": False}}
    value = resolve(incomplete)
    expect_failure(
        lambda: validate_conditions(value, TASK_ID, TASK_SHA), "agentic unresolved"
    )
    override = copy.deepcopy(base)
    override["validation_overrides"] = [
        {
            "check": "AI assessment",
            "heading": "Quality Review Agent",
            "reason": "submitter rationale",
        }
    ]
    assert resolve(override)["validation_override"]["state"] == "required"
    missing_override = copy.deepcopy(base)
    missing_override.pop("validation_overrides")
    value = resolve(missing_override)
    expect_failure(
        lambda: validate_conditions(value, TASK_ID, TASK_SHA),
        "validation_override unresolved",
    )
    ios = copy.deepcopy(base)
    ios["track"] = "ios-swe-bench"
    assert resolve(ios)["ios"]["state"] == "required"
    assert resolve(base)["ios"]["state"] == "not_required"
    f = Fixture(temp / "fixture")
    conditional_conditions = copy.deepcopy(f.conditions)
    conditional_conditions["agentic"] = {
        "state": "required",
        "reason": "completed review body",
        "source": "api",
        "run_id": "agentic-run-1",
    }
    conditional_conditions["validation_override"] = {
        "state": "required",
        "reason": "live override reasons exist",
        "reasons": [
            {
                "check": "AI assessment",
                "heading": "Quality Review Agent",
                "reason": "submitter rationale",
            }
        ],
    }
    conditional_data = copy.deepcopy(f.review_data)
    conditional_data["sections"]["agentic"] = {
        "Reviewer Agrees?": "Agree",
        "Notes": "The completed Agentic report matches the current evidence.",
    }
    conditional_data["validation_overrides"] = [
        {
            "heading": "Quality Review Agent",
            "Submitter Reason": "submitter rationale",
            "Reviewer Agrees?": "Partially",
            "Reviewer Notes": "The override is only partly supported by the current tests.",
        }
    ]
    payload = render_live_payload(conditional_data, f.findings, conditional_conditions)
    if (
        payload.get("decision") != "accept"
        or payload.get("mmAgenticFullTaskReviewRunId") != "agentic-run-1"
        or payload.get("overrideReview")
        != {
            "AI assessment": {
                "agree": "Partially",
                "notes": "The override is only partly supported by the current tests.",
            }
        }
    ):
        raise AssertionError("conditional live payload does not match pinned API shape")
    cases += 1
    taxonomy = f.review_path.read_text().replace(
        "### Human Checks",
        "### Taxonomy Verification\n- **Whatever:** banana\n\n### Human Checks",
    )
    taxonomy_path = temp / "taxonomy.md"
    taxonomy_path.write_text(taxonomy)
    cases += 1
    expect_failure(
        lambda: parse_review(taxonomy_path, load_review_format(), f.conditions),
        "canonical section order",
    )
    old_template = baseline_file(
        "references/output-template.md", temp / "old-template.md"
    )
    old_review = temp / "old-review.md"
    old_review.write_text(f.review_path.read_text())
    old = old_script(
        "scripts/validate_review_schema.py",
        ["--template", str(old_template), "--review", str(old_review)],
        temp,
    ).returncode
    assert old == 0
    print("DIRECTION I4 STRICTER old=0 new=2")
    print("DIRECTION I4 LOOSER old=2 new=0 recovery=review.xml")
    return cases


def item_i5(temp: Path) -> int:
    f = Fixture(temp / "fixture")
    cases = 1
    validate_evidence(f.ledger, f.findings, f.manifest)
    unavailable_manifest = copy.deepcopy(f.manifest)
    unavailable_run = next(
        run for run in unavailable_manifest["runs"] if run["role"] == "supplemental"
    )
    unavailable_run.update(
        {
            "status": "unavailable",
            "loaded_skill": None,
            "output_path": None,
            "output_sha256": None,
            "output_task_id": None,
            "output_task_sha": None,
        }
    )
    unavailable_reason = (
        "review-trials-and-spec was attempted but unavailable in the active catalog."
    )
    unavailable_ledger = copy.deepcopy(f.ledger)
    unavailable_ledger["supplemental"] = {
        "status": "unavailable",
        "descriptor_path": None,
        "descriptor_sha256": None,
        "reason": unavailable_reason,
    }
    unavailable_ledger["unresolved"].append(unavailable_reason)
    validate_evidence(unavailable_ledger, f.findings, unavailable_manifest)
    cases += 1
    missing_baseline = copy.deepcopy(f.ledger)
    del missing_baseline["baselines"]["shortcut"]
    expect_failure(
        lambda: validate_evidence(missing_baseline, f.findings, f.manifest),
        "baseline shortcut missing",
    )
    cases += 1
    incomplete = copy.deepcopy(f.ledger)
    incomplete["pagination"]["jobs"]["complete"] = False
    expect_failure(
        lambda: validate_evidence(incomplete, f.findings, f.manifest),
        "pagination incomplete",
    )
    cases += 1
    total = copy.deepcopy(f.ledger)
    total["pagination"]["trials"]["total"] = 1
    expect_failure(
        lambda: validate_evidence(total, f.findings, f.manifest), "total mismatch"
    )
    cases += 1
    missing_column = copy.deepcopy(f.ledger)
    missing_column["jobs"] = [{"id": "j1"}]
    missing_column["pagination"]["jobs"] = {
        "complete": True,
        "total": 1,
        "ids": ["j1"],
        "pages": 1,
        "next_cursor": None,
    }
    expect_failure(
        lambda: validate_evidence(missing_column, f.findings, f.manifest), "missing"
    )
    cases += 1
    mixed = copy.deepcopy(missing_column)
    mixed["jobs"][0] = {
        "id": "j1",
        "task_id": TASK_ID,
        "class": "solve",
        "model_runtime": "x",
        "source_sha": "f" * 40,
        "reward": 1,
        "status": "completed",
        "artifacts_available": True,
        "exclusion_reason": "included",
        "scope": "current",
    }
    expect_failure(
        lambda: validate_evidence(mixed, f.findings, f.manifest), "mixed current SHA"
    )
    cases += 1
    foreign_job = copy.deepcopy(mixed)
    foreign_job["jobs"][0]["source_sha"] = TASK_SHA
    foreign_job["jobs"][0]["task_id"] = "foreign"
    expect_failure(
        lambda: validate_evidence(foreign_job, f.findings, f.manifest),
        "foreign task in job",
    )
    cases += 1
    invalid_scope = copy.deepcopy(mixed)
    invalid_scope["jobs"][0]["source_sha"] = TASK_SHA
    invalid_scope["jobs"][0]["scope"] = "mystery"
    expect_failure(
        lambda: validate_evidence(invalid_scope, f.findings, f.manifest),
        "not in enum",
    )
    cases += 1
    orphan = copy.deepcopy(mixed)
    orphan["jobs"][0]["source_sha"] = TASK_SHA
    orphan["trials"] = [
        {
            "id": "t1",
            "task_id": TASK_ID,
            "parent_job": "missing-job",
            "artifact_paths": [],
            "class": "solve",
            "model_runtime": "x",
            "source_sha": TASK_SHA,
            "reward": 0,
            "status": "completed",
            "artifacts_available": False,
            "exclusion_reason": "included",
            "scope": "current",
        }
    ]
    orphan["pagination"]["trials"] = {
        "complete": True,
        "total": 1,
        "ids": ["t1"],
        "pages": 1,
        "next_cursor": None,
    }
    expect_failure(
        lambda: validate_evidence(orphan, f.findings, f.manifest), "orphan trial"
    )
    cases += 1
    review_body = temp / "body.md"
    review_body.write_text("body\n")
    bad_review = copy.deepcopy(f.ledger)
    bad_review["reviews"] = [
        {
            "id": "r1",
            "task_id": TASK_ID,
            "kind": "human",
            "scope": "current",
            "sha": TASK_SHA,
            "body_path": str(temp / "missing.md"),
            "body_sha256": sha256_file(review_body),
            "finding_ids": [],
        }
    ]
    bad_review["history"] = {"complete": True, "count": 1, "review_ids": ["r1"]}
    bad_review["pagination"]["reviews"] = {
        "complete": True,
        "total": 1,
        "ids": ["r1"],
        "pages": 1,
        "next_cursor": None,
    }
    expect_failure(
        lambda: validate_evidence(bad_review, f.findings, f.manifest),
        "required nonempty",
    )
    cases += 1
    unreconciled = copy.deepcopy(f.ledger)
    unreconciled["reviews"] = [
        {
            "id": "current-review",
            "task_id": TASK_ID,
            "kind": "canonical",
            "scope": "current",
            "sha": TASK_SHA,
            "body_path": str(review_body),
            "body_sha256": sha256_file(review_body),
            "finding_ids": ["external-finding"],
        }
    ]
    unreconciled["history"] = {
        "complete": True,
        "count": 1,
        "review_ids": ["current-review"],
    }
    unreconciled["pagination"]["reviews"] = {
        "complete": True,
        "total": 1,
        "ids": ["current-review"],
        "pages": 1,
        "next_cursor": None,
    }
    expect_failure(
        lambda: validate_evidence(unreconciled, f.findings, f.manifest),
        "reconciliation is incomplete",
    )
    cases += 1
    prior = copy.deepcopy(f.ledger)
    prior["reviews"] = [
        {
            "id": "prior-review",
            "task_id": TASK_ID,
            "kind": "human",
            "scope": "prior",
            "sha": HEAD_SHA,
            "body_path": str(review_body),
            "body_sha256": sha256_file(review_body),
            "finding_ids": ["P1"],
        }
    ]
    prior["history"] = {
        "complete": True,
        "count": 1,
        "review_ids": ["prior-review"],
    }
    prior["pagination"]["reviews"] = {
        "complete": True,
        "total": 1,
        "ids": ["prior-review"],
        "pages": 1,
        "next_cursor": None,
    }
    prior["prior_findings"] = [
        {
            "id": "P1",
            "severity": "High",
            "prior_sha": HEAD_SHA,
            "prior_evidence": "old",
            "current_evidence": "new",
            "state": "present",
            "current_severity": "High",
            "replay_disposition": "",
        }
    ]
    expect_failure(
        lambda: validate_evidence(prior, f.findings, f.manifest), "replay disposition"
    )
    cases += 1
    missing_finding = copy.deepcopy(f.findings)
    del missing_finding["findings"][0]["reviewer_contribution"]
    expect_failure(
        lambda: validate_evidence(f.ledger, missing_finding, f.manifest),
        "missing required properties",
    )
    cases += 1
    duplicate = copy.deepcopy(f.findings)
    duplicate["findings"].append(copy.deepcopy(duplicate["findings"][0]))
    expect_failure(
        lambda: validate_evidence(f.ledger, duplicate, f.manifest), "duplicate id"
    )
    cases += 1
    supplemental = copy.deepcopy(f.ledger)
    invalid_descriptor_path = temp / "invalid-supplemental.json"
    write_json(
        invalid_descriptor_path,
        {
            "schema_version": 1,
            "task_id": TASK_ID,
            "task_sha": TASK_SHA,
            "complete": False,
            "total_records": 0,
            "summary_path": str(f.evidence_path),
            "summary_sha256": sha256_file(f.evidence_path),
            "ledger_path": str(f.ledger_path),
            "ledger_sha256": sha256_file(f.ledger_path),
        },
    )
    supplemental["supplemental"] = {
        "status": "completed",
        "descriptor_path": str(invalid_descriptor_path),
        "descriptor_sha256": sha256_file(invalid_descriptor_path),
        "reason": None,
    }
    supplemental_manifest = copy.deepcopy(f.manifest)
    supplemental_run = next(
        run for run in supplemental_manifest["runs"] if run["role"] == "supplemental"
    )
    supplemental_run["output_path"] = str(invalid_descriptor_path)
    supplemental_run["output_sha256"] = sha256_file(invalid_descriptor_path)
    expect_failure(
        lambda: validate_evidence(supplemental, f.findings, supplemental_manifest),
        "not complete",
    )
    cases += 1
    traversal_conditions = copy.deepcopy(f.conditions)
    traversal_conditions["agentic"] = {
        "state": "not_required",
        "reason": "verified report artifacts are empty",
        "traversal": {
            "complete": True,
            "job_id": "missing-job",
            "trial_ids": ["missing-trial"],
            "artifacts": [],
        },
    }
    traversal_conditions_path = temp / "traversal-conditions.json"
    write_json(traversal_conditions_path, traversal_conditions)
    traversal_manifest = copy.deepcopy(f.manifest)
    traversal_manifest["conditions"] = {
        "path": str(traversal_conditions_path),
        "sha256": sha256_file(traversal_conditions_path),
    }
    expect_failure(
        lambda: validate_evidence(f.ledger, f.findings, traversal_manifest),
        "not tied to job/trial inventory",
    )
    cases += 1
    ios_conditions = copy.deepcopy(f.conditions)
    ios_conditions["ios"] = {"state": "required", "reason": "iOS track"}
    ios_conditions_path = temp / "ios-conditions.json"
    write_json(ios_conditions_path, ios_conditions)
    ios_manifest = copy.deepcopy(f.manifest)
    ios_manifest["conditions"] = {
        "path": str(ios_conditions_path),
        "sha256": sha256_file(ios_conditions_path),
    }
    expect_failure(
        lambda: validate_evidence(f.ledger, f.findings, ios_manifest),
        "required iOS evidence missing",
    )
    cases += 1
    ios_ledger = copy.deepcopy(f.ledger)
    ios_ledger["ios"] = {
        "runner": "aai-ios",
        "target": "RealApp",
        "native_command": "xcodebuild test",
        "f2p": "base fail, gold pass",
        "p2p": "pass",
        "oracle": "1.0",
        "no_solution": "0.0",
        "surrogate_grading": False,
    }
    validate_evidence(ios_ledger, f.findings, ios_manifest)
    cases += 1
    surrogate = copy.deepcopy(ios_ledger)
    surrogate["ios"]["surrogate_grading"] = True
    expect_failure(
        lambda: validate_evidence(surrogate, f.findings, ios_manifest),
        "requires Request changes",
    )
    cases += 1
    print("DIRECTION I5 STRICTER old=0 new=2")
    return cases


def pad_to_words(text: str, target: int) -> str:
    current = max(
        len(text.split()), len(__import__("re").findall(r"\b\w+(?:[-']\w+)*\b", text))
    )
    if current > target:
        raise AssertionError("base fixture exceeds target")
    addition = " ".join(["word"] * (target - current))
    return text.replace(
        "The task is sound with one narrow coverage caveat.",
        "The task is sound with one narrow coverage caveat. " + addition,
    )


def item_i6(temp: Path) -> int:
    f = Fixture(temp / "fixture")
    cases = 1
    validate_final(
        f.review_path,
        f.template_path,
        f.conditions_path,
        f.findings_path,
        f.manifest_path,
    )
    exact = temp / "exact700.md"
    exact.write_text(pad_to_words(f.review_path.read_text(), 700))
    expect_failure(lambda: validate_language(exact, f.manifest), "WORD LIMIT REJECTED")
    cases += 1
    old = old_script("scripts/lint_final_review.py", [str(exact)], temp).returncode
    assert old == 0
    drift = temp / "drift.md"
    drift.write_text(f.template_path.read_text() + "\n- **New Required:** value\n")
    expect_failure(
        lambda: validate_final(
            f.review_path, drift, f.conditions_path, f.findings_path, f.manifest_path
        ),
        "template drift",
    )
    cases += 1
    mutations = [
        ("preamble", "hello\n" + f.review_path.read_text(), "preamble"),
        ("fenced", f.review_path.read_text() + "```\n", "fenced"),
        (
            "counts",
            f.review_path.read_text().replace("Low 1", "Low 0"),
            "counts mismatch",
        ),
        (
            "placeholder",
            f.review_path.read_text().replace(
                "The task models a concrete engineering maintenance scenario.", "None"
            ),
            "placeholder",
        ),
        (
            "short-rationale",
            f.review_path.read_text().replace(
                "The task models a concrete engineering maintenance scenario.", "x"
            ),
            "too short",
        ),
        (
            "tbr",
            f.review_path.read_text().replace(
                "Disagreed Checks:** none", "Disagreed Checks:** invented_check"
            ),
            "unknown TBR check IDs",
        ),
        (
            "tbr-agree-with-check",
            f.review_path.read_text().replace(
                "### TBR Review Agreement\n- **Reviewer Agrees?:** Agree\n- **Disagreed Checks:** none",
                "### TBR Review Agreement\n- **Reviewer Agrees?:** Agree\n- **Disagreed Checks:** behavior_in_tests",
            ),
            "TBR agreement contradicts",
        ),
        (
            "tbr-disagree-with-none",
            f.review_path.read_text().replace(
                "### TBR Review Agreement\n- **Reviewer Agrees?:** Agree\n- **Disagreed Checks:** none",
                "### TBR Review Agreement\n- **Reviewer Agrees?:** Disagree\n- **Disagreed Checks:** none",
            ),
            "TBR disagreement requires",
        ),
        (
            "extra",
            f.review_path.read_text().replace(
                "- **Notes:** The task is sound",
                "extra prose\n- **Notes:** The task is sound",
            ),
            "field count",
        ),
        (
            "missing",
            f.review_path.read_text().split("### Other Notes")[0]
            + f.review_path.read_text()
            .split("### Reviewer Confidence")[1]
            .join(["### Reviewer Confidence", ""]),
            "section order",
        ),
        (
            "order",
            f.review_path.read_text()
            .replace("### Contamination Review Agent", "### TEMP")
            .replace("### Novelty Review Agent", "### Contamination Review Agent")
            .replace("### TEMP", "### Novelty Review Agent"),
            "section order",
        ),
    ]
    for name, text, message in mutations:
        path = temp / f"{name}.md"
        path.write_text(text)
        expect_failure(
            lambda path=path: validate_final(
                path,
                f.template_path,
                f.conditions_path,
                f.findings_path,
                f.manifest_path,
            ),
            message,
        )
        cases += 1
    mismatch_findings = copy.deepcopy(f.findings)
    mismatch_findings["decision"] = "Request changes"
    mismatch_findings["decision_reconciliation"] = (
        "The quality view is positive, but a separately verified reward-integrity blocker requires revision."
    )
    mismatch_findings["findings"][0]["blocking"] = True
    mismatch_data = copy.deepcopy(f.review_data)
    mismatch_data["sections"]["decision"][
        "Reason"
    ] = "Critical 0, High 0, Medium 0, Low 1. A separately verified blocker requires revision despite the quality direction. Add one behavioral assertion for the edge case."
    mismatch_review = temp / "mismatch-valid.md"
    mismatch_review.write_text(
        render_review(mismatch_data, mismatch_findings, f.conditions)
    )
    mismatch_findings_path = temp / "mismatch-findings.json"
    write_json(mismatch_findings_path, mismatch_findings)
    mismatch_manifest = copy.deepcopy(f.manifest)
    mismatch_manifest["final"]["review"] = {
        "path": str(mismatch_review),
        "sha256": sha256_file(mismatch_review),
    }
    mismatch_manifest["final"]["findings"] = {
        "path": str(mismatch_findings_path),
        "sha256": sha256_file(mismatch_findings_path),
    }
    mismatch_manifest["publisher"]["source_path"] = str(mismatch_review)
    mismatch_manifest["publisher"]["source_sha256"] = sha256_file(mismatch_review)
    mismatch_manifest_path = temp / "mismatch-manifest.json"
    write_json(mismatch_manifest_path, mismatch_manifest)
    validate_final(
        mismatch_review,
        f.template_path,
        f.conditions_path,
        mismatch_findings_path,
        mismatch_manifest_path,
    )
    if (
        render_live_payload(mismatch_data, mismatch_findings, f.conditions)["decision"]
        != "revision"
    ):
        raise AssertionError("Request changes did not map to live revision action")
    cases += 1
    missing_reconciliation = copy.deepcopy(mismatch_findings)
    missing_reconciliation["decision_reconciliation"] = "short"
    missing_path = temp / "short-reconciliation.json"
    write_json(missing_path, missing_reconciliation)
    expect_failure(
        lambda: validate_final(
            mismatch_review,
            f.template_path,
            f.conditions_path,
            missing_path,
            mismatch_manifest_path,
        ),
        "substantive reconciliation",
    )
    cases += 1
    critical_nonblocking = copy.deepcopy(f.findings)
    critical_nonblocking["findings"][0]["severity"] = "Critical"
    expect_failure(
        lambda: validate_findings(critical_nonblocking, TASK_ID, TASK_SHA),
        "must be blocking",
    )
    cases += 1
    medium_threshold = copy.deepcopy(f.findings)
    medium_threshold["findings"] = []
    for index in range(3):
        finding = copy.deepcopy(f.findings["findings"][0])
        finding["id"] = f"M{index + 1}"
        finding["severity"] = "Medium"
        finding["blocking"] = False
        medium_threshold["findings"].append(finding)
    expect_failure(
        lambda: validate_findings(medium_threshold, TASK_ID, TASK_SHA),
        "blocking severity threshold",
    )
    cases += 1
    request_without_blocker = copy.deepcopy(f.findings)
    request_without_blocker["decision"] = "Request changes"
    request_without_blocker["decision_reconciliation"] = (
        "The decision diverges from the positive quality verdict for a separate verified reason."
    )
    expect_failure(
        lambda: validate_findings(request_without_blocker, TASK_ID, TASK_SHA),
        "no blocking finding",
    )
    cases += 1
    short_close = copy.deepcopy(f.findings)
    short_close["findings"][0]["close_condition"] = "short"
    expect_failure(
        lambda: validate_findings(short_close, TASK_ID, TASK_SHA),
        "string is shorter than 15",
    )
    cases += 1
    omitted_close_data = copy.deepcopy(mismatch_data)
    omitted_close_data["sections"]["decision"][
        "Reason"
    ] = "Critical 0, High 0, Medium 0, Low 1. A separately verified blocker requires revision despite the quality direction."
    omitted_close_review = temp / "omitted-close.md"
    omitted_close_review.write_text(
        render_review(omitted_close_data, mismatch_findings, f.conditions)
    )
    omitted_close_manifest = copy.deepcopy(mismatch_manifest)
    omitted_close_manifest["final"]["review"] = {
        "path": str(omitted_close_review),
        "sha256": sha256_file(omitted_close_review),
    }
    omitted_close_manifest["publisher"]["source_path"] = str(omitted_close_review)
    omitted_close_manifest["publisher"]["source_sha256"] = sha256_file(
        omitted_close_review
    )
    omitted_close_manifest_path = temp / "omitted-close-manifest.json"
    write_json(omitted_close_manifest_path, omitted_close_manifest)
    expect_failure(
        lambda: validate_final(
            omitted_close_review,
            f.template_path,
            f.conditions_path,
            mismatch_findings_path,
            omitted_close_manifest_path,
        ),
        "omits close condition",
    )
    cases += 1
    wrong_high = copy.deepcopy(f.findings)
    wrong_high["findings"][0]["status"] = "WRONG"
    wrong_high["findings"][0]["severity"] = "High"
    wrong_high["findings"][0]["blocking"] = True
    wrong_high["decision"] = "Request changes"
    expect_failure(
        lambda: validate_findings(wrong_high, TASK_ID, TASK_SHA),
        "WRONG finding",
    )
    cases += 1
    reject_without_critical = copy.deepcopy(mismatch_findings)
    reject_without_critical["decision"] = "Reject"
    expect_failure(
        lambda: validate_findings(reject_without_critical, TASK_ID, TASK_SHA),
        "requires a confirmed Critical blocker",
    )
    cases += 1
    print(f"DIRECTION I6 STRICTER old={old} new=2")
    return cases


def item_i7(temp: Path) -> int:
    f = Fixture(temp / "fixture")
    policy = ROOT / "references" / "command-policy.md"
    cases = 1
    validate_command_audit(f.audit_path, f.manifest, policy)
    empty = temp / "empty.jsonl"
    empty.write_text("")
    expect_failure(
        lambda: validate_command_audit(empty, f.manifest, policy), "empty command audit"
    )
    cases += 1

    def audit_case(
        name: str, argv: list[str], writes: list[str] | None = None, task: str = TASK_ID
    ) -> Path:
        path = temp / f"{name}.jsonl"
        path.write_text(
            json.dumps(
                {
                    "timestamp": timestamp(3),
                    "phase_sequence": 4,
                    "task_id": task,
                    "argv": argv,
                    "cwd": str(f.scratch),
                    "writes": writes or [],
                    "exit_code": 0,
                    "sandbox": "linux",
                    "resolved_executable": f"/usr/bin/{Path(argv[0]).name}",
                }
            )
            + "\n"
        )
        return path

    for name, argv, message in (
        ("binary", ["unknown-tool"], "unapproved executable"),
        ("queue", ["codimango", "task", "list", "--reviewing"], "mutation command"),
        ("feedback", ["codimango", "feedback", "send", TASK_ID], "mutation command"),
        ("push", ["git", "push"], "mutation command"),
        (
            "meta-mutation",
            ["meta", "tasks.task", "update", "--id=T1"],
            "unapproved Meta command",
        ),
    ):
        path = audit_case(name, argv)
        expect_failure(
            lambda path=path: validate_command_audit(path, f.manifest, policy), message
        )
        cases += 1
    outside = audit_case(
        "outside", ["python3", "--version"], [str(temp / "outside.txt")]
    )
    expect_failure(
        lambda: validate_command_audit(outside, f.manifest, policy), "outside scratch"
    )
    cases += 1
    foreign_task = audit_case("foreign-task", ["python3", "--version"], task="other")
    expect_failure(
        lambda: validate_command_audit(foreign_task, f.manifest, policy), "foreign task"
    )
    cases += 1
    preseal = temp / "preseal-history.jsonl"
    preseal.write_text(
        json.dumps(
            {
                "timestamp": timestamp(3),
                "phase_sequence": 3,
                "task_id": TASK_ID,
                "argv": [
                    "codimango",
                    "trial",
                    "artifacts",
                    TASK_ID,
                    "--key",
                    "review.xml",
                ],
                "cwd": str(f.scratch),
                "writes": [],
                "exit_code": 0,
                "sandbox": "linux",
                "resolved_executable": "/usr/bin/codimango",
            }
        )
        + "\n"
    )
    expect_failure(
        lambda: validate_command_audit(preseal, f.manifest, policy),
        "before blind_sealed",
    )
    cases += 1
    foreign_review = temp / "foreign.md"
    foreign_review.write_text(
        f.review_path.read_text().replace(
            "No additional caveat.", f"No additional caveat at {'9'*40}."
        )
    )
    expect_failure(
        lambda: validate_language(foreign_review, f.manifest), "foreign identifier"
    )
    cases += 1
    old = old_script(
        "scripts/lint_final_review.py", [str(foreign_review)], temp
    ).returncode
    assert old == 0
    print(f"DIRECTION I7 STRICTER old={old} new=2")
    return cases


def item_i8(temp: Path) -> int:
    cases = 0
    summary = temp / "summary.md"
    summary.write_text("Short summary.\n")
    ledger_path = temp / "supplemental-ledger.json"
    write_json(
        ledger_path,
        {
            "complete": True,
            "task_id": TASK_ID,
            "task_sha": TASK_SHA,
            "records": [
                {
                    "id": "one",
                    "task_id": TASK_ID,
                    "task_sha": TASK_SHA,
                    "finding_ids": [],
                    "disposition": "included",
                }
            ],
        },
    )
    value = {
        "schema_version": 1,
        "task_id": TASK_ID,
        "task_sha": TASK_SHA,
        "complete": True,
        "total_records": 1,
        "summary_path": str(summary),
        "summary_sha256": sha256_file(summary),
        "ledger_path": str(ledger_path),
        "ledger_sha256": sha256_file(ledger_path),
    }
    validate_supplemental(value, TASK_ID, TASK_SHA)
    cases += 1
    huge = temp / "huge.md"
    huge.write_text("x" * 12001)
    too_big = copy.deepcopy(value)
    too_big["summary_path"] = str(huge)
    too_big["summary_sha256"] = sha256_file(huge)
    expect_failure(lambda: validate_supplemental(too_big, TASK_ID, TASK_SHA), "exceeds")
    cases += 1
    count = copy.deepcopy(value)
    count["total_records"] = 2
    expect_failure(
        lambda: validate_supplemental(count, TASK_ID, TASK_SHA), "count mismatch"
    )
    cases += 1
    incomplete = copy.deepcopy(value)
    incomplete["complete"] = False
    expect_failure(
        lambda: validate_supplemental(incomplete, TASK_ID, TASK_SHA), "not complete"
    )
    cases += 1
    validate_release_lock(
        ROOT / "references" / "release-lock.md",
        ROOT / "references" / "output-template.md",
    )
    cases += 1
    bad_lock = copy.deepcopy(load_json(ROOT / "references" / "release-lock.md"))
    bad_lock["dependencies"]["aai-review-flow"] = "master"
    bad_lock_path = temp / "bad-release.json"
    write_json(bad_lock_path, bad_lock)
    expect_failure(
        lambda: validate_release_lock(bad_lock_path), "dependency aai-review-flow"
    )
    cases += 1
    foreign_ledger = temp / "foreign-supplemental-ledger.json"
    foreign_data = load_json(ledger_path)
    foreign_data["task_id"] = "foreign"
    write_json(foreign_ledger, foreign_data)
    foreign_descriptor = copy.deepcopy(value)
    foreign_descriptor["ledger_path"] = str(foreign_ledger)
    foreign_descriptor["ledger_sha256"] = sha256_file(foreign_ledger)
    expect_failure(
        lambda: validate_supplemental(foreign_descriptor, TASK_ID, TASK_SHA),
        "identity/completeness mismatch",
    )
    cases += 1
    ledger_before = sha256_file(ledger_path)
    alias = run(
        [
            sys.executable,
            str(ROOT / "scripts" / "compact_supplemental.py"),
            "--task-id",
            TASK_ID,
            "--task-sha",
            TASK_SHA,
            "--summary",
            str(summary),
            "--ledger",
            str(ledger_path),
            "--output",
            str(ledger_path),
        ]
    )
    if alias.returncode != 2 or "must not alias" not in alias.stderr:
        raise AssertionError("supplemental alias control did not fire")
    if sha256_file(ledger_path) != ledger_before:
        raise AssertionError("supplemental alias control modified its input")
    cases += 1
    print("DIRECTION I8 STRICTER old=0 new=2")
    return cases


ITEMS: dict[str, Callable[[Path], int]] = {
    "I1": item_i1,
    "I2": item_i2,
    "I3": item_i3,
    "I4": item_i4,
    "I5": item_i5,
    "I6": item_i6,
    "I7": item_i7,
    "I8": item_i8,
}
EXPECTED = {"I1": 6, "I2": 11, "I3": 5, "I4": 12, "I5": 20, "I6": 23, "I7": 11, "I8": 8}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--item", choices=sorted(ITEMS))
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--compare-base", required=True)
    args = parser.parse_args()
    if args.compare_base not in {"d790666", BASELINE}:
        print(f"unsupported comparison baseline: {args.compare_base}", file=sys.stderr)
        return 2
    selected = sorted(ITEMS) if args.all else [args.item]
    if selected == [None]:
        parser.error("choose --item or --all")
    try:
        with tempfile.TemporaryDirectory(prefix="critic-contract-tests-") as raw:
            root = Path(raw)
            total = 0
            for item in selected:
                item_root = root / item
                item_root.mkdir()
                cases = ITEMS[item](item_root)
                if cases != EXPECTED[item]:
                    raise AssertionError(
                        f"{item}: expected {EXPECTED[item]} cases, ran {cases}"
                    )
                total += cases
                print(f"CONTRACT {item} PASS cases={cases}")
            print(f"CONTRACT SUITE PASS items={len(selected)} cases={total}")
        return 0
    except (AssertionError, ContractError, OSError, ValueError, KeyError) as exc:
        print(f"CONTRACT SUITE FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
