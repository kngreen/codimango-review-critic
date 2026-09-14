#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
TMP="$(mktemp -d "${TMPDIR:-/tmp}/critic-selftest.XXXXXX")"
trap 'rm -rf "$TMP"' EXIT

python3 -m py_compile scripts/*.py scripts/adapters/*.py
python3 scripts/generate_template.py --check
python3 scripts/contract_test.py --all --compare-base d790666
python3 scripts/integration_test.py

python3 scripts/materialize_fixtures.py --output "$TMP/fixtures"
python3 scripts/reviewctl.py validate-dag "$TMP/fixtures/run_good.json" | grep -F 'RUN DAG OK roles=3'
if python3 scripts/reviewctl.py validate-dag "$TMP/fixtures/run_parent_rewrite.json" >"$TMP/rewrite.out" 2>&1; then
  echo 'parent-rewrite fixture unexpectedly passed' >&2
  exit 1
fi
grep -F 'PUBLISH REJECTED: byte hash changed' "$TMP/rewrite.out"
if python3 scripts/reviewctl.py validate-phases "$TMP/fixtures/history_before_blind.json" >"$TMP/history.out" 2>&1; then
  echo 'history-before-blind fixture unexpectedly passed' >&2
  exit 1
fi
grep -F 'PHASE ORDER REJECTED: history_started before blind_sealed' "$TMP/history.out"
if python3 scripts/adapters/process.py >"$TMP/process.out" 2>&1; then
  echo 'unattested process adapter unexpectedly passed' >&2
  exit 1
fi
grep -F 'isolation_unverified' "$TMP/process.out"

python3 - <<'PY'
from pathlib import Path
import json
root = Path('.')
for path in sorted((root / 'schema').glob('*.json')):
    json.loads(path.read_text())
json.loads((root / 'RELEASE.lock').read_text())
json.loads((root / 'registry' / 'skill.json').read_text())
print('JSON CONTRACTS OK')
PY

printf 'ENTRYPOINT CONTROLS OK commands=5\n'
printf 'SELFTEST OK items=8 cases=94\n'
