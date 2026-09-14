#!/usr/bin/env python3
"""Single source of truth for Codimango review-critic contracts.

All command-line wrappers in this repository import this module. Keep policy here,
not in the wrappers.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


ROOT = Path(__file__).resolve().parent.parent
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^[0-9a-f]{64}$")
UUID = re.compile(
    r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
    re.IGNORECASE,
)
COUNTS = re.compile(r"^Critical (\d+) \| High (\d+) \| Medium (\d+) \| Low (\d+)$")
FIELD_LINE = re.compile(r"^- \*\*(.+?):\*\*\s*(\S(?:.*\S)?)$")
GROUP_LINE = re.compile(r"^- \*\*([^:]+)\*\*$")
HEADING_LINE = re.compile(r"^### (\S(?:.*\S)?)$")
TBR_CHECKS = re.compile(
    r"^(?:none|NOT VERIFIED|[a-z][a-z0-9_]*(?:, ?[a-z][a-z0-9_]*)*)$"
)
LANGUAGE = re.compile(r"^[A-Za-z][A-Za-z0-9+#.-]*(?: [A-Za-z][A-Za-z0-9+#.-]*)?$")

BASELINES = {
    "prior_revision",
    "no_solution",
    "model_floor",
    "hot_vs_cold",
    "with_vs_without_skill",
    "shortcut",
}
SEVERITIES = {"Critical", "High", "Medium", "Low", "advisory"}
FINDING_STATUSES = {"CONFIRMED", "OVERSTATED", "WRONG", "NOT VERIFIED"}
BASELINE_STATUSES = {"pass", "fail", "not_verified", "not_applicable"}
CONDITION_STATES = {"required", "not_required", "unresolved"}
PHASE_ORDER = [
    "preflight",
    "identity_frozen",
    "blind_started",
    "blind_sealed",
    "history_started",
    "history_complete",
    "finalized",
]
FALLBACKS = {
    ("tbench", "single"): "team-aai:review-task-tbench-v2",
    ("swe", "single"): "team-aai:review-task-swebench-v2",
    ("tbench", "multi"): "team-aai:review-task-tbench-multiturn",
    ("swe", "multi"): "team-aai:review-task-swebench-multiturn",
}
RUNTIME_PREFIXES = (
    "SKILL.md",
    "README.md",
    "RELEASE.lock",
    ".github/",
    "docs/",
    "references/",
    "scripts/",
    "schema/",
    "registry/",
    "tests/",
)
RUNTIME_EXCLUDES = {"schema/bundle-lock.json"}

FORBIDDEN_LANGUAGE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "batch or cross-task comparison",
        re.compile(
            r"\b(best|strongest|weakest|cleanest|easiest|hardest)\b.{0,50}\b(batch|submissions?|tasks?|reviews?)\b"
            r"|\b(review batch|batch of (?:submissions?|tasks?|reviews?))\b"
            r"|\bcompared (?:to|with) (?:the )?(?:other|rest of the) (?:submissions?|tasks?|reviews?)\b"
            r"|\bamong (?:the )?(?:submissions?|tasks?|reviews?)\b"
            r"|\b(?:another|other|sibling) tasks?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "review-history narration",
        re.compile(
            r"\b(?:previous|prior|earlier|last|first|second) (?:human )?(?:review|iteration|round|pass|assessment)\b"
            r"|\b(?:review|reviewer) (?:iteration|round)\b"
            r"|\bre-?review(?:ing|ed)?\b|\bfollow-?up review\b|\bsecond pass\b",
            re.IGNORECASE,
        ),
    ),
    (
        "reviewer process narration",
        re.compile(
            r"\bfrom (?:my|our) earlier miss\b"
            r"|\b(?:i|we) (?:had )?(?:previously |earlier )?missed\b"
            r"|\b(?:my|our) (?:previous|earlier) (?:miss|analysis|finding|assessment)\b"
            r"|\bblind pass\b|\bon re-?review\b|\bwhat (?:i|we) would have missed\b"
            r"|\bthe reviewer caught\b|\bindependently verified\b|\bi verified\b",
            re.IGNORECASE,
        ),
    ),
    ("redundant confirmation narration", re.compile(r"\bconfirmed\b", re.IGNORECASE)),
    (
        "relative submission ranking",
        re.compile(
            r"\bone of the (?:best|strongest|cleanest) submissions\b", re.IGNORECASE
        ),
    ),
)


class ContractError(ValueError):
    """A fail-closed contract violation."""


def validate_json_schema(
    instance: Any, schema: Mapping[str, Any], path: str = "$"
) -> None:
    if "const" in schema and instance != schema["const"]:
        raise ContractError(f"{path}: expected constant {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        raise ContractError(f"{path}: value {instance!r} is not in enum")
    expected_type = schema.get("type")
    if expected_type is not None:
        names = (
            [expected_type] if isinstance(expected_type, str) else list(expected_type)
        )
        checks = {
            "object": lambda value: isinstance(value, dict),
            "array": lambda value: isinstance(value, list),
            "string": lambda value: isinstance(value, str),
            "integer": lambda value: isinstance(value, int)
            and not isinstance(value, bool),
            "number": lambda value: isinstance(value, (int, float))
            and not isinstance(value, bool),
            "boolean": lambda value: isinstance(value, bool),
            "null": lambda value: value is None,
        }
        if not any(checks[name](instance) for name in names):
            raise ContractError(
                f"{path}: expected type {names}, found {type(instance).__name__}"
            )
    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            raise ContractError(f"{path}: string is shorter than {schema['minLength']}")
        if "pattern" in schema and re.fullmatch(schema["pattern"], instance) is None:
            raise ContractError(f"{path}: string does not match {schema['pattern']!r}")
    if isinstance(instance, (int, float)) and not isinstance(instance, bool):
        if "minimum" in schema and instance < schema["minimum"]:
            raise ContractError(f"{path}: value is below minimum {schema['minimum']}")
    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            raise ContractError(
                f"{path}: array has fewer than {schema['minItems']} items"
            )
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, value in enumerate(instance):
                validate_json_schema(value, item_schema, f"{path}[{index}]")
    if isinstance(instance, dict):
        required = schema.get("required", [])
        missing = [name for name in required if name not in instance]
        if missing:
            raise ContractError(f"{path}: missing required properties {missing}")
        properties = schema.get("properties", {})
        for name, child_schema in properties.items():
            if name in instance and isinstance(child_schema, dict):
                validate_json_schema(instance[name], child_schema, f"{path}.{name}")
        if schema.get("additionalProperties") is False:
            extra = sorted(set(instance) - set(properties))
            if extra:
                raise ContractError(f"{path}: unexpected properties {extra}")


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read valid JSON {path}: {exc}") from exc


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    if path.is_symlink():
        raise ContractError(f"symlink evidence is not accepted: {path}")
    try:
        return sha256_bytes(path.read_bytes())
    except OSError as exc:
        raise ContractError(f"cannot hash {path}: {exc}") from exc


def require_file(path: Path, expected_sha: str | None = None) -> None:
    if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
        raise ContractError(f"required nonempty regular file missing: {path}")
    if expected_sha is not None:
        if not DIGEST.fullmatch(expected_sha):
            raise ContractError(
                f"invalid expected SHA-256 for {path}: {expected_sha!r}"
            )
        actual = sha256_file(path)
        if actual != expected_sha:
            raise ContractError(
                f"digest mismatch for {path}: {actual} != {expected_sha}"
            )


def parse_time(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value:
        raise ContractError(f"missing timestamp: {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ContractError(f"invalid timestamp {field}: {value!r}") from exc
    if parsed.tzinfo is None:
        raise ContractError(f"timestamp lacks timezone: {field}")
    return parsed.astimezone(timezone.utc)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def require_full_sha(value: object, field: str) -> str:
    if not isinstance(value, str) or FULL_SHA.fullmatch(value) is None:
        raise ContractError(f"{field} must be a full lowercase 40-hex SHA")
    return value


def path_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def git_output(repo: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo), *args],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        raise ContractError(f"git unavailable: {exc}") from exc
    if proc.returncode != 0:
        raise ContractError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def runtime_files(bundle: Path) -> list[Path]:
    candidates: list[Path] = []
    for path in bundle.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(bundle).as_posix()
        if rel in RUNTIME_EXCLUDES or rel.endswith((".pyc", ".DS_Store")):
            continue
        if rel in RUNTIME_PREFIXES or any(
            rel.startswith(prefix)
            for prefix in RUNTIME_PREFIXES
            if prefix.endswith("/")
        ):
            candidates.append(path)
    return sorted(candidates, key=lambda p: p.relative_to(bundle).as_posix())


def seal_bundle(bundle: Path) -> dict[str, Any]:
    files = runtime_files(bundle)
    if not files:
        raise ContractError("bundle has zero runtime files")
    return {
        "schema_version": 1,
        "runtime_files": {
            path.relative_to(bundle).as_posix(): sha256_file(path) for path in files
        },
        "generated_by": "python3 scripts/reviewctl.py seal-bundle --bundle . --write",
        "note": "This file intentionally does not hash itself.",
    }


def validate_bundle(bundle: Path) -> tuple[str, str, int]:
    lock_path = bundle / "schema" / "bundle-lock.json"
    lock = load_json(lock_path)
    entries = lock.get("runtime_files")
    if not isinstance(entries, dict) or not entries:
        raise ContractError("PREFLIGHT REJECTED: bundle lock has zero runtime files")
    current = {
        p.relative_to(bundle).as_posix(): sha256_file(p) for p in runtime_files(bundle)
    }
    if set(current) != set(entries):
        missing = sorted(set(entries) - set(current))
        extra = sorted(set(current) - set(entries))
        raise ContractError(
            f"PREFLIGHT REJECTED: runtime file set changed missing={missing} extra={extra}"
        )
    for rel, expected in entries.items():
        if current[rel] != expected:
            raise ContractError(f"PREFLIGHT REJECTED: digest mismatch for {rel}")
    if (bundle / ".git").exists():
        head = require_full_sha(
            git_output(bundle, "rev-parse", "HEAD"), "bundle git HEAD"
        )
        tree = require_full_sha(
            git_output(bundle, "rev-parse", "HEAD^{tree}"), "bundle git tree"
        )
        dirty = git_output(bundle, "status", "--short", "--untracked-files=no")
        if dirty:
            raise ContractError("PREFLIGHT REJECTED: tracked bundle files are dirty")
    else:
        release = load_json(bundle / "RELEASE.lock")
        release_name = str(release.get("release", ""))
        if re.fullmatch(r"\d+\.\d+\.\d+", release_name) is None:
            raise ContractError(
                "PREFLIGHT REJECTED: registry bundle lacks release identity"
            )
        lock_digest = sha256_file(lock_path)
        canonical_entries = json.dumps(entries, sort_keys=True, separators=(",", ":"))
        head = hashlib.sha1(
            f"skills-sdk:{release_name}:{lock_digest}".encode("utf-8")
        ).hexdigest()
        tree = hashlib.sha1(canonical_entries.encode("utf-8")).hexdigest()
    return head, tree, len(entries)


def preflight(bundle: Path, scratch_root: Path, receipt_path: Path) -> dict[str, Any]:
    if path_within(scratch_root, bundle):
        raise ContractError(
            "PREFLIGHT REJECTED: scratch root must be outside the skill bundle"
        )
    if scratch_root.exists() and any(scratch_root.iterdir()):
        raise ContractError("PREFLIGHT REJECTED: scratch root is not empty")
    scratch_root.mkdir(parents=True, exist_ok=True)
    head, tree, count = validate_bundle(bundle)
    receipt = {
        "schema_version": 1,
        "bundle_commit": head,
        "bundle_tree": tree,
        "bundle_lock_sha256": sha256_file(bundle / "schema" / "bundle-lock.json"),
        "template_sha256": sha256_file(bundle / "references" / "output-template.md"),
        "runtime_file_count": count,
        "scratch_root": str(scratch_root.resolve()),
        "timestamp": utc_now(),
        "verdict": "PASS",
    }
    write_json(receipt_path, receipt)
    return receipt


def _task_family(task: Mapping[str, Any]) -> tuple[str, str]:
    track = str(task.get("track", "")).lower().replace("_", "-")
    variant = str(task.get("variant", "")).lower().replace("_", "-")
    multi = "multi" if "multi" in variant or "multi" in track else "single"
    if "tbench" in track or "t-bench" in track or "terminal" in variant:
        family = "tbench"
    elif "swe" in track or "swe" in variant or "ios" in track:
        family = "swe"
    elif "long" in track or "long" in variant:
        base = str(task.get("base_track", "")).lower()
        family = "tbench" if "tbench" in base or "terminal" in base else "swe"
    else:
        raise ContractError(f"unsupported track/variant: {track!r}/{variant!r}")
    return family, multi


def _validate_run_record(
    run: Mapping[str, Any], manifest: Mapping[str, Any], scratch: Path
) -> None:
    required = {
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
        "started_at",
        "ended_at",
        "output_path",
        "output_sha256",
        "output_task_id",
        "output_task_sha",
        "attestation_source",
    }
    missing = sorted(required - set(run))
    if missing:
        raise ContractError(f"run {run.get('role')!r} missing fields: {missing}")
    if run["status"] not in {"completed", "finalizing", "failed", "unavailable"}:
        raise ContractError(f"invalid run status for {run['role']}: {run['status']!r}")
    if not isinstance(run["session_id"], str) or not run["session_id"].strip():
        raise ContractError(f"empty session id for {run['role']}")
    workspace = Path(run["workspace"])
    if not isinstance(run["workspace"], str) or not workspace.is_absolute():
        raise ContractError(f"run workspace must be absolute: {run['role']}")
    task_repo = manifest.get("task_repo_root")
    if task_repo and (
        path_within(workspace, Path(task_repo))
        or path_within(Path(task_repo), workspace)
    ):
        raise ContractError(f"run workspace overlaps task repository: {run['role']}")
    if run["harness"] not in {"native", "claude_code", "codex", "muse_code"}:
        raise ContractError(f"unsupported harness for {run['role']}")
    expected_loaded_skill = {
        "canonical_primary": "aai-review-flow",
        "supplemental": "review-trials-and-spec",
        "ios": "aai-ios",
        "lh_addon": "aai-long-horizon",
    }.get(run["role"])
    if (
        run["status"] in {"completed", "finalizing"}
        and run["loaded_skill"] != expected_loaded_skill
    ):
        if expected_loaded_skill is not None:
            raise ContractError(f"run {run['role']} lacks attested skill load")
    revision = run["skill_revision"]
    if not isinstance(revision, str) or not (
        FULL_SHA.fullmatch(revision) or re.fullmatch(r"v?\d+\.\d+\.\d+", revision)
    ):
        raise ContractError(f"run {run['role']} lacks immutable skill revision")
    if run["status"] in {"completed", "finalizing"}:
        if str(run["task_id"]) != str(manifest["task"]["id"]):
            raise ContractError(f"foreign task id in run {run['role']}")
        if run["task_sha"] != manifest["task"]["validation_sha"]:
            raise ContractError(f"foreign task SHA in run {run['role']}")
    elif run["task_id"] not in (None, str(manifest["task"]["id"])) or run[
        "task_sha"
    ] not in (None, manifest["task"]["validation_sha"]):
        raise ContractError(f"failed run {run['role']} claims foreign task identity")
    started = parse_time(run["started_at"], f"{run['role']}.started_at")
    if run["status"] == "finalizing":
        if run["role"] != "critic" or run["ended_at"] is not None:
            raise ContractError("only the critic may be finalizing without ended_at")
    else:
        ended = parse_time(run["ended_at"], f"{run['role']}.ended_at")
        if ended < started:
            raise ContractError(f"run ends before it starts: {run['role']}")
    if run["attestation_source"] != "agentcloud" or not isinstance(
        run.get("attested_run"), int
    ):
        raise ContractError(f"run {run['role']} lacks Agentcloud run attestation")
    output = Path(str(run["output_path"] or ""))
    if run["status"] in {"completed", "finalizing"}:
        if (
            str(run["output_task_id"]) != str(manifest["task"]["id"])
            or run["output_task_sha"] != manifest["task"]["validation_sha"]
        ):
            raise ContractError(f"output identity mismatch in run {run['role']}")
        require_file(output, run["output_sha256"])
        if not path_within(output, workspace):
            raise ContractError(
                f"run output outside attested session workspace: {run['role']}"
            )
    elif (
        run["output_path"] not in (None, "")
        or run["output_sha256"] not in (None, "")
        or run["output_task_id"] not in (None, "")
        or run["output_task_sha"] not in (None, "")
    ):
        raise ContractError(
            f"failed/unavailable run must not claim output: {run['role']}"
        )


def validate_dag(manifest: Mapping[str, Any]) -> dict[str, Any]:
    validate_json_schema(manifest, load_json(ROOT / "schema" / "run-manifest-v2.json"))
    if manifest.get("schema_version") != 2:
        raise ContractError("run manifest schema_version must be 2")
    task = manifest.get("task")
    if not isinstance(task, dict):
        raise ContractError("run manifest missing task")
    for key in (
        "id",
        "repo",
        "track",
        "variant",
        "head_sha",
        "validation_sha",
        "inspected_sha",
    ):
        if key not in task or task[key] in (None, ""):
            raise ContractError(f"run manifest task missing {key}")
    for key in ("head_sha", "validation_sha", "inspected_sha"):
        require_full_sha(task[key], f"task.{key}")
    if task.get("review_job_sha") is not None:
        require_full_sha(task["review_job_sha"], "task.review_job_sha")
    bundle = manifest.get("bundle")
    if not isinstance(bundle, dict):
        raise ContractError("run manifest missing bundle")
    for key in ("commit", "tree", "preflight_receipt_path", "preflight_receipt_sha256"):
        if not bundle.get(key):
            raise ContractError(f"run manifest bundle missing {key}")
    require_full_sha(bundle["commit"], "bundle.commit")
    require_full_sha(bundle["tree"], "bundle.tree")
    receipt_path = Path(bundle["preflight_receipt_path"])
    require_file(receipt_path, bundle["preflight_receipt_sha256"])
    preflight_receipt = load_json(receipt_path)
    if (
        preflight_receipt.get("verdict") != "PASS"
        or preflight_receipt.get("bundle_commit") != bundle["commit"]
        or preflight_receipt.get("bundle_tree") != bundle["tree"]
        or preflight_receipt.get("scratch_root")
        != str(Path(manifest.get("scratch_root", "")).resolve())
    ):
        raise ContractError("run manifest bundle disagrees with preflight receipt")
    if preflight_receipt.get("sandbox_backend") not in {
        "systemd",
        "unshare",
        "sandbox-exec",
    }:
        raise ContractError("run manifest lacks sandbox-attested preflight")
    scratch = Path(str(manifest.get("scratch_root", "")))
    if not scratch.is_absolute() or not scratch.exists():
        raise ContractError("scratch_root must be an existing absolute directory")
    repo_root = manifest.get("task_repo_root")
    if repo_root and path_within(scratch, Path(repo_root)):
        raise ContractError("scratch root must not be inside task repository")
    runs = manifest.get("runs")
    if not isinstance(runs, list) or not runs:
        raise ContractError("run manifest has zero runs")
    for run in runs:
        if not isinstance(run, dict):
            raise ContractError("run record must be an object")
        _validate_run_record(run, manifest, scratch)
    roles = [run["role"] for run in runs]
    if len(roles) != len(set(roles)):
        raise ContractError("duplicate run role")
    sessions = [run["session_id"] for run in runs]
    if len(sessions) != len(set(sessions)):
        raise ContractError("RUN DAG REJECTED: duplicate session ids")
    workspaces = [run["workspace"] for run in runs]
    if len(workspaces) != len(set(workspaces)):
        raise ContractError("RUN DAG REJECTED: duplicate workspaces")
    completed_outputs = [
        run["output_path"]
        for run in runs
        if run["status"] in {"completed", "finalizing"}
    ]
    if len(completed_outputs) != len(set(completed_outputs)):
        raise ContractError("RUN DAG REJECTED: duplicate output paths")
    completed_hashes = [
        run["output_sha256"]
        for run in runs
        if run["status"] in {"completed", "finalizing"}
    ]
    if len(completed_hashes) != len(set(completed_hashes)):
        raise ContractError("RUN DAG REJECTED: duplicate output digests")
    by_role = {run["role"]: run for run in runs}
    if "critic" not in by_role:
        raise ContractError("RUN DAG REJECTED: missing critic")
    critic = by_role["critic"]
    if critic["runner"] != "codimango-review-critic" or critic["status"] not in {
        "completed",
        "finalizing",
    }:
        raise ContractError("RUN DAG REJECTED: critic is not completed/finalizing")
    dispatcher = manifest.get("dispatcher_session_id")
    if (
        not isinstance(dispatcher, str)
        or not dispatcher
        or critic["parent_session_id"] != dispatcher
    ):
        raise ContractError("RUN DAG REJECTED: critic parent does not match dispatcher")
    for role, run in by_role.items():
        if role != "critic" and run["parent_session_id"] != critic["session_id"]:
            raise ContractError(f"RUN DAG REJECTED: {role} is not a child of critic")
    release = load_json(ROOT / "RELEASE.lock")
    expected_revisions = {
        "critic": manifest["bundle"]["commit"],
        "canonical_primary": release["dependencies"]["aai-review-flow"],
        "canonical_fallback": release["dependencies"]["team-aai-fbsource"],
        "supplemental": release["dependencies"]["review-trials-and-spec"],
        "ios": release["dependencies"]["aai-ios"],
        "lh_addon": release["dependencies"]["aai-long-horizon"],
    }
    for role, run in by_role.items():
        expected_revision = expected_revisions.get(role)
        if expected_revision is not None and run["skill_revision"] != expected_revision:
            raise ContractError(
                f"RUN DAG REJECTED: {role} skill revision differs from RELEASE.lock"
            )
    primary = by_role.get("canonical_primary")
    if primary is None or primary["runner"] != "aai-review-flow":
        raise ContractError("RUN DAG REJECTED: missing aai-review-flow primary")
    family, turn = _task_family(task)
    expected_fallback = FALLBACKS[(family, turn)]
    fallback = by_role.get("canonical_fallback")
    if primary["status"] == "completed":
        if fallback is not None:
            raise ContractError(
                "RUN DAG REJECTED: fallback present after primary success"
            )
        decision_run = primary
    else:
        if (
            fallback is None
            or fallback["status"] != "completed"
            or fallback["runner"] != expected_fallback
        ):
            raise ContractError(
                f"RUN DAG REJECTED: expected fallback {expected_fallback}"
            )
        if parse_time(fallback["started_at"], "fallback.started_at") < parse_time(
            primary["ended_at"], "primary.ended_at"
        ):
            raise ContractError(
                "RUN DAG REJECTED: fallback started before primary failure completed"
            )
        decision_run = fallback
    if "long" in str(task["track"]).lower() or "long" in str(task["variant"]).lower():
        addon = by_role.get("lh_addon")
        if (
            addon is None
            or addon["runner"] != "aai-long-horizon:lh-review-task"
            or addon["status"] != "completed"
        ):
            raise ContractError(
                "RUN DAG REJECTED: Long Horizon requires matching reviewer plus lh-review-task"
            )
    supplemental = by_role.get("supplemental")
    if (
        supplemental is None
        or supplemental["runner"] != "review-trials-and-spec"
        or supplemental["status"] != "completed"
    ):
        raise ContractError("RUN DAG REJECTED: separate supplemental did not complete")
    conditions_entry = manifest.get("conditions")
    if (
        not isinstance(conditions_entry, dict)
        or not conditions_entry.get("path")
        or not conditions_entry.get("sha256")
    ):
        raise ContractError("run manifest missing frozen conditions")
    conditions_path = Path(conditions_entry["path"])
    require_file(conditions_path, conditions_entry["sha256"])
    conditions = load_json(conditions_path)
    if conditions.get("ios", {}).get("state") == "required":
        ios = by_role.get("ios")
        if ios is None or ios["runner"] != "aai-ios" or ios["status"] != "completed":
            raise ContractError("RUN DAG REJECTED: iOS lens required but absent")
    final = manifest.get("final")
    if not isinstance(final, dict):
        raise ContractError("run manifest missing final block")
    for name in (
        "review",
        "live_payload",
        "evidence",
        "findings",
        "evidence_ledger",
        "command_audit",
    ):
        entry = final.get(name)
        if (
            not isinstance(entry, dict)
            or not entry.get("path")
            or not entry.get("sha256")
        ):
            raise ContractError(f"final block missing {name}")
        require_file(Path(entry["path"]), entry["sha256"])
        if not path_within(Path(entry["path"]), scratch):
            raise ContractError(f"final {name} outside scratch root")
        if not path_within(Path(entry["path"]), Path(critic["workspace"])):
            raise ContractError(f"final {name} outside attested critic workspace")
    if (
        critic.get("output_path") != final["evidence"]["path"]
        or critic.get("output_sha256") != final["evidence"]["sha256"]
    ):
        raise ContractError(
            "RUN DAG REJECTED: critic journal output is not the final evidence artifact"
        )
    publisher = manifest.get("publisher")
    if not isinstance(publisher, dict):
        raise ContractError("run manifest missing publisher block")
    if publisher.get("source_sha256") != final["review"]["sha256"]:
        raise ContractError(
            "PUBLISH REJECTED: source hash differs from critic-approved review"
        )
    if final.get("owner_session_id") != critic["session_id"]:
        raise ContractError(
            "PUBLISH REJECTED: final files are not owned by the critic session"
        )
    published = publisher.get("published_sha256")
    if published not in (None, "") and published != publisher["source_sha256"]:
        raise ContractError("PUBLISH REJECTED: byte hash changed")
    return {"roles": len(runs), "decision_runner": decision_run["runner"]}


def validate_phases(manifest: Mapping[str, Any]) -> int:
    phases = manifest.get("phases")
    if not isinstance(phases, list) or not phases:
        raise ContractError("PHASE ORDER REJECTED: empty phase stream")
    names = [phase.get("name") for phase in phases if isinstance(phase, dict)]
    if names != PHASE_ORDER:
        if (
            "history_started" in names
            and "blind_sealed" in names
            and names.index("history_started") < names.index("blind_sealed")
        ):
            raise ContractError(
                "PHASE ORDER REJECTED: history_started before blind_sealed"
            )
        raise ContractError(
            f"PHASE ORDER REJECTED: expected {PHASE_ORDER}, found {names}"
        )
    sequences = [phase.get("sequence") for phase in phases]
    if sequences != list(range(1, len(PHASE_ORDER) + 1)):
        raise ContractError(
            f"PHASE ORDER REJECTED: non-monotonic sequences {sequences}"
        )
    times = [
        parse_time(phase.get("timestamp"), f"phase.{phase.get('name')}")
        for phase in phases
    ]
    if times != sorted(times):
        raise ContractError("PHASE ORDER REJECTED: timestamps are not monotonic")
    receipt = load_json(Path(manifest["bundle"]["preflight_receipt_path"]))
    if parse_time(receipt.get("timestamp"), "preflight receipt") > times[0]:
        raise ContractError("PHASE ORDER REJECTED: preflight phase predates receipt")
    task_id = str(manifest["task"]["id"])
    if any(str(phase.get("task_id")) != task_id for phase in phases):
        raise ContractError("PHASE ORDER REJECTED: foreign task event")
    blind = phases[PHASE_ORDER.index("blind_sealed")]
    require_file(Path(blind.get("artifact_path", "")), blind.get("artifact_sha256"))
    if parse_time(blind["timestamp"], "blind_sealed") > parse_time(
        phases[4]["timestamp"], "history_started"
    ):
        raise ContractError("PHASE ORDER REJECTED: history_started before blind_sealed")
    blind_start = times[PHASE_ORDER.index("blind_started")]
    blind_end = times[PHASE_ORDER.index("blind_sealed")]
    finalized = times[PHASE_ORDER.index("finalized")]
    for run in manifest.get("runs", []):
        started = parse_time(run.get("started_at"), f"{run.get('role')}.started_at")
        if run.get("role") == "critic":
            if started > times[0]:
                raise ContractError(
                    "PHASE ORDER REJECTED: critic starts after preflight"
                )
            if run.get("status") == "completed":
                ended = parse_time(run.get("ended_at"), "critic.ended_at")
                if ended < finalized:
                    raise ContractError(
                        "PHASE ORDER REJECTED: critic ended before finalization"
                    )
        elif run.get("role") in {
            "canonical_primary",
            "canonical_fallback",
            "lh_addon",
            "supplemental",
            "ios",
        }:
            ended = parse_time(run.get("ended_at"), f"{run.get('role')}.ended_at")
            if started < blind_start or ended > blind_end:
                raise ContractError(
                    f"PHASE ORDER REJECTED: {run.get('role')} lies outside sealed blind pass"
                )
    return len(phases)


def resolve_conditions(metadata: Mapping[str, Any]) -> dict[str, Any]:
    task_id = str(metadata.get("task_id", ""))
    task_sha = require_full_sha(metadata.get("task_sha"), "condition metadata task_sha")
    agentic_meta = metadata.get("agentic")
    if not isinstance(agentic_meta, dict):
        agentic = {"state": "unresolved", "reason": "agentic metadata absent"}
    else:
        state = agentic_meta.get("state")
        body = agentic_meta.get("review_body")
        body_path = Path(str(agentic_meta.get("review_body_path", "")))
        if not isinstance(body, str) and body_path.is_file():
            body = body_path.read_text(encoding="utf-8", errors="replace")
        if (
            state == "completed"
            and isinstance(body, str)
            and body.strip()
            and isinstance(agentic_meta.get("run_id"), str)
            and agentic_meta["run_id"].strip()
        ):
            agentic = {
                "state": "required",
                "reason": "completed review body",
                "source": "api",
                "run_id": agentic_meta["run_id"],
            }
        elif state == "completed":
            agentic = {
                "state": "unresolved",
                "reason": "completed Agentic review lacks body or run identity",
            }
        elif state == "parse_error":
            traversal = agentic_meta.get("traversal")
            verified_artifacts: list[dict[str, str]] = []
            trial_ids: list[str] = []
            traversal_valid = (
                isinstance(traversal, dict) and traversal.get("complete") is True
            )
            if traversal_valid:
                job_id = traversal.get("job_id")
                trial_ids_raw = traversal.get("trial_ids")
                artifacts_raw = traversal.get("artifacts")
                traversal_valid = (
                    isinstance(job_id, str)
                    and bool(job_id.strip())
                    and isinstance(trial_ids_raw, list)
                    and bool(trial_ids_raw)
                    and all(
                        isinstance(value, str) and value.strip()
                        for value in trial_ids_raw
                    )
                    and len(trial_ids_raw) == len(set(trial_ids_raw))
                    and isinstance(artifacts_raw, list)
                    and bool(artifacts_raw)
                )
                if traversal_valid:
                    trial_ids = list(trial_ids_raw)
                    seen_paths: set[str] = set()
                    for artifact in artifacts_raw:
                        if not isinstance(artifact, dict):
                            traversal_valid = False
                            break
                        path = Path(str(artifact.get("path", "")))
                        digest = artifact.get("sha256")
                        if (
                            not path.is_absolute()
                            or str(path) in seen_paths
                            or not isinstance(digest, str)
                            or re.fullmatch(r"[0-9a-f]{64}", digest) is None
                        ):
                            traversal_valid = False
                            break
                        seen_paths.add(str(path))
                        if not path.is_file() or sha256_file(path) != digest:
                            traversal_valid = False
                            break
                        verified_artifacts.append({"path": str(path), "sha256": digest})
            traversal_receipt = {
                "job_id": (
                    traversal.get("job_id") if isinstance(traversal, dict) else None
                ),
                "trial_ids": trial_ids,
                "artifacts": verified_artifacts,
                "complete": traversal_valid,
            }
            recovered = next(
                (
                    Path(artifact["path"])
                    for artifact in verified_artifacts
                    if Path(artifact["path"]).stat().st_size > 0
                ),
                None,
            )
            if (
                recovered is not None
                and isinstance(agentic_meta.get("run_id"), str)
                and agentic_meta["run_id"].strip()
            ):
                agentic = {
                    "state": "required",
                    "reason": "nonempty report artifact recovered after parse_error",
                    "source": recovered.name,
                    "run_id": agentic_meta["run_id"],
                    "traversal": traversal_receipt,
                }
            elif recovered is not None:
                agentic = {
                    "state": "unresolved",
                    "reason": "recovered Agentic report lacks run identity",
                    "traversal": traversal_receipt,
                }
            elif traversal_valid:
                agentic = {
                    "state": "not_required",
                    "reason": "verified report artifacts are empty",
                    "traversal": traversal_receipt,
                }
            else:
                agentic = {
                    "state": "unresolved",
                    "reason": "parse_error job-to-trial-to-artifact traversal incomplete",
                    "traversal": traversal_receipt,
                }
        elif state in {"not_run", "absent"}:
            agentic = {"state": "not_required", "reason": state}
        else:
            agentic = {"state": "unresolved", "reason": f"agentic state {state!r}"}
    overrides = metadata.get("validation_overrides")
    if overrides is None:
        validation_override = {
            "state": "unresolved",
            "reason": "override metadata absent",
            "reasons": [],
        }
    elif not isinstance(overrides, list):
        validation_override = {
            "state": "unresolved",
            "reason": "override metadata invalid",
            "reasons": [],
        }
    elif overrides:
        validation_override = {
            "state": "required",
            "reason": "live override reasons exist",
            "reasons": overrides,
        }
    else:
        validation_override = {
            "state": "not_required",
            "reason": "no live override reasons",
            "reasons": [],
        }
    track = str(metadata.get("track", "")).lower()
    ios_signal = metadata.get("ios_signal")
    if ios_signal is None and not track:
        ios = {"state": "unresolved", "reason": "track and iOS signal absent"}
    elif ios_signal is True or "ios" in track:
        ios = {"state": "required", "reason": "iOS track signal"}
    else:
        ios = {"state": "not_required", "reason": "non-iOS track"}
    return {
        "schema_version": 1,
        "task_id": task_id,
        "task_sha": task_sha,
        "agentic": agentic,
        "validation_override": validation_override,
        "ios": ios,
    }


def validate_conditions(
    conditions: Mapping[str, Any], task_id: str, task_sha: str
) -> None:
    validate_json_schema(conditions, load_json(ROOT / "schema" / "conditions.json"))
    if conditions.get("schema_version") != 1:
        raise ContractError("condition schema_version must be 1")
    if (
        str(conditions.get("task_id")) != str(task_id)
        or conditions.get("task_sha") != task_sha
    ):
        raise ContractError("condition identity mismatch")
    for name in ("agentic", "validation_override", "ios"):
        item = conditions.get(name)
        if not isinstance(item, dict) or item.get("state") not in CONDITION_STATES:
            raise ContractError(f"CONDITION REJECTED: {name} unresolved")
        if item["state"] == "unresolved":
            raise ContractError(f"CONDITION REJECTED: {name} unresolved")
    overrides = conditions["validation_override"]
    reasons = overrides.get("reasons")
    if not isinstance(reasons, list):
        raise ContractError("CONDITION REJECTED: override reasons invalid")
    allowed_override_checks = set(
        load_json(ROOT / "schema" / "live-form-payload.json").get(
            "override_review_valid_checks", []
        )
    )
    if overrides["state"] == "required":
        if not reasons:
            raise ContractError("CONDITION REJECTED: required override reasons empty")
        for reason in reasons:
            if (
                not isinstance(reason, dict)
                or reason.get("check") not in allowed_override_checks
                or not isinstance(reason.get("heading"), str)
                or not reason["heading"].strip()
                or not isinstance(reason.get("reason"), str)
                or not reason["reason"].strip()
            ):
                raise ContractError("CONDITION REJECTED: override reason invalid")
    elif reasons:
        raise ContractError("CONDITION REJECTED: non-required override has reasons")
    if conditions["agentic"]["state"] == "required" and (
        not isinstance(conditions["agentic"].get("run_id"), str)
        or not conditions["agentic"]["run_id"].strip()
    ):
        raise ContractError("CONDITION REJECTED: Agentic run identity missing")


def validate_findings(
    data: Mapping[str, Any], task_id: str, task_sha: str
) -> Counter[str]:
    validate_json_schema(data, load_json(ROOT / "schema" / "findings.json"))
    if data.get("schema_version") != 1:
        raise ContractError("findings schema_version must be 1")
    if str(data.get("task_id")) != str(task_id) or data.get("task_sha") != task_sha:
        raise ContractError("findings identity mismatch")
    if data.get("quality_verdict") not in {"Accept", "Revise", "Reject", "Unavailable"}:
        raise ContractError("invalid findings quality_verdict")
    if data.get("decision") not in {"Accept", "Request changes", "Reject"}:
        raise ContractError("invalid findings decision")
    if (
        not isinstance(data.get("decision_reconciliation"), str)
        or not data["decision_reconciliation"].strip()
    ):
        raise ContractError("findings decision_reconciliation is required")
    findings = data.get("findings")
    if not isinstance(findings, list):
        raise ContractError("findings must be a list")
    ids: set[str] = set()
    counts: Counter[str] = Counter()
    required = {
        "id",
        "finding",
        "status",
        "independent_evidence",
        "attribution",
        "severity",
        "blocking",
        "reviewer_contribution",
        "close_condition",
    }
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            raise ContractError(f"finding {index} is not an object")
        missing = sorted(required - set(finding))
        if missing:
            raise ContractError(f"finding {index} missing columns: {missing}")
        if (
            not isinstance(finding["id"], str)
            or not finding["id"]
            or finding["id"] in ids
        ):
            raise ContractError(f"finding {index} has empty/duplicate id")
        ids.add(finding["id"])
        if finding["status"] not in FINDING_STATUSES:
            raise ContractError(f"finding {finding['id']} has invalid status")
        if finding["severity"] not in SEVERITIES:
            raise ContractError(f"finding {finding['id']} has invalid severity")
        if not isinstance(finding["blocking"], bool):
            raise ContractError(f"finding {finding['id']} has invalid blocking flag")
        evidence = finding["independent_evidence"]
        if (
            not isinstance(evidence, list)
            or not evidence
            or any(not isinstance(v, str) or not v.strip() for v in evidence)
        ):
            raise ContractError(f"finding {finding['id']} lacks independent evidence")
        for field in (
            "finding",
            "attribution",
            "reviewer_contribution",
            "close_condition",
        ):
            if not isinstance(finding[field], str) or not finding[field].strip():
                raise ContractError(f"finding {finding['id']} has empty {field}")
        if finding["status"] == "WRONG" and (
            finding["blocking"] or finding["severity"] != "advisory"
        ):
            raise ContractError(
                f"WRONG finding {finding['id']} cannot drive severity or blocking"
            )
        if finding["status"] == "OVERSTATED" and finding["severity"] in {
            "Critical",
            "High",
        }:
            raise ContractError(
                f"OVERSTATED finding {finding['id']} cannot remain Critical/High"
            )
        if finding["blocking"] and finding["status"] != "CONFIRMED":
            raise ContractError(f"blocking finding {finding['id']} is not CONFIRMED")
        if finding["severity"] != "advisory":
            counts[finding["severity"]] += 1
    blocking = [finding for finding in findings if finding["blocking"]]
    for finding in findings:
        if finding["severity"] in {"Critical", "High"} and not finding["blocking"]:
            raise ContractError(
                f"{finding['severity']} finding {finding['id']} must be blocking"
            )
        if len(finding["close_condition"].strip()) < 15:
            raise ContractError(f"finding {finding['id']} close condition is too short")
    if data["decision"] == "Accept" and blocking:
        raise ContractError("Accept decision contains blocking findings")
    if data["decision"] == "Request changes" and not blocking:
        raise ContractError("Request changes decision has no blocking finding")
    if data["decision"] == "Reject" and not any(
        finding["blocking"] and finding["severity"] == "Critical"
        for finding in findings
    ):
        raise ContractError("Reject decision requires a confirmed Critical blocker")
    if (counts["Critical"] > 0 or counts["High"] > 0 or counts["Medium"] >= 3) and data[
        "decision"
    ] == "Accept":
        raise ContractError("Accept decision contradicts blocking severity threshold")
    return counts


def _validate_pagination(
    name: str, page: Mapping[str, Any], records: Sequence[Mapping[str, Any]]
) -> None:
    if page.get("complete") is not True:
        raise ContractError(f"EVIDENCE REJECTED: {name} pagination incomplete")
    ids = page.get("ids")
    if not isinstance(ids, list) or len(ids) != len(set(map(str, ids))):
        raise ContractError(f"EVIDENCE REJECTED: {name} pagination IDs invalid")
    if page.get("total") != len(ids):
        raise ContractError(f"EVIDENCE REJECTED: {name} total mismatch")
    if page.get("next_cursor") not in (None, ""):
        raise ContractError(f"EVIDENCE REJECTED: {name} next_cursor remains")
    pages = page.get("pages")
    if not isinstance(pages, int) or pages < (1 if ids else 0):
        raise ContractError(f"EVIDENCE REJECTED: {name} pages invalid")
    record_ids = [str(record.get("id")) for record in records]
    if sorted(map(str, ids)) != sorted(record_ids):
        raise ContractError(f"EVIDENCE REJECTED: {name} record set mismatch")


def validate_supplemental(
    data: Mapping[str, Any], task_id: str, task_sha: str, max_summary_bytes: int = 12000
) -> set[str]:
    validate_json_schema(data, load_json(ROOT / "schema" / "supplemental-output.json"))
    if (
        data.get("schema_version") != 1
        or str(data.get("task_id")) != str(task_id)
        or data.get("task_sha") != task_sha
    ):
        raise ContractError("supplemental output identity/schema mismatch")
    if data.get("complete") is not True:
        raise ContractError("supplemental output is not complete")
    total = data.get("total_records")
    if not isinstance(total, int) or total < 0:
        raise ContractError("supplemental total_records invalid")
    summary = Path(str(data.get("summary_path", "")))
    ledger = Path(str(data.get("ledger_path", "")))
    require_file(summary, data.get("summary_sha256"))
    require_file(ledger, data.get("ledger_sha256"))
    if summary.stat().st_size > max_summary_bytes:
        raise ContractError(f"supplemental summary exceeds {max_summary_bytes} bytes")
    ledger_data = load_json(ledger)
    if (
        not isinstance(ledger_data, dict)
        or ledger_data.get("complete") is not True
        or str(ledger_data.get("task_id")) != str(task_id)
        or ledger_data.get("task_sha") != task_sha
    ):
        raise ContractError("supplemental ledger identity/completeness mismatch")
    records = ledger_data.get("records")
    if not isinstance(records, list) or len(records) != total:
        raise ContractError("supplemental ledger record count mismatch")
    finding_ids: set[str] = set()
    record_ids: set[str] = set()
    for record in records:
        if not isinstance(record, dict):
            raise ContractError("supplemental ledger record is not an object")
        required = {"id", "task_id", "task_sha", "finding_ids", "disposition"}
        missing = sorted(required - set(record))
        if missing:
            raise ContractError(f"supplemental record missing {missing}")
        record_id = str(record["id"])
        if not record_id or record_id in record_ids:
            raise ContractError("supplemental record ID is empty/duplicate")
        record_ids.add(record_id)
        if str(record["task_id"]) != str(task_id) or record["task_sha"] != task_sha:
            raise ContractError("supplemental record has foreign task identity")
        if record["disposition"] not in {"included", "excluded"}:
            raise ContractError("supplemental record disposition invalid")
        ids = record["finding_ids"]
        if not isinstance(ids, list) or len(ids) != len(set(ids)):
            raise ContractError("supplemental record finding IDs invalid")
        finding_ids.update(str(value) for value in ids)
    return finding_ids


def validate_evidence(
    ledger: Mapping[str, Any], findings: Mapping[str, Any], manifest: Mapping[str, Any]
) -> dict[str, int]:
    validate_json_schema(ledger, load_json(ROOT / "schema" / "evidence-ledger.json"))
    if ledger.get("schema_version") != 1:
        raise ContractError("evidence schema_version must be 1")
    task = ledger.get("task")
    if (
        not isinstance(task, dict)
        or str(task.get("id")) != str(manifest["task"]["id"])
        or task.get("sha") != manifest["task"]["validation_sha"]
    ):
        raise ContractError("evidence task identity mismatch")
    jobs = ledger.get("jobs")
    trials = ledger.get("trials")
    reviews = ledger.get("reviews")
    if not all(isinstance(value, list) for value in (jobs, trials, reviews)):
        raise ContractError("evidence jobs/trials/reviews must be lists")
    pagination = ledger.get("pagination")
    if not isinstance(pagination, dict):
        raise ContractError("evidence pagination missing")
    _validate_pagination("jobs", pagination.get("jobs", {}), jobs)
    _validate_pagination("trials", pagination.get("trials", {}), trials)
    _validate_pagination("reviews", pagination.get("reviews", {}), reviews)
    for kind, records, required in (
        (
            "job",
            jobs,
            {
                "id",
                "task_id",
                "class",
                "model_runtime",
                "source_sha",
                "reward",
                "status",
                "artifacts_available",
                "exclusion_reason",
                "scope",
            },
        ),
        (
            "trial",
            trials,
            {
                "id",
                "task_id",
                "parent_job",
                "artifact_paths",
                "class",
                "model_runtime",
                "source_sha",
                "reward",
                "status",
                "artifacts_available",
                "exclusion_reason",
                "scope",
            },
        ),
    ):
        for record in records:
            missing = sorted(required - set(record))
            if missing:
                raise ContractError(
                    f"EVIDENCE REJECTED: {kind} {record.get('id')} missing {missing}"
                )
            if str(record["task_id"]) != str(manifest["task"]["id"]):
                raise ContractError(
                    f"EVIDENCE REJECTED: foreign task in {kind} {record.get('id')}"
                )
            if record["scope"] not in {"current", "prior"}:
                raise ContractError(
                    f"EVIDENCE REJECTED: invalid scope in {kind} {record.get('id')}"
                )
            if kind == "trial" and (
                not isinstance(record["artifact_paths"], list)
                or len(record["artifact_paths"]) != len(set(record["artifact_paths"]))
                or any(
                    not isinstance(path, str) or not Path(path).is_absolute()
                    for path in record["artifact_paths"]
                )
            ):
                raise ContractError(
                    f"EVIDENCE REJECTED: trial {record.get('id')} artifact paths invalid"
                )
            require_full_sha(
                record["source_sha"], f"{kind}.{record.get('id')}.source_sha"
            )
            if (
                record["scope"] == "current"
                and record["source_sha"] != manifest["task"]["validation_sha"]
            ):
                raise ContractError(
                    f"EVIDENCE REJECTED: mixed current SHA in {kind} {record.get('id')}"
                )
    job_ids = {str(record["id"]) for record in jobs}
    for trial in trials:
        if str(trial["parent_job"]) not in job_ids:
            raise ContractError(f"EVIDENCE REJECTED: orphan trial {trial.get('id')}")
    for review in reviews:
        for field in (
            "id",
            "task_id",
            "kind",
            "scope",
            "sha",
            "body_path",
            "body_sha256",
            "finding_ids",
        ):
            if field not in review or review[field] in (None, ""):
                if field == "finding_ids" and review.get(field) == []:
                    continue
                raise ContractError(f"EVIDENCE REJECTED: review missing {field}")
        if str(review["task_id"]) != str(manifest["task"]["id"]):
            raise ContractError(
                f"EVIDENCE REJECTED: foreign task review {review['id']}"
            )
        if review["scope"] not in {"current", "prior"}:
            raise ContractError(
                f"EVIDENCE REJECTED: review {review['id']} scope invalid"
            )
        require_full_sha(review["sha"], f"review.{review['id']}.sha")
        if (
            review["scope"] == "current"
            and review["sha"] != manifest["task"]["validation_sha"]
        ):
            raise ContractError(
                f"EVIDENCE REJECTED: current review {review['id']} has foreign SHA"
            )
        if not isinstance(review["finding_ids"], list) or len(
            review["finding_ids"]
        ) != len(set(review["finding_ids"])):
            raise ContractError(
                f"EVIDENCE REJECTED: review {review['id']} finding_ids invalid"
            )
        require_file(Path(review["body_path"]), review["body_sha256"])
    history = ledger.get("history")
    if not isinstance(history, dict) or history.get("complete") is not True:
        raise ContractError("EVIDENCE REJECTED: history completeness missing")
    if history.get("count") != len(reviews) or sorted(
        map(str, history.get("review_ids", []))
    ) != sorted(str(review["id"]) for review in reviews):
        raise ContractError("EVIDENCE REJECTED: history count/IDs mismatch")
    baselines = ledger.get("baselines")
    if not isinstance(baselines, dict):
        raise ContractError("EVIDENCE REJECTED: baselines missing")
    missing_baselines = sorted(BASELINES - set(baselines))
    extra_baselines = sorted(set(baselines) - BASELINES)
    if missing_baselines:
        raise ContractError(
            f"EVIDENCE REJECTED: baseline {missing_baselines[0]} missing"
        )
    if extra_baselines:
        raise ContractError(f"EVIDENCE REJECTED: unknown baselines {extra_baselines}")
    for name, baseline in baselines.items():
        if (
            not isinstance(baseline, dict)
            or baseline.get("status") not in BASELINE_STATUSES
            or not isinstance(baseline.get("rationale"), str)
            or not baseline["rationale"].strip()
        ):
            raise ContractError(f"EVIDENCE REJECTED: baseline {name} invalid")
    prior = ledger.get("prior_findings")
    if not isinstance(prior, list):
        raise ContractError("EVIDENCE REJECTED: prior_findings missing")
    for item in prior:
        required_prior = {
            "id",
            "severity",
            "prior_sha",
            "prior_evidence",
            "current_evidence",
            "state",
            "current_severity",
            "replay_disposition",
        }
        missing = sorted(required_prior - set(item))
        if missing:
            raise ContractError(f"EVIDENCE REJECTED: prior finding missing {missing}")
        require_full_sha(item["prior_sha"], f"prior finding {item['id']} SHA")
        if item["severity"] in {"Critical", "High"} and item["replay_disposition"] in (
            None,
            "",
        ):
            raise ContractError(
                f"EVIDENCE REJECTED: prior {item['severity']} lacks replay disposition"
            )
    prior_ids = {str(item["id"]) for item in prior}
    declared_prior_ids = {
        str(finding_id)
        for review in reviews
        if review["scope"] == "prior"
        for finding_id in review["finding_ids"]
    }
    if prior_ids != declared_prior_ids:
        raise ContractError(
            "EVIDENCE REJECTED: prior-finding ledger does not cover review finding IDs"
        )
    if not isinstance(ledger.get("unresolved"), list):
        raise ContractError("EVIDENCE REJECTED: unresolved list missing")
    counts = validate_findings(
        findings, str(manifest["task"]["id"]), manifest["task"]["validation_sha"]
    )
    supplemental_ref = ledger.get("supplemental")
    if not isinstance(supplemental_ref, dict):
        raise ContractError("EVIDENCE REJECTED: supplemental descriptor missing")
    descriptor_path = Path(str(supplemental_ref.get("descriptor_path", "")))
    require_file(descriptor_path, supplemental_ref.get("descriptor_sha256"))
    descriptor = load_json(descriptor_path)
    supplemental_finding_ids = validate_supplemental(
        descriptor,
        str(manifest["task"]["id"]),
        manifest["task"]["validation_sha"],
    )
    supplemental_run = next(
        (run for run in manifest.get("runs", []) if run.get("role") == "supplemental"),
        None,
    )
    if (
        supplemental_run is None
        or supplemental_run.get("output_path") != str(descriptor_path)
        or supplemental_run.get("output_sha256")
        != supplemental_ref.get("descriptor_sha256")
    ):
        raise ContractError(
            "EVIDENCE REJECTED: supplemental descriptor is not linked to supplemental run output"
        )
    final_finding_ids = {str(item["id"]) for item in findings["findings"]}
    current_review_finding_ids = {
        str(finding_id)
        for review in reviews
        if review["scope"] == "current"
        for finding_id in review["finding_ids"]
    }
    external_finding_ids = current_review_finding_ids | supplemental_finding_ids
    dispositions = ledger.get("finding_dispositions")
    if not isinstance(dispositions, dict):
        raise ContractError("EVIDENCE REJECTED: finding dispositions missing")
    expected_dispositions = external_finding_ids - final_finding_ids
    if set(dispositions) != expected_dispositions:
        raise ContractError(
            "EVIDENCE REJECTED: external finding reconciliation is incomplete"
        )
    for finding_id, disposition in dispositions.items():
        if (
            not isinstance(disposition, dict)
            or disposition.get("status") not in {"rejected", "merged", "not_verified"}
            or not isinstance(disposition.get("rationale"), str)
            or len(disposition["rationale"].strip()) < 15
        ):
            raise ContractError(
                f"EVIDENCE REJECTED: finding disposition {finding_id} invalid"
            )
    conditions_entry = manifest.get("conditions")
    if (
        not isinstance(conditions_entry, dict)
        or not conditions_entry.get("path")
        or not conditions_entry.get("sha256")
    ):
        raise ContractError("run manifest missing frozen conditions")
    conditions_path = Path(conditions_entry["path"])
    require_file(conditions_path, conditions_entry["sha256"])
    conditions = load_json(conditions_path)
    traversal = conditions.get("agentic", {}).get("traversal")
    if isinstance(traversal, dict) and traversal.get("complete") is True:
        traversal_job = str(traversal.get("job_id"))
        traversal_trials = {str(value) for value in traversal.get("trial_ids", [])}
        trials_by_id = {str(record["id"]): record for record in trials}
        if traversal_job not in job_ids or not traversal_trials.issubset(trials_by_id):
            raise ContractError(
                "EVIDENCE REJECTED: Agentic traversal is not tied to job/trial inventory"
            )
        if any(
            str(trials_by_id[trial_id]["parent_job"]) != traversal_job
            for trial_id in traversal_trials
        ):
            raise ContractError(
                "EVIDENCE REJECTED: Agentic traversal trial belongs to another job"
            )
        inventory_artifacts = {
            path
            for trial_id in traversal_trials
            for path in trials_by_id[trial_id]["artifact_paths"]
        }
        traversal_artifacts = {
            str(artifact["path"]) for artifact in traversal.get("artifacts", [])
        }
        if not traversal_artifacts.issubset(inventory_artifacts):
            raise ContractError(
                "EVIDENCE REJECTED: Agentic artifacts are absent from trial inventory"
            )
    if conditions["ios"]["state"] == "required":
        ios = ledger.get("ios")
        required_ios = {
            "runner",
            "target",
            "native_command",
            "f2p",
            "p2p",
            "oracle",
            "no_solution",
            "surrogate_grading",
        }
        if not isinstance(ios, dict) or required_ios - set(ios):
            raise ContractError("EVIDENCE REJECTED: required iOS evidence missing")
        if ios["runner"] != "aai-ios" or ios["surrogate_grading"] not in {True, False}:
            raise ContractError("EVIDENCE REJECTED: invalid iOS evidence")
        if (
            ios["surrogate_grading"] is True
            and findings.get("decision") != "Request changes"
        ):
            raise ContractError(
                "EVIDENCE REJECTED: surrogate iOS grading requires Request changes"
            )
    return {
        "jobs": len(jobs),
        "trials": len(trials),
        "reviews": len(reviews),
        "findings": sum(counts.values()),
    }


def load_review_format(path: Path | None = None) -> dict[str, Any]:
    data = load_json(path or (ROOT / "schema" / "review-format.json"))
    if data.get("schema_version") != 2:
        raise ContractError("review format schema_version must be 2")
    return data


def expected_headings(
    schema: Mapping[str, Any], conditions: Mapping[str, Any]
) -> list[str]:
    headings = [section["heading"] for section in schema["base_sections"]]
    for key in ("agentic", "validation_override"):
        if conditions[key]["state"] == "required":
            conditional = schema["conditional_sections"][key]
            index = headings.index(conditional["after"]) + 1
            headings.insert(index, conditional["heading"])
    return headings


def _validate_value(kind: str, value: str, spec: Mapping[str, Any]) -> None:
    if not value or value != value.strip():
        raise ContractError("empty or padded field value")
    if kind == "enum" and value not in spec["values"]:
        raise ContractError(f"invalid enum value {value!r}; expected {spec['values']}")
    if kind == "counts" and COUNTS.fullmatch(value) is None:
        raise ContractError(f"invalid Counts value: {value!r}")
    if kind == "score_1_4" and value not in {"1", "2", "3", "4"}:
        raise ContractError(f"invalid 1-4 score: {value!r}")
    if kind == "confidence" and re.fullmatch(r"[1-5] - \S.*", value) is None:
        raise ContractError(f"invalid confidence: {value!r}")
    if kind == "tbr_checks":
        if TBR_CHECKS.fullmatch(value) is None:
            raise ContractError(f"invalid TBR check list: {value!r}")
        if value not in {"none", "NOT VERIFIED"}:
            unknown = [
                item.strip()
                for item in value.split(",")
                if item.strip() not in spec.get("values", [])
            ]
            if unknown:
                raise ContractError(f"unknown TBR check IDs: {unknown}")
    if kind == "language" and LANGUAGE.fullmatch(value) is None:
        raise ContractError(f"invalid primary language token: {value!r}")
    if kind == "languages" and value != "None":
        for language in [part.strip() for part in value.split(",")]:
            if LANGUAGE.fullmatch(language) is None:
                raise ContractError(f"invalid language token: {language!r}")
    if kind == "rationale":
        if value in {"None", "No finding", "NOT VERIFIED", "NO DATA", "Not applicable"}:
            raise ContractError("task-specific rationale cannot be a placeholder")
        if len(value) < 20 or len(value.split()) < 4:
            raise ContractError("task-specific rationale is too short")
    if kind == "other_notes" and value != "None":
        for prefix in ("Strengths:", "To fix:", "To notice:"):
            if prefix not in value:
                raise ContractError(f"Other Notes missing {prefix}")


def parse_review(
    review_path: Path, schema: Mapping[str, Any], conditions: Mapping[str, Any]
) -> dict[str, dict[str, str]]:
    text = review_path.read_text(encoding="utf-8")
    if "```" in text:
        raise ContractError("final review must not contain fenced code")
    lines = text.splitlines()
    nonempty = [line for line in lines if line.strip()]
    if not nonempty or not nonempty[0].startswith("### "):
        raise ContractError("unexpected preamble before first canonical section")
    sections: list[tuple[str, list[str]]] = []
    current: tuple[str, list[str]] | None = None
    for line in lines:
        if not line.strip():
            continue
        match = HEADING_LINE.fullmatch(line)
        if match:
            if current is not None:
                sections.append(current)
            current = (match.group(1), [])
        elif current is None:
            raise ContractError(f"unconsumed prose before first heading: {line!r}")
        else:
            current[1].append(line)
    if current is not None:
        sections.append(current)
    headings = [heading for heading, _ in sections]
    expected = expected_headings(schema, conditions)
    if headings != expected:
        raise ContractError(
            f"canonical section order mismatch: found {headings}; expected {expected}"
        )
    standard = {section["heading"]: section for section in schema["base_sections"]}
    standard[schema["conditional_sections"]["agentic"]["heading"]] = schema[
        "conditional_sections"
    ]["agentic"]
    parsed: dict[str, dict[str, str]] = {}
    for heading, body in sections:
        if heading == schema["conditional_sections"]["validation_override"]["heading"]:
            reasons = conditions["validation_override"].get("reasons", [])
            cursor = 0
            groups: dict[str, str] = {}
            for reason in reasons:
                expected_name = str(reason.get("heading") or reason.get("check") or "")
                if (
                    cursor >= len(body)
                    or GROUP_LINE.fullmatch(body[cursor]) is None
                    or GROUP_LINE.fullmatch(body[cursor]).group(1) != expected_name
                ):
                    raise ContractError(
                        f"Validation Override missing group {expected_name!r}"
                    )
                cursor += 1
                for label in ("Submitter Reason", "Reviewer Agrees?", "Reviewer Notes"):
                    if cursor >= len(body):
                        raise ContractError(
                            f"Validation Override {expected_name} missing {label}"
                        )
                    field = FIELD_LINE.fullmatch(body[cursor])
                    if field is None or field.group(1) != label:
                        raise ContractError(
                            f"Validation Override {expected_name} expected {label}"
                        )
                    if label == "Reviewer Agrees?" and field.group(2) not in {
                        "Agree",
                        "Partially",
                        "Disagree",
                    }:
                        raise ContractError(
                            f"Validation Override {expected_name} invalid agreement"
                        )
                    if label == "Submitter Reason" and field.group(2) != reason.get(
                        "reason"
                    ):
                        raise ContractError(
                            f"Validation Override {expected_name} submitter reason drift"
                        )
                    groups[f"{expected_name}.{label}"] = field.group(2)
                    cursor += 1
            if cursor != len(body):
                raise ContractError("unconsumed Validation Override content")
            parsed[heading] = groups
            continue
        spec = standard[heading]
        fields = spec["fields"]
        if len(body) != len(fields):
            raise ContractError(
                f"field count mismatch in {heading}: {len(body)} != {len(fields)}"
            )
        values: dict[str, str] = {}
        for line, field_spec in zip(body, fields):
            match = FIELD_LINE.fullmatch(line)
            if match is None or match.group(1) != field_spec["label"]:
                raise ContractError(
                    f"field shape/order mismatch in {heading}: {line!r}"
                )
            value = match.group(2)
            _validate_value(field_spec["kind"], value, field_spec)
            values[field_spec["label"]] = value
        parsed[heading] = values
    return parsed


def count_words(text: str) -> tuple[int, int]:
    lexical = len(re.findall(r"\b\w+(?:[-']\w+)*\b", text))
    whitespace = len(text.split())
    return lexical, whitespace


def line_number(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def validate_context(text: str, manifest: Mapping[str, Any]) -> int:
    context = manifest.get("context")
    if not isinstance(context, dict):
        raise ContractError("CONTEXT REJECTED: frozen context manifest missing")
    allowed_ids = {
        str(value).casefold() for value in context.get("allowed_identifiers", [])
    }
    allowed_paths = [str(value) for value in context.get("allowed_path_prefixes", [])]
    allowed_repos = {
        str(value).casefold() for value in context.get("allowed_repositories", [])
    }
    if not allowed_ids or not allowed_paths or not allowed_repos:
        raise ContractError("CONTEXT REJECTED: context allowlists must be nonempty")
    discovered: set[str] = set()
    discovered.update(
        match.group(0)
        for match in re.finditer(r"\b[0-9a-f]{40}\b", text, re.IGNORECASE)
    )
    discovered.update(UUID.findall(text))
    discovered.update(
        match.group(1)
        for match in re.finditer(r"codimango\.internalmeta\.com/reviews/(\d+)", text)
    )
    discovered.update(re.findall(r"\b[DTSP]\d{5,}\b", text))
    discovered.update(
        token for token in re.findall(r"`([0-9a-f]{7,39})`", text, re.IGNORECASE)
    )
    discovered.update(
        match.group(1)
        for match in re.finditer(
            r"\b(?:task|job|trial)\s+`?(\d{5,})`?", text, re.IGNORECASE
        )
    )
    for value in discovered:
        folded_value = value.casefold()
        if not any(
            folded_value == allowed
            or (
                re.fullmatch(r"[0-9a-f]{7,39}", folded_value)
                and re.fullmatch(r"[0-9a-f]{40}", allowed)
                and allowed.startswith(folded_value)
            )
            for allowed in allowed_ids
        ):
            raise ContractError(f"CONTEXT REJECTED: foreign identifier {value}")
    for repo in re.findall(r"\bcodimango/[A-Za-z0-9_.-]+", text):
        if repo.casefold() not in allowed_repos:
            raise ContractError(f"CONTEXT REJECTED: foreign repository {repo}")
    path_count = 0
    for token in re.findall(r"`([^`]+)`", text):
        candidate = re.sub(r":\d+(?:-\d+)?$", "", token)
        if "/" not in candidate and not re.search(r"\.[A-Za-z0-9]+$", candidate):
            continue
        if candidate.startswith(("http://", "https://")):
            continue
        path_count += 1
        if not any(
            candidate == prefix or candidate.startswith(prefix.rstrip("/") + "/")
            for prefix in allowed_paths
        ):
            raise ContractError(f"CONTEXT REJECTED: foreign path {candidate}")
    return len(discovered) + path_count


def validate_language(
    review_path: Path, manifest: Mapping[str, Any], max_words: int | None = None
) -> tuple[int, int, int]:
    text = review_path.read_text(encoding="utf-8")
    schema = load_review_format()
    limit = max_words if max_words is not None else int(schema["word_limit_exclusive"])
    lexical, whitespace = count_words(text)
    maximum = max(lexical, whitespace)
    if maximum >= limit:
        raise ContractError(f"WORD LIMIT REJECTED max={maximum} required<{limit}")
    for token in ("—", "#thanks"):
        if token.casefold() in text.casefold():
            raise ContractError(f"forbidden style token: {token!r}")
    for label, pattern in FORBIDDEN_LANGUAGE_PATTERNS:
        match = pattern.search(text)
        if match:
            raise ContractError(
                f"line {line_number(text, match.start())}: {label}: {match.group(0)!r}"
            )
    identifiers = validate_context(text, manifest)
    return lexical, whitespace, identifiers


def _counts_tuple(value: str) -> tuple[int, int, int, int]:
    match = COUNTS.fullmatch(value)
    if match is None:
        raise ContractError(f"invalid counts: {value}")
    return tuple(int(group) for group in match.groups())


def validate_final(
    review_path: Path,
    template_path: Path,
    conditions_path: Path,
    findings_path: Path,
    manifest_path: Path,
) -> dict[str, int]:
    schema = load_review_format()
    generated = generate_template(schema)
    actual_template = template_path.read_text(encoding="utf-8")
    if actual_template != generated:
        raise ContractError("template drift: regenerate references/output-template.md")
    manifest = load_json(manifest_path)
    task_id = str(manifest["task"]["id"])
    task_sha = manifest["task"]["validation_sha"]
    conditions = load_json(conditions_path)
    validate_conditions(conditions, task_id, task_sha)
    findings = load_json(findings_path)
    counts = validate_findings(findings, task_id, task_sha)
    parsed = parse_review(review_path, schema, conditions)
    tbr = parsed["TBR Review Agreement"]
    tbr_agreement = tbr["Reviewer Agrees?"]
    tbr_checks = tbr["Disagreed Checks"]
    if tbr_agreement == "Agree" and tbr_checks != "none":
        raise ContractError("TBR agreement contradicts disagreed checks")
    if tbr_agreement in {"Partially", "Disagree"} and tbr_checks == "none":
        raise ContractError("TBR disagreement requires at least one check")
    expected_counts = (
        counts["Critical"],
        counts["High"],
        counts["Medium"],
        counts["Low"],
    )
    actual_counts = _counts_tuple(parsed["Quality Review Agent"]["Counts"])
    if actual_counts != expected_counts:
        raise ContractError(
            f"finding counts mismatch: review={actual_counts} findings={expected_counts}"
        )
    if parsed["Quality Review Agent"]["Verdict"] != findings["quality_verdict"]:
        raise ContractError("Quality verdict differs from findings source")
    if parsed["Decision"]["Decision"] != findings["decision"]:
        raise ContractError("Decision differs from findings source")
    mapped = schema["quality_to_decision"][findings["quality_verdict"]]
    if (
        findings["decision"] != mapped
        and len(findings["decision_reconciliation"].strip()) < 20
    ):
        raise ContractError(
            "Quality verdict/Decision difference lacks a substantive reconciliation"
        )
    counts_text = f"Critical {actual_counts[0]}, High {actual_counts[1]}, Medium {actual_counts[2]}, Low {actual_counts[3]}"
    if counts_text not in parsed["Decision"]["Reason"]:
        raise ContractError("Decision Reason does not repeat canonical severity counts")
    blocking = [finding for finding in findings["findings"] if finding["blocking"]]
    for finding in blocking:
        if finding["close_condition"] not in parsed["Decision"]["Reason"]:
            raise ContractError(
                f"Decision Reason omits close condition for {finding['id']}"
            )
    lexical, whitespace, identifiers = validate_language(review_path, manifest)
    return {
        "sections": len(parsed),
        "fields": sum(len(values) for values in parsed.values()),
        "lexical": lexical,
        "whitespace": whitespace,
        "identifiers": identifiers,
    }


def render_review(
    review_data: Mapping[str, Any],
    findings: Mapping[str, Any],
    conditions: Mapping[str, Any],
) -> str:
    validate_json_schema(review_data, load_json(ROOT / "schema" / "review-data.json"))
    schema = load_review_format()
    task_id = str(review_data.get("task_id", ""))
    task_sha = review_data.get("task_sha")
    validate_conditions(conditions, task_id, task_sha)
    counts = validate_findings(findings, task_id, task_sha)
    sections_data = review_data.get("sections")
    if not isinstance(sections_data, dict):
        raise ContractError("review-data sections missing")
    headings = expected_headings(schema, conditions)
    by_heading = {section["heading"]: section for section in schema["base_sections"]}
    by_heading[schema["conditional_sections"]["agentic"]["heading"]] = schema[
        "conditional_sections"
    ]["agentic"]
    rendered: list[str] = []
    for heading in headings:
        rendered.append(f"### {heading}")
        if heading == schema["conditional_sections"]["validation_override"]["heading"]:
            supplied = review_data.get("validation_overrides")
            reasons = conditions["validation_override"].get("reasons", [])
            if not isinstance(supplied, list) or len(supplied) != len(reasons):
                raise ContractError("review-data Validation Override group mismatch")
            for expected, group in zip(reasons, supplied):
                name = str(expected.get("heading") or expected.get("check") or "")
                if group.get("heading") != name:
                    raise ContractError(
                        "review-data Validation Override heading mismatch"
                    )
                if group.get("Submitter Reason") != expected.get("reason"):
                    raise ContractError(
                        f"review-data Validation Override reason mismatch for {name}"
                    )
                rendered.extend(
                    [
                        f"- **{name}**",
                        f"- **Submitter Reason:** {group.get('Submitter Reason', '')}",
                        f"- **Reviewer Agrees?:** {group.get('Reviewer Agrees?', '')}",
                        f"- **Reviewer Notes:** {group.get('Reviewer Notes', '')}",
                    ]
                )
            rendered.append("")
            continue
        spec = by_heading[heading]
        key = spec.get("key", "agentic")
        values = sections_data.get(key)
        if not isinstance(values, dict):
            raise ContractError(f"review-data missing section {key}")
        for field in spec["fields"]:
            label = field["label"]
            if heading == "Quality Review Agent" and label == "Verdict":
                value = findings["quality_verdict"]
            elif heading == "Quality Review Agent" and label == "Counts":
                value = f"Critical {counts['Critical']} | High {counts['High']} | Medium {counts['Medium']} | Low {counts['Low']}"
            elif heading == "Decision" and label == "Decision":
                value = findings["decision"]
            else:
                value = values.get(label, "")
            if not isinstance(value, str) or not value.strip():
                raise ContractError(f"review-data missing {heading} / {label}")
            rendered.append(f"- **{label}:** {value.strip()}")
        rendered.append("")
    return "\n".join(rendered).rstrip() + "\n"


def render_live_payload(
    review_data: Mapping[str, Any],
    findings: Mapping[str, Any],
    conditions: Mapping[str, Any],
) -> dict[str, Any]:
    mapping = load_json(ROOT / "schema" / "live-form-payload.json")
    if mapping.get("schema_version") != 1:
        raise ContractError("live-form payload mapping schema mismatch")
    sources: dict[str, Any] = {
        "sections": review_data.get("sections", {}),
        "findings": findings,
        "review_data": review_data,
        "conditions": conditions,
    }

    def lookup(path: str) -> Any:
        value: Any = sources
        for part in path.split("."):
            if not isinstance(value, Mapping) or part not in value:
                raise ContractError(f"live-form mapping source missing: {path}")
            value = value[part]
        return value

    def transform(value: Any, name: str | None) -> Any:
        if name is None:
            return value
        if name == "score_prefix":
            return str(value).split(" - ", 1)[0]
        if name == "csv_or_empty":
            return (
                []
                if value in {"none", "NOT VERIFIED"}
                else [part.strip() for part in str(value).split(",")]
            )
        if name == "decision_action":
            return {
                "Accept": "accept",
                "Request changes": "revision",
                "Reject": "reject",
            }[str(value)]
        if name == "override_review":
            groups = value
            reasons = conditions["validation_override"].get("reasons", [])
            if not isinstance(groups, list) or len(groups) != len(reasons):
                raise ContractError("live-form override review count mismatch")
            result: dict[str, dict[str, str]] = {}
            for reason, group in zip(reasons, groups):
                check = reason.get("check")
                if (
                    not isinstance(check, str)
                    or not check
                    or not isinstance(group, dict)
                ):
                    raise ContractError("live-form override review identity invalid")
                result[check] = {
                    "agree": str(group.get("Reviewer Agrees?", "")).strip(),
                    "notes": str(group.get("Reviewer Notes", "")).strip(),
                }
            return result
        raise ContractError(f"unknown live-form transform: {name}")

    entries = list(mapping.get("field_mappings", []))
    for condition in ("agentic", "validation_override"):
        if conditions[condition]["state"] == "required":
            entries.extend(
                mapping.get("conditional_field_mappings", {}).get(condition, [])
            )
    payload: dict[str, Any] = {}
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not entry.get("source")
            or not entry.get("target")
        ):
            raise ContractError("invalid live-form field mapping")
        target = entry["target"]
        if target in payload:
            raise ContractError(f"duplicate live-form target: {target}")
        payload[target] = transform(lookup(entry["source"]), entry.get("transform"))
    expected_targets = {entry["target"] for entry in entries}
    if set(payload) != expected_targets:
        raise ContractError(
            "live-form payload mapping did not produce every target exactly once"
        )
    validate_live_payload(payload, conditions)
    return payload


def validate_live_payload(
    payload: Mapping[str, Any], conditions: Mapping[str, Any]
) -> None:
    agreements = {"Agree", "Partially", "Disagree"}
    for field in (
        "qualityAgree",
        "contaminationAgree",
        "noveltyAgree",
        "mmAgenticFullTaskReviewAgree",
    ):
        if field in payload and payload[field] not in agreements:
            raise ContractError(f"live-form payload {field} is invalid")
    for field in ("realisticScenario", "domainExpertise", "originality"):
        if payload.get(field) not in {"1", "2", "3", "4"}:
            raise ContractError(f"live-form payload {field} is invalid")
    if payload.get("decision") not in {"accept", "revision", "reject"}:
        raise ContractError("live-form payload decision is invalid")
    if payload.get("reviewerConfidence") not in {"1", "2", "3", "4", "5"}:
        raise ContractError("live-form payload reviewerConfidence is invalid")
    criteria = payload.get("tbrDisagreeCriteria")
    allowed_criteria = {
        value
        for section in load_review_format()["base_sections"]
        if section["heading"] == "TBR Review Agreement"
        for field in section["fields"]
        if field["label"] == "Disagreed Checks"
        for value in field["values"]
    }
    if not isinstance(criteria, list) or any(
        value not in allowed_criteria for value in criteria
    ):
        raise ContractError("live-form payload TBR criteria are invalid")
    if "followUpNeeded" in payload or "validationOverrides" in payload:
        raise ContractError("live-form payload contains legacy fields")
    if conditions["agentic"]["state"] == "required":
        if (
            not isinstance(payload.get("mmAgenticFullTaskReviewRunId"), str)
            or not payload["mmAgenticFullTaskReviewRunId"].strip()
        ):
            raise ContractError("live-form payload lacks Agentic run identity")
    override_reasons = conditions["validation_override"].get("reasons", [])
    mapping = load_json(ROOT / "schema" / "live-form-payload.json")
    allowed_override_checks = set(mapping.get("override_review_valid_checks", []))
    if any(
        reason.get("check") not in allowed_override_checks
        for reason in override_reasons
    ):
        raise ContractError("live-form payload contains unknown override check")
    if conditions["validation_override"]["state"] == "required":
        review = payload.get("overrideReview")
        expected_checks = {reason["check"] for reason in override_reasons}
        if not isinstance(review, dict) or set(review) != expected_checks:
            raise ContractError("live-form payload overrideReview keys mismatch")
        for check, value in review.items():
            if (
                not isinstance(value, dict)
                or value.get("agree") not in agreements
                or not isinstance(value.get("notes"), str)
                or not value["notes"].strip()
            ):
                raise ContractError(
                    f"live-form payload overrideReview entry invalid: {check}"
                )


def generate_template(schema: Mapping[str, Any]) -> str:
    lines = [
        "# Canonical Codimango review form contract",
        "",
        "This file is generated from `schema/review-format.json`. Edit the schema, then run:",
        "",
        "`python3 scripts/generate_template.py --write`",
        "",
        "A reviewer that cannot read this file must stop with:",
        "",
        "`Canonical review format could not be generated.`",
        "",
        "The author-facing review contains eight base sections in order. Conditional Agentic and Validation Override sections are inserted only when `conditions.json` marks them required. The complete form must remain under 700 words.",
        "",
        "## Exact skeleton",
        "",
        "```markdown",
    ]
    sections = list(schema["base_sections"])
    agentic = dict(schema["conditional_sections"]["agentic"])
    validation_override = dict(schema["conditional_sections"]["validation_override"])
    insertion = (
        next(
            i
            for i, section in enumerate(sections)
            if section["heading"] == agentic["after"]
        )
        + 1
    )
    sections.insert(insertion, agentic)
    insertion = (
        next(
            i
            for i, section in enumerate(sections)
            if section["heading"] == validation_override["after"]
        )
        + 1
    )
    sections.insert(insertion, validation_override)
    for section in sections:
        heading = section["heading"]
        conditional = heading in {agentic["heading"], validation_override["heading"]}
        if conditional:
            lines.append(
                f"<!-- conditional: {section.get('key', 'validation_override')} -->"
            )
        lines.append(f"### {heading}")
        if section.get("kind") == "override_groups":
            lines.extend(
                [
                    "- **CHECK_HEADING**",
                    "- **Submitter Reason:** Existing submitter rationale.",
                    "- **Reviewer Agrees?:** Agree / Partially / Disagree",
                    "- **Reviewer Notes:** Current-task evidence.",
                ]
            )
        else:
            for field in section["fields"]:
                kind = field["kind"]
                if kind == "enum":
                    value = " / ".join(field["values"])
                elif kind == "counts":
                    value = "Critical N | High N | Medium N | Low N"
                elif kind == "score_1_4":
                    value = "1 / 2 / 3 / 4"
                elif kind == "confidence":
                    value = "N - concise evidence-coverage rationale"
                elif kind == "tbr_checks":
                    value = "none / comma-separated snake_case check IDs / NOT VERIFIED"
                elif kind == "language":
                    value = "One verified language token"
                elif kind == "languages":
                    value = "Comma-separated languages / None"
                elif kind == "other_notes":
                    value = "Strengths: ... To fix: ... To notice: ..."
                elif kind == "decision_reason":
                    value = "Current-state counts, evidence, required changes, and close conditions"
                elif kind == "rationale":
                    value = "Task-specific rationale"
                else:
                    value = "Current-task text / explicit unavailable state"
                lines.append(f"- **{field['label']}:** {value}")
        lines.append("")
    lines.extend(
        [
            "```",
            "",
            "## Content rules",
            "",
            "- `conditions.json` decides whether Agentic and Validation Override are present. An unresolved condition blocks delivery.",
            "- Every affirmative statement is verified by evidence. Use `NOT VERIFIED` only for unavailable or uncertain evidence.",
            "- Human Check scores require task-specific rationales.",
            "- Decision findings descend by severity and include observable close conditions.",
            "- Other Notes preserves missing artifacts, unrun baselines, revision mismatches, and material caveats.",
            "- No batch comparisons, cross-task facts, review-history narration, reviewer self-history, `#thanks`, AI-speak, or em dashes.",
            "",
            "## Validation",
            "",
            "Run `python3 scripts/finalize_review.py --help`; only its approval receipt authorizes publication.",
            "",
        ]
    )
    return "\n".join(lines)


def validate_command_audit(
    audit_path: Path, manifest: Mapping[str, Any], policy_path: Path
) -> int:
    policy = load_json(policy_path)
    entries: list[dict[str, Any]] = []
    try:
        for number, raw in enumerate(
            audit_path.read_text(encoding="utf-8").splitlines(), 1
        ):
            if not raw.strip():
                continue
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ContractError(f"command audit line {number} is not an object")
            entries.append(value)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read command audit: {exc}") from exc
    if not entries:
        raise ContractError("READ-ONLY REJECTED: empty command audit is unmeasured")
    task_id = str(manifest["task"]["id"])
    scratch = Path(manifest["scratch_root"])
    repo_root = (
        Path(manifest["task_repo_root"]) if manifest.get("task_repo_root") else None
    )
    allowed_ids = {str(v) for v in manifest["context"]["allowed_identifiers"]}
    blind_events = [
        phase
        for phase in manifest.get("phases", [])
        if phase.get("name") == "blind_sealed"
    ]
    blind_sealed_sequence = (
        int(blind_events[0].get("sequence")) if len(blind_events) == 1 else None
    )
    review_artifact_ids = {
        str(value)
        for value in manifest.get("context", {}).get("review_artifact_ids", [])
    }
    allowed_binaries = set(policy.get("allowed_binaries", []))
    allowed_codimango_reads = {
        tuple(item) for item in policy.get("allowed_codimango_reads", [])
    }
    allowed_git_reads = set(policy.get("allowed_git_reads", []))
    allowed_meta_prefixes = tuple(policy.get("allowed_meta_prefixes", []))
    for index, entry in enumerate(entries, 1):
        argv = entry.get("argv")
        if (
            not isinstance(argv, list)
            or not argv
            or any(not isinstance(v, str) for v in argv)
        ):
            raise ContractError(f"READ-ONLY REJECTED: invalid argv at entry {index}")
        if entry.get("sandbox") not in {"linux", "darwin"}:
            raise ContractError(
                f"READ-ONLY REJECTED: command {index} lacks OS sandbox receipt"
            )
        resolved = Path(str(entry.get("resolved_executable", "")))
        if not resolved.is_absolute():
            raise ContractError(
                f"READ-ONLY REJECTED: command {index} lacks resolved executable"
            )
        if path_within(resolved, scratch) or (
            repo_root is not None and path_within(resolved, repo_root)
        ):
            raise ContractError(
                f"READ-ONLY REJECTED: command {index} used untrusted executable"
            )
        command = " ".join(argv)
        command_time = parse_time(entry.get("timestamp"), f"command.{index}.timestamp")
        binary = Path(argv[0]).name
        phase_sequence = entry.get("phase_sequence")
        if not isinstance(phase_sequence, int) or phase_sequence < 0:
            raise ContractError(
                f"READ-ONLY REJECTED: command {index} lacks phase sequence"
            )
        history_sensitive = (
            binary == "codimango"
            and len(argv) >= 3
            and tuple(argv[1:3])
            in {
                ("task", "comments"),
                ("task", "reviews"),
                ("job", "review"),
                ("trial", "artifacts"),
            }
        ) or any(identifier in command for identifier in review_artifact_ids)
        if history_sensitive and (
            blind_sealed_sequence is None or phase_sequence < blind_sealed_sequence
        ):
            raise ContractError(
                "PHASE ORDER REJECTED: review/history command before blind_sealed"
            )
        if binary not in allowed_binaries:
            raise ContractError(f"READ-ONLY REJECTED: unapproved executable {binary}")
        folded = command.casefold()
        for pattern in policy["forbidden_patterns"]:
            if pattern.casefold() in folded:
                raise ContractError(f"READ-ONLY REJECTED: mutation command {command}")
        if "codimango" in Path(argv[0]).name:
            if len(argv) < 3 or tuple(argv[1:3]) not in allowed_codimango_reads:
                raise ContractError(
                    f"READ-ONLY REJECTED: unapproved Codimango command {command}"
                )
            if argv[1:3] == ["task", "list"]:
                raise ContractError("READ-ONLY REJECTED: broad task list")
            if task_id not in command and not any(
                identifier in command for identifier in allowed_ids
            ):
                raise ContractError(
                    f"READ-ONLY REJECTED: Codimango command not task-scoped: {command}"
                )
        if (
            Path(argv[0]).name == "git"
            and len(argv) > 1
            and argv[1] not in allowed_git_reads
        ):
            raise ContractError(f"READ-ONLY REJECTED: git mutation command {command}")
        if binary == "meta":
            subcommand = " ".join(argv[1:3])
            if not any(
                subcommand.startswith(prefix) for prefix in allowed_meta_prefixes
            ):
                raise ContractError(
                    f"READ-ONLY REJECTED: unapproved Meta command {command}"
                )
        for raw_path in entry.get("writes", []):
            write_path = Path(str(raw_path))
            if not path_within(write_path, scratch):
                raise ContractError(
                    f"READ-ONLY REJECTED: write outside scratch root {write_path}"
                )
            if repo_root is not None and path_within(write_path, repo_root):
                raise ContractError(
                    f"READ-ONLY REJECTED: task repository write {write_path}"
                )
        if str(entry.get("task_id")) != task_id:
            raise ContractError(f"READ-ONLY REJECTED: foreign task at command {index}")
    return len(entries)


def approval_receipt(
    manifest_path: Path,
    review_path: Path,
    live_payload_path: Path,
    evidence_path: Path,
    findings_path: Path,
    ledger_path: Path,
    command_audit_path: Path,
) -> dict[str, Any]:
    manifest = load_json(manifest_path)
    files = {
        "review": review_path,
        "live_payload": live_payload_path,
        "evidence": evidence_path,
        "findings": findings_path,
        "evidence_ledger": ledger_path,
        "command_audit": command_audit_path,
    }
    return {
        "schema_version": 1,
        "task_id": str(manifest["task"]["id"]),
        "task_sha": manifest["task"]["validation_sha"],
        "critic_session_id": next(
            run["session_id"] for run in manifest["runs"] if run["role"] == "critic"
        ),
        "bundle_commit": manifest["bundle"]["commit"],
        "run_manifest": {
            "path": str(manifest_path.resolve()),
            "sha256": sha256_file(manifest_path),
        },
        "conditions": manifest["conditions"],
        "approved_at": utc_now(),
        "files": {
            name: {"path": str(path.resolve()), "sha256": sha256_file(path)}
            for name, path in files.items()
        },
        "verdict": "PASS",
    }


def verify_identical_bytes(
    approval: Mapping[str, Any], source_name: str, source_path: Path, destination: Path
) -> str:
    entry = approval.get("files", {}).get(source_name)
    if not isinstance(entry, dict):
        raise ContractError(f"approval lacks {source_name}")
    require_file(source_path, entry.get("sha256"))
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source_path, destination)
    actual = sha256_file(destination)
    if actual != entry["sha256"]:
        raise ContractError("PUBLISH REJECTED: byte hash changed")
    return actual


def validate_release_lock(
    path: Path, template_path: Path | None = None
) -> dict[str, Any]:
    data = load_json(path)
    if data.get("schema_version") != 1:
        raise ContractError("LOCK REJECTED: schema_version must be 1")
    if re.fullmatch(r"\d+\.\d+\.\d+", str(data.get("release", ""))) is None:
        raise ContractError("LOCK REJECTED: release must be semantic version")
    dependencies = data.get("dependencies")
    required = {
        "aai-review-flow",
        "team-aai-fbsource",
        "review-trials-and-spec",
        "aai-ios",
        "aai-long-horizon",
        "codimango-cli-revision",
    }
    if not isinstance(dependencies, dict) or set(dependencies) != required:
        raise ContractError("LOCK REJECTED: dependency set mismatch")
    for name, revision in dependencies.items():
        if (
            not isinstance(revision, str)
            or re.fullmatch(r"[0-9a-f]{12,40}|v?\d+\.\d+\.\d+", revision) is None
        ):
            raise ContractError(
                f"LOCK REJECTED: dependency {name} lacks immutable revision"
            )
    external = data.get("external_contracts")
    if not isinstance(external, dict) or not external:
        raise ContractError("LOCK REJECTED: external contracts missing")
    for name, revision in external.items():
        if FULL_SHA.fullmatch(str(revision)) is None:
            raise ContractError(
                f"LOCK REJECTED: external contract {name} lacks full SHA"
            )
    schemas = data.get("schemas")
    if (
        not isinstance(schemas, dict)
        or not schemas
        or any(not isinstance(value, int) or value < 1 for value in schemas.values())
    ):
        raise ContractError("LOCK REJECTED: schema versions invalid")
    artifacts = data.get("artifacts")
    if not isinstance(artifacts, dict) or not artifacts:
        raise ContractError("LOCK REJECTED: artifact hashes missing")
    root = path.resolve().parent
    for relative, expected in artifacts.items():
        require_file(root / relative, expected)
    if template_path is not None and template_path.read_text(
        encoding="utf-8"
    ) != generate_template(load_review_format()):
        raise ContractError("LOCK REJECTED: template drift")
    return data


def format_error(prefix: str, exc: BaseException) -> str:
    return f"{prefix}: {exc}"
