---
name: codimango-review-critic
description: Evidence-first second-pass review of Codimango T-Bench, SWE-Bench, multi-turn, and Long Horizon tasks. Use after a canonical task reviewer, or when asked to review a review, re-review a revised submission, reconcile prior feedback, or produce paste-ready Codimango feedback under 700 words. Verifies every finding against the exact task revision, reads all prior reviews, checks baselines and omitted surfaces, and preserves open or unverified caveats.
---

# Codimango Review Critic

Review the task, then review the reviewer. This skill is a companion to the canonical track reviewers, not another copy of their rubrics.

## Hard rules

1. Keep the task repository read-only. Do not commit, push, submit feedback, rerun validation, or contact the author.
2. Review exactly one task per fresh agent session or process. Never loop over multiple tasks in one model context. A queue runner must spawn a new isolated reviewer for every task and collect only its final structured result.
3. Before a task review starts, clear all prior task context: conversation transcript, summaries, scratch files, retrieved snippets, trial downloads, repository paths, reviewer findings, examples, and output drafts. The new reviewer receives only this skill, the current task identifier, and explicitly current-task inputs.
4. A task reviewer must never enumerate the review queue or all tasks. With an explicit task ID, use only task-scoped commands (`task show`, `task comments`, `task reviews`, `job list TASK`, and task/job/trial descendants). `task list --reviewing`, `task list --all`, and equivalent broad reads are forbidden inside the child reviewer because their payloads carry other tasks into model context.
5. Queue enumeration belongs only in a parent dispatcher. It may select an identifier but must pass only that one identifier, never the queue row payload, to the fresh child.
6. Same-task history is the only exception. Fetch it fresh from Codimango after the blind current-state pass, using the current task ID. Never pass it in from the preceding review session.
7. If the runtime cannot guarantee a fresh context, stop and report that isolation is not verified. Do not produce an author-facing review.
8. Bind all evidence to one exact task revision. Record task ID, track, variant, task HEAD, validation SHA, review-job SHA, and locally inspected SHA.
9. Never mix review text, tests, trials, or findings from different SHAs without labeling the mismatch internally.
10. Before accepting any evidence, verify that its task ID, repository, SHA, paths, jobs, and trials belong to the current task. Foreign-task evidence is discarded and treated as a context-isolation failure.
11. A review with no baseline cannot call a defect a regression. Mark it pre-existing, newly discovered, or `NOT VERIFIED` internally.
12. Pull and read every previous human review and relevant bot review for this same task before the final verdict. A summary of prior feedback is not a substitute for the review bodies.
13. First complete an independent current-state pass without reading prior verdict prose. Then reconcile same-task history. This reduces anchoring while still making history mandatory.
14. Missing evidence is `NOT VERIFIED`, never pass. Preserve `PARTIAL`, `FAIL`, `NO DATA`, open questions, and unavailable artifacts in the final draft.
15. Every affirmative author-facing statement is independently verified by default. Never prefix or qualify it with `CONFIRMED`, `confirmed`, `independently confirmed`, or similar verification narration. State the fact and evidence directly. Use an explicit status only for `NOT VERIFIED`, partial evidence, uncertainty, or disagreement with an automated assessment.
16. One decision owner: the human reviewer. Other skills produce evidence. Do not average conflicting skill verdicts.
17. Never invent file lines, trial causes, baseline results, or review history.
18. Final author-facing output is under 700 words, contains no `#thanks`, no AI-speak, and no em dashes.
19. Final author-facing output describes only the current task and current state. Never mention batches, relative rank among tasks, previous or earlier reviews, review rounds or iterations, reviewer self-history, or how a finding was discovered. Ban wording such as `best in the batch`, `compared with other tasks`, `in the previous review`, `on the last iteration`, `from my earlier miss`, `I missed`, or equivalents.

## Inputs

Required:

- Codimango task URL, task name, UUID, or review URL.

Optional:

- AI-generated review text to audit.
- A specific review round or prior SHA.
- A follow-up question such as "Do these still stand?"

