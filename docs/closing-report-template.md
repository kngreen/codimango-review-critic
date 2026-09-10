# Closing report contract

Use these headings verbatim after implementation:

1. Premises
2. Item results: symptom and acceptance test
3. Direction of change
4. Verification plan and actual output
5. Control wiring and firing
6. Blast radius
7. Consolidation check
8. Second-order cost
9. Recurrence
10. Out of scope
11. Coverage gaps
12. Receipt block
13. Incomplete items

Paste actual command output for every item. Do not replace output with a narrative summary.

## Receipt block

| check | mode | sha | tree state | timestamp | verdict |
|---|---|---|---|---|---|
| `<gate>` | `local / pre-push / CI` | `<full commit SHA>` | `clean / dirty` | `<UTC ISO-8601 after commit>` | `PASS / FAIL / INCOMPLETE` |

A gate without a receipt did not run. Evidence timestamped before the commit it certifies does not certify it. Dirty-tree evidence may guide debugging but cannot certify release bytes.
