# Local-first job research checkpoint

## Published F1–F8 and R1 checkpoint

Branch `main` is published at `4a3a3845474161764cf1aaf1578d851f56b7da29`. Exactly 28 approved files were committed and pushed normally without force; local and remote were synchronized and the working tree was clean at publication. No deployment, live workflow or production database was accessed.

### Implemented

- Verification tasks re-assess existing sourced evidence without writing new evidence or timestamps. Reused global headcount evidence retains its original `verified_at` and must be recent, HTTPS-sourced, scope-matched and above the applicable threshold.
- India-employment and payroll checks use narrow affirmative/negative patterns; missing, ambiguous and contradictory text does not pass. Headcount ranges crossing the threshold remain unresolved, and explicit current below-threshold evidence fails.
- Location eligibility requires a recent vacancy reference, explicit India location and an approved region; foreign-plus-India listings and unknown work modes remain unresolved.
- The Applications API removes raw discovery metadata, descriptions and private Gmail message references after internal assessment. Manual submission outcomes dominate stale legacy readiness in backend and UI filters, with duplicate preparation actions disabled.
- The approved policy is 7 days for vacancy activity and vacancy/requirements evidence, and 90 days for employer headcount, India-employment and payroll evidence. Missing, expired, future-dated, contradictory or unverifiable evidence remains `NEEDS_VERIFICATION`.

### Verified

- Latest full Windows Python regression: **583 passed**, **91.94% aggregate coverage**; the preceding F1–F8 run had 576 passes at the same coverage. Changed Python module coverage: eligibility 96%, employer evidence 100%, requirement clauses 100%, M2D 98%, browser store 97%, priority queue 94%.
- Focused Python regression: **159 passed** across requirements freshness, eligibility, employer evidence, verification-task, browser-application and priority-queue tests.
- Complete synthetic UI: `npm.cmd run test:e2e -- --output=data\codex-f1-f8-playwright-final --reporter=list` — **157 passed**.
- R1: **four consecutive isolated runs passed** after repairing the fixture-only termination path. Windows denied the fixture's external `taskkill`; the fixture now uses its owned process handle and avoids creating Chrome in the deliberate hold case. Relevant lifecycle Python: **40 passed**. R2 rerun: **2 passed**.
- Focused manual-submission UI regression: **1 passed**; existing submitted-state UI regressions: **4 passed**. Pylance reports no diagnostics in eligibility, employer-evidence or browser-store modules. One Starlette/httpx deprecation warning remains.

### Blocked and planned

- Live eligibility evidence and current status of the four previously tracked applications were not rechecked. Synthetic passes do not establish employer eligibility or form readiness.
- No five-candidate live batch is claimed. The queue returns fewer than five where fewer than five opportunities meet the verified gates.
- Employer-specific work-authorization questions, live ATS compatibility, form read-back, production database migration/activation and visual acceptance remain unverified or planned.
- Publication did not include a service restart, schedule change, Gmail action, employer navigation, upload, submission or deployment.
- Product policy permits future automatic creation of unsent Gmail drafts after all recipient, relevance, eligibility, employer-evidence, grounding, preview, audit and recovery gates pass. The live adapter remains disabled pending implementation, security verification and release testing; sending and automatic employer submission remain prohibited.
- LinkedIn and Naukri coverage is incomplete. Permitted alerts, public employer links, structured manual imports and TechReferrals as a supplementary unverified referral source require later investigation; no new source integration is implemented.
- The selected six-tab Command Center prototype and design contract remain unchanged. Later acceptance must use persisted per-source coverage, original referral attribution, eligibility/verification and complete Gmail draft lifecycle states without invented readiness or recruiter details.
- Stage 2 read-only reconciliation remains the next operational milestone.

The earlier live-workflow report below records a historical, separately authorized read-only checkpoint; its application counts are not a current-state inspection. The previous repair checkpoint is documented in [live workflow repair](live-workflow-repair.md) and [repair milestone plan](../specs/live-workflow-repair.md).

## Historical privacy-refactor checkpoint

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
