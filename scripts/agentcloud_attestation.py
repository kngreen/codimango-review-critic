#!/usr/bin/env python3
"""Read immutable Agentcloud session facts from the durable control-plane journal."""

from __future__ import annotations

import json
import shlex
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from contract import ContractError, ROOT, load_json, sha256_file

ROLE_RUNNERS = {
    "critic": "codimango-review-critic",
    "canonical_primary": "aai-review-flow",
    "supplemental": "review-trials-and-spec",
    "ios": "aai-ios",
    "lh_addon": "aai-long-horizon:lh-review-task",
}
ROLE_DEPENDENCIES = {
    "canonical_primary": "aai-review-flow",
    "supplemental": "review-trials-and-spec",
    "ios": "aai-ios",
    "lh_addon": "aai-long-horizon",
}
ROLE_SKILLS = {
    "canonical_primary": "aai-review-flow",
    "supplemental": "review-trials-and-spec",
    "ios": "aai-ios",
    "lh_addon": "aai-long-horizon:lh-review-task",
}


def successful_skill_load(session_id: str, run: int, skill: str) -> bool:
    frames = history_frames(session_id)
    run_sequences = [
        int(frame.get("seq", -1))
        for frame in frames
        if (frame.get("ctx") or {}).get("run") == run
    ]
    if not run_sequences:
        return False
    run_end = max(run_sequences)
    intents: set[int] = set()
    for frame in frames:
        event = frame.get("event", {})
        if event.get("type") != "tool_intent" or str(event.get("tool")) != "Skill":
            continue
        if int(frame.get("seq", -1)) > run_end:
            continue
        raw = event.get("input")
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                continue
        requested = None
        if isinstance(raw, dict):
            requested = raw.get("name") or raw.get("skill")
        if isinstance(requested, str) and (
            requested == skill or requested.endswith(":" + skill)
        ):
            intents.add(int(frame.get("seq", -1)))
    if any(
        int(frame.get("seq", -1)) <= run_end
        and frame.get("event", {}).get("type") == "tool_result"
        and frame.get("event", {}).get("intent") in intents
        and frame.get("event", {}).get("outcome", {}).get("outcome") == "success"
        for frame in frames
    ):
        return True

    run_starts = [
        int(frame.get("seq", -1))
        for frame in frames
        if frame.get("event", {}).get("type") == "run_started"
        and frame.get("ctx", {}).get("run") == run
    ]
    if len(run_starts) != 1:
        return False
    prior_inputs = [
        frame
        for frame in frames
        if frame.get("event", {}).get("type") == "user_input"
        and int(frame.get("seq", -1)) < run_starts[0]
    ]
    if not prior_inputs:
        return False
    latest = max(prior_inputs, key=lambda frame: int(frame.get("seq", -1)))
    text = latest.get("event", {}).get("text")
    if not isinstance(text, str) or not text.lstrip().startswith("/"):
        return False
    command = text.lstrip().split(None, 1)[0][1:]
    return command == skill or command.endswith(":" + skill)


