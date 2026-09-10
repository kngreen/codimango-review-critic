#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 -m py_compile "$ROOT"/scripts/*.py

cat >"$TMP/good.md" <<'EOF'
### Quality Review Agent
- **Verdict:** Accept
- **Counts:** Critical 0 | High 0 | Medium 0 | Low 0
- **Reviewer Agrees?:** Agree
- **Notes:** No finding.

### Contamination Review Agent
- **Risk Level:** NOT VERIFIED
- **Reviewer Agrees?:** Agree
- **Notes:** NOT VERIFIED: service unavailable.

### Novelty Review Agent
- **Risk Level:** NOT VERIFIED
- **Reviewer Agrees?:** Partially
- **Notes:** NOT VERIFIED: no public-source result.

### Agentic Full-Task Review (MM)
- **Reviewer Agrees?:** Partially
- **Notes:** The review captures the functional core but misses one grading-fairness issue.

### TBR Review Agreement
- **Reviewer Agrees?:** Agree
- **Disagreed Checks:** none
- **Notes:** No finding.

### Human Checks
- **Realistic Scenario?:** 3
- **Realistic Scenario Notes:** The task models realistic maintenance work.
- **Domain Expertise?:** 2
- **Domain Expertise Notes:** It requires framework knowledge beyond general coding.
- **Original?:** 3
- **Original Notes:** The combination is task-specific despite familiar primitives.
- **Primary Language:** Python
- **Other Languages:** None
- **Additional Notes:** None

### Decision
- **Decision:** Accept
- **Reason:** No current blocker remains and the verified grader accepts the intended behavior.
- **Follow-up needed?:** No

### Other Notes
- **Notes:** Strengths: coherent task. To fix: None. To notice: unavailable public-source lookup.

### Reviewer Confidence
- **Confidence (1-5):** 4 - Exact task files and trials were available.
EOF

cat >"$TMP/bad.md" <<'EOF'
### Decision
- **Decision:** Accept
- **Reason:** Looks good.
- **Follow-up needed?:** No
EOF

printf 'canonical output\n' >"$TMP/canonical.md"
printf 'trial and spec output\n' >"$TMP/supplemental.md"

python3 - "$TMP" <<'PY'
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
receipt = {
    "task_id": "selftest",
    "task_sha": "0123456789abcdef0123456789abcdef01234567",
    "track": "swe-bench-pro",
    "variant": "swe_bench_single_turn",
    "primary_runner": "aai-review-flow",
    "primary_status": "completed",
    "primary_session_id": "canonical-session",
    "primary_skill_revision": "revision-a",
    "primary_output_path": str(root / "canonical.md"),
    "fallback_runner": None,
    "fallback_status": "not_needed",
    "fallback_reason": None,
    "supplemental_runner": "review-trials-and-spec",
    "supplemental_status": "completed",
    "supplemental_session_id": "supplemental-session",
    "supplemental_skill_revision": "revision-b",
    "supplemental_output_path": str(root / "supplemental.md"),
}
(root / "receipt.json").write_text(json.dumps(receipt), encoding="utf-8")
PY

python3 "$ROOT/scripts/validate_canonical_execution.py" \
  --receipt "$TMP/receipt.json" \
  --task-id selftest \
  --task-sha 0123456789abcdef0123456789abcdef01234567
python3 "$ROOT/scripts/lint_final_review.py" "$TMP/good.md"
python3 "$ROOT/scripts/validate_review_schema.py" \
  --template "$ROOT/references/output-template.md" \
  --review "$TMP/good.md" \
  --agentic-required

python3 - "$TMP/good.md" "$TMP/no-agentic.md" <<'PY'
from pathlib import Path
import sys
src = Path(sys.argv[1]).read_text()
start = src.index("### Agentic Full-Task Review (MM)")
end = src.index("### TBR Review Agreement")
Path(sys.argv[2]).write_text(src[:start] + src[end:])
PY

if python3 "$ROOT/scripts/validate_review_schema.py" \
  --template "$ROOT/references/output-template.md" \
  --review "$TMP/no-agentic.md" \
  --agentic-required >/dev/null 2>&1; then
  echo "schema validator accepted a missing required Agentic agreement" >&2
  exit 1
fi

if python3 "$ROOT/scripts/validate_review_schema.py" \
  --template "$ROOT/references/output-template.md" \
  --review "$TMP/bad.md" >/dev/null 2>&1; then
  echo "schema validator accepted an incomplete review" >&2
  exit 1
fi

printf 'Self-test passed\n'
