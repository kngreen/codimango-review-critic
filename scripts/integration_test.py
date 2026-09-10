#!/usr/bin/env python3
"""Command-level smoke test for the complete review protocol."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from contract import sha256_file, write_json
from contract_test import (
    Fixture,
    HEAD_SHA,
    INSPECTED_SHA,
    TASK_ID,
    TASK_SHA,
    make_clean_bundle,
)

ROOT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable


def invoke(
    args: list[str],
    expected: str | tuple[str, ...],
    cwd: Path = ROOT,
    expect: int = 0,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        args, cwd=cwd, text=True, capture_output=True, check=False, env=env
    )
    combined = proc.stdout + proc.stderr
    matched = (
        expected in combined
        if isinstance(expected, str)
        else any(value in combined for value in expected)
    )
    if proc.returncode != expect or not matched:
        raise AssertionError(
            f"command {args!r} returned {proc.returncode}, expected {expect}; "
            f"missing {expected!r}\nstdout={proc.stdout}\nstderr={proc.stderr}"
        )
    return proc


def main() -> int:
    try:
        with tempfile.TemporaryDirectory(prefix="critic-integration-") as raw:
            temp = Path(raw)
            fixture = Fixture(temp / "fixture")

            invoke(
                [
                    PYTHON,
                    "scripts/reviewctl.py",
                    "validate-dag",
                    str(fixture.manifest_path),
                ],
                "RUN DAG OK roles=3",
            )
            invoke(
                [
                    PYTHON,
                    "scripts/reviewctl.py",
                    "validate-phases",
                    str(fixture.manifest_path),
                ],
                "PHASE ORDER OK events=7",
            )
            invoke(
                [
                    PYTHON,
                    "scripts/validate_canonical_execution.py",
                    "--receipt",
                    str(fixture.manifest_path),
                    "--task-id",
                    TASK_ID,
                    "--task-sha",
                    TASK_SHA,
                ],
                "CANONICAL REVIEW EXECUTION OK",
            )
            invoke(
                [
                    PYTHON,
                    "scripts/validate_internal_evidence.py",
                    "--ledger",
                    str(fixture.ledger_path),
                    "--findings",
                    str(fixture.findings_path),
                    "--manifest",
                    str(fixture.manifest_path),
                ],
                "EVIDENCE LEDGER OK",
            )
            invoke(
                [
                    PYTHON,
                    "scripts/lint_final_review.py",
                    str(fixture.review_path),
                    "--manifest",
                    str(fixture.manifest_path),
                ],
                "FINAL REVIEW LANGUAGE OK",
            )
            invoke(
                [
                    PYTHON,
                    "scripts/validate_review_schema.py",
                    "--template",
                    str(fixture.template_path),
                    "--review",
                    str(fixture.review_path),
                    "--conditions",
                    str(fixture.conditions_path),
                    "--findings",
                    str(fixture.findings_path),
                    "--manifest",
                    str(fixture.manifest_path),
                ],
                "CANONICAL REVIEW SCHEMA OK",
            )
            invoke(
                [
                    PYTHON,
                    "scripts/validate_command_audit.py",
                    "--audit",
                    str(fixture.audit_path),
                    "--manifest",
                    str(fixture.manifest_path),
                ],
                "READ-ONLY AUDIT OK commands=1",
            )

            rendered = temp / "rendered.md"
            invoke(
                [
                    PYTHON,
                    "scripts/render_review.py",
                    "--data",
                    str(fixture.review_data_path),
                    "--findings",
                    str(fixture.findings_path),
                    "--conditions",
                    str(fixture.conditions_path),
                    "--output",
                    str(rendered),
                ],
                "REVIEW RENDERED",
            )
            if rendered.read_bytes() != fixture.review_path.read_bytes():
                raise AssertionError("renderer output differs from fixture review")
            live = temp / "live.json"
            invoke(
                [
                    PYTHON,
                    "scripts/render_live_payload.py",
                    "--data",
                    str(fixture.review_data_path),
                    "--findings",
                    str(fixture.findings_path),
                    "--conditions",
                    str(fixture.conditions_path),
                    "--output",
                    str(live),
                ],
                "LIVE PAYLOAD RENDERED",
            )

            live_payload = json.loads(live.read_text())
            if (
                live_payload.get("decision") != "accept"
                or "followUpNeeded" in live_payload
                or "validationOverrides" in live_payload
            ):
                raise AssertionError("live payload does not match pinned API contract")

            fake_bin = temp / "fake-bin"
            fake_bin.mkdir()
            fake_agentcloudctl = fake_bin / "agentcloudctl"
            attestation_path = temp / "finalization-attestation.json"
            role_runs = {
                "critic-session": (fixture.manifest["runs"][0], 42, True),
                "primary-session": (fixture.manifest["runs"][1], 43, False),
                "supplemental-session": (fixture.manifest["runs"][2], 44, False),
            }
            rows = []
            frames = []
            seq = 1
            for session_id, (record, run_id, running) in role_runs.items():
                rows.append(
                    {
                        "session_id": session_id,
                        "parent": record["parent_session_id"],
                        "workspace": record["workspace"],
                        "harness": "native",
                        "running": running,
                        "last_outcome": None if running else {"outcome": "completed"},
                    }
                )
                started_ms = (
                    1767225600000 if record["role"] == "critic" else 1767225602000
                )
                frames.append(
                    {
                        "frame": "durable",
                        "seq": seq,
                        "created_at_unix_ms": started_ms,
                        "event": {"type": "run_started"},
                        "ctx": {"run": run_id, "session_id": session_id},
                    }
                )
                seq += 1
                if record["loaded_skill"] is not None:
                    skill_intent = seq
                    frames.append(
                        {
                            "frame": "durable",
                            "seq": skill_intent,
                            "created_at_unix_ms": started_ms + 100,
                            "event": {
                                "type": "tool_intent",
                                "tool": "Skill",
                                "input": json.dumps(
                                    {"name": record["loaded_skill"], "args": None}
                                ),
                            },
                            "ctx": {"run": run_id, "session_id": session_id},
                        }
                    )
                    seq += 1
                    frames.append(
                        {
                            "frame": "durable",
                            "seq": seq,
                            "created_at_unix_ms": started_ms + 150,
                            "event": {
                                "type": "tool_result",
                                "intent": skill_intent,
                                "outcome": {
                                    "outcome": "success",
                                    "content": {"text": "skill loaded"},
                                },
                            },
                            "ctx": {"run": run_id, "session_id": session_id},
                        }
                    )
                    seq += 1
                run_receipt = {
                    "session_id": session_id,
                    "role": record["role"],
                    "runner": record["runner"],
                    "status": "completed",
                    "task_id": record["task_id"],
                    "task_sha": record["task_sha"],
                    "skill_revision": record["skill_revision"],
                    "output_path": record["output_path"],
                    "output_sha256": record["output_sha256"],
                }
                intent_seq = seq
                frames.append(
                    {
                        "frame": "durable",
                        "seq": intent_seq,
                        "created_at_unix_ms": started_ms + 250,
                        "event": {
                            "type": "tool_intent",
                            "tool": "bash",
                            "input": json.dumps(
                                {
                                    "command": "python3 scripts/emit_run_receipt.py --role "
                                    + record["role"]
                                }
                            ),
                        },
                        "ctx": {"run": run_id, "session_id": session_id},
                    }
                )
                seq += 1
                frames.append(
                    {
                        "frame": "durable",
                        "seq": seq,
                        "created_at_unix_ms": started_ms + 500,
                        "event": {
                            "type": "tool_result",
                            "intent": intent_seq,
                            "outcome": {
                                "outcome": "success",
                                "content": {
                                    "text": "CODIMANGO_RUN_RECEIPT="
                                    + json.dumps(run_receipt, sort_keys=True)
                                },
                            },
                        },
                        "ctx": {"run": run_id, "session_id": session_id},
                    }
                )
                seq += 1
                if not running:
                    frames.append(
                        {
                            "frame": "durable",
                            "seq": seq,
                            "created_at_unix_ms": 1767225603000,
                            "event": {"type": "run_finished", "outcome": "completed"},
                            "ctx": {"run": run_id, "session_id": session_id},
                        }
                    )
                    seq += 1
            no_skill_record = fixture.manifest["runs"][1]
            no_skill_receipt = {
                "session_id": "no-skill-session",
                "role": "canonical_primary",
                "runner": "aai-review-flow",
                "status": "completed",
                "task_id": TASK_ID,
                "task_sha": TASK_SHA,
                "skill_revision": no_skill_record["skill_revision"],
                "output_path": no_skill_record["output_path"],
                "output_sha256": no_skill_record["output_sha256"],
            }
            rows.extend(
                [
                    {
                        "session_id": "failed-session",
                        "parent": "critic-session",
                        "workspace": str(temp / "failed-workspace"),
                        "harness": "native",
                        "running": False,
                        "last_outcome": {"outcome": "completed"},
                    },
                    {
                        "session_id": "rogue-session",
                        "parent": "critic-session",
                        "workspace": str(temp / "rogue-workspace"),
                        "harness": "native",
                        "running": False,
                        "last_outcome": {"outcome": "completed"},
                    },
                    {
                        "session_id": "no-skill-session",
                        "parent": "critic-session",
                        "workspace": str(temp / "no-skill-workspace"),
                        "harness": "native",
                        "running": False,
                        "last_outcome": {"outcome": "completed"},
                    },
                ]
            )
            frames.extend(
                [
                    {
                        "frame": "durable",
                        "seq": seq,
                        "created_at_unix_ms": 1767225604000,
                        "event": {"type": "run_started"},
                        "ctx": {"run": 45, "session_id": "failed-session"},
                    },
                    {
                        "frame": "durable",
                        "seq": seq + 1,
                        "created_at_unix_ms": 1767225605000,
                        "event": {"type": "run_finished", "outcome": "failed"},
                        "ctx": {"run": 45, "session_id": "failed-session"},
                    },
                    {
                        "frame": "durable",
                        "seq": seq + 2,
                        "created_at_unix_ms": 1767225604000,
                        "event": {"type": "run_started"},
                        "ctx": {"run": 46, "session_id": "rogue-session"},
                    },
                    {
                        "frame": "durable",
                        "seq": seq + 3,
                        "created_at_unix_ms": 1767225604500,
                        "event": {
                            "type": "tool_result",
                            "tool_call_id": "missing-call",
                            "outcome": {
                                "outcome": "success",
                                "content": {
                                    "text": "CODIMANGO_RUN_RECEIPT="
                                    + json.dumps(
                                        {
                                            **run_receipt,
                                            "session_id": "rogue-session",
                                        },
                                        sort_keys=True,
                                    )
                                },
                            },
                        },
                        "ctx": {"run": 46, "session_id": "rogue-session"},
                    },
                    {
                        "frame": "durable",
                        "seq": seq + 4,
                        "created_at_unix_ms": 1767225605000,
                        "event": {"type": "run_finished", "outcome": "completed"},
                        "ctx": {"run": 46, "session_id": "rogue-session"},
                    },
                    {
                        "frame": "durable",
                        "seq": seq + 5,
                        "created_at_unix_ms": 1767225604000,
                        "event": {"type": "run_started"},
                        "ctx": {"run": 47, "session_id": "no-skill-session"},
                    },
                    {
                        "frame": "durable",
                        "seq": seq + 6,
                        "created_at_unix_ms": 1767225604250,
                        "event": {
                            "type": "tool_intent",
                            "tool": "bash",
                            "input": json.dumps(
                                {
                                    "command": "python3 scripts/emit_run_receipt.py --role canonical_primary"
                                }
                            ),
                        },
                        "ctx": {"run": 47, "session_id": "no-skill-session"},
                    },
                    {
                        "frame": "durable",
                        "seq": seq + 7,
                        "created_at_unix_ms": 1767225604500,
                        "event": {
                            "type": "tool_result",
                            "intent": seq + 6,
                            "outcome": {
                                "outcome": "success",
                                "content": {
                                    "text": "CODIMANGO_RUN_RECEIPT="
                                    + json.dumps(no_skill_receipt, sort_keys=True)
                                },
                            },
                        },
                        "ctx": {"run": 47, "session_id": "no-skill-session"},
                    },
                    {
                        "frame": "durable",
                        "seq": seq + 8,
                        "created_at_unix_ms": 1767225605000,
                        "event": {"type": "run_finished", "outcome": "completed"},
                        "ctx": {"run": 47, "session_id": "no-skill-session"},
                    },
                ]
            )
            frames.append(
                {
                    "frame": "durable",
                    "seq": 90,
                    "created_at_unix_ms": 1767225603500,
                    "event": {
                        "type": "tool_intent",
                        "tool": "bash",
                        "input": json.dumps(
                            {
                                "command": "python3 scripts/finalize_review.py --manifest run-manifest.json"
                            }
                        ),
                    },
                    "ctx": {"run": 42, "session_id": "critic-session"},
                }
            )
            fake_agentcloudctl.write_text(
                "#!/usr/bin/env python3\n"
                "import json, pathlib, sys\n"
                "rows = "
                + repr(rows)
                + "\nframes = "
                + repr(frames)
                + "\nattestation_path = pathlib.Path("
                + repr(str(attestation_path))
                + ")\n"
                "if len(sys.argv) > 1 and sys.argv[1] == 'list':\n"
                "    print(json.dumps(rows))\n"
                "elif len(sys.argv) > 1 and sys.argv[1] == 'history':\n"
                "    selected = next((sys.argv[i+1] for i,v in enumerate(sys.argv[:-1]) if v == '-s'), None)\n"
                "    for frame in frames:\n"
                "        if frame.get('ctx', {}).get('session_id') == selected:\n"
                "            print(json.dumps(frame))\n"
                "    if selected == 'critic-session' and attestation_path.is_file():\n"
                "        receipt = json.loads(attestation_path.read_text())\n"
                "        frame = {'frame':'durable','seq':99,'created_at_unix_ms':1767225604000,'event':{'type':'tool_result','intent':90,'outcome':{'outcome':'success','content':{'text':'FINALIZATION_RECEIPT=' + json.dumps(receipt, sort_keys=True)}}},'ctx':{'run':42,'session_id':'critic-session'}}\n"
                "        print(json.dumps(frame))\n"
                "else:\n"
                "    raise SystemExit(2)\n"
            )
            fake_agentcloudctl.chmod(0o755)
            publish_env = os.environ.copy()
            publish_env["PATH"] = str(fake_bin) + os.pathsep + publish_env["PATH"]

            approval = temp / "approval.json"
            final_env = publish_env.copy()
            final_env["AGENTCLOUD_SESSION_ID"] = "critic-session"
            invoke(
                [
                    PYTHON,
                    "scripts/finalize_review.py",
                    "--manifest",
                    str(fixture.manifest_path),
                    "--conditions",
                    str(fixture.conditions_path),
                    "--review",
                    str(fixture.review_path),
                    "--live-payload",
                    str(fixture.live_path),
                    "--review-data",
                    str(fixture.review_data_path),
                    "--findings",
                    str(fixture.findings_path),
                    "--ledger",
                    str(fixture.ledger_path),
                    "--evidence",
                    str(fixture.evidence_path),
                    "--command-audit",
                    str(fixture.audit_path),
                    "--approval",
                    str(approval),
                ],
                "FINALIZATION OK",
                env=final_env,
            )
            approval_data = json.loads(approval.read_text())
            attestation = {
                "approval_sha256": sha256_file(approval),
                "run_manifest_sha256": approval_data["run_manifest"]["sha256"],
                "review_sha256": approval_data["files"]["review"]["sha256"],
                "live_payload_sha256": approval_data["files"]["live_payload"]["sha256"],
                "critic_session_id": "critic-session",
            }
            forged_manifest = temp / "forged-manifest.json"
            forged_manifest_data = json.loads(fixture.manifest_path.read_text())
            forged_manifest_data["runs"][1]["parent_session_id"] = "forged-parent"
            write_json(forged_manifest, forged_manifest_data)
            invoke(
                [
                    PYTHON,
                    "scripts/finalize_review.py",
                    "--manifest",
                    str(forged_manifest),
                    "--conditions",
                    str(fixture.conditions_path),
                    "--review",
                    str(fixture.review_path),
                    "--live-payload",
                    str(fixture.live_path),
                    "--review-data",
                    str(fixture.review_data_path),
                    "--findings",
                    str(fixture.findings_path),
                    "--ledger",
                    str(fixture.ledger_path),
                    "--evidence",
                    str(fixture.evidence_path),
                    "--command-audit",
                    str(fixture.audit_path),
                    "--approval",
                    str(temp / "forged-run-approval.json"),
                ],
                "Agentcloud run attestation mismatch",
                expect=2,
                env=final_env,
            )
            write_json(attestation_path, attestation)
            alternate_conditions = temp / "alternate-conditions.json"
            alternate = json.loads(fixture.conditions_path.read_text())
            alternate["agentic"] = {
                "state": "required",
                "reason": "completed review body",
                "source": "api",
                "run_id": "foreign-run",
            }
            write_json(alternate_conditions, alternate)
            invoke(
                [
                    PYTHON,
                    "scripts/finalize_review.py",
                    "--manifest",
                    str(fixture.manifest_path),
                    "--conditions",
                    str(alternate_conditions),
                    "--review",
                    str(fixture.review_path),
                    "--live-payload",
                    str(fixture.live_path),
                    "--review-data",
                    str(fixture.review_data_path),
                    "--findings",
                    str(fixture.findings_path),
                    "--ledger",
                    str(fixture.ledger_path),
                    "--evidence",
                    str(fixture.evidence_path),
                    "--command-audit",
                    str(fixture.audit_path),
                    "--approval",
                    str(temp / "alternate-conditions-approval.json"),
                ],
                "conditions path differs from frozen manifest",
                expect=2,
                env=final_env,
            )
            run_record = temp / "agentcloud-run.json"
            invoke(
                [
                    PYTHON,
                    "scripts/adapters/agentcloud.py",
                    "--session-id",
                    "primary-session",
                    "--run",
                    "43",
                    "--expected-role",
                    "canonical_primary",
                    "--output",
                    str(run_record),
                ],
                "AGENTCLOUD RUN RECORD OK",
                env=publish_env,
            )
            attested_record = json.loads(run_record.read_text())
            if (
                attested_record["parent_session_id"] != "critic-session"
                or attested_record["runner"] != "aai-review-flow"
            ):
                raise AssertionError("Agentcloud adapter did not derive trusted fields")
            failed_record = temp / "failed-run.json"
            invoke(
                [
                    PYTHON,
                    "scripts/adapters/agentcloud.py",
                    "--session-id",
                    "failed-session",
                    "--run",
                    "45",
                    "--expected-role",
                    "canonical_primary",
                    "--output",
                    str(failed_record),
                ],
                "AGENTCLOUD RUN RECORD OK",
                env=publish_env,
            )
            failed_data = json.loads(failed_record.read_text())
            if (
                failed_data["status"] != "failed"
                or failed_data["output_path"] is not None
            ):
                raise AssertionError(
                    "failed Agentcloud run was not derived from run outcome"
                )
            invoke(
                [
                    PYTHON,
                    "scripts/adapters/agentcloud.py",
                    "--session-id",
                    "rogue-session",
                    "--run",
                    "46",
                    "--expected-role",
                    "canonical_primary",
                    "--output",
                    str(temp / "rogue-run.json"),
                ],
                "expected exactly one CODIMANGO_RUN_RECEIPT tool receipt, found 0",
                expect=2,
                env=publish_env,
            )
            invoke(
                [
                    PYTHON,
                    "scripts/adapters/agentcloud.py",
                    "--session-id",
                    "no-skill-session",
                    "--run",
                    "47",
                    "--expected-role",
                    "canonical_primary",
                    "--output",
                    str(temp / "no-skill-run.json"),
                ],
                "lacks successful aai-review-flow skill load",
                expect=2,
                env=publish_env,
            )
            published = temp / "published.md"
            invoke(
                [
                    PYTHON,
                    "scripts/publish_verified.py",
                    "--approval",
                    str(approval),
                    "--critic-session-id",
                    "critic-session",
                    "--run",
                    "42",
                    "--source",
                    str(fixture.review_path),
                    "--destination",
                    str(published),
                ],
                "PUBLISH VERIFIED",
                env=publish_env,
            )
            if published.read_bytes() != fixture.review_path.read_bytes():
                raise AssertionError("publisher changed review bytes")
            forged_approval = temp / "forged-approval.json"
            forged = json.loads(approval.read_text())
            forged["files"]["review"]["sha256"] = "8" * 64
            write_json(forged_approval, forged)
            invoke(
                [
                    PYTHON,
                    "scripts/publish_verified.py",
                    "--approval",
                    str(forged_approval),
                    "--critic-session-id",
                    "critic-session",
                    "--run",
                    "42",
                    "--source",
                    str(fixture.review_path),
                    "--destination",
                    str(temp / "forged-publish.md"),
                ],
                "Agentcloud finalization receipt mismatch",
                expect=2,
                env=publish_env,
            )
            tampered = temp / "tampered.md"
            tampered.write_text(fixture.review_path.read_text() + "changed\n")
            invoke(
                [
                    PYTHON,
                    "scripts/publish_verified.py",
                    "--approval",
                    str(approval),
                    "--critic-session-id",
                    "critic-session",
                    "--run",
                    "42",
                    "--source",
                    str(tampered),
                    "--destination",
                    str(temp / "bad-publish.md"),
                ],
                "digest mismatch",
                expect=2,
                env=publish_env,
            )

            summary = temp / "supplemental-summary.md"
            summary.write_text("Bounded summary.\n")
            supplemental_ledger = temp / "supplemental-ledger.json"
            write_json(
                supplemental_ledger,
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
            descriptor = temp / "supplemental.json"
            invoke(
                [
                    PYTHON,
                    "scripts/compact_supplemental.py",
                    "--task-id",
                    TASK_ID,
                    "--task-sha",
                    TASK_SHA,
                    "--summary",
                    str(summary),
                    "--ledger",
                    str(supplemental_ledger),
                    "--output",
                    str(descriptor),
                ],
                "SUPPLEMENTAL OUTPUT OK records=1",
            )

            # Lifecycle commands: preflight -> bootstrap -> audited first command -> identity freeze.
            bundle = make_clean_bundle(temp / "lifecycle")
            scratch = temp / "lifecycle-scratch"
            receipt = scratch / "preflight.json"
            manifest = scratch / "manifest.json"
            invoke(
                [
                    PYTHON,
                    str(bundle / "scripts" / "reviewctl.py"),
                    "preflight",
                    "--bundle",
                    str(bundle),
                    "--scratch-root",
                    str(scratch),
                    "--receipt",
                    str(receipt),
                ],
                "PREFLIGHT OK",
                cwd=bundle,
            )
            invoke(
                [
                    PYTHON,
                    str(bundle / "scripts" / "run_review.py"),
                    "bootstrap",
                    "--bundle",
                    str(bundle),
                    "--scratch-root",
                    str(scratch),
                    "--preflight-receipt",
                    str(receipt),
                    "--manifest",
                    str(manifest),
                    "--dispatcher-session-id",
                    "dispatcher",
                    "--task-id",
                    TASK_ID,
                ],
                "REVIEW BOOTSTRAPPED",
                cwd=bundle,
            )
            audit = scratch / "audit.jsonl"
            sandbox_supported = True
            if sys.platform.startswith("linux"):
                unshare = shutil.which("unshare")
                sandbox_supported = bool(
                    unshare
                    and subprocess.run(
                        [unshare, "-Ur", "true"],
                        text=True,
                        capture_output=True,
                        check=False,
                    ).returncode
                    == 0
                )
            invoke(
                [
                    PYTHON,
                    str(bundle / "scripts" / "audit_exec.py"),
                    "--audit",
                    str(audit),
                    "--manifest",
                    str(manifest),
                    "--cwd",
                    str(scratch),
                    "--",
                    "python3",
                    "--version",
                ],
                "Python" if sandbox_supported else "Linux user namespace unavailable",
                cwd=bundle,
                expect=0 if sandbox_supported else 2,
            )
            fake_python = scratch / "python3"
            fake_python.write_text("#!/bin/sh\nexit 0\n")
            fake_python.chmod(0o755)
            invoke(
                [
                    PYTHON,
                    str(bundle / "scripts" / "audit_exec.py"),
                    "--audit",
                    str(audit),
                    "--manifest",
                    str(manifest),
                    "--cwd",
                    str(scratch),
                    "--",
                    str(fake_python),
                    "--version",
                ],
                "untrusted workspace",
                cwd=bundle,
                expect=2,
            )
            task_root = temp / "task-root"
            task_root.mkdir()
            protected = task_root / "protected.txt"
            protected.write_text("original\n")
            invoke(
                [
                    PYTHON,
                    str(bundle / "scripts" / "run_review.py"),
                    "freeze-identity",
                    "--manifest",
                    str(manifest),
                    "--repo",
                    "codimango/example-repo",
                    "--track",
                    "swe-bench-pro",
                    "--variant",
                    "swe_bench_single_turn",
                    "--head-sha",
                    HEAD_SHA,
                    "--validation-sha",
                    TASK_SHA,
                    "--review-job-sha",
                    TASK_SHA,
                    "--inspected-sha",
                    INSPECTED_SHA,
                    "--task-repo-root",
                    str(temp / "task-root"),
                    "--allow-path",
                    "tests",
                ],
                "IDENTITY FROZEN",
                cwd=bundle,
            )
            invoke(
                [
                    PYTHON,
                    str(bundle / "scripts" / "audit_exec.py"),
                    "--audit",
                    str(audit),
                    "--manifest",
                    str(manifest),
                    "--cwd",
                    str(scratch),
                    "--",
                    "python3",
                    "-c",
                    f"from pathlib import Path; Path({str(protected)!r}).write_text('changed')",
                ],
                (
                    ("Read-only file system", "Operation not permitted")
                    if sandbox_supported
                    else "Linux user namespace unavailable"
                ),
                cwd=bundle,
                expect=1 if sandbox_supported else 2,
            )
            if protected.read_text() != "original\n":
                raise AssertionError("task repository was modified through audit_exec")
            shm_probe = (
                "/dev/shm/codimango-critic-write-probe"
                if sys.platform.startswith("linux")
                else str(temp / "outside-scratch-write-probe")
            )
            invoke(
                [
                    PYTHON,
                    str(bundle / "scripts" / "audit_exec.py"),
                    "--audit",
                    str(audit),
                    "--manifest",
                    str(manifest),
                    "--cwd",
                    str(scratch),
                    "--",
                    "python3",
                    "-c",
                    f"from pathlib import Path; Path({shm_probe!r}).write_text('changed')",
                ],
                (
                    ("Read-only file system", "Operation not permitted")
                    if sandbox_supported
                    else "Linux user namespace unavailable"
                ),
                cwd=bundle,
                expect=1 if sandbox_supported else 2,
            )
            if Path(shm_probe).exists():
                raise AssertionError("sandbox wrote outside scratch")

            print(
                "INTEGRATION OK commands=23 final_sha256="
                + sha256_file(fixture.review_path)
                + " published_sha256="
                + sha256_file(published)
            )
        return 0
    except (AssertionError, OSError, ValueError, KeyError) as exc:
        print(f"INTEGRATION FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
