---
name: codimango-review-critic
description: Evidence-first Codimango review. With no task it dispatches the assigned queue through a preflight canary, then one isolated reviewer per ready task. With a task ID or URL it runs the sealed single-task review protocol.
---

# Codimango Review Critic

Review the task, then review the reviewer. This skill is a protocol around the canonical reviewers, not a replacement for them.

## Invocation modes

### No task identifier: dispatcher

The dispatcher enumerates assignments but never reviews a task itself.

1. Attach the authenticated Codimango devserver. Never request or copy a credential.
2. Run:

   ```bash
   export no_proxy="${no_proxy:-},.internalmeta.com"
   codimango task list --reviewing --status being_reviewed \
     --sort updated-at --dir asc --compact --json
   ```

3. Select only rows where `currentUserIsReviewer` is true, `status` is
   `being_reviewed`, and `validationStatus` is neither missing nor `pending`.
   Preserve each row's numeric `id` and `name` directly from JSON. Never
   hand-transcribe or infer an ID.
4. Before dispatching reviews, start one fresh **CANARY ONLY** session for the
   first selected task. Pass only its numeric ID, this skill, and the canary
   instruction below. The canary also checks the plugin-only supplemental and
   iOS lanes using `agentcloudctl spawn -s "$AGENTCLOUD_SESSION_ID"
   --harness claude-code --node <attached-node-id>`; do not use the generic
   subagent launcher and never let those children choose a fresh host. The iOS
   child must use the message-initial slash command because that skill disables
   model invocation. Wait for `CANARY READY`. If it does
   not arrive, stop; do not fan out a shared packaging, authentication,
   sandbox, or plugin-routing failure.
5. After the canary passes, start one fresh root session per task, passing only
   that task's numeric ID and this skill. Never pass a queue row or sibling
   identifier into a reviewer.
6. Hide worker traffic with an explicit duration, for example
   `meta agentcloud.ui snooze --session-id=<id> --duration=8h`.
7. Report each validated verdict as it settles. Never submit the review.

Create sessions with `agentcloudctl create --skill codimango-review-critic:always`.
The canary prompt is:

```text
CANARY ONLY for task TASK_ID. Attach the authenticated Codimango devserver.
Run sealed preflight and bootstrap, then use audit_exec.py for exactly one
`codimango task show TASK_ID --json` read. Use `agentcloudctl spawn` twice with
`-s "$AGENTCLOUD_SESSION_ID" --harness claude-code --node <attached-node-id>`;
do not use the generic subagent launcher. In the first child, use the Skill tool
to load `review-trials-and-spec:review-trials-and-spec`. The second child's
first input must be `/team-aai:aai-ios help`; do not run a review. Never
provision or choose a fresh child host for either plugin check. Return
`CANARY READY: TASK_ID` only if bundle integrity, registry materialization,
authentication, the OS sandbox, and both plugin checks pass. Read no review
prose and perform no review.
```

A normal reviewer prompt names exactly one numeric task ID, requires the
complete workflow below, keeps the repository read-only, and submits nothing.
The task link shown to the user is
`https://codimango.internalmeta.com/reviews/<TASK-ID>`.

### `CANARY ONLY` with one task identifier

Run Phase 0 and bootstrap in an empty scratch root, then run exactly one audited
`codimango task show TASK_ID --json`. Run both plugin checks through
`agentcloudctl spawn -s "$AGENTCLOUD_SESSION_ID" --harness claude-code --node
<attached-node-id>`; the generic subagent launcher does not inherit the same
plugin set. In the first child, load
`review-trials-and-spec:review-trials-and-spec` with the Skill tool but do not
run it. The second child's first input must be `/team-aai:aai-ios help`; the
skill intentionally disables model invocation. Never use a fresh child host for
either check. Read no comments, reviews, trials, or repository content. Return
`CANARY READY: TASK_ID` only after the task read and both plugin checks exit
successfully; otherwise return the exact failing gate.

### One task identifier: reviewer

Review exactly that task. Never enumerate the queue or read another task.

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

The complete released bundle is required; either a clean Git checkout or a content-addressed Skills SDK materialization is valid. `SKILL.md` alone is not sufficient. Outputs live outside both the skill bundle and the task checkout:

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

