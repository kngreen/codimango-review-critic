{
  "schema_version": 2,
  "word_limit_exclusive": 700,
  "base_sections": [
    {
      "key": "quality",
      "heading": "Quality Review Agent",
      "fields": [
        {"label": "Verdict", "kind": "enum", "values": ["Accept", "Revise", "Reject", "Unavailable"]},
        {"label": "Counts", "kind": "counts"},
        {"label": "Reviewer Agrees?", "kind": "enum", "values": ["Agree", "Partially", "Disagree"]},
        {"label": "Notes", "kind": "text"}
      ]
    },
    {
      "key": "contamination",
      "heading": "Contamination Review Agent",
      "fields": [
        {"label": "Risk Level", "kind": "enum", "values": ["LOW", "MEDIUM", "HIGH", "NONE", "NOT VERIFIED"]},
        {"label": "Reviewer Agrees?", "kind": "enum", "values": ["Agree", "Partially", "Disagree"]},
        {"label": "Notes", "kind": "text"}
      ]
    },
    {
      "key": "novelty",
      "heading": "Novelty Review Agent",
      "fields": [
        {"label": "Risk Level", "kind": "enum", "values": ["LOW", "MEDIUM", "HIGH", "NONE", "NOT VERIFIED"]},
        {"label": "Reviewer Agrees?", "kind": "enum", "values": ["Agree", "Partially", "Disagree"]},
        {"label": "Notes", "kind": "text"}
      ]
    },
    {
      "key": "tbr",
      "heading": "TBR Review Agreement",
      "fields": [
        {"label": "Reviewer Agrees?", "kind": "enum", "values": ["Agree", "Partially", "Disagree"]},
        {"label": "Disagreed Checks", "kind": "tbr_checks", "values": ["behavior_in_instruction", "behavior_in_tests", "tests_not_in_image", "test_deps_not_in_image", "no_hardcoded_solution", "output_files_mentioned", "no_solution_leak", "dockerfile_sets_up_task_environment", "self_contained", "no_trivial_solution", "anti_cheating_measures", "pinned_dependencies", "dockerfile_sets_up_broken_state", "instr_clarity", "spec_clarity", "test_quality", "code_patch_quality", "valid_task", "output_ambiguity", "information_leakage", "hackability"]},
        {"label": "Notes", "kind": "text"}
      ]
    },
    {
      "key": "human",
      "heading": "Human Checks",
      "fields": [
        {"label": "Realistic Scenario?", "kind": "score_1_4"},
        {"label": "Realistic Scenario Notes", "kind": "rationale"},
        {"label": "Domain Expertise?", "kind": "score_1_4"},
        {"label": "Domain Expertise Notes", "kind": "rationale"},
        {"label": "Original?", "kind": "score_1_4"},
        {"label": "Original Notes", "kind": "rationale"},
        {"label": "Primary Language", "kind": "language"},
        {"label": "Other Languages", "kind": "languages"},
        {"label": "Additional Notes", "kind": "text"}
      ]
    },
    {
      "key": "decision",
      "heading": "Decision",
      "fields": [
        {"label": "Decision", "kind": "enum", "values": ["Accept", "Request changes", "Reject"]},
        {"label": "Reason", "kind": "decision_reason"},
        {"label": "Follow-up needed?", "kind": "text"}
      ]
    },
    {
      "key": "other",
      "heading": "Other Notes",
      "fields": [
        {"label": "Notes", "kind": "other_notes"}
      ]
    },
    {
      "key": "confidence",
      "heading": "Reviewer Confidence",
      "fields": [
        {"label": "Confidence (1-5)", "kind": "confidence"}
      ]
    }
  ],
  "conditional_sections": {
    "agentic": {
      "key": "agentic",
      "heading": "Agentic Full-Task Review (MM)",
      "after": "Novelty Review Agent",
      "fields": [
        {"label": "Reviewer Agrees?", "kind": "enum", "values": ["Agree", "Partially", "Disagree"]},
        {"label": "Notes", "kind": "rationale"}
      ]
    },
    "validation_override": {
      "key": "validation_override",
      "heading": "Validation Override",
      "after": "TBR Review Agreement",
      "kind": "override_groups",
      "fields": ["Submitter Reason", "Reviewer Agrees?", "Reviewer Notes"]
    }
  },
  "quality_to_decision": {
    "Accept": "Accept",
    "Revise": "Request changes",
    "Reject": "Reject",
    "Unavailable": "Request changes"
  }
}
