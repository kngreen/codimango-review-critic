# Contract fixtures

Run:

```bash
python3 scripts/materialize_fixtures.py --output /tmp/codimango-critic-fixtures
python3 scripts/reviewctl.py validate-dag /tmp/codimango-critic-fixtures/run_good.json
```

The generator creates three executable fixtures: `run_good.json`, `run_parent_rewrite.json`, and `history_before_blind.json`, plus all digest-bound files they reference. Dynamic materialization is required because manifests contain absolute paths, workspaces, timestamps, and SHA-256 values; checked-in placeholder JSON would fail before reaching its intended predicate.

`scripts/selftest.sh` materializes the fixtures and proves the passing and failing entrypoints on every run.
