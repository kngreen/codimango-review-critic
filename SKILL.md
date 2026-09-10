---
name: codimango-review-critic
description: Evidence-first, task-isolated Codimango review for T-Bench, SWE-Bench, multi-turn, Long Horizon, and iOS. Uses a sealed blind pass, canonical and supplemental child sessions, exact-revision evidence, structured ledgers, conditional live-form fields, and verify-only publication.
---

# Codimango Review Critic

Review the task, then review the reviewer. This skill is a protocol around the canonical reviewers, not a replacement for them.

## Non-negotiable rules

1. One task per fresh Agentcloud critic session. Never enumerate a queue inside the critic. Unattested process-only mode fails closed as `isolation_unverified`.
2. The dispatcher passes only the task identifier, this sealed skill bundle, and an empty scratch root.
3. Keep task and platform state read-only. Do not submit feedback, rerun platform validation, edit the task repository, push, or contact anyone.
4. Run the bundled preflight before the first task read. If preflight fails, stop.
5. Bind all evidence to one task ID and exact validation SHA. Mixed-SHA evidence is rejected unless explicitly classified as prior-revision history.
6. Complete and seal the blind current-state pass before fetching human or bot review bodies.
7. The critic, canonical decision runner, supplemental reviewer, and applicable iOS/Long-Horizon add-ons use distinct sessions and workspaces.
8. The parent may verify and copy approved bytes only. It must never rewrite review, evidence, findings, ledgers, receipt, or approval files.
9. Missing evidence is `NOT VERIFIED`, never pass.
10. Never emit `CONFIRMED` in author-facing prose. State verified facts directly.
11. Final output is under 700 words by both lexical and raw-whitespace counts, with no `#thanks`, AI-process narration, batch comparison, or em dash.
12. A run is not paste-ready without the critic-owned approval receipt from `scripts/finalize_review.py`.

## Runtime files and scratch layout

The complete repository is required. `SKILL.md` alone is not sufficient. Outputs live outside both the skill repository and the task checkout:

```text
$SCRATCH/
  preflight.json
  run-manifest.json
  command-audit.jsonl
  blind-review.md
  conditions.json
  review-data.json
  findings.json
  evidence-ledger.json
  internal-evidence.md
  final-review.md
  live-form-payload.json
  approval.json
```

## Phase 0: sealed preflight before task access

Start with an empty scratch directory inside the critic's attested Agentcloud workspace and outside both the sealed skill bundle and task repository. Child reviewer outputs stay inside each child's own attested workspace; only their run-record JSON is copied into critic scratch. Then run:

```bash
python3 scripts/reviewctl.py preflight \
  --bundle . \
  --scratch-root "$SCRATCH" \
  --receipt "$SCRATCH/preflight.json"

python3 scripts/run_review.py bootstrap \
  --bundle . \
  --scratch-root "$SCRATCH" \
  --preflight-receipt "$SCRATCH/preflight.json" \
  --manifest "$SCRATCH/run-manifest.json" \
  --dispatcher-session-id "$DISPATCHER_SESSION_ID" \
  --task-id "$TASK_ID"
```

Required output includes `PREFLIGHT OK` and `REVIEW BOOTSTRAPPED`. Do not read task data first. Run every subsequent shell/CLI command through `scripts/audit_exec.py`; it prevalidates the command, executes it in an OS sandbox with the task repository mounted read-only, disables network for arbitrary interpreters/shells, and records the result. A host without the required Linux or macOS sandbox fails closed.

## Phase 1: freeze identity without review prose

Use only identity/job metadata until the blind pass is sealed. Do not fetch `task comments`, `task reviews --full`, Agentic report prose, TBR prose, or other verdict bodies yet. The first task read is audited, for example:

```bash
python3 scripts/audit_exec.py \
  --audit "$SCRATCH/command-audit.jsonl" \
  --manifest "$SCRATCH/run-manifest.json" \
  --cwd "$SCRATCH" -- \
  codimango task show "$TASK_ID" --json
```

