# Local-first job research checkpoint

## Current local handoff

The current uncommitted milestone is based on `main` at `e94340d61ee88aea137a878ad1e48ca860f3e60f`. It adds evidence-backed eligibility checks, mode-specific employer-size validation, closed-alias exclusion, richer Applications projections and synthetic UI failure-isolation coverage.

**Implemented:** deterministic gates require recent sourced evidence; queue and browser-preparation checks share those gates; the UI displays blockers and safe next actions without overstating ready states; batch selection remains capped at five and may return fewer.

**Verified:** focused Python passed 159 tests; full Windows Python passed 576 tests with 91.94% aggregate coverage. The complete synthetic UI suite passed 157 tests and R2 passed two. After a fixture-only Windows process-control repair, R1 passed four consecutive runs; relevant lifecycle Python passed 40 tests and R2 passed again. Exact commands are in [project status](project-status.md).

**Blocked / planned:** current production records, Chrome sessions, live employer evidence and a genuinely eligible batch were not inspected. No five-candidate or live-form acceptance is claimed. The approved freshness policy is 7 days for vacancy evidence and 90 days for employer evidence. Employer-specific work authorization, live ATS form acceptance and production activation remain unverified.

No commit/push, service restart, schedule change, Gmail operation, employer form interaction, upload or submission was performed in this milestone. The earlier live-workflow report below records a historical read-only checkpoint; its application counts are not current-state inspection.

## Historical workflow checkpoint

At the earlier recorded checkpoint, four applications were connected and awaiting inspection/eligibility verification; one was manually reported submitted but not independently verified; zero verified eligible pending candidates; and zero employer forms ready for review. A fresh eligible batch of five remained blocked. The publication handoff below is historical.

Privacy refactor implemented and verified locally; legitimate concurrent operational activity confirmed by the user. Final publication approval remains required. This document is the sanitized publication handoff; private source evidence is excluded.

## Implemented

- Neutral fresh-install identity, career and experience defaults. Explicit persisted profiles remain authoritative.
- Generic local confirmation loader; reconciliation still requires an explicit invocation and accepted confirmation source. Startup never applies private confirmations.
- Hash-bound manifest document roles with optional private legacy aliases. No original file or manifest was renamed or modified.
- Application text derives identity from persisted evidence; missing identity remains an explicit blocker. Historical packets, manual edits and approvals were not regenerated.
- Synthetic fixtures and a disposable full-UI test server. No private candidate defaults are needed for a fresh test checkout.
- R1/R2/R3 functionality, deterministic safety hooks, local-only binding, manual outcomes, exact draft approval and dormant schedules retained.

## Verification and publication boundary

See [privacy refactor verification](privacy-refactor-verification.md) for exact final commands, coverage, protected-state comparison, intended Git manifest and exclusions. Final Python:502 passed/91.57%; full populated UI:152 passed/no skips; R1:1 passed; R2:2 passed. Original protected rows and all design/image hashes match; the user confirmed the two operational evidence appends were legitimate concurrent activity. No production restoration or rebaseline. Exact file proposal and audit are available for final publication review. No commit or push is authorized in this phase; final user approval is required.

Production backend was not restarted or reconciled. New source is exercised only in isolated tests. No production SQLite writes, original document changes, new fact approval, packet regeneration, external messages, submissions or schedule activation.

The six-workspace UI proposal remains separate from production visual acceptance. Design contract and interactive proposal are preserved separately. Production visual acceptance is NOT COMPLETE; no redesign implementation has started.

No new commit was created or published during this refactor.
