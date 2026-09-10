# Canonical Codimango review form contract

This file is part of the runtime input. A reviewer that cannot read it must stop with:

`Canonical review format could not be generated.`

The author-facing review must contain all eight base sections below, in order. When an Agentic Full-Task Review exists for the reviewed SHA, it must also contain the conditional `Agentic Full-Task Review (MM)` section immediately after Novelty and before TBR. Do not replace the form with a Decision/Blockers summary. Fold any additional agentic evidence into the canonical fields.

Every heading and field is mandatory, including fields whose value is `None`, `No finding`, `NOT VERIFIED`, `NO DATA`, or `Not applicable`. The complete form, not a substitute summary, must remain under 700 words.

## Exact skeleton

```markdown
### Quality Review Agent
- **Verdict:** Accept / Revise / Reject / Unavailable
- **Counts:** Critical N | High N | Medium N | Low N
- **Reviewer Agrees?:** Agree / Partially / Disagree
- **Notes:** Current-task findings and the strongest evidence, or `No finding`.

### Contamination Review Agent
- **Risk Level:** LOW / MEDIUM / HIGH / NONE / NOT VERIFIED
- **Reviewer Agrees?:** Agree / Partially / Disagree
- **Notes:** Actual lookup evidence, or `NOT VERIFIED: <reason>`.

### Novelty Review Agent
- **Risk Level:** LOW / MEDIUM / HIGH / NONE / NOT VERIFIED
- **Reviewer Agrees?:** Agree / Partially / Disagree
- **Notes:** Recall/public-source reasoning, or `NOT VERIFIED: <reason>`.

### Agentic Full-Task Review (MM)
- **Reviewer Agrees?:** Agree / Partially / Disagree
- **Notes:** Required when the reviewed SHA has an Agentic Full-Task Review. State whether its verdict, causal explanation, rubric findings, and attempt classifications survive independent verification.

### TBR Review Agreement
- **Reviewer Agrees?:** Agree / Partially / Disagree
- **Disagreed Checks:** none / comma-separated snake_case check IDs / NOT VERIFIED
- **Notes:** Material agreement or disagreement evidence, or `No finding`.

### Human Checks
- **Realistic Scenario?:** 1 / 2 / 3 / 4
- **Realistic Scenario Notes:** Task-specific engineering-scenario rationale.
- **Domain Expertise?:** 1 / 2 / 3 / 4
- **Domain Expertise Notes:** Task-specific specialized-knowledge rationale.
- **Original?:** 1 / 2 / 3 / 4
- **Original Notes:** Task-specific novelty/public-source rationale.
- **Primary Language:** One verified language token.
- **Other Languages:** Comma-separated languages / None
- **Additional Notes:** Concise extra context / None

### Decision
- **Decision:** Accept / Request changes / Reject
- **Reason:** Current-state decision, severity counts, evidence, what must change, and observable close conditions.
- **Follow-up needed?:** No / concise required action

### Other Notes
- **Notes:** `Strengths: ... To fix: ... To notice: ...` Use `None` only when no material caveat or context exists.

### Reviewer Confidence
- **Confidence (1-5):** N - concise evidence-coverage rationale
```

## Content rules

- Agentic Full-Task Review agreement is conditional, but mandatory whenever the live task exposes an Agentic Full-Task Review for the reviewed SHA. Use the serialized heading `Agentic Full-Task Review (MM)` and include both `Reviewer Agrees?` and `Notes`.
- Every affirmative statement is already verified. State facts directly; never prefix them with `CONFIRMED`.
- Use `NOT VERIFIED`, `NO DATA`, partial evidence, or uncertainty explicitly where applicable.
- Human Check scores always include task-specific rationales.
- Decision findings descend by severity and include current evidence plus a binary close condition.
- Other Notes preserves missing artifacts, unrun baselines, revision mismatches, and other material caveats.
- No batch comparisons, cross-task facts, review-history narration, reviewer self-history, `#thanks`, AI-speak, or em dashes.

## Validation

Before calling the review paste-ready, run both:

```bash
python3 scripts/lint_final_review.py FINAL.md
python3 scripts/validate_review_schema.py \
  --template references/output-template.md \
  --review FINAL.md \
  [--agentic-required]
```

Both commands must exit 0. The schema validator prints every detected canonical section and field. Copy that output into the private evidence report. A missing, renamed, duplicated, reordered, merged, empty, or invalid-valued field blocks delivery.
