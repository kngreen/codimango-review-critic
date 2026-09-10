# codimango-review-critic

Evidence-first, task-isolated review of Codimango T-Bench, SWE-Bench, multi-turn, Long Horizon, and iOS tasks.

The skill wraps canonical task reviewers in an executable protocol: sealed preflight, exact-revision binding, distinct reviewer sessions, complete evidence ledgers, conditional live-form fields, strict final validation, and byte-identical publication.

Certified publication in `v0.2.1` requires an Agentcloud session and `agentcloudctl`, because run ownership and final approval are verified against the durable control-plane journal. Standalone process-only use may inspect the protocol but fails closed as `isolation_unverified`; it is not paste-ready.

## Install a pinned release

### Claude Code

```bash
mkdir -p ~/.claude/skills
git clone --branch v0.2.1 \
  https://github.com/kngreen/codimango-review-critic.git \
  ~/.claude/skills/codimango-review-critic
```

### Codex

```bash
mkdir -p ~/.codex/skills
git clone --branch v0.2.1 \
  https://github.com/kngreen/codimango-review-critic.git \
  ~/.codex/skills/codimango-review-critic
```

Start a fresh agent session for every distinct task, then invoke:

```text
/codimango-review-critic https://codimango.internalmeta.com/reviews/TASK_ID
```

## Prerequisites

Pinned compatibility lives in [`RELEASE.lock`](RELEASE.lock):

- authenticated Agentcloud/`agentcloudctl` control plane and Codimango CLI;
- `aai-review-flow`;
- the track-specific `team-aai` reviewer and `aai-long-horizon` add-on where applicable;
- `review-trials-and-spec`;
- `aai-ios` and native macOS/Xcode infrastructure for iOS tasks.

Unknown or unpinned dependencies block the release gate.

## Protocol overview

1. Run bundle preflight before reading task data.
2. Bootstrap a fresh scratch root and task-only manifest.
3. Freeze identity metadata without reading review prose.
4. Run a distinct canonical child and a distinct supplemental child.
5. Seal the blind pass, then fetch same-task review history.
6. Resolve Agentic, Validation Override, and iOS conditions.
7. Produce structured findings, evidence, review data, and command audit.
8. Render the preferred Markdown and live-form payload.
9. Finalize through the exact bundled validators.
10. Publish only critic-approved, hash-identical bytes.

See [`SKILL.md`](SKILL.md) for commands and [`references/looping-prompt.md`](references/looping-prompt.md) for the standalone prompt.

## Repository layout

```text
.github/workflows/contract.yml
RELEASE.lock
SKILL.md
README.md
docs/
  closing-report-template.md
registry/skill.json
references/
  ios-harness-gate.md
  looping-prompt.md
  output-template.md
schema/
  bundle-lock.json
  command-policy.json
  conditions.json
  evidence-ledger.json
  findings.json
  live-form-payload.json
  review-data.json
  review-format.json
  run-manifest-v2.json
  supplemental-output.json
scripts/
  adapters/
    agentcloud.py
    process.py
  agentcloud_attestation.py
  audit_exec.py
  compact_supplemental.py
  contract.py
  contract_test.py
  emit_run_receipt.py
  finalize_review.py
  generate_template.py
  lint_final_review.py
  materialize_fixtures.py
  publish_verified.py
  render_live_payload.py
  render_review.py
  resolve_conditions.py
  reviewctl.py
  run_review.py
  selftest.sh
  validate_canonical_execution.py
  validate_command_audit.py
  validate_internal_evidence.py
  validate_review_schema.py
  verify_release.sh
tests/
  baseline/d790666/
  fixtures/
```

`schema/review-format.json` is the single source of truth for the preferred form. `references/output-template.md` is generated from it. `scripts/contract.py` is the single implementation of validation policy; compatibility commands are thin wrappers.

## Preflight

Before the first task read:

```bash
SCRATCH="$(mktemp -d /tmp/codimango-review-XXXXXX)"
python3 scripts/reviewctl.py preflight \
  --bundle . \
  --scratch-root "$SCRATCH" \
  --receipt "$SCRATCH/preflight.json"
```

Expected output starts with `PREFLIGHT OK`. A dirty/tampered bundle, missing runtime file, nonempty scratch root, or scratch root inside the bundle fails closed.

## Final validation

The critic calls one finalizer after recording the final files and `finalized` phase:

```bash
python3 scripts/finalize_review.py \
  --manifest "$SCRATCH/run-manifest.json" \
  --conditions "$SCRATCH/conditions.json" \
  --review "$SCRATCH/final-review.md" \
  --live-payload "$SCRATCH/live-form-payload.json" \
  --review-data "$SCRATCH/review-data.json" \
  --findings "$SCRATCH/findings.json" \
  --ledger "$SCRATCH/evidence-ledger.json" \
  --evidence "$SCRATCH/internal-evidence.md" \
  --command-audit "$SCRATCH/command-audit.jsonl" \
  --approval "$SCRATCH/approval.json"
```

Only `FINALIZATION OK` from the attested critic session authorizes publication. The parent must use `publish_verified.py` with `--critic-session-id` and `--run`; the publisher verifies the approval, manifest, and review hashes against the critic's durable `FINALIZATION_RECEIPT` tool-result event. It cannot edit or regenerate child bytes.

## Test and release gates

```bash
bash scripts/selftest.sh
```

The suite runs 93 directional cases across all eight implementation items, including wrong-track fallback, duplicate sessions, blind/history inversion, conditional omission, native iOS evidence, template drift, exact-700-word rejection, semantic decision contradictions, foreign identifiers, phase-aware read-only violations, and bounded supplemental output.

After committing, run:

```bash
bash scripts/verify_release.sh --mode pre-push --sha "$(git rev-parse HEAD)"
```

Expected output includes `RELEASE GATES OK`. CI runs the same gate against the pushed SHA. A receipt timestamped before the commit does not certify it.

## Updating

Update only to an intentional release tag:

```bash
git -C ~/.claude/skills/codimango-review-critic fetch --tags
git -C ~/.claude/skills/codimango-review-critic checkout v0.2.1
```

Do not track mutable `main` for review-critical execution.

## Registry metadata

[`registry/skill.json`](registry/skill.json) describes the same pinned release for Agentcloud/Metamate registration. GitHub publication and registry publication are separate operations; verify the registry copy against `schema/bundle-lock.json` before enabling it.

## Safety

The skill is read-only by default. It does not submit feedback, rerun platform validation, modify task repositories, push task code, or contact authors. `audit_exec.py` prevalidates commands, mounts the task repository read-only in a Linux/macOS OS sandbox, disables network for arbitrary interpreters and shells, and records each command. `validate_command_audit.py` also blocks broad queue reads, pre-seal history reads, and mutation commands.
