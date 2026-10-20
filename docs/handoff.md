# Local-first job research checkpoint

## Current published handoff

The milestone is published on local and remote `main` at `4a3a3845474161764cf1aaf1578d851f56b7da29`. Its 28 approved files add evidence-backed eligibility checks, mode-specific employer-size validation, closed-alias exclusion, richer Applications projections and synthetic UI failure-isolation coverage.

**Implemented:** deterministic gates require recent sourced evidence; queue and browser-preparation checks share those gates; the UI displays blockers and safe next actions without overstating ready states; batch selection remains capped at five and may return fewer.

**Verified:** latest full Windows Python passed 583 tests with 91.94% aggregate coverage; the preceding F1–F8 run passed 576. The complete synthetic UI suite passed 157 tests with zero skips and R2 passed two. After a fixture-only Windows process-control repair, R1 passed four consecutive runs; relevant lifecycle Python passed 40 tests. Exact commands are in [verification](ai-handoff/verification.md).

**Blocked / planned:** current production records, Chrome sessions, live employer evidence and a genuinely eligible batch were not inspected. No five-candidate or live-form acceptance is claimed. The approved freshness policy is 7 days for vacancy evidence and 90 days for employer evidence. Employer-specific work authorization, live ATS form acceptance and production activation remain unverified.

**Approved policy, pending implementation:** automatic creation of unsent Gmail drafts is permitted only after verified recipient and role relevance, current eligibility and employer evidence, approved-fact grounding, exact preview, durable audit history, duplicate prevention, uncertain-outcome recovery and preservation of user edits. The live adapter remains disabled pending implementation, security verification and release testing. Sending, forwarding, reply-sending and automatic employer submission remain prohibited without their own authorization.

**Discovery gap:** LinkedIn and Naukri are not comprehensively covered by Gmail alerts or indirect ATS links. Later work may evaluate permitted saved-search alerts, public employer links, structured manual imports and TechReferrals as a supplementary unverified source; no integration or complete-coverage claim exists. Stage 2 read-only application reconciliation remains next.

The checkpoint was committed and pushed normally without force. No deployment, service restart, schedule change, Gmail operation, employer form interaction, upload or submission accompanied publication. The earlier live-workflow report below records a historical read-only checkpoint; its application counts are not current-state inspection.

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
