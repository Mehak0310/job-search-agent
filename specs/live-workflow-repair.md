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

## Successor milestone: eligibility and application review

This successor work was developed on `e94340d61ee88aea137a878ad1e48ca860f3e60f` and published to local and remote `main` as `4a3a3845474161764cf1aaf1578d851f56b7da29`; it does not replace the historical live-checkpoint observations above.

| Area | Implemented behavior | Verification / remaining limit |
|---|---|---|
| Hard eligibility | Shared deterministic gates require recent HTTPS evidence for activity, India employment, size and direct/permanent payroll; requirements and the approved India location list also gate selection. Unknown, stale, contradictory and unsupported evidence do not pass. | Python synthetic tests use the approved 7-day vacancy and 90-day employer evidence windows. |
| Headcount and aliases | Preserve 1,000 employees for non-remote and 500 for remote roles in cached and direct checks. Reused counts retain their source verification time. Closed requisitions exclude stable aliases; a batch returns fewer than five when fewer qualify. | Threshold, stale evidence, closed alias and partial-batch regressions passed. No live employer evidence or candidate count was checked. |
| Applications view | Expose vacancy source, eligibility status/blockers, browser connection, progress, missing answers, documents and next safe action. A persisted ready state is not presented as ready unless current eligibility, missing/check/document preconditions pass. | Latest full synthetic UI suite: 157 passed. Focused checks cover stale-ready suppression, source/progress failure isolation and answer-draft preservation. No live ATS form was inspected. |
| Recovery and persistence | Retain published recovery/session identity mechanisms; this milestone did not replace them. | Existing focused recovery regression passed as part of the Windows suite. No production browser session was inspected or changed. |
| Validation | Latest post-audit-correction Windows Python: 583 passed, 91.94% aggregate coverage. Latest full synthetic UI: 157 passed. The immediately preceding F1-F8 run passed 576 Python tests at 91.94% coverage. R1 passed four consecutive isolated runs after its fixture-only termination correction; R2 passed 2 tests; relevant lifecycle Python passed 40 tests. Focused new-module coverage: eligibility 96%, employer evidence 100%. | Earlier milestone runs recorded 529 Python passes at 91.84% coverage and 156 UI passes before the final F1-F8 and R1 verification. Historical failures and exact commands remain in the verification ledger. These synthetic tests do not establish live form acceptance. |

The reviewed 28-file checkpoint was committed and pushed normally without force. No database migration, deployment, production restart, browser/employer action, upload, Gmail operation, submission or schedule change accompanied publication.
