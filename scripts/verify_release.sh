#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE=""
SHA=""
while (($#)); do
  case "$1" in
    --mode) MODE="$2"; shift 2 ;;
    --sha) SHA="$2"; shift 2 ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
if [[ "$MODE" != "pre-push" && "$MODE" != "ci" ]]; then
  echo "--mode must be pre-push or ci" >&2
  exit 2
fi
if [[ -z "$SHA" ]]; then
  SHA="$(git -C "$ROOT" rev-parse HEAD)"
fi
if [[ ! "$SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "release SHA must be full lowercase 40-hex" >&2
  exit 2
fi
HEAD_SHA="$(git -C "$ROOT" rev-parse HEAD)"
if [[ "$HEAD_SHA" != "$SHA" ]]; then
  echo "release SHA mismatch: $SHA != $HEAD_SHA" >&2
  exit 2
fi
if [[ -n "$(git -C "$ROOT" status --short --untracked-files=no)" ]]; then
  echo "release tree is dirty" >&2
  exit 2
fi
python3 -m py_compile "$ROOT"/scripts/*.py
black --check "$ROOT/scripts"
git -C "$ROOT" diff --check
python3 "$ROOT/scripts/generate_template.py" --check
SCRATCH="$(mktemp -d "${TMPDIR:-/tmp}/critic-release-preflight.XXXXXX")"
trap 'rm -rf "$SCRATCH"' EXIT
python3 "$ROOT/scripts/reviewctl.py" preflight \
  --bundle "$ROOT" \
  --scratch-root "$SCRATCH/work" \
  --receipt "$SCRATCH/preflight.json"
bash "$ROOT/scripts/selftest.sh"
python3 - "$ROOT" <<'PY'
from pathlib import Path
import sys
sys.path.insert(0, str(Path(sys.argv[1]) / 'scripts'))
from contract import validate_release_lock
root=Path(sys.argv[1])
lock=validate_release_lock(root/'references'/'release-lock.md', root/'references'/'output-template.md')
print(f"RELEASE LOCK OK version={lock['release']} dependencies={len(lock['dependencies'])}")
PY
RECEIPT="${TMPDIR:-/tmp}/codimango-review-critic-release-receipt.json"
TIMESTAMP="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
TREE="$(git -C "$ROOT" rev-parse HEAD^{tree})"
printf '{\n  "check": "release-gates",\n  "mode": "%s",\n  "sha": "%s",\n  "tree": "%s",\n  "tree_state": "clean",\n  "timestamp": "%s",\n  "verdict": "PASS"\n}\n' "$MODE" "$SHA" "$TREE" "$TIMESTAMP" > "$RECEIPT"
echo "RELEASE GATES OK mode=$MODE sha=$SHA receipt=$RECEIPT"