Derive track, variant, repository, and review history from live task data. Do not ask for facts the task, repository, or Codimango can answer.

## 1. Freeze identity and evidence

Capture the current task metadata and exact validation revision before running reviewers. Use the current Codimango CLI contract, checking `--help` when syntax has changed.

At minimum, read only the explicit task and its descendants:

```bash
codimango task show TASK --json
codimango task comments TASK --json
codimango task reviews TASK --full --limit 100 --json
codimango job list TASK --json
codimango job review TASK --commit FULL_SHA --json
```

Do not call `codimango task list --reviewing`, `task list --all`, or any queue/list command inside a task reviewer. Even if you later filter it, the full queue payload may already have entered model context. If `task show TASK` fails, use another task-scoped endpoint or stop with identity unresolved; never fall back to a broad list in the child.

Also enumerate every job and trial considered. Record model/runtime, parent job, source SHA, reward, execution status, artifact availability, and exclusion reason. A quality-review trial is not a solve trial. Do not compute pass rates until review, oracle, and infra-only trials are excluded.

Acquire and inspect the exact repository revision. Do not review a mutable branch tip when Codimango validates a different SHA.

## 2. Run the canonical current-task review

### Mandatory canonical review execution

The critic never drafts the author-facing form from its own evidence pass alone.

1. **Required primary runner:** run `aai-review-flow` in a dedicated same-task subagent/session. Load its full file set, not only its description. Record the child session ID, served skill revision, task ID/SHA, exit state, and output path.
2. If `aai-review-flow` cannot be loaded or fails before producing its operator handoff, run exactly one defined track fallback:

| Task kind | Required fallback reviewer |
|---|---|
| T-Bench single-turn | `team-aai:review-task-tbench-v2` |
| SWE-Bench single-turn | `team-aai:review-task-swebench-v2` |
| T-Bench multi-turn | `team-aai:review-task-tbench-multiturn` |
| SWE-Bench multi-turn | `team-aai:review-task-swebench-multiturn` |
| Long Horizon | matching v2 reviewer plus `aai-long-horizon:lh-review-task` |

3. Run `review-trials-and-spec` as a separate supplemental evidence pass for every applicable task.
4. Write `canonical-execution.json` with:
   - `task_id`, `task_sha`, `track`, and `variant`;
   - `primary_runner`, `primary_status`, `primary_session_id`, `primary_skill_revision`, and `primary_output_path`;
   - `fallback_runner`, `fallback_status`, and `fallback_reason` (`null` when primary succeeded);
   - `supplemental_runner`, `supplemental_status`, `supplemental_session_id`, and `supplemental_output_path`.
5. The primary succeeds only when it produces a nonempty canonical handoff. A fallback succeeds only when its canonical issues/verdict output is nonempty. The supplemental succeeds only when its trial/spec report is nonempty.
6. If neither the primary nor the required fallback succeeds, stop and report exactly:

`Canonical review format could not be generated.`

Do not invent, approximate, or condense the Codimango form. If `review-trials-and-spec` cannot run, mark the supplemental evidence unavailable and do not make universal trial/spec claims; this lowers confidence but does not substitute the critic for the canonical runner.

For any iOS signal, also read `references/ios-harness-gate.md` and run the current `team-aai:aai-ios review` lens after the generic per-track reviewer. An iOS task whose primary grader regex-extracts Swift production methods into a dummy shell or surrogate class instead of executing the submitted target through the supported native harness has a blocking reward-integrity defect. Default to **Request changes** and require native XCTest/XCUITest execution on the current supported iOS harness. Regex that only parses native runner output is not this defect. When this is the only blocker, use the exact concise rejection message in the iOS gate reference.

Use `team-aai:ado-task-review` only as an evidence-producing pre-pass. It does not own the final verdict.

Run every decision-bearing task review in a newly created session or process with no transcript, summary, scratch directory, retrieved evidence, or task artifacts from any other review. Do not reuse the authoring session. When processing a queue, the parent may pass only the current task identifier and this skill to a fresh child, then collect its final structured result. It must not pass findings or prose from sibling tasks. If fresh-session isolation cannot be guaranteed, stop without drafting an author-facing review. If Long Horizon evidence or another immutable evidence bundle exists for the current task, preserve it instead of replacing it with a summary.

