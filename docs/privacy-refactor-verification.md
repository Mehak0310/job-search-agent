# Privacy refactor â€” local verification and publication proposal

Status: IMPLEMENTED AND VERIFIED LOCALLY. Concurrent operational appends were confirmed legitimate by the user. Final publication approval is still required. No commit or push is authorized in this phase. Production visual acceptance remains NOT COMPLETE.

## Implemented protections

Private confirmation/configuration, the complete persisted profile, original source/docs/tests and pre-change protected-state fingerprints were saved under ignored `data/privacy-refactor/` before source edits. The confirmation file has inheritance disabled and explicit access for the host user, the authorized sandbox account and SYSTEM; general Users, Authenticated Users and Everyone are excluded. No secret values are printed in this report.

`CandidateProfile` and `SearchBackground` now have neutral fresh-install identity, professional evidence and duration defaults. Existing database profiles remain authoritative; startup does not apply confirmations or approve facts. Explicit local reconciliation requires a confirmation reference and validates its fields. Private local document-role aliases preserve legacy references; manifest bytes and original document bytes were not changed.

Application text uses accepted persisted identity and manifest roles. Missing identity and ambiguous/missing document roles block preparation. Hash validation, exact draft approval, security hooks, history and manual edits remain intact. No production reconciliation, packet regeneration or profile update occurred.

Fictional test profiles are injected explicitly. Privacy tests cover neutral initialization, unchanged persisted profiles, malformed/missing confirmations, document-role ambiguity, local aliases and unsupported confirmation fields. The complete UI suite now has a disposable localhost server with a fictional packet so existing populated editor assertions run without private data. Its fixture-only teardown does not operate the production server.

Raw operational reports and personal one-shot scripts remain local under explicit ignore rules. Original handoffs are backed up privately; current handoff/status and publication checklist are sanitized. The design contract, prototype and original 78 proposal /72 baseline images are preserved.

## Actual validation

Final checks:

| Command / check | Result |
|---|---|
| `.venv\Scripts\python.exe -m pytest -q` | 502 passed, 91.57% coverage; existing 90% gate; 392.97s; one upstream deprecation warning |
| `npm.cmd run test:e2e` (fresh populated disposable server) | 152 passed, no skips, 3.3 minutes; graceful fixture shutdown |
| `npm.cmd run test:e2e:r1` (required fixture process permissions) | 1 passed, 55.9s |
| `npm.cmd run test:e2e:r2` | 2 passed, 29.1s |
| Focused privacy/profile/safety | 62 passed |
| Focused privacy/browser/profile/persistence | 60 passed |
| Corrected explicit-fixture assertions | 67 passed |
| Dependency integrity, Python compilation, static JavaScript syntax | Passed |
| Known-private-fact, contact, credential-literal/assignment and absolute-user-path scans | No findings in proposed public paths |
| Local imports | No missing modules; personal omitted scripts are not runtime dependencies |

Coverage is not 100%; no blanket live-provider or accessibility certification is claimed. Intermediate failures are not hidden: the first full Python run had five assertions tied to old personal defaults (497 passed, five failed). The corrected tests inject fictional values or assert neutral defaults; the 67-test correction set passed. Focused privacy/profile/safety tests passed 62 cases; the subsequent privacy/browser/profile/persistence set passed 60 cases.

The initial disposable UI run completed 150 cases and skipped two editor cases because it had no packets, then required test-only process cleanup for a teardown stall. A fictional packet and explicit fixture-only graceful teardown were added. Final full UI verification must run from fresh fixture initialization with no skipped editor assertions. No production process was stopped.

## Protected state and assets

The project's read-only snapshot procedure compares nine canonical tables, document references/hashes, browser outcomes/session state, manual text and Gmail operation count. Final strict comparison found two appended operational evidence rows during verification. A previously verified backup exactly matches the initial nine-table fingerprint; comparison proves every pre-existing row is unchanged and present. The other eight canonical tables, six document references, browser state, manual text and draft count match. Integrity is OK and FK errors are zero. The complete persisted profile equals the private preserved copy. The user explicitly confirmed the concurrent append-only activity was legitimate. Preservation is cleared with those authorized additions retained, not by claiming strict table equality. No database restoration or rebaselining was performed. All 152 preserved asset hashes match: 78 proposal images, 72 baseline images, the design contract and prototype. Confirmation ACL inheritance is disabled; three explicit trusted access rules and zero broad-access rules were verified. Strict equality of the evidence table is NOT claimed. The original baseline is retained; all original rows match and authorized appended rows remain present. No production write was used to force equality. This is not an assertion that every cache/runtime file is byte-identical. No production database migration or reconciliation is authorized.

