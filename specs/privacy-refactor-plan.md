# Publication privacy refactor plan

Approval scope: implementation and local verification only; no commit/push and no production UI redesign.

| Milestone | Status |
|---|---|
| Preserve private facts/defaults, complete persisted profile and original source/notes | Implemented under ignored local data with restricted ACLs |
| Neutral defaults and explicit local confirmations | Implemented |
| Generic hash-bound manifest roles and private legacy aliases | Implemented |
| Fictional fixtures, isolated populated UI suite and privacy/persistence tests | Implemented |
| Sanitize needed handoffs/checklist; exclude raw reports/personal scripts | Implemented |
| Focused verification | Passed as documented |
| Final functional, remote and review-index verification | Passed: 502 Python/91.57%, 152 UI/no skips, R1/R2 and 309 blobs |
| Protected-state attribution | Cleared: all original rows/assets match; user confirmed legitimate concurrent appends, retained without rebaseline |
| Exact staged-file proposal | Ready: 265 changed paths; real index untouched |
| Final publication approval | Required; not granted |

Exact evidence, limits and proposed message/destination: docs/privacy-refactor-verification.md. Canonical documents, protected production data, approved facts/history and visual proposal artifacts must remain preserved. Never run production reconciliation or regenerate historical packets to validate this refactor.
