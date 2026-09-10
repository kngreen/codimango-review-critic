# Codimango review follow-up loop

Replace `TASK` and run this in a brand-new task-only critic session. Mount the complete released repository, not only `SKILL.md`.

```text
Review exactly one Codimango task: TASK.

Follow the mounted `codimango-review-critic/SKILL.md` as an executable protocol, not a prose checklist.

Before reading task data:
1. Start with an empty scratch root outside the task repository.
2. Run the bundled `reviewctl.py preflight` and `run_review.py bootstrap` commands.
3. Run every shell/CLI command through `audit_exec.py`; require its OS-level read-only sandbox and command receipt.
4. Stop if bundle integrity, Agentcloud journal attestation, authentication, or isolation cannot be proven. Process-only mode is not a certified fallback.

Then:
1. Resolve identity-only metadata and freeze task ID, repository, track, variant, HEAD, validation SHA, review-job SHA, inspected SHA, and allowed identifiers/paths.
2. Record `blind_started`, then create a distinct canonical child for `aai-review-flow`. Require the child to load that pinned skill through the platform loader and emit a journal-bound run receipt. Use the exact track fallback only if the primary fails before a nonempty handoff. Long Horizon requires the matching fallback plus `lh-review-task`.
3. Create a distinct `review-trials-and-spec` child. For iOS, create a distinct `aai-ios` child and record native target/XCTest evidence. Every child must run `emit_run_receipt.py`; build its manifest record only with `adapters/agentcloud.py` from the durable session journal.
4. Complete the blind current-state analysis and seal its artifact before fetching any human or bot review body.
5. After the seal, fetch every same-task review with pagination to completion. Record task ID, current/prior scope, SHA, body hash, finding IDs, an explicit history count/ID completeness receipt, and the prior-finding ledger, including explicit empty values when there are none.
6. Resolve Agentic, Validation Override, and iOS conditions from frozen metadata. For Agentic `parse_error`, record unique job/trial IDs and unique absolute artifact paths with SHA-256, all tied to the evidence inventory, before deciding no report exists. Unknown conditions block delivery. Do not emit Taxonomy Verification: it is not part of the current live form contract.
7. Write `findings.json`, `evidence-ledger.json`, `review-data.json`, `internal-evidence.md`, and `command-audit.jsonl` using the bundled schemas.
8. Render `final-review.md` and `live-form-payload.json` with the bundled renderers. Do not hand-format or repair Markdown.
9. Emit and record the running critic's own Agentcloud receipt, record final hashes and the `finalized` phase, then run `finalize_review.py`. If it fails, return the exact machine error to this same isolated critic and regenerate. A parent must never rewrite the files.
10. The parent may publish only through `publish_verified.py` with the critic session/run; the durable `FINALIZATION_RECEIPT`, approval, manifest, and published bytes must have matching hashes.

Evidence requirements:
- independently verify every canonical finding;
- classify every job/trial and exclude oracle, review, cancelled, errored, and infrastructure-only work from solve rates;
- record all six baselines as pass, fail, not_verified, or not_applicable with rationale;
- record every unavailable artifact and unsupported checker;
- record every canonical/supplemental finding ID in `findings.json` or an explicit `finding_dispositions` entry with rationale;
- inspect the exact validated revision, or prove task-subtree byte identity when inspecting a newer commit;
- replay prior Critical/High findings when feasible;
- for iOS, compile and execute the real submitted target with native XCTest/XCUITest. Regex-rehosted Swift is a blocking reward-integrity defect.

Author-facing rules:
- eight base sections in exact order;
- Agentic and Validation Override only when frozen conditions require them;
- under 700 lexical and whitespace-separated words;
- no `CONFIRMED`, review-history narration, batch comparison, AI-speak, `#thanks`, or em dash;
- every Human Check score has a task-specific rationale;
- preserve blockers, unavailable evidence, and close conditions.

If neither canonical primary nor fallback succeeds, return exactly:
`Canonical review format could not be generated.`

Do not submit feedback, rerun platform validation, mutate the task repository, or contact anyone.
```

For a same-task new SHA, start another fresh critic session and scratch root. Repeat every phase. Do not reuse prior prose or artifacts; fetch same-task history only after the new blind seal.
