# codimango-review-critic

Evidence-first, task-isolated review of Codimango T-Bench, SWE-Bench, multi-turn, Long Horizon, and iOS tasks.

The skill wraps canonical task reviewers in an executable protocol: sealed preflight, exact-revision binding, distinct reviewer sessions, complete evidence ledgers, conditional live-form fields, strict final validation, and byte-identical publication.

Certified publication in `v0.2.4` requires an Agentcloud session and `agentcloudctl`, because run ownership and final approval are verified against the durable control-plane journal. Standalone process-only use may inspect the protocol but fails closed as `isolation_unverified`; it is not paste-ready.

## Install a pinned release

### Claude Code

```bash
mkdir -p ~/.claude/skills
git clone --branch v0.2.4 \
  https://github.com/kngreen/codimango-review-critic.git \
  ~/.claude/skills/codimango-review-critic
```

### Codex

```bash
mkdir -p ~/.codex/skills
git clone --branch v0.2.4 \
  https://github.com/kngreen/codimango-review-critic.git \
  ~/.codex/skills/codimango-review-critic
```

Start a fresh agent session for every distinct task, then invoke:

```text
/codimango-review-critic https://codimango.internalmeta.com/reviews/TASK_ID
```

Invoking `/codimango-review-critic` without a task runs the queue dispatcher. It first starts a single preflight-and-auth canary; only a successful canary unlocks parallel review dispatch.

## Prerequisites

Pinned compatibility lives in [`references/release-lock.md`](references/release-lock.md):

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
SKILL.md
references/
  bundle-lock.md
  command-policy.md
  ios-harness-gate.md
  looping-prompt.md
  output-template.md
  release-lock.md
  schema-*.md
scripts/
  *.py
```

That flat runtime layout is deliberate: the Skills SDK represents only
`SKILL.md`, `scripts/<name>.py`, and `references/<name>.md`. Source-only CI,
docs, tests, and shell release helpers remain in the Git repository but are not
part of the registry bundle. `references/schema-review-format.md` is the single
source of truth for the preferred form, and `references/output-template.md` is
generated from it. `scripts/contract.py` is the single implementation of
validation policy.

## Preflight

Before the first task read:

```bash
SCRATCH="$(mktemp -d /tmp/codimango-review-XXXXXX)"
python3 scripts/reviewctl.py preflight \
  --bundle . \
  --scratch-root "$SCRATCH" \
  --receipt "$SCRATCH/preflight.json"
```

Expected output starts with `PREFLIGHT OK` and names the verified sandbox backend. A dirty/tampered bundle, missing runtime file, incomplete registry snapshot, unsupported sandbox, nonempty scratch root, or scratch root inside the bundle fails closed. Registry materializations are content-addressed from the sealed bundle lock and do not require a `.git` directory.

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

The suite runs 96 directional cases across all eight implementation items, including registry materialization without `.git`, plugin-qualified skill attestation, unavailable supplemental evidence, wrong-track fallback, duplicate sessions, blind/history inversion, conditional omission, native iOS evidence, template drift, exact-700-word rejection, semantic decision contradictions, foreign identifiers, phase-aware read-only violations, and bounded supplemental output.

After committing, run:

```bash
bash scripts/verify_release.sh --mode pre-push --sha "$(git rev-parse HEAD)"
```

Expected output includes `RELEASE GATES OK`. CI runs the same gate against the pushed SHA. A receipt timestamped before the commit does not certify it.

## Updating

Update only to an intentional release tag:

```bash
git -C ~/.claude/skills/codimango-review-critic fetch --tags
git -C ~/.claude/skills/codimango-review-critic checkout v0.2.4
```

Do not track mutable `main` for review-critical execution.

## Registry metadata

Build the exact portable file set, then publish that staged directory. Never publish the repository root or a hand-selected subset:

```bash
python3 scripts/build_registry_package.py \
  --bundle=. --output=/tmp/codimango-review-critic-registry
meta --local skills.sdk revise \
  --alias=codimango-review-critic \
  --dir=/tmp/codimango-review-critic-registry \
  --base-revision=REVISION_FROM_SKILLS_SDK_LOAD \
  --revision-title='Release v0.2.4' \
  --output=json
```

Load the resulting revision with `--content --out-dir` and run its bundled
`reviewctl.py preflight`. The package builder and preflight both compare the
materialized file set against `references/bundle-lock.md`, so a four-file or
otherwise truncated registry revision fails before any task read.

## Safety

The skill is read-only by default. It does not submit feedback, rerun platform validation, modify task repositories, push task code, or contact authors. `audit_exec.py` prevalidates commands and uses a transient systemd user service on Linux to make the filesystem read-only except for the review scratch root, bind the task repository read-only, remove capabilities, block namespace escape, and disable networking for arbitrary interpreters and shells. Linux user namespaces and macOS `sandbox-exec` remain fail-closed fallbacks. `validate_command_audit.py` also blocks broad queue reads, pre-seal history reads, and mutation commands.
