# Milestone 2A.1 implementation plan

Status: implemented and verified; parallel source fetching deferred (2026-10-10)

## Goal
Expand verified public employer coverage and make eligibility, seniority, lifecycle, ranking, metrics, and dashboard behavior explicit while preserving all user data and manual statuses.

## Tasks
- [x] Read repository instructions, prior specifications, verification evidence, architecture, connectors, storage, API, UI, and tests.
- [x] Confirm Git state (workspace has no Git metadata available to `git status`).
- [x] Add schema v3 with reversible backup, evidence fields, source verification metadata, listing lifecycle, and duplicate groups.
- [x] Add three-state India eligibility, evidence/confidence, seniority parsing, relevant-experience handling, deterministic ranking, and freshness.
- [ ] Add parallel source fetching. Per-source cooldowns, lifecycle transitions, budgets, and expanded persistent metrics are complete; current source execution remains sequential.
- [x] Verify candidate employers and enable only boards whose official public endpoint identifies the intended employer.
- [x] Extend API and dashboard filters, explanations, source evidence, and efficiency views.
- [x] Add mocked regression tests and browser interaction tests.
- [x] Run full tests, coverage, static checks, migration/integrity checks, two bounded live scans, and browser QA.
- [x] Update architecture, security, decisions, verification, and README with measured results and limitations.

## Constraints
Public GET-only Greenhouse/Lever access; bounded request/runtime/response budgets; no accounts, LLM calls, applications, scheduler registration, persistent system changes, invented boards, or status loss.
