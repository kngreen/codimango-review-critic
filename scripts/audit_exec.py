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


PASSTHROUGH_ENV = (
    "AGENTCLOUD_ORCHESTRATOR_URL",
    "ALL_PROXY",
    "CURL_CA_BUNDLE",
    "GIT_CONFIG_GLOBAL",
    "GIT_CONFIG_SYSTEM",
    "HOME",
    "HTTPS_PROXY",
    "HTTP_PROXY",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
    "LOGNAME",
    "NO_PROXY",
    "PATH",
    "REQUESTS_CA_BUNDLE",
    "SHELL",
    "SSL_CERT_DIR",
    "SSL_CERT_FILE",
    "TZ",
    "USER",
    "X509_USER_PROXY",
    "XDG_CONFIG_HOME",
    "XDG_DATA_HOME",
    "http_proxy",
    "https_proxy",
    "no_proxy",
)


def systemd_sandbox(
    command: list[str], task_repo: Path, scratch: Path, cwd: Path
) -> list[str]:
    executable = shutil.which("systemd-run")
    if executable is None:
        raise ContractError("READ-ONLY REJECTED: systemd sandbox unavailable")
    temp_root = scratch / "tmp"
    cache_root = scratch / "cache"
    temp_root.mkdir(parents=True, exist_ok=True)
    cache_root.mkdir(parents=True, exist_ok=True)
    result = [
        executable,
        "--user",
        "--wait",
        "--pipe",
        "--collect",
        "--quiet",
        "--property=ProtectSystem=strict",
        "--property=ProtectHome=read-only",
        "--property=ReadOnlyPaths=/",
        f"--property=ReadWritePaths={scratch}",
        f"--property=BindReadOnlyPaths={task_repo}",
        "--property=ReadOnlyPaths=/dev/shm",
        "--property=NoNewPrivileges=yes",
        "--property=RestrictNamespaces=yes",
        "--property=CapabilityBoundingSet=",
        "--property=PrivateDevices=yes",
        "--property=PrivateIPC=yes",
        "--property=ProtectKernelTunables=yes",
        "--property=ProtectKernelModules=yes",
        "--property=ProtectControlGroups=yes",
        "--property=RestrictSUIDSGID=yes",
        "--property=LockPersonality=yes",
        "--property=UMask=0077",
        f"--working-directory={cwd}",
        f"--setenv=TMPDIR={temp_root}",
        f"--setenv=XDG_CACHE_HOME={cache_root}",
        "--setenv=PYTHONDONTWRITEBYTECODE=1",
    ]
    if Path(command[0]).name in OFFLINE_BINARIES:
        result.append("--property=PrivateNetwork=yes")
    uid = os.getuid()
    for path in (
        Path(f"/run/user/{uid}/bus"),
        Path(f"/run/user/{uid}/systemd/private"),
    ):
        if path.exists():
            result.append(f"--property=InaccessiblePaths={path}")
    for name in PASSTHROUGH_ENV:
        if name in os.environ:
            result.append(f"--setenv={name}")
    result.extend(command)
    return result


def unshare_sandbox(
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


def linux_sandbox(
    command: list[str],
    task_repo: Path,
    scratch: Path,
    cwd: Path,
    backend: str | None = None,
) -> tuple[list[str], str]:
    if backend == "systemd":
        return systemd_sandbox(command, task_repo, scratch, cwd), "systemd"
    if backend == "unshare":
        return unshare_sandbox(command, task_repo, scratch, cwd), "unshare"
    if backend is not None:
        raise ContractError(f"READ-ONLY REJECTED: unknown Linux sandbox {backend}")
    if shutil.which("systemd-run") is not None:
        return systemd_sandbox(command, task_repo, scratch, cwd), "systemd"
    return unshare_sandbox(command, task_repo, scratch, cwd), "unshare"


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


def probe_sandbox() -> str:
    system = platform.system()
    if system == "Linux":
        candidates = []
        if shutil.which("systemd-run") is not None:
            candidates.append("systemd")
        if shutil.which("unshare") is not None:
            candidates.append("unshare")
    elif system == "Darwin":
        candidates = ["sandbox-exec"]
    else:
        raise ContractError(
            f"READ-ONLY REJECTED: unsupported sandbox platform {system}"
        )
    failures = []
    for backend in candidates:
        with tempfile.TemporaryDirectory(prefix="critic-sandbox-probe.") as raw:
            root = Path(raw)
            scratch = root / "scratch"
            task_repo = root / "task-repo"
            outside = root / "outside"
            scratch.mkdir()
            task_repo.mkdir()
            protected = task_repo / "protected"
            protected.write_text("original\n", encoding="utf-8")
            command = [
                "/bin/sh",
                "-c",
                "set -eu; "
                'test "$(cat "$1/protected")" = original; '
                'if printf changed > "$1/protected" 2>/dev/null; then exit 41; fi; '
                'if printf changed > "$3" 2>/dev/null; then exit 42; fi; '
                'printf allowed > "$2/allowed"',
                "sandbox-probe",
                str(task_repo),
                str(scratch),
                str(outside),
            ]
            try:
                if backend == "systemd":
                    wrapped = systemd_sandbox(command, task_repo, scratch, scratch)
                elif backend == "unshare":
                    wrapped = unshare_sandbox(command, task_repo, scratch, scratch)
                else:
                    wrapped = macos_sandbox(command, task_repo, scratch, scratch)
                proc = subprocess.run(
                    wrapped, text=True, capture_output=True, check=False
                )
                if proc.returncode != 0:
                    detail = (proc.stderr or proc.stdout).strip().splitlines()
                    suffix = detail[-1] if detail else f"exit {proc.returncode}"
                    raise ContractError(suffix)
                if (
                    protected.read_text(encoding="utf-8") != "original\n"
                    or outside.exists()
                ):
                    raise ContractError("sandbox allowed an external write")
                if (scratch / "allowed").read_text(encoding="utf-8") != "allowed":
                    raise ContractError("sandbox blocked scratch writes")
                return backend
            except (ContractError, OSError, ValueError) as exc:
                failures.append(f"{backend}: {exc}")
    detail = "; ".join(failures) if failures else "no sandbox backend installed"
    raise ContractError(f"READ-ONLY REJECTED: sandbox probe failed: {detail}")


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
) -> tuple[list[str], str, str]:
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
    receipt_path = manifest.get("bundle", {}).get("preflight_receipt_path")
    sandbox_backend = None
    if receipt_path:
        sandbox_backend = load_json(Path(receipt_path)).get("sandbox_backend")
    if system == "Linux":
        wrapped, backend = linux_sandbox(
            command, task_repo, scratch, cwd, sandbox_backend
        )
        return wrapped, resolved_executable, backend
    if system == "Darwin":
        if sandbox_backend not in (None, "sandbox-exec"):
            raise ContractError(
                f"READ-ONLY REJECTED: preflight selected {sandbox_backend} on macOS"
            )
        return (
            macos_sandbox(command, task_repo, scratch, cwd),
            resolved_executable,
            "sandbox-exec",
        )
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
        wrapped, resolved_executable, sandbox_backend = sandboxed_command(
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
            "sandbox_backend": sandbox_backend,
        }
        args.audit.parent.mkdir(parents=True, exist_ok=True)
        existing = args.audit.read_text(encoding="utf-8") if args.audit.exists() else ""
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False) as handle:
            handle.write(existing)
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
            candidate = Path(handle.name)
        try:
            validate_command_audit(
                candidate, manifest, ROOT / "references" / "command-policy.md"
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
