#!/usr/bin/env python3
"""Validate the eight base Codimango sections plus live conditional sections."""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Field:
    label: str
    value_pattern: re.Pattern[str]


def enum(*values: str) -> re.Pattern[str]:
    return re.compile(r"^(?:" + "|".join(re.escape(v) for v in values) + r")$")


NONEMPTY = re.compile(r"^\S(?:.*\S)?$")
COUNTS = re.compile(r"^Critical \d+ \| High \d+ \| Medium \d+ \| Low \d+$")
SCORE_1_4 = re.compile(r"^[1-4]$")
CONFIDENCE = re.compile(r"^[1-5]\s+-\s+\S.*$")

SECTIONS: tuple[tuple[str, tuple[Field, ...]], ...] = (
    (
        "Quality Review Agent",
        (
            Field("Verdict", enum("Accept", "Revise", "Reject", "Unavailable")),
            Field("Counts", COUNTS),
            Field("Reviewer Agrees?", enum("Agree", "Partially", "Disagree")),
            Field("Notes", NONEMPTY),
        ),
    ),
    (
        "Contamination Review Agent",
        (
            Field("Risk Level", enum("LOW", "MEDIUM", "HIGH", "NONE", "NOT VERIFIED")),
            Field("Reviewer Agrees?", enum("Agree", "Partially", "Disagree")),
            Field("Notes", NONEMPTY),
        ),
    ),
    (
        "Novelty Review Agent",
        (
            Field("Risk Level", enum("LOW", "MEDIUM", "HIGH", "NONE", "NOT VERIFIED")),
            Field("Reviewer Agrees?", enum("Agree", "Partially", "Disagree")),
            Field("Notes", NONEMPTY),
        ),
    ),
    (
        "TBR Review Agreement",
        (
            Field("Reviewer Agrees?", enum("Agree", "Partially", "Disagree")),
            Field("Disagreed Checks", NONEMPTY),
            Field("Notes", NONEMPTY),
        ),
    ),
    (
        "Human Checks",
        (
            Field("Realistic Scenario?", SCORE_1_4),
            Field("Realistic Scenario Notes", NONEMPTY),
            Field("Domain Expertise?", SCORE_1_4),
            Field("Domain Expertise Notes", NONEMPTY),
            Field("Original?", SCORE_1_4),
            Field("Original Notes", NONEMPTY),
            Field("Primary Language", NONEMPTY),
            Field("Other Languages", NONEMPTY),
            Field("Additional Notes", NONEMPTY),
        ),
    ),
    (
        "Decision",
        (
            Field("Decision", enum("Accept", "Request changes", "Reject")),
            Field("Reason", NONEMPTY),
            Field("Follow-up needed?", NONEMPTY),
        ),
    ),
    ("Other Notes", (Field("Notes", NONEMPTY),)),
    ("Reviewer Confidence", (Field("Confidence (1-5)", CONFIDENCE),)),
)

AGENTIC_SECTION: tuple[str, tuple[Field, ...]] = (
    "Agentic Full-Task Review (MM)",
    (
        Field("Reviewer Agrees?", enum("Agree", "Partially", "Disagree")),
        Field("Notes", NONEMPTY),
    ),
)

HEADING_RE = re.compile(r"^###\s+(.+?)\s*$", re.MULTILINE)
FIELD_RE = re.compile(r"^\s*-\s+\*\*(.+?):\*\*\s*(.*?)\s*$", re.MULTILINE)
OPTIONAL_AGENTIC = AGENTIC_SECTION[0]
OPTIONAL_TAXONOMY = "Taxonomy Verification"


