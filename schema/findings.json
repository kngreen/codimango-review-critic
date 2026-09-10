{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "findings.json",
  "title": "Codimango structured findings",
  "type": "object",
  "required": ["schema_version", "task_id", "task_sha", "quality_verdict", "decision", "decision_reconciliation", "findings"],
  "properties": {
    "schema_version": {"const": 1},
    "task_id": {"type": "string", "minLength": 1},
    "task_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
    "quality_verdict": {"enum": ["Accept", "Revise", "Reject", "Unavailable"]},
    "decision": {"enum": ["Accept", "Request changes", "Reject"]},
    "decision_reconciliation": {"type": "string", "minLength": 1},
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "finding", "status", "independent_evidence", "attribution", "severity", "blocking", "reviewer_contribution", "close_condition"],
        "properties": {
          "id": {"type": "string", "minLength": 1},
          "finding": {"type": "string", "minLength": 1},
          "status": {"enum": ["CONFIRMED", "OVERSTATED", "WRONG", "NOT VERIFIED"]},
          "independent_evidence": {"type": "array", "minItems": 1, "items": {"type": "string", "minLength": 1}},
          "attribution": {"type": "string", "minLength": 1},
          "severity": {"enum": ["Critical", "High", "Medium", "Low", "advisory"]},
          "blocking": {"type": "boolean"},
          "reviewer_contribution": {"type": "string", "minLength": 1},
          "close_condition": {"type": "string", "minLength": 15}
        },
        "additionalProperties": false
      }
    }
  },
  "additionalProperties": false
}
