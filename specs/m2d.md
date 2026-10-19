# M2D: unified discovery, coverage and reliable handoffs

## Scope

M2D owns persistent discovery, verification queues, bounded coverage accounting, review shortlists and downstream data contracts. It preserves the reviewed requirements of Major Job Discovery V2.9, Gmail Job Discovery V3.4, Specialist Job Discovery V1.2, Remote Job Discovery V1.0 and Application Pipeline Stages 3-5 V1.4. Their 09:55, 10:20, 10:00, 10:30 and 11:30 Asia/Kolkata times are reference metadata only. The local engine consumes committed completed snapshots and never infers completion from time.

M3 is excluded. M2D does not write tailored applications, research contacts, create drafts, send messages, submit forms, install schedules, alter ChatGPT schedules or claim Library upload.

## Design

- Four streams share one canonical job identity and one SQLite operational store. Source ownership limits broad sweeps while cross-stream observations retain provenance.
- Discovery captures broad metadata first. Verification is a separate persistent bounded queue. A failed source cannot discard healthy results.
- Lifecycle, eligibility, verification and readiness are independent. Readiness is one of `FULLY_VERIFIED_APPLICATION_READY`, `READY_FOR_PORTAL_REVIEW`, `EMAIL_DRAFT_READY`, `PROMISING_NEEDS_VERIFICATION`, `EXCLUDED`; `ACCESS_BLOCKED` is a source/check outcome.
- Local/hybrid headcount passes at 1,000 or more. Fully remote India-eligible headcount passes at 500 or more. Unknown headcount, payroll, India eligibility or dates stay pending.
- Coverage uses `UNATTEMPTED`, `ATTEMPTED_NO_USABLE_RESULTS`, `PARTIALLY_SEARCHED`, `MEANINGFULLY_SEARCHED`, `EXHAUSTIVELY_SEARCHED`, `ACCESS_BLOCKED`. Exhaustive applies only to the bounded source/query represented by its checkpoint.
- Immutable completed or explicitly partial snapshots carry schema version, counts, artifact identity and SHA-256 checksum. Consumers advance idempotent checkpoints by snapshot ID.
- Gmail live access is blocked unless local authorization exists. Synthetic/export ingestion reads received messages only, extracts every specific vacancy, preserves message identity and distinguishes received time from vacancy publication time.
- JobQueue-v1 XLSX exports contain Jobs, Draft Inputs, Verification Queue, Source Coverage and Run Audit. Major exports also contain Employer Careers Registry and Application Review Shortlist. Excluded is included when applicable. Files are local handoffs with a manual-transfer manifest, never proof of Library upload.

## Safety and budgets

Imported job, mail and JD text is untrusted data. Public connectors remain GET-only and cannot bypass login, paywall, CAPTCHA or guessed ATS IDs. Runs have request, page, response-size and runtime bounds; unfinished work persists and produces `PARTIAL`. Audit stores metadata only. Resume bytes, extracted text, mail content, credentials, databases, caches, models, workbooks and browser profiles remain ignored local data.

## Source truth

Each named source records an implementation state independently from coverage: `IMPLEMENTED_LIVE_VERIFIED`, `FIXTURE_TESTED`, `MANUAL_IMPORT_ONLY`, `ACCESS_BLOCKED` or `NOT_IMPLEMENTED`. Registry presence does not prove coverage. Historical live verification is dated; fixture/import success is never reported as live mailbox or platform coverage.

## Profile conflicts

Schedule defaults are advisory requirements. Existing user-edited preferences and accepted evidence remain authoritative. Conflicts are recorded with stored and schedule values before any override. No salary, shift, notice-period or additional experience preference is invented.

## JobQueue-v1 contract

`Jobs` columns: `JobKey`, `Lifecycle`, `Eligibility`, `Verification`, `Readiness`, `Company`, `Title`, `Location`, `WorkMode`, `ExactVacancyURL`, `ProviderIDs`, `Streams`, `SourceProvenance`, `PublishedAt`, `PublishedPrecision`, `EmailReceivedAt`, `FirstDiscoveredAt`, `LastSeenAt`, `LastChangedAt`, `FitScore`, `FitEvidence`, `Gaps`, `EligibilityEvidence`, `MissingFacts`, `NextAction`.

`Draft Inputs` contains structured `JobKey`, company/title/link, verified facts, missing facts and constraints; it contains no M3 prose. `Verification Queue` contains task identity, check type, status, attempts, due time, blocker and checkpoint. `Source Coverage` contains source, stream, owner, implementation state, bounded coverage state, attempt/success/due timestamps, blocker and backlog. `Run Audit` contains immutable snapshot metadata and counts. Additional Major sheets follow the same stable JobKey.

## Acceptance

M2D is complete only when schema migration, source matrix, persistent queues, fairness, coverage metrics, Gmail export boundary, conservative status mapping, immutable snapshots, JobQueue-v1 round trip, dashboard visibility and preserved-data checks pass. Live source/mail coverage remains partial wherever access is blocked or not attempted.
