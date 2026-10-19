# Publication privacy remediation — source changes proposed for review

Status: user-approved privacy refactor implemented; final verification in progress. No commit/push authorized. See privacy-refactor-verification.md. The proposal below records the approved scope; no production UI implementation is included.

The existing GitHub repository is public. The pending local source embeds actual candidate facts rather than merely reading ignored local data. No credential literal was detected by the current pattern scan; that is not an exhaustive credential clearance. No sensitive values are reproduced here.

## Changes already authorized and applied

- Added exact root-anchored ignore rules for `artifacts.zip` and `artifacts/command-center-proposal.zip`.
- Replaced machine-specific user/workspace prefixes with `<user-home>` / `<workspace>` in `docs/m4-runbook.md` and `docs/r1-implementation-report.md`.
- Preserved the existing archive present at cleanup start, source, candidate database, canonical documents, baseline/proposal images and local working changes. The root `artifacts.zip` was already absent when this cleanup started; this task did not delete it.

## Source changes requiring approval

| Scope | Proposed change | Protection / validation |
|---|---|---|
| `job_agent/profile_m31.py` | Replace embedded identity, employment/education, compensation and professional-duration facts with an explicitly loaded ignored local confirmation file. Keep reconciliation generic and fail closed when no explicit confirmation source is available. | Preserve existing local values outside Git before editing source. Do not invoke reconciliation on production or approve any new fact. No migration or production database write. |
| `job_agent/candidate.py`, `job_agent/service.py` | Use neutral fresh-install defaults and return accepted database/manifest values for names, locations, experience and document display. Existing persisted profiles remain authoritative. | Do not overwrite an existing profile. Test fresh empty state and unchanged existing profile separately. |
| `job_agent/m3.py` | Render names/signatures from accepted profile evidence; resolve document roles from the approved local manifest instead of named personal constants. Missing identity/document evidence remains an explicit blocker. | Preserve immutable packet revisions, manual edits, approval snapshots and historical outcomes. Do not regenerate production packets. |
| `job_agent/application_answers.py`, `browser_applications.py`, `review_workflow.py` | Resolve document roles through the existing hash-bound manifest. Preserve legacy canonical references through local metadata, not by renaming files or rewriting history. | Original resume/document bytes and hash checks unchanged. Unknown required facts still block preparation; declarations stay manual. |
| Tests and integrated fixtures | Replace real candidate-derived constants with independently fictional facts and generic document aliases. Inject fixtures explicitly rather than using private defaults. | Retain all safety, persistence, R1/R2/R3 and approval assertions. Do not weaken tests or coverage. |
| Personalized static copy | Replace fixed career-background assertions with accepted-profile projections or neutral explanatory copy. | Privacy-only text/data binding; no production redesign or change to accepted local evidence. |
| Candidate-specific one-shot scripts | Keep historical live-case scripts local-only; publish generic guarded tooling only where useful after removing fixed application IDs and personal references. | Do not execute those scripts or replay any live operation. Do not stage omitted personal scripts. |

Detailed operational handoffs/reports also contain actual application/candidate context. Keep unresolved originals local and excluded from staging. A publication copy must retain implementation/test evidence while removing individual candidate facts and application-history details. Existing local records must be backed up before any such edit. A public source checkpoint must remain dependency-complete; simply omitting a required imported module is not a safe solution.

## Exclusion and clearance policy

Keep archives, `data/`, environments, credentials, browser profiles/authentication, traces, caches, logs and real screenshots local. Current proposal images are synthetic; they were reviewed via their source and an all-image contact sheet without rewriting the 78 originals. Ordinary fixture emails use synthetic domains or intentionally hostile URL cases; a pattern hit alone does not establish a real contact.

The tested candidate identity defaults and the private reconciliation module are pending local changes, not the same content in fetched HEAD. This does not constitute a comprehensive historical privacy audit. Do not rewrite history, rotate credentials, change visibility, push a partial broken checkpoint or publish candidate facts.

## Required gates after approval

1. Preserve local personal configuration under ignored data; implement only the reviewed generic-source refactor.
2. Rescan all intended blobs and synthetic images; inspect the exact staged diff, tracked sensitive paths and unexpected deletions.
3. Run focused safety/persistence checks before full Python/coverage, Playwright and isolated integration checks. Verify original local database/document hashes read-only.
4. Re-fetch and recheck remote SHA, visibility, branch rules and destination. Normal fast-forward push only after every publication gate passes.

Approval of this proposal authorizes the privacy refactor only; it does not approve the production UI redesign, new candidate facts, live external actions or schedule activation.
