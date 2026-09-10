{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "review-data.json",
  "title": "Structured author-facing review data",
  "type": "object",
  "required": ["schema_version", "task_id", "task_sha", "sections"],
  "properties": {
    "schema_version": {"const": 1},
    "task_id": {"type": "string"},
    "task_sha": {"type": "string", "pattern": "^[0-9a-f]{40}$"},
    "sections": {"type": "object"},
    "validation_overrides": {"type": "array"}
  },
  "additionalProperties": false
}
