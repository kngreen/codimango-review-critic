#!/usr/bin/env python3
"""Execute one prevalidated command in a read-only task sandbox and audit it."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from contract import (
    ContractError,
    ROOT,
    load_json,
    path_within,
    utc_now,
    validate_command_audit,
)

OFFLINE_BINARIES = {
    "python",
    "python3",
    "bash",
    "sh",
    "jq",
    "grep",
    "rg",
    "sed",
    "awk",
    "wc",
    "sha256sum",
    "xcodebuild",
    "xcrun",
    "buck2",
    "tar",
    "unzip",
}


def linux_sandbox(
    command: list[str], task_repo: Path, scratch: Path, cwd: Path
) -> list[str]:
    if shutil.which("unshare") is None:
        raise ContractError("READ-ONLY REJECTED: Linux mount namespace unavailable")
    probe = subprocess.run(
        ["unshare", "-Ur", "true"],
        text=True,
        capture_output=True,
        check=False,
    )
    if probe.returncode != 0:
        raise ContractError("READ-ONLY REJECTED: Linux user namespace unavailable")
    offline = Path(command[0]).name in OFFLINE_BINARIES
    script = r"""
set -eu
repo="$1"; scratch="$2"; cwd="$3"; home="$4"; shift 4
for root in /tmp "$home" /var/tmp "${XDG_RUNTIME_DIR:-}"; do
  if [ -d "$root" ]; then
    mount --bind "$root" "$root"
    mount -o remount,ro,bind "$root"
  fi
done
if [ -d /dev/shm ]; then
  mount -t tmpfs -o ro,size=1m tmpfs /dev/shm
fi
mount --bind "$scratch" "$scratch"
mount -o remount,rw,bind "$scratch"
mount --bind "$repo" "$repo"
mount -o remount,ro,bind "$repo"
mkdir -p "$scratch/cache" "$scratch/tmp"
export XDG_CACHE_HOME="$scratch/cache"
export TMPDIR="$scratch/tmp"
cd "$cwd"
exec "$@"
"""
    result = ["unshare", "-Ur", "-m"]
    if offline:
        result.append("-n")
    result.extend(
        [
            "sh",
            "-c",
            script,
            "sandbox",
            str(task_repo),
            str(scratch),
            str(cwd),
            str(Path.home()),
            *command,
        ]
    )
    return result


def macos_sandbox(
    command: list[str], task_repo: Path, scratch: Path, cwd: Path
) -> list[str]:
    executable = shutil.which("sandbox-exec")
    if executable is None:
        raise ContractError("READ-ONLY REJECTED: macOS sandbox-exec unavailable")

    def escaped(path: Path) -> str:
        return str(path).replace("\\", "\\\\").replace('"', '\\"')

    temp_root = scratch / "tmp"
    cache_root = scratch / "cache"
    temp_root.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    network = "" if Path(command[0]).name in OFFLINE_BINARIES else "(allow network*)"
    profile = (
        "(version 1)(deny default)(allow process*)(allow file-read*)"
        f'(allow file-write* (subpath "{escaped(scratch)}"))'
        '(allow file-write* (literal "/dev/null"))'
        f"{network}"
        f'(deny file-write* (subpath "{escaped(task_repo)}"))'
    )
    return [
        executable,
        "-p",
        profile,
        "/usr/bin/env",
        f"TMPDIR={temp_root}",
        f"DARWIN_USER_TEMP_DIR={temp_root}",
        f"DARWIN_USER_CACHE_DIR={cache_root}",
        f"XDG_CACHE_HOME={cache_root}",
        *command,
    ]


def resolve_executable(command: list[str], task_repo: Path, scratch: Path) -> list[str]:
    raw = command[0]
    if "/" in raw:
        executable = Path(raw).resolve()
    else:
        located = shutil.which(raw)
        if located is None:
            raise ContractError(f"READ-ONLY REJECTED: executable not found: {raw}")
        executable = Path(located).resolve()
    if not executable.is_file():
        raise ContractError(
            f"READ-ONLY REJECTED: executable is not a file: {executable}"
        )
    if path_within(executable, scratch) or path_within(executable, task_repo):
        raise ContractError(
            f"READ-ONLY REJECTED: executable comes from untrusted workspace: {executable}"
        )
    return [str(executable), *command[1:]]


def sandboxed_command(
    command: list[str], manifest: dict, cwd: Path
) -> tuple[list[str], str]:
    scratch = Path(manifest["scratch_root"]).resolve()
    task_repo_raw = manifest.get("task_repo_root")
    if not task_repo_raw:
        raise ContractError("READ-ONLY REJECTED: task repository root is unresolved")
    task_repo = Path(task_repo_raw).resolve()
    if not task_repo.is_dir():
        raise ContractError("READ-ONLY REJECTED: task repository root is missing")
    if not path_within(cwd, scratch):
        raise ContractError(
            "READ-ONLY REJECTED: command cwd must be inside scratch root"
        )
    command = resolve_executable(command, task_repo, scratch)
    resolved_executable = command[0]
    system = platform.system()
    if system == "Linux":
        return linux_sandbox(command, task_repo, scratch, cwd), resolved_executable
    if system == "Darwin":
        return macos_sandbox(command, task_repo, scratch, cwd), resolved_executable
    raise ContractError(f"READ-ONLY REJECTED: unsupported sandbox platform {system}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audit", required=True, type=Path)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--cwd", required=True, type=Path)
    parser.add_argument("--write", action="append", default=[])
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        print("AUDIT EXEC REJECTED: empty command", file=sys.stderr)
        return 2
    try:
        manifest = load_json(args.manifest)
        wrapped, resolved_executable = sandboxed_command(
            command, manifest, args.cwd.resolve()
        )
        entry = {
            "timestamp": utc_now(),
            "phase_sequence": max(
                (int(phase.get("sequence", 0)) for phase in manifest.get("phases", [])),
                default=0,
            ),
            "task_id": str(manifest["task"]["id"]),
            "argv": command,
            "resolved_executable": resolved_executable,
            "cwd": str(args.cwd.resolve()),
            "writes": [str(Path(path).resolve()) for path in args.write],
            "exit_code": None,
            "sandbox": platform.system().lower(),
        }
        args.audit.parent.mkdir(parents=True, exist_ok=True)
        existing = args.audit.read_text(encoding="utf-8") if args.audit.exists() else ""
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(existing)
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
            candidate = Path(handle.name)
        try:
            validate_command_audit(
                candidate, manifest, ROOT / "schema" / "command-policy.json"
            )
        finally:
            candidate.unlink(missing_ok=True)
        proc = subprocess.run(wrapped, check=False)
        entry["exit_code"] = proc.returncode
        with args.audit.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
        print(
            f"AUDIT EXEC RECORDED exit={proc.returncode} command={command[0]}",
            file=sys.stderr,
        )
        return proc.returncode
    except (ContractError, OSError, ValueError, KeyError) as exc:
        print(f"AUDIT EXEC REJECTED: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