At minimum, resolve:

- task ID, name, repository, track, variant;
- task HEAD, validation SHA, review-job SHA, inspected SHA;
- current job/trial identifiers and server totals;
- task-repository root, if a checkout exists.

Then run:

```bash
python3 scripts/run_review.py freeze-identity \
  --manifest "$SCRATCH/run-manifest.json" \
  --repo "$REPO" --track "$TRACK" --variant "$VARIANT" \
  --head-sha "$HEAD_SHA" --validation-sha "$VALIDATION_SHA" \
  --review-job-sha "$REVIEW_JOB_SHA" --inspected-sha "$INSPECTED_SHA" \
  --task-repo-root "$TASK_REPO_ROOT" \
  --allow-path tests --allow-path README.md \
  --allow-identifier "$JOB_ID" --allow-identifier "$TRIAL_ID"
```

Record every additional current-task identifier or path needed by final prose in the frozen context manifest. Unknown identifiers are rejected later.

## Phase 2: blind current-state pass

Begin the blind phase before spawning any reviewer:

```bash
python3 scripts/run_review.py phase --manifest "$SCRATCH/run-manifest.json" --name blind_started
```

Create the critic session as a child of the dispatcher. Then create a distinct canonical child of the critic:

Each canonical/supplemental/add-on child must load its named pinned skill through the platform skill loader before doing work; the adapter verifies the successful Skill intent/result in that child's durable journal.

1. Primary: `aai-review-flow` with its full file set and immutable revision.
2. Only if primary fails before a nonempty handoff, run the exact track fallback:

| Task kind | Fallback |
|---|---|
| T-Bench single-turn | `team-aai:review-task-tbench-v2` |
| SWE-Bench single-turn | `team-aai:review-task-swebench-v2` |
| T-Bench multi-turn | `team-aai:review-task-tbench-multiturn` |
| SWE-Bench multi-turn | `team-aai:review-task-swebench-multiturn` |
| Long Horizon | matching v2 fallback **and** `aai-long-horizon:lh-review-task` |

Run `review-trials-and-spec` in another distinct child for every task. For iOS, also run `aai-ios` in a distinct child and apply `references/ios-harness-gate.md`.

Record each child from its durable Agentcloud journal. In the child, emit a receipt as the final tool command after its output is complete:

```bash
python3 scripts/emit_run_receipt.py \
  --role canonical_primary --runner aai-review-flow \
  --task-id "$TASK_ID" --task-sha "$VALIDATION_SHA" \
  --skill-revision "$PINNED_SKILL_REVISION" \
  --output-path "$SCRATCH_CHILD/canonical-output.md"
```

Then, from the critic, derive the run record from control-plane metadata rather than caller assertions:

```bash
python3 scripts/adapters/agentcloud.py \
  --session-id "$CANONICAL_SESSION_ID" --run "$CANONICAL_RUN" \
  --expected-role canonical_primary \
  --output "$SCRATCH/canonical-run.json"
python3 scripts/run_review.py record-run \
  --manifest "$SCRATCH/run-manifest.json" \
  --run-record "$SCRATCH/canonical-run.json"
```

Repeat this for supplemental and required add-ons. If a reviewer returns a controlled failure before a handoff, emit the same receipt with `--status failed` and no `--output-path`; if the Agentcloud run itself fails, the adapter derives failure from that exact run's terminal event. `scripts/adapters/process.py` deliberately rejects; it cannot prove session isolation.

Seal the blind pass only after every blind reviewer and required add-on has finished:

```bash
python3 scripts/run_review.py phase --manifest "$SCRATCH/run-manifest.json" \
  --name blind_sealed --artifact "$SCRATCH/blind-review.md"
```

A successful primary forbids a fallback. A failed primary must have no output claim. A Long Horizon add-on alone is not a canonical decision runner.

