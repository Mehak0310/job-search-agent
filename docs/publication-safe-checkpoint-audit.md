> Historical pre-refactor audit. Superseded by [privacy refactor verification](privacy-refactor-verification.md). Current repository is public; no publication clearance or authorization is implied.

# Publication-safe checkpoint audit

Status: cleanup applied; publication BLOCKED pending review of the source privacy refactor. No application feature or production UI change was made. No source edits were applied as part of cleanup.

## Destination

Existing repository: https://github.com/Mehak0310/job-search-agent, verified **public** through repository metadata. Visibility unchanged. Branch `main`, upstream `origin/main`, HEAD `5eb64454f4e04c0e0bfe624c2d70380e7cc2346f`. Permissioned `git fetch origin` succeeded; local and remote were 0 ahead / 0 behind. Public branch API reports `protected: false`; branch rule list is empty. No merge, rebase, reset, history rewrite, force push or PR.

## Actual cleanup

- `.gitignore`: appended only `/artifacts.zip` and `/artifacts/command-center-proposal.zip`; previous local ignore additions preserved.
- `docs/m4-runbook.md`: sanitized three machine-specific path prefixes.
- `docs/r1-implementation-report.md`: sanitized three machine-specific path prefixes.
- Added [source remediation proposal](publication-privacy-remediation-proposal.md), this audit and current publication status notes; prior local work retained.

The proposal ZIP present at cleanup start retained its size and modification time. The root `artifacts.zip` was already absent at that point; this task did not delete, move or modify it. Both exact ignore rules are verified. No private database, resume, DOCX, environment or archive is currently tracked under the audited sensitive-path checks.

## Privacy findings and staging exclusions

1. Real candidate identity, employment/education, compensation and experience values are embedded in pending source, principally `profile_m31.py`, with identity/default/presentation dependencies elsewhere. Keep those changes out of staging until the proposed refactor is reviewed and applied. Removing a required imported module alone would produce an incomplete checkpoint.
2. Detailed operational reports and one-shot live-case scripts contain personal application/candidate context. Unresolved originals remain local and excluded. Sanitizing absolute paths does not clear all their content.
3. Current pattern scan found no credential literals or credential assignments. This is limited pattern-based evidence, not a blanket guarantee. Credential-related filenames in generic adapters refer to ignored local files; their raw contents were not read or staged.
4. Fixture email hits were reviewed as synthetic, service-sender examples or intentional hostile URL cases. Public repository-owner references are destination metadata, not candidate-contact evidence.
5. The 78 proposal PNGs were read and hashed, reviewed via the synthetic HTML source and all-image contact sheet, and left unchanged. The 72 actual baseline screenshots remain under ignored `data/`. Synthetic proposal assets are not proof of production visual acceptance.

Private location-only inventory is `data/publication-audit/inventory.json`. It classifies source/configuration, tests/automation/fixtures, specs/docs, synthetic visuals and generated artifacts. Aggregate evaluation JSON is separately held for intended-versioning review, not automatically cleared. Raw logs, traces, databases, documents, credentials, caches and authentication state remain excluded. No broad `git add` was used; nothing is staged.

## Verification

| Check | Actual result |
|---|---|
| Focused safety/approval tests | 62 passed; one upstream deprecation warning |
| Full Python / coverage | 497 passed; 91.62%, 90% gate retained; one upstream warning |
| R1 isolated integration | Initial sandbox run failed simulated termination (RUNNING instead of INTERRUPTED) and fixture cleanup. Permission-corrected run passed 1/1 in 39.6s; no source fix or weakened assertion. Only exact failed-fixture process trees were cleaned up. |
| R2 isolated integration | 2 passed in 18.4s; fake adapter / disposable database only |
| Live GET-only Command Center / orchestration | 31/31 passed; zero write/external attempts or page errors |
| Proposal routes / existing images | 72/72 geometry/navigation checks; 78 original proposal hashes unchanged, 72 baseline files present; zero network requests |
| Dependency integrity | `pip check` passed |
| Python compilation / all static JS syntax | Passed |
| Whitespace | `git diff --check` passed; existing LF/CRLF conversion notices only |
| Full Playwright | 152 passed in 10.3 minutes; R3 Command Center cases included |
| Read-only protected-state preservation | Final comparison passed: all seven snapshot groups unchanged, covering nine canonical tables, six document references, browser outcomes/session state, manual text and draft operation count. SQLite integrity OK; zero FK errors. This is the project protected-state procedure, not a claim that every untracked runtime/cache file was byte-compared. |

Commands: `.venv\Scripts\python.exe -m pytest tests/test_workflow_guard.py tests/test_preparation_authorizations.py tests/test_orchestration.py tests/test_r2.py -q --no-cov`; `.venv\Scripts\python.exe -m pytest -q`; `npm.cmd run test:e2e`; `npm.cmd run test:e2e:r1` (sandboxed, then permission-corrected); `npm.cmd run test:e2e:r2`; `.venv\Scripts\python.exe -m scripts.verify_command_center --output-dir data/publication-audit/live --orchestration`; `.venv\Scripts\python.exe -m pip check`; `.venv\Scripts\python.exe -m compileall -q job_agent scripts tests`; `node --check` for each static JS file. Extra read-only proposal and preservation scripts/logs stay under ignored `data/publication-audit/`.

## Outcome and next action

No commit or push: privacy gate has not passed, even if functional checks pass. HEAD remains unchanged, all previous local modifications retained, no staged diff to claim reviewed. Publication is not ready for a cloud source checkout until the dependency-complete privacy refactor, report sanitization and exact staging audit are complete. See the concrete [remediation proposal](publication-privacy-remediation-proposal.md) for review before source edits.

R3 functional evidence is retained; production visual/design acceptance remains NOT COMPLETE. No production redesign, schedule activation, real Gmail draft, email, submission, original document change or production migration occurred.

Final staging check: index empty; cached diff/stat/check empty. No files committed or pushed. Final tests retained existing coverage gate and assertions. The R1 rerun required process permissions; its initial failure and test-only cleanup remain recorded above.
