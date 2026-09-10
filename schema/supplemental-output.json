{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "supplemental-output.json",
  "title": "Bounded supplemental review output",
  "type": "object",
  "required": ["schema_version", "task_id", "task_sha", "complete", "total_records", "summary_path", "summary_sha256", "ledger_path", "ledger_sha256"],
  "properties": {
    "schema_version": {"const": 1},
    "task_id": {"type": "string"},
    "task_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
    "complete": {"type": "boolean"},
    "total_records": {"type": "integer", "minimum": 0},
    "summary_path": {"type": "string"},
    "summary_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
    "ledger_path": {"type": "string"},
    "ledger_sha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"}
  },
  "additionalProperties": false
}
