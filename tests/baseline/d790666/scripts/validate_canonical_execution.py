#!/usr/bin/env python3
"""Fail closed unless canonical and supplemental Codimango reviewers actually completed."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ALLOWED_PRIMARY = {"aai-review-flow"}
ALLOWED_FALLBACKS = {
    "team-aai:review-task-tbench-v2",
    "team-aai:review-task-swebench-v2",
    "team-aai:review-task-tbench-multiturn",
    "team-aai:review-task-swebench-multiturn",
    "aai-long-horizon:lh-review-task",
}
ALLOWED_SUPPLEMENTAL = {"review-trials-and-spec"}


def nonempty_file(value: object) -> bool:
    if not isinstance(value, str) or not value:
        return False
    path = Path(value)
    return path.is_file() and path.stat().st_size > 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--task-sha", required=True)
    args = parser.parse_args()

    data = json.loads(args.receipt.read_text(encoding="utf-8"))
    errors: list[str] = []

    if str(data.get("task_id")) != args.task_id:
        errors.append(f"task_id mismatch: {data.get('task_id')!r} != {args.task_id!r}")
    if data.get("task_sha") != args.task_sha:
        errors.append(f"task_sha mismatch: {data.get('task_sha')!r} != {args.task_sha!r}")
    for key in ("track", "variant"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            errors.append(f"missing receipt field: {key}")

    primary_ok = (
        data.get("primary_runner") in ALLOWED_PRIMARY
        and data.get("primary_status") == "completed"
        and isinstance(data.get("primary_session_id"), str)
        and bool(data["primary_session_id"].strip())
        and isinstance(data.get("primary_skill_revision"), str)
        and bool(data["primary_skill_revision"].strip())
        and nonempty_file(data.get("primary_output_path"))
    )

    fallback_runner = data.get("fallback_runner")
    fallback_ok = (
        fallback_runner in ALLOWED_FALLBACKS
        and data.get("fallback_status") == "completed"
        and isinstance(data.get("fallback_reason"), str)
        and bool(data["fallback_reason"].strip())
        and isinstance(data.get("fallback_session_id"), str)
        and bool(data["fallback_session_id"].strip())
        and isinstance(data.get("fallback_skill_revision"), str)
        and bool(data["fallback_skill_revision"].strip())
        and nonempty_file(data.get("fallback_output_path"))
    )

    if not primary_ok and not fallback_ok:
        errors.append("neither aai-review-flow nor a defined canonical fallback completed with a nonempty output")

    if primary_ok:
        # A successful primary must not pretend a fallback also ran.
        if fallback_runner not in (None, "") or data.get("fallback_status") not in (None, "not_needed"):
            errors.append("fallback fields must be null/not_needed when aai-review-flow succeeds")
    else:
        if data.get("primary_runner") != "aai-review-flow":
            errors.append("primary_runner must identify aai-review-flow even when loading/execution failed")
        if data.get("primary_status") not in {"unavailable", "failed"}:
            errors.append("failed primary_status must be unavailable or failed")

    supplemental_ok = (
        data.get("supplemental_runner") in ALLOWED_SUPPLEMENTAL
        and data.get("supplemental_status") == "completed"
        and isinstance(data.get("supplemental_session_id"), str)
        and bool(data["supplemental_session_id"].strip())
        and isinstance(data.get("supplemental_skill_revision"), str)
        and bool(data["supplemental_skill_revision"].strip())
        and nonempty_file(data.get("supplemental_output_path"))
    )
    if not supplemental_ok:
        errors.append("review-trials-and-spec did not complete in a separate recorded session with nonempty output")

    if errors:
        print("CANONICAL REVIEW EXECUTION REJECTED", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    selected = data["primary_runner"] if primary_ok else data["fallback_runner"]
    print("CANONICAL REVIEW EXECUTION OK")
    print(f"TASK: {args.task_id} @ {args.task_sha}")
    print(f"PRIMARY DECISION RUNNER: {selected}")
    print(f"SUPPLEMENTAL RUNNER: {data['supplemental_runner']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
