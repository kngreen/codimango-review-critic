{
  "schema_version": 1,
  "source": {
    "repo": "fbsource",
    "commit": "f4f4bdbc2c3b790966a66566df2d8d7b50db4d99",
    "path": "nest/apps/codimango/app/components/review/tbench-reviewer-form.tsx"
  },
  "sections": {
    "Quality Review Agent": "quality",
    "Contamination Review Agent": "contamination",
    "Novelty Review Agent": "novelty",
    "Agentic Full-Task Review (MM)": "mmAgenticFullTaskReviewAgreement",
    "TBR Review Agreement": "tbrAgreement",
    "Validation Override": "overrideReasons",
    "Human Checks": "human",
    "Decision": "decision",
    "Other Notes": "other",
    "Reviewer Confidence": "confidence"
  },
  "override_review_valid_checks": [
    "Contamination check",
    "Provenance check",
    "AI assessment",
    "Skills AI assessment",
    "Novelty risk check",
    "CUA run",
    "Metacode or Opus pass/fail balance",
    "TBR Feedback",
    "ML Task QA",
    "ML Grading QA",
    "Agentic full-task review (MM)",
    "Configerable signals",
    "CUA run review",
    "__appeal_body__"
  ],
  "field_mappings": [
    {"source": "sections.quality.Reviewer Agrees?", "target": "qualityAgree"},
    {"source": "sections.quality.Notes", "target": "qualityNotes"},
    {"source": "sections.contamination.Reviewer Agrees?", "target": "contaminationAgree"},
    {"source": "sections.contamination.Notes", "target": "contaminationNotes"},
    {"source": "sections.novelty.Reviewer Agrees?", "target": "noveltyAgree"},
    {"source": "sections.novelty.Notes", "target": "noveltyNotes"},
    {"source": "sections.tbr.Disagreed Checks", "target": "tbrDisagreeCriteria", "transform": "csv_or_empty"},
    {"source": "sections.tbr.Notes", "target": "tbrAgreementNotes"},
    {"source": "sections.human.Realistic Scenario?", "target": "realisticScenario"},
    {"source": "sections.human.Realistic Scenario Notes", "target": "realisticScenarioNotes"},
    {"source": "sections.human.Domain Expertise?", "target": "domainExpertise"},
    {"source": "sections.human.Domain Expertise Notes", "target": "domainExpertiseNotes"},
    {"source": "sections.human.Original?", "target": "originality"},
    {"source": "sections.human.Original Notes", "target": "originalityNotes"},
    {"source": "sections.human.Primary Language", "target": "primaryLanguage"},
    {"source": "sections.human.Other Languages", "target": "otherLanguages"},
    {"source": "sections.human.Additional Notes", "target": "humanAdditionalNotes"},
    {"source": "findings.decision", "target": "decision", "transform": "decision_action"},
    {"source": "sections.decision.Reason", "target": "decisionReason"},
    {"source": "sections.other.Notes", "target": "otherNotes"},
    {"source": "sections.confidence.Confidence (1-5)", "target": "reviewerConfidence", "transform": "score_prefix"}
  ],
  "conditional_field_mappings": {
    "agentic": [
      {"source": "sections.agentic.Reviewer Agrees?", "target": "mmAgenticFullTaskReviewAgree"},
      {"source": "sections.agentic.Notes", "target": "mmAgenticFullTaskReviewNotes"},
      {"source": "conditions.agentic.run_id", "target": "mmAgenticFullTaskReviewRunId"}
    ],
    "validation_override": [
      {"source": "review_data.validation_overrides", "target": "overrideReview", "transform": "override_review"}
    ]
  },
  "unsupported_preferred_sections": [],
  "unsupported_live_sections": []
}
