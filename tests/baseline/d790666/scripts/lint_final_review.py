#!/usr/bin/env python3
"""Fail closed when a Codimango final review leaks review-process or foreign-task context."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "batch comparison",
        re.compile(
            r"\b(best|strongest|weakest|cleanest|easiest|hardest)\b.{0,40}\b(batch|tasks?|reviews?)\b"
            r"|\b(review batch|batch of (?:tasks?|reviews?))\b",
            re.IGNORECASE,
        ),
    ),
    (
        "cross-task comparison",
        re.compile(
            r"\bcompared (?:to|with) (?:the )?(?:other|rest of the) (?:tasks?|reviews?)\b"
            r"|\bamong (?:the )?(?:tasks?|reviews?)\b"
            r"|\b(?:another|other|sibling) tasks?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "review-history narration",
        re.compile(
            r"\b(?:previous|prior|earlier|last|first) (?:human )?(?:review|iteration|round|pass)\b"
            r"|\b(?:review|reviewer) (?:iteration|round)\b"
            r"|\bre-?review(?:ing|ed)?\b"
            r"|\bfollow-?up review\b",
            re.IGNORECASE,
        ),
    ),
    (
        "reviewer self-history",
        re.compile(
            r"\bfrom (?:my|our) earlier miss\b"
            r"|\b(?:i|we) (?:had )?(?:previously |earlier )?missed\b"
            r"|\b(?:my|our) (?:previous|earlier) (?:miss|analysis|finding|assessment)\b"
            r"|\bblind pass\b"
            r"|\bwhat (?:i|we) would have missed\b"
            r"|\bthe reviewer caught\b",
            re.IGNORECASE,
        ),
    ),
    (
        "redundant confirmation narration",
        re.compile(r"\bconfirmed\b", re.IGNORECASE),
    ),
)


def line_number(text: str, position: int) -> int:
    return text.count("\n", 0, position) + 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("review", type=Path, help="Final author-facing review markdown")
    parser.add_argument(
        "--forbid-token",
        action="append",
        default=[],
        help="Known non-current task/repository identifier; repeat as needed",
    )
    parser.add_argument("--max-words", type=int, default=700)
    args = parser.parse_args()

    text = args.review.read_text(encoding="utf-8")
    findings: list[str] = []

    words = re.findall(r"\b\w+(?:[-']\w+)*\b", text)
    if len(words) > args.max_words:
        findings.append(f"word limit: {len(words)} > {args.max_words}")

    for token in ("—", "#thanks"):
        if token.casefold() in text.casefold():
            findings.append(f"forbidden style token: {token!r}")

    for label, pattern in FORBIDDEN_PATTERNS:
        for match in pattern.finditer(text):
            excerpt = " ".join(match.group(0).split())
            findings.append(
                f"line {line_number(text, match.start())}: {label}: {excerpt!r}"
            )

    folded = text.casefold()
    for token in args.forbid_token:
        token = token.strip()
        if token and token.casefold() in folded:
            findings.append(f"foreign-task token present: {token!r}")

    if re.search(r"^### Human Checks\s*$", text, re.MULTILINE):
        human_check_fields = (
            ("Realistic Scenario?", "Realistic Scenario Notes"),
            ("Domain Expertise?", "Domain Expertise Notes"),
            ("Original?", "Original Notes"),
        )
        for score_label, notes_label in human_check_fields:
            score_match = re.search(
                rf"^\s*-?\s*\*\*{re.escape(score_label)}:\*\*\s*([1-4])\s*$",
                text,
                re.MULTILINE,
            )
            notes_match = re.search(
                rf"^\s*-?\s*\*\*{re.escape(notes_label)}:\*\*\s*(\S.*)$",
                text,
                re.MULTILINE,
            )
            if score_match is None:
                findings.append(f"missing Human Check score: {score_label}")
            if notes_match is None:
                findings.append(f"missing Human Check rationale: {notes_label}")

    if findings:
        print("FINAL REVIEW REJECTED", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1

    print(f"OK: {len(words)} words; no review-history or supplied foreign-task leaks found")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
