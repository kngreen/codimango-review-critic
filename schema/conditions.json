{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "conditions.json",
  "title": "Frozen conditional review sections",
  "type": "object",
  "required": ["schema_version", "task_id", "task_sha", "agentic", "validation_override", "ios"],
  "properties": {
    "schema_version": {"const": 1},
    "task_id": {"type": "string", "minLength": 1},
    "task_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
    "agentic": {
      "type": "object",
      "required": ["state", "reason"],
      "properties": {
        "state": {"enum": ["required", "not_required", "unresolved"]},
        "reason": {"type": "string", "minLength": 1},
        "source": {"type": "string"},
        "run_id": {"type": "string", "minLength": 1},
        "traversal": {
          "type": "object",
          "required": ["job_id", "trial_ids", "artifacts", "complete"],
          "properties": {
            "job_id": {"type": ["string", "null"]},
            "trial_ids": {"type": "array", "items": {"type": "string"}},
            "artifacts": {
              "type": "array",
              "items": {
                "type": "object",
                "required": ["path", "sha256"],
                "properties": {
                  "path": {"type": "string", "minLength": 1},
                  "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
                },
                "additionalProperties": false
              }
            },
            "complete": {"type": "boolean"}
          },
          "additionalProperties": false
        }
      },
      "additionalProperties": false
    },
    "validation_override": {
      "type": "object",
      "required": ["state", "reason", "reasons"],
      "properties": {
        "state": {"enum": ["required", "not_required", "unresolved"]},
        "reason": {"type": "string", "minLength": 1},
        "reasons": {
          "type": "array",
          "items": {
            "type": "object",
            "required": ["check", "heading", "reason"],
            "properties": {
              "check": {"type": "string", "minLength": 1},
              "heading": {"type": "string", "minLength": 1},
              "reason": {"type": "string", "minLength": 1}
            },
            "additionalProperties": false
          }
        }
      },
      "additionalProperties": false
    },
    "ios": {
      "type": "object",
      "required": ["state", "reason"],
      "properties": {
        "state": {"enum": ["required", "not_required", "unresolved"]},
        "reason": {"type": "string", "minLength": 1}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