def fail(errors: list[str]) -> int:
    print("CANONICAL REVIEW SCHEMA REJECTED", file=sys.stderr)
    for error in errors:
        print(f"- {error}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", required=True, type=Path)
    parser.add_argument("--review", required=True, type=Path)
    parser.add_argument("--agentic-required", action="store_true")
    parser.add_argument("--taxonomy-required", action="store_true")
    args = parser.parse_args()

    template = args.template.read_text(encoding="utf-8")
    review = args.review.read_text(encoding="utf-8")
    errors: list[str] = []

    # Prove the runtime actually received the canonical template being enforced.
    for section, fields in (*SECTIONS, AGENTIC_SECTION):
        if f"### {section}" not in template:
            errors.append(f"template missing canonical heading: {section}")
        for field in fields:
            if f"**{field.label}:**" not in template:
                errors.append(f"template missing canonical field: {section} / {field.label}")
    if errors:
        return fail(errors)

    heading_matches = list(HEADING_RE.finditer(review))
    headings = [m.group(1) for m in heading_matches]
    expected = [name for name, _ in SECTIONS]
    allowed = set(expected) | {OPTIONAL_AGENTIC, OPTIONAL_TAXONOMY}

    for heading in headings:
        if heading not in allowed:
            errors.append(f"unexpected or renamed section: {heading}")
    for heading in expected:
        count = headings.count(heading)
        if count != 1:
            errors.append(f"section {heading!r} appears {count} times; expected exactly once")
    agentic_count = headings.count(OPTIONAL_AGENTIC)
    if agentic_count > 1:
        errors.append("Agentic Full-Task Review (MM) appears more than once")
    if args.agentic_required and agentic_count != 1:
        errors.append(
            "Agentic Full-Task Review (MM) is required by the live form but missing"
        )

    tax_count = headings.count(OPTIONAL_TAXONOMY)
    if tax_count > 1:
        errors.append("Taxonomy Verification appears more than once")
    if args.taxonomy_required and tax_count != 1:
        errors.append("Taxonomy Verification is required by the live form but missing")

    normalized = [
        h for h in headings if h not in {OPTIONAL_AGENTIC, OPTIONAL_TAXONOMY}
    ]
    if normalized != expected:
        errors.append(
            "canonical section order mismatch: "
            + " -> ".join(normalized or ["<none>"])
        )
    if agentic_count == 1:
        agentic_index = headings.index(OPTIONAL_AGENTIC)
        novelty_index = headings.index("Novelty Review Agent") if "Novelty Review Agent" in headings else -1
        tbr_index = headings.index("TBR Review Agreement") if "TBR Review Agreement" in headings else 10**9
        if not (novelty_index < agentic_index < tbr_index):
            errors.append(
                "Agentic Full-Task Review (MM) must appear between Novelty Review Agent and TBR Review Agreement"
            )
    if tax_count == 1:
        tax_index = headings.index(OPTIONAL_TAXONOMY)
        tbr_index = headings.index("TBR Review Agreement") if "TBR Review Agreement" in headings else -1
        human_index = headings.index("Human Checks") if "Human Checks" in headings else 10**9
        if not (tbr_index < tax_index < human_index):
            errors.append("Taxonomy Verification must appear between TBR Review Agreement and Human Checks")

    section_map = {name: fields for name, fields in (*SECTIONS, AGENTIC_SECTION)}
    for idx, match in enumerate(heading_matches):
        heading = match.group(1)
        start = match.end()
        end = heading_matches[idx + 1].start() if idx + 1 < len(heading_matches) else len(review)
        body = review[start:end]
        found = list(FIELD_RE.finditer(body))

        if heading == OPTIONAL_TAXONOMY:
            if not found:
                errors.append("Taxonomy Verification has no fields")
            continue
        if heading not in section_map:
            continue

        required = section_map[heading]
        required_labels = [f.label for f in required]
        found_labels = [m.group(1) for m in found]
        if found_labels != required_labels:
            errors.append(
                f"field order/shape mismatch in {heading}: found {found_labels!r}; "
                f"expected {required_labels!r}"
            )
            continue

        for spec, field_match in zip(required, found):
            value = field_match.group(2).strip()
            if not spec.value_pattern.fullmatch(value):
                errors.append(
                    f"invalid or empty value for {heading} / {spec.label}: {value!r}"
                )

    if errors:
        return fail(errors)

    print("CANONICAL REVIEW SCHEMA OK")
    for heading in headings:
        if heading == OPTIONAL_TAXONOMY:
            print("SECTION: Taxonomy Verification (conditional)")
            continue
        fields = section_map[heading]
        suffix = " (conditional)" if heading == OPTIONAL_AGENTIC else ""
        print(f"SECTION: {heading}{suffix}")
        for field in fields:
            print(f"  FIELD: {field.label}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
