# Local-first job research checkpoint

Current priority: [live workflow repair](live-workflow-repair.md). At the latest recorded checkpoint, four applications were connected and awaiting inspection/eligibility verification; one was manually reported submitted but not independently verified; zero verified eligible pending candidates; and zero employer forms ready for review. A fresh eligible batch of five remains blocked. Historical targeted fixes and regression results are in the repair report. See [repair milestone plan](../specs/live-workflow-repair.md). No repair commit, push, field filling, upload or employer submission.

Privacy refactor implemented and verified locally; legitimate concurrent operational activity confirmed by the user. Final publication approval remains required. This document is the sanitized publication handoff. Original operational notes and candidate-specific history were preserved under ignored local data before editing; they are not publication inputs.

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

The six-workspace UI proposal remains separate from production visual acceptance. Design contract, interactive proposal, 78 proposal images and 72 private baseline screenshots are preserved. Production visual acceptance is NOT COMPLETE; no redesign implementation has started.

No new commit was created or published during this refactor.
