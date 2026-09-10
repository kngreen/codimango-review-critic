# Codimango review follow-up loop

Replace `TASK` and optionally paste `REVIEW_TEXT`, then run this in a fresh Claude Code session with the relevant AAI review plugins installed.

```text
HARD ISOLATION REQUIREMENT: Run this review in a brand-new agent session or process created for exactly one task. Do not reuse a session that reviewed or authored another task. Do not pass in another task's transcript, summary, findings, examples, repository path, artifacts, trial data, scratch files, or draft prose. A queue runner may pass only this prompt, the current task identifier, and explicitly current-task inputs. If fresh-context isolation cannot be guaranteed, stop without producing a final review.

Review Codimango task TASK as a staff-level reviewer, then audit the generated review itself.

Before using any evidence, verify its task ID, repository, SHA, file paths, jobs, and trials belong to TASK. Treat any foreign-task identifier or fact as a context-isolation failure and discard the entire contaminated draft.

Never enumerate the review queue or all tasks from this child. Do not call `codimango task list --reviewing`, `task list --all`, or equivalent broad commands. Resolve identity with `codimango task show TASK --json`, then use only task-scoped comments, reviews, jobs, trials, and artifacts. If task-scoped resolution fails, stop rather than falling back to a broad list.

First freeze the exact task identity and revision: task ID, track, single-turn or multi-turn variant, task HEAD, validation SHA, review-job SHA, and every job/trial cohort used. Do not mix revisions.

MANDATORY CANONICAL REVIEW EXECUTION:
1. Run `aai-review-flow` in a dedicated same-task subagent/session with its full skill files loaded. Record its session ID, served skill revision, status, and nonempty output path.
2. If and only if it cannot load or fails before producing its operator handoff, run the one canonical track fallback:
   - T-Bench single-turn: team-aai:review-task-tbench-v2
   - SWE-Bench single-turn: team-aai:review-task-swebench-v2
   - T-Bench multi-turn: team-aai:review-task-tbench-multiturn
   - SWE-Bench multi-turn: team-aai:review-task-swebench-multiturn
   - Long Horizon: matching v2 reviewer plus aai-long-horizon:lh-review-task
3. Run `review-trials-and-spec` in a separate same-task subagent as supplemental evidence.
4. Write `canonical-execution.json` with task/SHA/track/variant, primary runner/session/revision/status/output, fallback runner/status/reason, and supplemental runner/session/status/output.
5. Do not draft the author-facing review from this critic prompt alone. If neither primary nor fallback produces nonempty canonical output, stop with exactly: `Canonical review format could not be generated.`
6. Treat ado-task-review as evidence, not the decision owner.

If TASK has any iOS signal, also run the current team-aai:aai-ios review lens and apply the skill's ios-harness-gate reference. An iOS task that regex-extracts Swift production code into a dummy shell, mock class, or surrogate executable instead of compiling and running the submitted target through the supported native harness has a blocking reward-integrity defect. Default to Request changes. Require native XCTest/XCUITest behavior on the current macOS-VM iOS harness, with real fail-to-pass and pass-to-pass coverage for iOS SWE-Bench. Do not misclassify regex used only to parse native runner output.

Complete a blind current-state pass before reading prior verdict prose. Then fetch and read every previous human review and relevant bot review for this same task directly from Codimango. Bind each to its SHA. A review summary is not enough. Same-task history stays internal and must not be described in the final author-facing review.

Audit REVIEW_TEXT if supplied; otherwise audit the canonical review you just produced.

For each finding, verify it against the exact repo revision. Keep the verification status in the private ledger as supported, overstated, wrong, or not verified. Cite your own file:line, test, trial, or reproduction. Separate what broke from why it broke. In the final review, state supported facts directly without `CONFIRMED` labels; use `NOT VERIFIED` only for material unresolved claims. Record internally what the reviewer got right that the blind pass missed, but never expose that self-comparison in the final review.

Then go past the findings:
- identify files, consumers, interfaces, generated artifacts, tests, and failure modes the review did not inspect;
- check task-description and README premises instead of accepting them;
- inspect passing and failing trajectories, excluding review, oracle, and infra-only trials from solve-rate claims;
- test whether severity ordering puts reward integrity and spec-test fairness above cosmetics;
- distinguish symptom addressed from root cause fixed;
- compare against the relevant named baseline: prior revision, no-solution, model-floor, hot-vs-cold, with-vs-without-skill, or shortcut;
- if no baseline exists, do not call anything a regression;
- for iOS tasks, verify that the native submitted target is built and executed through the supported iOS harness rather than source-parsed into a surrogate shell.

For a revised submission, build a ledger of every prior finding. Replay prior Critical and High counterexamples when feasible. Mark each fixed, partial, present, stale, or not verified. Re-run the whole-task invariant sweep, not only the diff.

Lean Accept if all prior blocking feedback is verified fixed, no new Critical or High issue exists, no major regression was introduced, and only Low or advisory findings remain. This is a tie-break toward closure, not permission to suppress a current blocker.

Produce two outputs:
1. A detailed internal evidence report with exact revision binding, `canonical-execution.json` receipt, canonical reviewer output and reconciliation, trial ledger, finding audit, omitted surfaces, baseline results, prior-finding ledger, all open or unverified items, and complete outputs from both final validators.
2. A paste-ready reviewer follow-up under 700 words. Before drafting, read the full mounted `references/output-template.md`. Return all eight base sections and every exact field in that template, in order. When the reviewed SHA has an Agentic Full-Task Review, also include `Agentic Full-Task Review (MM)` after Novelty and before TBR, with `Reviewer Agrees?` and `Notes`. Do not rename or merge fields, omit fields, or substitute a Decision/Blockers summary. Use `None`, `No finding`, `NOT VERIFIED`, `NO DATA`, or `Not applicable` where needed. If the template is inaccessible, stop with `Canonical review format could not be generated.`

Apply a strict language firewall to output 2. Every affirmative statement is independently verified by default, so do not use `CONFIRMED`, `confirmed`, `independently confirmed`, or similar verification narration. State the fact and evidence directly; reserve explicit status language for `NOT VERIFIED`, partial evidence, uncertainty, or disagreement. It must not mention batches, relative ranking among tasks, other tasks, previous or earlier reviews, review rounds, review iterations, first or blind passes, re-reviewing, or reviewer self-history. Ban wording such as "best in the batch", "compared with other tasks", "in the previous review", "on the last iteration", "from my earlier miss", "I missed", "we missed", and equivalents. Do not explain how a conclusion was discovered. Translate a fixed historical blocker into a current positive fact or omit it; state an unresolved blocker directly with current evidence.

Match this voice: terse, technical, causal, and specific. No #thanks, no AI-speak, no em dashes. Lead with the decision. State defect, consequence, and required correction. Cut duplicate or Low findings before cutting caveats. Never cut what was not done, what remains open, what could not be verified, or a blocking close condition.

Before delivery, scan every proper noun, task or repository identifier, file path, SHA, job, trial, and factual claim again. Every one must belong to TASK. Run all three validators and fix every finding:

`python3 scripts/validate_canonical_execution.py --receipt canonical-execution.json --task-id TASK --task-sha FULL_SHA`

`python3 scripts/lint_final_review.py FINAL.md`

`python3 scripts/validate_review_schema.py --template references/output-template.md --review FINAL.md [--agentic-required]`

Pass `--agentic-required` whenever the reviewed SHA exposes an Agentic Full-Task Review.

Do not claim paste-ready unless all three exit 0. Include all validator outputs and the detected canonical section/field list in the private evidence report.

Do not submit feedback, rerun validation, modify the task repository, or contact the author.
```

For the next revision of the same task, start another fresh isolated session, rerun the same prompt with the new SHA, and append:

```text
Task Reviewer Follow Up: Internally verify every earlier same-task finding against the new exact revision and all same-task review bodies fetched fresh from Codimango. Credit fixes only when the current grading path proves them. Apply the acceptance bias if blockers are fixed without major regressions. The final author-facing review must describe current state only and must not mention earlier reviews, iterations, rounds, or the comparison process.
```