## Phase 3: same-task history after the seal

Only now run:

```bash
python3 scripts/run_review.py phase --manifest "$SCRATCH/run-manifest.json" --name history_started
```

Fetch every human review body and relevant bot review for this task, with pagination to completion. Every review row records `task_id`, `scope` (`current` or `prior`), SHA, body hash, and all finding IDs. Record history completeness even when empty:

```json
{"history": {"complete": true, "count": 0, "review_ids": []}, "prior_findings": []}
```

Replay every prior Critical/High counterexample when feasible. Then record `history_complete`.

## Phase 4: evidence and finding ledgers

Create `findings.json` using `schema/findings.json`. Every row contains:

- stable ID and concise finding;
- internal status: `CONFIRMED`, `OVERSTATED`, `WRONG`, or `NOT VERIFIED`;
- independent evidence list;
- attribution;
- current severity and a `blocking` boolean; Critical/High findings are always blocking;
- what the canonical reviewer contributed;
- observable close condition, which must appear verbatim in the Decision reason for every blocker.

Create `evidence-ledger.json` using `schema/evidence-ledger.json`. It must contain:

- complete paginated job, trial, and review inventories;
- task ID, scope (`current` or `prior`), source SHA, model/runtime, reward, status, artifact availability, and exclusion reason for every job/trial;
- each trial's parent job and absolute artifact paths, with no orphan trial;
- all six named baselines: `prior_revision`, `no_solution`, `model_floor`, `hot_vs_cold`, `with_vs_without_skill`, and `shortcut`;
- prior-finding ledger, explicit dispositions for every current/supplemental finding not carried into `findings.json`, and unresolved evidence;
- native iOS evidence when required;
- bounded supplemental descriptor whose ledger repeats task ID/SHA and finding IDs.

Do not compute solve rates until oracle, review, cancelled, errored, and infrastructure-only trials are classified and excluded.

## Phase 5: live conditions

Freeze raw condition metadata, including Agentic state/artifact paths, Validation Override reasons, and iOS signal. Resolve it:

```bash
python3 scripts/resolve_conditions.py \
  "$SCRATCH/condition-metadata.json" \
  --output "$SCRATCH/conditions.json"
python3 scripts/run_review.py set-conditions \
  --manifest "$SCRATCH/run-manifest.json" \
  --conditions "$SCRATCH/conditions.json"
```

Rules:

- Agentic `completed` with a body: section required.
- Agentic `parse_error`: record a complete machine-readable job -> trial -> artifact traversal with one job ID, unique trial IDs, and unique absolute artifact paths plus SHA-256. Every path must be readable and appear in the evidence-ledger trial inventory. Any nonempty recovered artifact makes the section required; a missing/mismatched artifact or incomplete traversal is `unresolved` and blocks delivery.
- Validation Override reasons: section required.
- iOS signal: native iOS evidence required.
- Taxonomy is not part of the current live review form and must not be emitted.

## Phase 6: render from structured data

Write `review-data.json`; do not hand-format the final Markdown. Render both preferred Markdown and live payload:

```bash
python3 scripts/render_review.py \
  --data "$SCRATCH/review-data.json" \
  --findings "$SCRATCH/findings.json" \
  --conditions "$SCRATCH/conditions.json" \
  --output "$SCRATCH/final-review.md"

python3 scripts/render_live_payload.py \
  --data "$SCRATCH/review-data.json" \
  --findings "$SCRATCH/findings.json" \
  --conditions "$SCRATCH/conditions.json" \
  --output "$SCRATCH/live-form-payload.json"
```

The preferred form has eight base sections. Agentic appears after Novelty; Validation Override appears after TBR, only when frozen conditions require them. Human scores always have task-specific rationales. Decision reason includes canonical severity counts and close conditions. Other Notes preserves unavailable evidence.

## Phase 7: final validation and approval