## 3. Audit the generated review finding by finding

Use the supplied AI review, or the canonical review output from step 2. Create an internal ledger with one row per finding:

| Finding | Status | Independent evidence | Attribution | Severity now | What the reviewer got right |
|---|---|---|---|---|---|
| concise claim | CONFIRMED / OVERSTATED / WRONG / NOT VERIFIED | own file:line, test, trial, or reproduction | introduced now / pre-existing / unknown | C/H/M/L/advisory | concrete point I would have missed |

For each finding:

1. Reproduce or inspect it independently.
2. Cite your own file:line, test, trial, or artifact.
3. Separate observation from causal explanation. Reviews are often right that something failed and wrong about why.
4. Distinguish symptom addressed from root cause fixed.
5. Re-rank severity by current impact, not the reviewer's label.
6. Record internally what the reviewer correctly surfaced that the blind pass missed. Do not expose that self-comparison in the author-facing draft.

Do not praise a finding merely because it sounds plausible.

## 4. Go past the review

Explicitly answer these questions in the internal evidence report:

- What files, tests, consumers, interfaces, generated artifacts, or runtime paths did the review not inspect?
- Which task-description premises did it accept without checking?
- Is a serious integrity defect ranked below cosmetics?
- Did it inspect passing and failing trajectories, or infer from summaries and pass rates?
- Did it compare against a baseline, or only inspect the current state?
- Could the verifier accept a shortcut, no-op, hardcoded answer, stale generated output, or reference-specific implementation?
- Does the task test observable behavior while allowing equivalent representations, idiomatic implementations, and alternate hook boundaries?
- Are failures genuine capability gaps rather than setup, parser, timeout, rate-limit, or harness failures?
- For an iOS-labeled task, does the grader compile and execute the real submitted target on the supported iOS harness, or does it substitute regex-extracted Swift in a dummy shell?

Use the relevant named baseline, not a generic baseline bucket:

- `prior_revision`: attribution and regression claims
- `no_solution`: tests fail without the intended implementation
- `model_floor`: task is solvable but discriminating
- `hot_vs_cold`: multi-turn context is load-bearing
- `with_vs_without_skill`: skill ablation value
- `shortcut`: gameability and false-positive reward

If a required baseline is absent, say exactly what cannot be concluded.

## 5. Reconcile every previous submission and review

After the independent pass, read all prior human review bodies and relevant bot reviews in chronological order. Bind each review to its task SHA and reviewer round where possible.

Build a prior-finding ledger:

| Prior finding | Prior SHA and evidence | Current evidence | State | Current severity |
|---|---|---|---|---|
| concise identity | exact review and old location | current file:line or replay | fixed / partial / present / stale / not verified | C/H/M/L/none |

For every prior Critical or High finding, replay the counterexample or exploit when feasible. A changed line or author claim is not proof of closure.

Then run the full current-task invariant sweep. A re-review is never diff-only. Keep history reconciliation in the internal evidence report only. The author-facing review states the current condition and required action without mentioning prior reviews, iterations, rounds, or reviewer learning history.

### Re-review acceptance bias

Lean toward **Accept** when all of these are true:

- the author addressed every prior blocking finding in substance;
- current tests or reproductions prove the fixes;
- no new Critical or High issue exists;
- no major regression was introduced;
- remaining findings are Low or advisory under the current canonical rubric.

This is a tie-break toward closure, not permission to suppress a current blocker. Do not inherit a prior rejection after its reasons are fixed. Do not inherit a prior acceptance when the current revision regresses.

## 6. Decide

Use exactly one operational decision:

- **Accept:** no current blocker. Low, advisory, or explicitly unverified caveats may remain.
- **Request changes:** one or more concrete, fixable blockers remain.
- **Reject:** the task is unsuitable in a way revision cannot plausibly repair. Do not reject a fixable task.