def _run_json(args: list[str]) -> Any:
    try:
        proc = subprocess.run(
            ["agentcloudctl", *args],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise ContractError(f"Agentcloud attestation unavailable: {exc}") from exc
    if proc.returncode != 0:
        raise ContractError(
            f"Agentcloud attestation command failed: {' '.join(args)}: {proc.stderr.strip()}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ContractError("Agentcloud attestation returned invalid JSON") from exc


def session_row(session_id: str) -> dict[str, Any]:
    rows = _run_json(["list"])
    matches = [row for row in rows if row.get("session_id") == session_id]
    if len(matches) != 1:
        raise ContractError(
            f"Agentcloud session {session_id} was not found exactly once"
        )
    return matches[0]


def history_frames(session_id: str) -> list[dict[str, Any]]:
    try:
        proc = subprocess.run(
            ["agentcloudctl", "history", "-s", session_id, "--raw"],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise ContractError(f"Agentcloud history unavailable: {exc}") from exc
    if proc.returncode != 0:
        raise ContractError(f"Agentcloud history failed: {proc.stderr.strip()}")
    frames: list[dict[str, Any]] = []
    for number, line in enumerate(proc.stdout.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ContractError(
                f"Agentcloud history line {number} is invalid JSON"
            ) from exc
        if isinstance(value, dict):
            frames.append(value)
    if not frames:
        raise ContractError("Agentcloud history is empty")
    return frames


def _tool_text(frame: dict[str, Any]) -> str | None:
    event = frame.get("event", {})
    if event.get("type") != "tool_result":
        return None
    outcome = event.get("outcome", {})
    if outcome.get("outcome") != "success":
        return None
    content = outcome.get("content", {})
    text = content.get("text") if isinstance(content, dict) else None
    return text if isinstance(text, str) else None


def _bound_tool_calls(
    frames: list[dict[str, Any]], required_script: str
) -> dict[tuple[int, str], dict[str, Any]]:
    calls: dict[tuple[int, str], dict[str, Any]] = {}
    for frame in frames:
        event = frame.get("event", {})
        if event.get("type") not in {"tool_call", "tool_intent"}:
            continue
        name = (
            str(event.get("name") or event.get("tool") or "").lower().replace("__", ".")
        )
        if not name.endswith("bash"):
            continue
        frame_run = frame.get("ctx", {}).get("run")
        raw_input = event.get("input", {})
        if isinstance(raw_input, str):
            try:
                raw_input = json.loads(raw_input)
            except json.JSONDecodeError:
                continue
        command = raw_input.get("command") if isinstance(raw_input, dict) else None
        if not isinstance(frame_run, int) or not isinstance(command, str):
            continue
        try:
            tokens = shlex.split(command)
        except ValueError:
            continue
        if any(token in {";", "&&", "||", "|", ">", ">>", "<"} for token in tokens):
            continue
        script_positions = [
            index
            for index, token in enumerate(tokens)
            if Path(token).name == required_script
        ]
        if script_positions != [1] or Path(tokens[0]).name not in {
            "python",
            "python3",
            "python3.12",
        }:
            continue
        intent_id = (
            event.get("tool_call_id")
            if event.get("type") == "tool_call"
            else frame.get("seq")
        )
        calls[(frame_run, str(intent_id))] = event
    return calls


def tool_receipt(
    session_id: str,
    prefix: str,
    run: int | None = None,
    required_script: str | None = None,
) -> tuple[dict[str, Any], int]:
    frames = history_frames(session_id)
    calls = _bound_tool_calls(frames, required_script) if required_script else {}
    matches: list[tuple[dict[str, Any], int, int]] = []
    for frame in frames:
        text = _tool_text(frame)
        if text is None:
            continue
        event = frame.get("event", {})
        frame_run = frame.get("ctx", {}).get("run")
        if run is not None and frame_run != run:
            continue
        if required_script:
            intent_id = event.get("tool_call_id", event.get("intent"))
            if (frame_run, str(intent_id)) not in calls:
                continue
        for line in text.splitlines():
            if line.startswith(prefix):
                try:
                    value = json.loads(line[len(prefix) :])
                except json.JSONDecodeError as exc:
                    raise ContractError(
                        f"invalid {prefix.rstrip('=')} JSON in Agentcloud journal"
                    ) from exc
                matches.append((value, int(frame_run), int(frame.get("seq", 0))))
    if len(matches) != 1:
        raise ContractError(
            f"expected exactly one {prefix.rstrip('=')} tool receipt, found {len(matches)}"
        )
    value, frame_run, _ = matches[0]
    return value, frame_run


def attested_run_record(
    session_id: str,
    run: int | None = None,
    allow_running: bool = False,
    expected_role: str | None = None,
) -> dict[str, Any]:
    if not isinstance(run, int) or run < 1:
        raise ContractError("Agentcloud attestation requires an exact run number")
    row = session_row(session_id)
    started_at, ended_at, lifecycle_status = run_lifecycle(session_id, run)
    if lifecycle_status == "running":
        if not allow_running:
            raise ContractError("Agentcloud run is still open")
        status = "finalizing"
    else:
        status = lifecycle_status
    parent = row.get("parent")
    workspace = row.get("workspace")
    harness = row.get("harness")
    if not isinstance(parent, str) or not parent:
        raise ContractError("Agentcloud control plane lacks parent session")
    if not isinstance(workspace, str) or not workspace:
        raise ContractError("Agentcloud control plane lacks workspace")
    if harness not in {"native", "claude_code", "codex", "muse_code"}:
        raise ContractError("Agentcloud control plane lacks a supported harness")

    if status in {"failed", "unavailable"}:
        if expected_role not in ROLE_RUNNERS or expected_role == "critic":
            raise ContractError("failed Agentcloud run needs a supported expected role")
        lock = load_json(ROOT / "references" / "release-lock.md")
        dependency = ROLE_DEPENDENCIES.get(expected_role)
        if dependency is None:
            raise ContractError(
                "failed fallback/add-on run cannot be inferred without receipt"
            )
        return {
            "role": expected_role,
            "runner": ROLE_RUNNERS[expected_role],
            "session_id": session_id,
            "parent_session_id": parent,
            "workspace": workspace,
            "harness": harness,
            "loaded_skill": None,
            "status": status,
            "skill_revision": lock["dependencies"][dependency],
            "task_id": None,
            "task_sha": None,
            "started_at": started_at,
            "ended_at": ended_at,
            "output_path": None,
            "output_sha256": None,
            "output_task_id": None,
            "output_task_sha": None,
            "attestation_source": "agentcloud",
            "attested_run": run,
        }

    receipt, attested_run = tool_receipt(
        session_id,
        "CODIMANGO_RUN_RECEIPT=",
        run,
        required_script="emit_run_receipt.py",
    )
    if receipt.get("session_id") != session_id:
        raise ContractError("journal receipt session mismatch")
    required = {
        "role",
        "runner",
        "status",
        "task_id",
        "task_sha",
        "skill_revision",
        "output_path",
        "output_sha256",
    }
    missing = sorted(required - set(receipt))
    if missing:
        raise ContractError(f"journal receipt missing {missing}")
    if expected_role is not None and receipt["role"] != expected_role:
        raise ContractError("journal receipt role differs from expected role")
    expected_runner = ROLE_RUNNERS.get(receipt["role"])
    if expected_runner is not None and receipt["runner"] != expected_runner:
        raise ContractError("journal receipt runner is not canonical for its role")
    expected_skill = ROLE_SKILLS.get(receipt["role"])
    semantic_status = receipt["status"]
    if semantic_status not in {"completed", "failed", "unavailable"}:
        raise ContractError("journal receipt has invalid semantic status")
    if (
        semantic_status == "completed"
        and expected_skill is not None
        and not successful_skill_load(session_id, attested_run, expected_skill)
    ):
        raise ContractError(
            f"Agentcloud journal lacks successful {expected_skill} skill load"
        )
    if status == "finalizing":
        if receipt["role"] != "critic" or semantic_status != "completed":
            raise ContractError(
                "running finalizer receipt must belong to completed critic work"
            )
    else:
        status = semantic_status
    output_path: Path | None = None
    if status in {"completed", "finalizing"}:
        if not receipt.get("output_path") or not receipt.get("output_sha256"):
            raise ContractError("successful journal receipt lacks output")
        output_path = Path(receipt["output_path"])
        if sha256_file(output_path) != receipt["output_sha256"]:
            raise ContractError("journal run output digest mismatch")
    elif (
        receipt.get("output_path") is not None
        or receipt.get("output_sha256") is not None
    ):
        raise ContractError("failed journal receipt claims output")
    return {
        "role": receipt["role"],
        "runner": receipt["runner"],
        "session_id": session_id,
        "parent_session_id": parent,
        "workspace": workspace,
        "harness": harness,
        "loaded_skill": (
            expected_skill if status in {"completed", "finalizing"} else None
        ),
        "status": status,
        "skill_revision": receipt["skill_revision"],
        "task_id": receipt["task_id"],
        "task_sha": receipt["task_sha"],
        "started_at": started_at,
        "ended_at": ended_at,
        "output_path": str(output_path.resolve()) if output_path else None,
        "output_sha256": receipt["output_sha256"] if output_path else None,
        "output_task_id": receipt["task_id"] if output_path else None,
        "output_task_sha": receipt["task_sha"] if output_path else None,
        "attestation_source": "agentcloud",
        "attested_run": attested_run,
    }


def run_lifecycle(session_id: str, run: int) -> tuple[str, str | None, str]:
    started_ms: int | None = None
    finished_ms: int | None = None
    terminal: str | None = None
    for frame in history_frames(session_id):
        event = frame.get("event", {})
        ctx_run = frame.get("ctx", {}).get("run")
        if event.get("type") == "run_started" and (
            ctx_run == run or event.get("run") == run
        ):
            started_ms = int(frame["created_at_unix_ms"])
        if event.get("type") == "run_finished" and (
            ctx_run == run or event.get("run") == run
        ):
            finished_ms = int(frame["created_at_unix_ms"])
            raw = event.get("outcome", event.get("result", frame.get("outcome")))
            if isinstance(raw, dict):
                raw = raw.get("outcome") or raw.get("status")
            terminal = str(raw).lower() if raw is not None else None
    if started_ms is None:
        raise ContractError(f"Agentcloud run {run} lacks run_started")

    def iso(value: int) -> str:
        return (
            datetime.fromtimestamp(value / 1000, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z")
        )

    if finished_ms is None:
        return iso(started_ms), None, "running"
    if terminal in {"completed", "success", "succeeded", "done"}:
        status = "completed"
    elif terminal in {"expired", "unavailable"}:
        status = "unavailable"
    elif terminal in {"failed", "error", "cancelled", "canceled"}:
        status = "failed"
    else:
        raise ContractError(
            f"Agentcloud run {run} has unknown terminal outcome {raw!r}"
        )
    return iso(started_ms), iso(finished_ms), status


def run_times(session_id: str, run: int) -> tuple[str, str]:
    started_at, ended_at, status = run_lifecycle(session_id, run)
    if ended_at is None or status == "running":
        raise ContractError(f"Agentcloud run {run} lacks start/finish events")
    return started_at, ended_at