## Git boundary

No commit or push. The real staging index will remain untouched. A separate ignored review index/manifest may be used to inspect the exact proposed diff and Git blobs without altering existing staging. The [complete file proposal](publication-file-proposal.md) enumerates all 265 added/modified paths against HEAD (309 files in the full proposed tree). It includes the prior R1/R2/R3 implementation and tests, not just this privacy refactor. Nineteen raw reports, two operational specifications and thirteen personal scripts are explicitly excluded in addition to private data, archives, authentication and generated outputs. Separate review-index audit passed: all 309 Git blobs scanned, zero findings, zero unexpected deletions and cached whitespace check passed. Results, exact diff/stat and blob manifest are recorded under ignored local audit data. No unexpected deletion is proposed.

Proposed destination: the existing `origin`, branch `main`, upstream `origin/main`. Proposed message: `feat: checkpoint R1-R3 with private local profile configuration`. Fresh checks: repository visibility PUBLIC, branch unprotected, no branch rules, local and remote HEAD both `5eb64454f4e04c0e0bfe624c2d70380e7cc2346f`, zero ahead/behind after fetch. Normal fast-forward eligibility is established for that observed state; it must be rechecked if publication is approved later. No force push, history rewrite, merge, PR, visibility change, schedule or external action.

Runtime limitation: the production backend is intentionally not restarted. New source is verified in isolated Python/UI/R1/R2 environments; this phase does not claim live activation of the refactor. Production UI redesign has not started. Final publication approval remains a separate user decision.

## Exact changes in this privacy refactor

Earlier pending R1/R2/R3 work is also included in the complete publication proposal. This approved refactor itself changed the following paths; originals are preserved privately.

### Modified existing files

- `.github/workflows/playwright.yml`
- `.gitignore`
- `docs/handoff.md`
- `docs/project-status.md`
- `docs/publication-checklist.md`
- `docs/publication-privacy-remediation-proposal.md`
- `docs/publication-safe-checkpoint-audit.md`
- `e2e/fixtures.ts`
- `job_agent/application_answers.py`
- `job_agent/browser_applications.py`
- `job_agent/candidate.py`
- `job_agent/m3.py`
- `job_agent/profile_m31.py`
- `job_agent/review_workflow.py`
- `job_agent/service.py`
- `job_agent/static/index.html`
- `job_agent/static/portal.css`
- `package.json`
- `specs/browser-preparation.md`
- `specs/m3-acceptance.md`
- `specs/m3-tasks.md`
- `specs/m3.1.md`
- `tests/conftest.py`
- `tests/r1_fixture_server.py`
- `tests/test_api.py`
- `tests/test_browser_applications.py`
- `tests/test_classification.py`
- `tests/test_discovery.py`
- `tests/test_m2b.py`
- `tests/test_m2d.py`
- `tests/test_m2d1.py`
- `tests/test_m3.py`
- `tests/test_m31.py`
- `tests/test_m4.py`
- `tests/test_preparation_authorizations.py`
- `tests/test_r2.py`
- `tests/test_release_step1.py`
- `tests/test_review_workflow.py`

### New files

- `docs/implementation-checkpoint.md`
- `docs/privacy-refactor-verification.md`
- `docs/publication-file-proposal.md`
- `e2e/privacy-teardown.ts`
- `job_agent/private_config.py`
- `playwright.privacy.config.ts`
- `specs/privacy-refactor-plan.md`
- `specs/release-safety.md`
- `tests/synthetic_profile.py`
- `tests/test_privacy_config.py`
- `tests/ui_fixture_server.py`

## Remaining limitations and approval

No unresolved private-marker or credential finding remains in the intended content. Concurrent append-only operational activity is accounted for by explicit user confirmation. No unresolved preservation-attribution blocker remains; publication still requires separate final approval. Pattern/known-value scans are not proof against every conceivable secret and do not audit all historical Git commits. Private production state was compared read-only; no cloud job, production restart, live provider action or real application/Gmail operation was used as verification. Production visual parity remains pending.

The real staging index, HEAD and remote are unchanged. Proposed message and destination above are for review only. Final user approval is required before any commit or push.

Review preparation also found trailing whitespace in previously untracked files. CSS trailing-space and Python EOF/BOM cleanup were formatting-only; Python AST equality was checked. Two raw historical operational specifications were excluded, with a generic release contract published instead. No protected design/prototype bytes changed.

Private runtime configuration: retain `data/privacy-refactor/candidate-confirmations.json`; it is not a disposable test log. It preserves accepted local values and legacy document-role aliases for later activation. Do not publish or automatically reapply it.