Record the final files in the manifest, emit and record the running critic's own journal receipt, append the `finalized` phase, then run the exact bundled finalizer:

```bash
python3 scripts/emit_run_receipt.py \
  --role critic --runner codimango-review-critic \
  --task-id "$TASK_ID" --task-sha "$VALIDATION_SHA" \
  --skill-revision "$CRITIC_BUNDLE_COMMIT" \
  --output-path "$SCRATCH/internal-evidence.md"
python3 scripts/adapters/agentcloud.py \
  --session-id "$CRITIC_SESSION_ID" --run "$CRITIC_RUN" \
  --expected-role critic --allow-running-critic \
  --output "$SCRATCH/critic-run.json"
python3 scripts/run_review.py record-run \
  --manifest "$SCRATCH/run-manifest.json" \
  --run-record "$SCRATCH/critic-run.json"

python3 scripts/run_review.py set-final \
  --manifest "$SCRATCH/run-manifest.json" \
  --critic-session-id "$CRITIC_SESSION_ID" \
  --review "$SCRATCH/final-review.md" \
  --live-payload "$SCRATCH/live-form-payload.json" \
  --evidence "$SCRATCH/internal-evidence.md" \
  --findings "$SCRATCH/findings.json" \
  --ledger "$SCRATCH/evidence-ledger.json" \
  --command-audit "$SCRATCH/command-audit.jsonl"
python3 scripts/run_review.py phase \
  --manifest "$SCRATCH/run-manifest.json" \
  --name finalized

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

The finalizer validates:

- sealed-bundle identity plus live Agentcloud journal attestation for critic and every child run;
- phase order and sealed blind artifact;
- complete evidence/findings ledgers;
- frozen conditions loaded only from the manifest, plus conditional Markdown sections;
- the live payload against the pinned lowercase decision enums and nested `overrideReview` shape;
- exact generated template and complete Markdown consumption;
- counts and decision consistency;
- lexical and whitespace word counts, both strictly below 700;
- current-task identifier/path manifest;
- task-scoped read-only command audit.

If it fails, return the machine error to the same isolated critic. The parent does not edit files.

## Phase 8: verify-only publication

The parent publishes exact approved bytes only:

```bash
python3 scripts/publish_verified.py \
  --approval "$SCRATCH/approval.json" \
  --critic-session-id "$CRITIC_SESSION_ID" \
  --run "$CRITIC_RUN" \
  --name review \
  --source "$SCRATCH/final-review.md" \
  --destination "$PUBLISH_STAGING/final-review.md"
```

The approval SHA, manifest SHA, review SHA, and live-payload SHA must be present in the critic's durable `FINALIZATION_RECEIPT` tool-result event, and any staged/uploaded bytes must match their approved hashes. A caller-authored approval JSON without that journal event is rejected. Do not claim paste-ready without `FINALIZATION OK` and `PUBLISH VERIFIED`.

## Decision and language policy

Use one operational decision: Accept, Request changes, or Reject. The Quality verdict may differ from the operational decision only when `findings.json.decision_reconciliation` explains the independently verified reason.

Severity priority: reward integrity/training value, spec-test fairness, reproducibility, task quality, cosmetics. Confidence measures evidence coverage.

Author-facing output never mentions other tasks, batches, prior review rounds, reviewer learning, or verification process. It contains no `CONFIRMED`, `#thanks`, or em dash. Preserve blockers, missing evidence, and close conditions under compression.

## Failure behavior

If the canonical primary and required fallback both fail, report exactly:

`Canonical review format could not be generated.`

If isolation, phase order, live conditions, evidence completeness, native iOS execution, or publication byte identity cannot be proven, stop without an author-facing review and report the specific machine rejection.

## Same-task follow-up

A new SHA starts a fresh critic session and scratch root. Repeat every phase, fetch history only after the new blind seal, replay prior blockers, rerun whole-task invariants, and generate a new approval receipt. Never reuse a prior task context or parent-edited review.
