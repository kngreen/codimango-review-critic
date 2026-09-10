# Canonical Codimango review form contract

This file is generated from `schema/review-format.json`. Edit the schema, then run:

`python3 scripts/generate_template.py --write`

A reviewer that cannot read this file must stop with:

`Canonical review format could not be generated.`

The author-facing review contains eight base sections in order. Conditional Agentic and Validation Override sections are inserted only when `conditions.json` marks them required. The complete form must remain under 700 words.

## Exact skeleton

```markdown
### Quality Review Agent
- **Verdict:** Accept / Revise / Reject / Unavailable
- **Counts:** Critical N | High N | Medium N | Low N
- **Reviewer Agrees?:** Agree / Partially / Disagree
- **Notes:** Current-task text / explicit unavailable state

### Contamination Review Agent
- **Risk Level:** LOW / MEDIUM / HIGH / NONE / NOT VERIFIED
- **Reviewer Agrees?:** Agree / Partially / Disagree
- **Notes:** Current-task text / explicit unavailable state

### Novelty Review Agent
- **Risk Level:** LOW / MEDIUM / HIGH / NONE / NOT VERIFIED
- **Reviewer Agrees?:** Agree / Partially / Disagree
- **Notes:** Current-task text / explicit unavailable state

<!-- conditional: agentic -->
### Agentic Full-Task Review (MM)
- **Reviewer Agrees?:** Agree / Partially / Disagree
- **Notes:** Task-specific rationale

### TBR Review Agreement
- **Reviewer Agrees?:** Agree / Partially / Disagree
- **Disagreed Checks:** none / comma-separated snake_case check IDs / NOT VERIFIED
- **Notes:** Current-task text / explicit unavailable state

<!-- conditional: validation_override -->
### Validation Override
- **CHECK_HEADING**
- **Submitter Reason:** Existing submitter rationale.
- **Reviewer Agrees?:** Agree / Partially / Disagree
- **Reviewer Notes:** Current-task evidence.

### Human Checks
- **Realistic Scenario?:** 1 / 2 / 3 / 4
- **Realistic Scenario Notes:** Task-specific rationale
- **Domain Expertise?:** 1 / 2 / 3 / 4
- **Domain Expertise Notes:** Task-specific rationale
- **Original?:** 1 / 2 / 3 / 4
- **Original Notes:** Task-specific rationale
- **Primary Language:** One verified language token
- **Other Languages:** Comma-separated languages / None
- **Additional Notes:** Current-task text / explicit unavailable state

### Decision
- **Decision:** Accept / Request changes / Reject
- **Reason:** Current-state counts, evidence, required changes, and close conditions
- **Follow-up needed?:** Current-task text / explicit unavailable state

### Other Notes
- **Notes:** Strengths: ... To fix: ... To notice: ...

### Reviewer Confidence
- **Confidence (1-5):** N - concise evidence-coverage rationale

```

## Content rules

- `conditions.json` decides whether Agentic and Validation Override are present. An unresolved condition blocks delivery.
- Every affirmative statement is verified by evidence. Use `NOT VERIFIED` only for unavailable or uncertain evidence.
- Human Check scores require task-specific rationales.
- Decision findings descend by severity and include observable close conditions.
- Other Notes preserves missing artifacts, unrun baselines, revision mismatches, and material caveats.
- No batch comparisons, cross-task facts, review-history narration, reviewer self-history, `#thanks`, AI-speak, or em dashes.

## Validation

Run `python3 scripts/finalize_review.py --help`; only its approval receipt authorizes publication.
