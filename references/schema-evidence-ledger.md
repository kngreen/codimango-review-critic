{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "evidence-ledger.json",
  "title": "Codimango review evidence ledger",
  "type": "object",
  "required": ["schema_version", "task", "pagination", "jobs", "trials", "reviews", "history", "baselines", "prior_findings", "finding_dispositions", "unresolved", "ios", "supplemental"],
  "properties": {
    "schema_version": {"const": 1},
    "task": {
      "type": "object",
      "required": ["id", "sha"],
      "properties": {
        "id": {"type": "string", "minLength": 1},
        "sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"}
      },
      "additionalProperties": false
    },
    "pagination": {
      "type": "object",
      "required": ["jobs", "trials", "reviews"],
      "properties": {
        "jobs": {"type": "object"},
        "trials": {"type": "object"},
        "reviews": {"type": "object"}
      },
      "additionalProperties": false
    },
    "jobs": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "task_id", "class", "model_runtime", "source_sha", "reward", "status", "artifacts_available", "exclusion_reason", "scope"],
        "properties": {
          "id": {"type": "string", "minLength": 1},
          "task_id": {"type": "string", "minLength": 1},
          "class": {"type": "string", "minLength": 1},
          "model_runtime": {"type": "string", "minLength": 1},
          "source_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
          "reward": {"type": ["number", "null"]},
          "status": {"type": "string", "minLength": 1},
          "artifacts_available": {"type": "boolean"},
          "exclusion_reason": {"type": "string", "minLength": 1},
          "scope": {"enum": ["current", "prior"]}
        },
        "additionalProperties": false
      }
    },
    "trials": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "task_id", "parent_job", "artifact_paths", "class", "model_runtime", "source_sha", "reward", "status", "artifacts_available", "exclusion_reason", "scope"],
        "properties": {
          "id": {"type": "string", "minLength": 1},
          "task_id": {"type": "string", "minLength": 1},
          "parent_job": {"type": "string", "minLength": 1},
          "artifact_paths": {"type": "array", "items": {"type": "string"}},
          "class": {"type": "string", "minLength": 1},
          "model_runtime": {"type": "string", "minLength": 1},
          "source_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
          "reward": {"type": ["number", "null"]},
          "status": {"type": "string", "minLength": 1},
          "artifacts_available": {"type": "boolean"},
          "exclusion_reason": {"type": "string", "minLength": 1},
          "scope": {"enum": ["current", "prior"]}
        },
        "additionalProperties": false
      }
    },
    "reviews": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["id", "task_id", "kind", "scope", "sha", "body_path", "body_sha256", "finding_ids"],
        "properties": {
          "id": {"type": "string", "minLength": 1},
          "task_id": {"type": "string", "minLength": 1},
          "kind": {"type": "string", "minLength": 1},
          "scope": {"enum": ["current", "prior"]},
          "sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
          "body_path": {"type": "string", "minLength": 1},
          "body_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
          "finding_ids": {"type": "array", "items": {"type": "string"}}
        },
        "additionalProperties": false
      }
    },
    "history": {
      "type": "object",
      "required": ["complete", "count", "review_ids"],
      "properties": {
        "complete": {"const": true},
        "count": {"type": "integer", "minimum": 0},
        "review_ids": {"type": "array", "items": {"type": "string"}}
      },
      "additionalProperties": false
    },
    "baselines": {"type": "object"},
    "prior_findings": {"type": "array", "items": {"type": "object"}},
    "finding_dispositions": {"type": "object"},
    "unresolved": {"type": "array", "items": {"type": "string"}},
    "ios": {"type": ["object", "null"]},
    "supplemental": {
      "type": "object",
      "required": ["status", "descriptor_path", "descriptor_sha256", "reason"],
      "properties": {
        "status": {"enum": ["completed", "failed", "unavailable"]},
        "descriptor_path": {"type": ["string", "null"]},
        "descriptor_sha256": {"type": ["string", "null"]},
        "reason": {"type": ["string", "null"]}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