Severity order must reflect reward integrity and training value first, then spec-test fairness, reproducibility, task quality, and cosmetics.

Confidence measures evidence coverage, not enthusiasm. Lower it for missing artifacts, mixed revisions, unrun baselines, or disputed policy boundaries.

## 7. Produce two outputs

### Internal evidence report

Write a detailed evidence artifact containing:

- exact revision binding;
- canonical execution receipt from `canonical-execution.json`, including runner/session/revision/output evidence;
- canonical reviewer output and the critic's reconciliation;
- job and trial ledger;
- finding audit;
- omitted-surface analysis;
- baseline results;
- prior-finding ledger;
- unresolved and not-verified items;
- final reasoning;
- complete output from both final-review validators, including the schema validator's detected section/field list.

This report may exceed 700 words.

### Paste-ready reviewer follow-up

Before drafting, read the full contents of `references/output-template.md`. The child must receive that file in its mounted skill bundle. If it is inaccessible, stop with `Canonical review format could not be generated.`

Render all eight mandatory sections and every exact field from that template, in order. Do not add an Agentic Full-Task Review section, merge fields, rename headings, omit empty fields, or replace the form with a summary. Use `None`, `No finding`, `NOT VERIFIED`, `NO DATA`, or `Not applicable` where appropriate. Keep the completed canonical form under 700 words.

Apply an author-facing language firewall before delivery:

- **Task scope:** every file, symbol, path, repository, task name, SHA, job, trial, and factual claim must belong to the current task. Any foreign identifier is a hard failure, not something to edit around.
- **History:** remove all mention of previous, prior, earlier, last, first, or follow-up review rounds and iterations. Translate history-derived conclusions into current-state facts only.
- **Batch comparison:** remove `batch`, relative rank, superlatives among tasks, comparisons with other reviews, and claims such as `best`, `strongest`, or `cleanest` when they compare this task to others.
- **Reviewer process:** remove first-person learning narration, including `I missed`, `we missed`, `my earlier miss`, `blind pass`, `on re-review`, or descriptions of how the conclusion was reached.
- **Current state only:** a fixed historical blocker becomes a current positive fact or disappears. An unresolved blocker is stated directly with current evidence and its close condition.
- **Human Checks:** every numeric score must have a task-specific rationale. Explain realism from the engineering scenario, domain expertise from the specialized knowledge barrier, and originality from novelty/public-source evidence. Bare scores are invalid.

Run all three validators before delivery:

```bash
python3 scripts/validate_canonical_execution.py \
  --receipt canonical-execution.json \
  --task-id TASK \
  --task-sha FULL_SHA
python3 scripts/lint_final_review.py FINAL.md
python3 scripts/validate_review_schema.py \
  --template references/output-template.md \
  --review FINAL.md
```

Also pass every known non-current task or repository identifier to the language linter as `--forbid-token TOKEN`. Any canonical-execution, language-lint, or schema finding blocks delivery. Do not claim `paste-ready` unless all three validators exit 0.

Compression order:

1. remove repeated context;
2. merge duplicate findings;
3. cut the lowest-value cosmetic or Low findings;
4. shorten examples.

Never cut what was not done, what remains open, what could not be verified, a blocking finding, or the exact condition for closing it. Cut findings before caveats, but never cut blockers.

## Follow-up loop

When the user provides a new SHA for the same task or asks "Do these still stand?", start a fresh isolated session for that task and:

1. freeze the new exact revision;
2. fetch the current review and all earlier same-task review bodies from Codimango after the blind pass;
3. update the internal prior-finding ledger;
4. replay prior blockers against the current grading path;
5. re-run the whole-task invariant sweep, not only changed files;
6. mark each old finding internally as `still stands`, `fixed`, `overstated`, `wrong`, or `not verified`;
7. apply the re-review acceptance bias;
8. regenerate a current-state-only, under-700-word follow-up that does not mention the earlier review, iteration, or the comparison process;
9. run the final-review linter.

Stop when the review is paste-ready. Never submit it on the user's behalf.