Required output includes `PREFLIGHT OK`, the verified sandbox backend, and `REVIEW BOOTSTRAPPED`. Do not read task data first. Run every subsequent shell/CLI command through `scripts/audit_exec.py`; it prevalidates the command, executes it with the filesystem read-only except for scratch and the task repository explicitly bound read-only, disables network for arbitrary interpreters/shells, and records the result. Linux prefers a transient hardened systemd user service and falls back to user namespaces; macOS uses `sandbox-exec`. A host that cannot pass the actual write-blocking probe fails closed.

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

Create the critic session as a child of the dispatcher. Then create a distinct canonical child of the critic.

The primary `aai-review-flow` runner is a Skills SDK skill and may use a native child. The track fallbacks and add-ons are Agent Marketplace plugins. Create those children with `agentcloudctl spawn -s "$AGENTCLOUD_SESSION_ID" --harness claude-code --node <attached-node-id>` from the critic; do not use the generic subagent launcher, which does not inherit the same plugin set, and never select a fresh host. Invoke their Skill tool names there. The durable journal may record either a bare alias or a plugin-qualified alias, and the adapter verifies both forms.

1. Primary: `aai-review-flow` with its full file set and immutable revision.
2. Only if primary fails before a nonempty handoff, run the exact track fallback:

| Task kind | Fallback |
|---|---|
| T-Bench single-turn | `team-aai:review-task-tbench-v2` |
| SWE-Bench single-turn | `team-aai:review-task-swebench-v2` |
| T-Bench multi-turn | `team-aai:review-task-tbench-multiturn` |
| SWE-Bench multi-turn | `team-aai:review-task-swebench-multiturn` |
| Long Horizon | matching v2 fallback **and** `aai-long-horizon:lh-review-task` |

Run `review-trials-and-spec:review-trials-and-spec` in another distinct `claude_code` child for every task. For iOS, create a distinct `claude_code` child whose first input is the slash command `/team-aai:aai-ios review` followed by the task brief; apply `references/ios-harness-gate.md`. The aai-ios skill intentionally disables model invocation, so a later model-issued Skill call is the wrong path. For Long Horizon, invoke `aai-long-horizon:lh-review-task` in its own plugin child. A missing Skills SDK alias is not evidence that these plugin skills are unavailable.

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
python3 scripts/agentcloud_adapter.py \
  --session-id "$CANONICAL_SESSION_ID" --run "$CANONICAL_RUN" \
  --expected-role canonical_primary \
  --output "$SCRATCH/canonical-run.json"
python3 scripts/run_review.py record-run \
  --manifest "$SCRATCH/run-manifest.json" \
  --run-record "$SCRATCH/canonical-run.json"
```

Repeat this for supplemental and required add-ons. If a reviewer returns a controlled failure before a handoff, emit the same receipt with `--status failed` and no `--output-path`; if the Agentcloud run itself fails, the adapter derives failure from that exact run's terminal event. `scripts/process_adapter.py` deliberately rejects; it cannot prove session isolation.

If the supplemental runner remains unavailable after both its native alias and installed Claude Code plugin are attempted, emit an `unavailable` supplemental receipt, put the exact reason in `evidence-ledger.json.unresolved`, and set `evidence-ledger.json.supplemental` to the matching unavailable state with no descriptor. Continue without universal trial/spec claims and lower confidence. This exception applies only to the supplemental lane. A required iOS or Long Horizon add-on remains blocking when unavailable.

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

Create `findings.json` using `references/schema-findings.md`. Every row contains:

- stable ID and concise finding;
- internal status: `CONFIRMED`, `OVERSTATED`, `WRONG`, or `NOT VERIFIED`;
- independent evidence list;
- attribution;
- current severity and a `blocking` boolean; Critical/High findings are always blocking;
- what the canonical reviewer contributed;
- observable close condition, which must appear verbatim in the Decision reason for every blocker.

Create `evidence-ledger.json` using `references/schema-evidence-ledger.md`. It must contain:

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
python3 scripts/agentcloud_adapter.py \
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
