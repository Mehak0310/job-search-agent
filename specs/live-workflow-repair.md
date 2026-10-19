# Live application workflow repair

Scope: restore the existing Windows workflow. No P1 portability, P2 redesign or P3 parity work.

| Phase | State |
|---|---|
| Read-only diagnosis | Complete: stale backend source, disconnected dedicated Chrome, no active leases, zero verified eligible pending candidates, four lost sessions and one manually reported outcome in the selected batch. Private operational evidence is excluded from this report. |
| Isolated reproduction | Complete: missing outcome counts, closed-vacancy selection, prepared-requisition alias selection, stale recovered target and unbounded connection errors reproduced with synthetic SQLite/browser doubles. |
| Targeted repair | Implemented: exhaustive batch counters, durable target rebinding, bounded tab connections, explicit errors, closed/removed and prepared-alias exclusion before ranking. |
| Validation | Passed: final 508 Python tests/91.53% coverage, 154 UI tests, R1 one integrated test and R2 two integrated tests. Exact commands and coverage limits in repair report. |
| Local activation | Complete: backend restarted gracefully and its source matched the workspace at activation; initial protected-state comparison unchanged. |
| Read-only application smoke | Complete within explicit user approval: four saved application URLs opened read-only and all four switch actions returned TAB_SELECTED. Original form tabs did not restore; cached partial progress retained, no filling/uploads/Submit. |
| Fresh eligible batch of five | Blocked: four applications remain connected and awaiting inspection/eligibility verification; one application is manually reported submitted but not independently verified; zero verified eligible pending candidates and zero forms ready for review. |

Retain one active batch and two independent browser actors. Preserve existing forms, user text, packet revisions, accepted facts, exact approvals, documents and monotonic submission history. Do not replay uncertain uploads, infer submission from UI state, or click final Submit. Five selections require five independently eligible nonduplicate vacancies; zero verified candidates is an explicit blocker, never a reason to weaken gates.

Current handoff and actual commands: [repair report](../docs/live-workflow-repair.md).
