# codimango-review-critic

Evidence-first, task-isolated review of Codimango T-Bench, SWE-Bench, multi-turn, Long Horizon, and iOS tasks.

The skill requires the canonical task reviewer, runs trial/spec analysis separately, verifies findings against the exact task revision, and emits the complete Codimango review form: eight base sections plus the conditional Agentic Full-Task Review agreement whenever that review exists. It fails closed when canonical review execution, task isolation, or form-schema validation cannot be proven.

## Install

### Codex

```bash
git clone https://github.com/kngreen/codimango-review-critic.git \
  ~/.codex/skills/codimango-review-critic
```

### Claude Code

```bash
git clone https://github.com/kngreen/codimango-review-critic.git \
  ~/.claude/skills/codimango-review-critic
```

For another agent, clone the repository into that agent's configured skills directory.

## Prerequisites

- `codimango` CLI authenticated for Nest reads
- `aai-review-flow`
- the `team-aai` canonical track reviewers
- `review-trials-and-spec`
- for iOS tasks, the `aai-ios` reviewer and native macOS/Xcode harness guidance

If the canonical orchestrator and defined track fallback are both unavailable, the skill stops instead of approximating a review.

## Use

Invoke without an argument to run the review queue:

```text
/codimango-review-critic
```

One dispatcher enumerates assigned, ready tasks; launches exactly one fresh root reviewer per task on the authenticated Codimango devserver; waits for those same session IDs; verifies each review and evidence Markdown paste; and returns one table with `Task`, `Decision`, `Findings`, `Review`, `Evidence`, and `Validation`.

A queue run never edits or republishes the skill and never creates duplicate task workers. A shared preflight failure stops the queue before fan-out; an individual worker failure is reported once below the final table.

Invoke with one task URL or identifier to review only that task:

```text
/codimango-review-critic https://codimango.internalmeta.com/reviews/202761?review=ai-assessment
```

Run every distinct task in a fresh agent session. The skill forbids broad review-queue reads inside task workers and fetches same-task history directly from Codimango.

The output includes:

- a private evidence report;
- a canonical execution receipt;
- a task-scoped command audit;
- a paste-ready review containing all eight base Codimango form sections plus the conditional Agentic agreement when available.

Nothing is submitted automatically.

## Repository layout

```text
SKILL.md
references/
  ios-harness-gate.md
  looping-prompt.md
  output-template.md
scripts/
  lint_final_review.py
  validate_canonical_execution.py
  validate_review_schema.py
```

`SKILL.md` is the entry point. The referenced files and scripts must remain beside it; publishing only `SKILL.md` is incomplete.

## Validate before publishing

```bash
bash scripts/selftest.sh
```

The self-test compiles all Python helpers, validates the eight base sections plus a required conditional Agentic agreement, checks a canonical execution receipt, and proves incomplete or misordered forms are rejected.

For an optional Meta Skills SDK structural dry run, use the server-compatible inline file set:

```bash
FILES_JSON="$(python3 - <<'PY'
import json
from pathlib import Path
root = Path('.')
paths = [root / 'SKILL.md', *sorted((root / 'references').glob('*.md')), *sorted((root / 'scripts').glob('*.py'))]
print(json.dumps([{'path': str(path), 'content': path.read_text()} for path in paths]))
PY
)"
meta skills.sdk create --files-json="$FILES_JSON" --visibility='Only Me' --dry-run --output=json
```

That SDK command validates a portable skill file set. It does not publish this GitHub repository.

A real task review is paste-ready only after all three runtime validators pass:

```bash
python3 scripts/validate_canonical_execution.py \
  --receipt /path/to/canonical-execution.json \
  --task-id TASK_ID \
  --task-sha FULL_SHA

python3 scripts/lint_final_review.py /path/to/final-review.md

python3 scripts/validate_review_schema.py \
  --template references/output-template.md \
  --review /path/to/final-review.md \
  --agentic-required
```

Pass `--agentic-required` whenever the reviewed SHA exposes an Agentic Full-Task Review; omit it only when the live form does not show that step.

## Publish in the Codimango GitHub organization

1. Create an empty private repository named `codimango-review-critic` under the `codimango` organization. Do not initialize it with generated files if you are pushing this directory.
2. Ensure your GitHub account, SSH key, or token is authorized for Codimango SSO.
3. From this directory:

```bash
git init -b main
git add SKILL.md README.md references scripts .gitignore
git commit -m "Publish Codimango review critic skill"
git remote add origin \
  org-272075201@github.com:codimango/codimango-review-critic.git
git push -u origin main
```

If `main` is protected, push a branch and open a pull request instead:

```bash
git switch -c publish-skill
git push -u origin publish-skill
```

After the initial publish, protect `main` and require pull requests for updates, matching the `codimango/ripen` contribution model.

If you cannot create or push the repository, add yourself as a contributor through Meta's OSS repository portal, authorize Codimango SSO for your SSH key, and retry.

## Update an installation

```bash
git -C ~/.codex/skills/codimango-review-critic pull --ff-only
```

Use the corresponding path for Claude Code or another agent.

## Optional: publish to the Metamate skill registry too

GitHub publication and Metamate skill publication are separate. To create a private registry entry from the same files:

```bash
meta skills.sdk create --dir=. --visibility='Only Me' --output=json
```

That command publishes to the skills registry. It does not create or update the GitHub repository. Make it `Public` only when you intentionally want registry-wide visibility.
