{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "run-manifest-v2.json",
  "title": "Codimango critic trusted execution manifest",
  "type": "object",
  "required": ["schema_version", "dispatcher_session_id", "task", "bundle", "scratch_root", "task_repo_root", "runs", "phases", "conditions", "final", "publisher", "context"],
  "properties": {
    "schema_version": {"const": 2},
    "dispatcher_session_id": {"type": "string", "minLength": 1},
    "task": {
      "type": "object",
      "required": ["id", "repo", "track", "variant", "base_track", "head_sha", "validation_sha", "review_job_sha", "inspected_sha"],
      "properties": {
        "id": {"type": "string", "minLength": 1},
        "repo": {"type": "string", "minLength": 1},
        "track": {"type": "string", "minLength": 1},
        "variant": {"type": "string", "minLength": 1},
        "base_track": {"type": "string"},
        "head_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
        "validation_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
        "review_job_sha": {"type": ["string", "null"]},
        "inspected_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"}
      },
      "additionalProperties": false
    },
    "bundle": {
      "type": "object",
      "required": ["commit", "tree", "preflight_receipt_path", "preflight_receipt_sha256"],
      "properties": {
        "commit": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
        "tree": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
        "preflight_receipt_path": {"type": "string", "minLength": 1},
        "preflight_receipt_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
      },
      "additionalProperties": false
    },
    "scratch_root": {"type": "string", "minLength": 1},
    "task_repo_root": {"type": ["string", "null"]},
    "runs": {
      "type": "array",
      "minItems": 3,
      "items": {
        "type": "object",
        "required": ["role", "runner", "session_id", "parent_session_id", "workspace", "harness", "loaded_skill", "status", "skill_revision", "task_id", "task_sha", "started_at", "ended_at", "output_path", "output_sha256", "output_task_id", "output_task_sha", "attestation_source", "attested_run"],
        "properties": {
          "role": {"type": "string", "minLength": 1},
          "runner": {"type": "string", "minLength": 1},
          "session_id": {"type": "string", "minLength": 1},
          "parent_session_id": {"type": "string", "minLength": 1},
          "workspace": {"type": "string", "minLength": 1},
          "harness": {"enum": ["native", "claude_code", "codex", "muse_code"]},
          "loaded_skill": {"type": ["string", "null"]},
          "status": {"enum": ["completed", "finalizing", "failed", "unavailable"]},
          "skill_revision": {"type": "string", "minLength": 1},
          "task_id": {"type": ["string", "null"]},
          "task_sha": {"type": ["string", "null"]},
          "started_at": {"type": "string", "minLength": 1},
          "ended_at": {"type": ["string", "null"]},
          "output_path": {"type": ["string", "null"]},
          "output_sha256": {"type": ["string", "null"]},
          "output_task_id": {"type": ["string", "null"]},
          "output_task_sha": {"type": ["string", "null"]},
          "attestation_source": {"const": "agentcloud"},
          "attested_run": {"type": "integer", "minimum": 1}
        },
        "additionalProperties": false
      }
    },
    "phases": {
      "type": "array",
      "minItems": 7,
      "items": {
        "type": "object",
        "required": ["name", "sequence", "timestamp", "task_id"],
        "properties": {
          "name": {"type": "string", "minLength": 1},
          "sequence": {"type": "integer", "minimum": 1},
          "timestamp": {"type": "string", "minLength": 1},
          "task_id": {"type": "string", "minLength": 1},
          "artifact_path": {"type": "string"},
          "artifact_sha256": {"type": "string"}
        },
        "additionalProperties": false
      }
    },
    "conditions": {
      "type": "object",
      "required": ["path", "sha256"],
      "properties": {
        "path": {"type": "string", "minLength": 1},
        "sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
      },
      "additionalProperties": false
    },
    "final": {"type": "object"},
    "publisher": {"type": "object"},
    "context": {
      "type": "object",
      "required": ["allowed_identifiers", "allowed_path_prefixes", "allowed_repositories"],
      "properties": {
        "allowed_identifiers": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "allowed_path_prefixes": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "allowed_repositories": {"type": "array", "minItems": 1, "items": {"type": "string"}},
        "review_artifact_ids": {"type": "array", "items": {"type": "string"}}
      },
      "additionalProperties": false
    }
  },
  "additionalProperties": false
}
