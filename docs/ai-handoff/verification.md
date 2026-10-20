# Shared AI handoff: verification ledger

Recorded: 2026-10-20. Keep observed results, historical reports and unrun checks distinct. The shared baseline is `6e195c8c9ec265f8bcd9628d44c68d0e4f17fcbb`. Documentation changes in this setup do not constitute a new application test run.

## Current local application-recovery/eligibility milestone

The commands below were observed in the Windows workspace before publication while the implementation was based on `e94340d61ee88aea137a878ad1e48ca860f3e60f`. The exact reviewed 28-file result was subsequently committed and pushed to local and remote `main` as `4a3a3845474161764cf1aaf1578d851f56b7da29`. Publication used a normal non-force push and did not rerun these tests, deploy, or access live employer, production database, Gmail or current application state.

| Exact command | Result |
|---|---|
| `.venv\Scripts\python.exe -m pytest tests\test_requirement_completeness.py tests\test_eligibility.py -q -p no:cacheprovider -o addopts='' --basetemp=data\publication-blockers-focused` | 99 passed; validates the seven-day requirement-evidence boundary and rejects missing, HTTP, file, JavaScript, malformed and credential-bearing requirement-source URLs; one existing Starlette/httpx deprecation warning |
| `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=data\publication-blockers-full-python` | 583 passed; 91.94% aggregate coverage; one existing Starlette/httpx deprecation warning |
| `npm.cmd run test:e2e -- --output=data\publication-blockers-playwright --reporter=list` | 157 passed in 2.9 minutes using the disposable local fixture server |
| `npm.cmd run test:e2e:r1 -- --output=data\r1-termination-fix-1 --reporter=list` | 1 passed in 30.0 seconds |
| `npm.cmd run test:e2e:r1 -- --output=data\r1-termination-fix-2 --reporter=list` | 1 passed in 28.7 seconds |
| `npm.cmd run test:e2e:r1 -- --output=data\r1-termination-fix-3 --reporter=list` | 1 passed in 28.8 seconds |
| `npm.cmd run test:e2e:r1 -- --output=data\r1-termination-fix-4 --reporter=list` | 1 passed in 35.0 seconds |
| `.venv\Scripts\python.exe -m pytest tests\test_r1_reliability.py tests\test_r1_workers_and_migration.py tests\test_workflow_guard.py tests\test_m4.py -q -p no:cacheprovider -o addopts='' --basetemp=data\r1-lifecycle-python` | 40 passed; one existing Starlette/httpx deprecation warning |
| `npm.cmd run test:e2e:r2 -- --output=data\r1-termination-r2 --reporter=list` | 2 passed in 18.1 seconds |
| `.venv\Scripts\python.exe -m pytest tests\test_requirement_completeness.py tests\test_eligibility.py tests\test_employer_evidence.py tests\test_m4.py tests\test_browser_applications.py tests\test_priority_queue.py -q -p no:cacheprovider -o addopts='' --basetemp=data\codex-f1-f8-focused-3` | 159 passed; one existing Starlette/httpx deprecation warning |
| `.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp=data\codex-f1-f8-full-python-final` | 576 passed; 91.94% aggregate coverage; one existing Starlette/httpx deprecation warning |
| `npm.cmd run test:e2e -- --output=data\codex-f1-f8-playwright-final --reporter=list` | 157 passed in 2.7 minutes |
| `npm.cmd run test:e2e:r1 -- --output=data\codex-f1-f8-r1 --reporter=list` | 1 failed: synthetic held worker did not terminate within 10 seconds; operation remained `RUNNING` instead of `INTERRUPTED` |
| `npm.cmd run test:e2e:r1 -- --output=data\codex-f1-f8-r1-rerun --reporter=list` | Same single failure reproduced; disposable worker lock remained held during temporary-directory cleanup |
| `npm.cmd run test:e2e:r2 -- --output=data\codex-f1-f8-r2-final --reporter=list` | 2 passed in 17.4 seconds |
| `.venv\Scripts\python.exe -m pytest -q --basetemp=data\milestone-full-python` | 529 passed; 91.84% aggregate line coverage; 509.62s |
| `.venv\Scripts\python.exe -m pytest tests\test_eligibility.py tests\test_employer_evidence.py tests\test_release_step1.py -q -o addopts='' --cov=job_agent.eligibility --cov=job_agent.employer_evidence --cov-report=term-missing --cov-fail-under=90 --basetemp=data\milestone-coverage-focused` | 29 passed; targeted coverage gate passed; eligibility 96%, employer evidence 100% |
| `npx.cmd playwright test --config=playwright.privacy.config.ts e2e\live-workflow-repair.spec.ts` | 4 passed; source/progress outage isolation, answer modal draft preservation and stale-ready suppression |
| `npm.cmd run test:e2e` | 156 passed in 4.7 minutes; one initial test-fixture timeout was corrected by supplying the newly required eligibility projection, then the full suite passed |
| `npm.cmd run test:e2e:r1` | 1 passed in 1.4 minutes; R1 synthetic fixture now supplies sourced eligibility facts and simulates a missing headcount evidence row rather than changing only a stale status flag |
| `npm.cmd run test:e2e:r2` | 2 passed in 29.1s |

Coverage in the latest full Python run for changed modules: `eligibility.py` 96%, `employer_evidence.py` 100%, `requirement_clauses.py` 100%, `m2d.py` 98%, `priority_queue.py` 94%, `browser_store.py` 97%. The post-audit correction added seven requirement-source URL cases, raising the full Python count from the preceding 576 to 583 without changing aggregate coverage. No tests were skipped or assertions suppressed. R1 root cause was fixture-only: Windows denied the fixture's external `taskkill` command, its nonzero result was ignored, and `process.wait` timed out. The fixture now terminates its owned `Popen` handle directly and does not create a Chrome child for the deliberate hold case. Production lease expiry and durable `INTERRUPTED` recovery were unchanged. Four consecutive R1 runs passed after the correction.

These results verify local deterministic behavior only. They do not establish that any real vacancy is eligible, that the previously tracked applications are currently reviewable, that five eligible opportunities exist, or that any live ATS form is accepted. The approved freshness windows are 7 days for vacancy evidence and 90 days for employer evidence.

Publication verification: the pre-commit audit returned `READY_TO_COMMIT`; the commit contained exactly 28 approved files; `git diff --cached --check` and the commit whitespace check passed; local and remote `main` both resolved to `4a3a3845474161764cf1aaf1578d851f56b7da29`; the working tree was clean and local/remote divergence was `0 0`. This records Git publication only, not a fresh application test or runtime acceptance run.

Documentation-only tracker reconciliation checked 55 unique issue IDs (`A01`–`A55`), all eight delivery stages, Markdown-only scope, local links, table shape, publication SHA references and targeted credential/private-path patterns. `git diff --check` passed. No Python or Playwright suite was rerun, and no live system was accessed.

## Historical local Windows evidence

Source: [privacy refactor verification](../privacy-refactor-verification.md), corroborated by the user handoff request. These results were not rerun or independently observed on Windows during this task. The report describes the pre-publication working tree based on an earlier commit, so the exact tested tree cannot be proven identical to the published baseline solely from that report.

| Recorded command | Reported outcome |
|---|---|
| `.venv\Scripts\python.exe -m pytest -q` | 502 passed; 91.57% coverage; existing 90% gate passed; one upstream deprecation warning |
| `npm.cmd run test:e2e` | 152 passed, no skips, populated disposable fixture server |
| `npm.cmd run test:e2e:r1` | 1 passed; required fixture process permissions |
| `npm.cmd run test:e2e:r2` | 2 passed |

The source report also preserves intermediate failures and subsequent corrections. Do not replace them with an assertion that every historical run passed. Older [publication audit](../publication-safe-checkpoint-audit.md) counts are superseded by that report's final verification, not additional current runs.

## Observed cloud Linux evidence

Observed during the preceding cloud onboarding session, on the shared baseline with tracked files unchanged. Python 3.12.14, Node 24.19.0 and npm 11.9.0 were observed. Python application/test/browser/export dependencies were installed through the CI dependency set constrained by `requirements.lock.txt`; optional embedding/GPU dependencies were omitted. Node dependencies used `npm ci` and the lockfile.

| Command / check | Actual outcome |
|---|---|
| `.venv/bin/python -m pip check` | Passed; no broken requirements |
| `.venv/bin/python -m pytest -q tests/test_api.py tests/test_entrypoint.py -o addopts=''` | 27 passed; focused API/entrypoint check, no coverage claim |
| `.venv/bin/python -m pytest -q --tb=short` | 476 passed, 26 setup errors, one upstream warning; 87.52% coverage; required 90% gate failed |
| `npx playwright test --config=<cloud-config>` | 152 passed, no skips; 2.1 minutes; Linux override with system Chromium and disposable synthetic UI server |
| `.venv/bin/python -m job_agent --port 8000` and local HTTP requests | Startup and restart passed; health status `ok`, submission disabled; dashboard, API schema and jobs endpoint returned 200 |

`<cloud-config>` redacts the machine-specific helper location from the recorded browser invocation; it is a placeholder, not a directly runnable command or a tracked configuration. The helper overrides Windows startup commands and browser selection without changing repository files. The bundled browser download was denied by network policy; installed system Chromium was used successfully. That override does not establish that the unchanged Windows-oriented npm commands run on Linux.

All 26 Python errors were attributed to browser fixtures hardcoding the Windows Chrome executable. They are errors, not passed or skipped tests. The lower coverage is the result of the incomplete Linux run, not evidence of an accepted gate exception. [P1](task-queue.md) must address portability in a separately authorized coding task; keep assertions and the 90% gate intact.

Cloud R1/R2 browser integration suites were **not run**. Full Windows/Linux parity, production activation, production visual acceptance, live-provider behavior and complete accessibility review are **not established**. Passing browser functionality does not prove screenshot parity or approve the visual baseline.

## Consolidated tracker addendum verification

On 2026-10-20, documentation-only checks were run against base commit `4a3a3845474161764cf1aaf1578d851f56b7da29` plus the eight preserved Markdown edits. PowerShell row checks found 55 issue rows, 55 unique IDs spanning A01–A55 and eight delivery-stage rows. Targeted content review confirmed the published checkpoint and latest 583 Python/91.94% coverage, 157 synthetic Playwright, four consecutive R1, two-test R2 and 40-test lifecycle results remain intact and historical totals remain labelled as historical.

The same review confirmed the approved Gmail draft-only policy, incomplete LinkedIn/Naukri coverage, candidate TechReferrals evaluation, expanded read-only Gmail discovery, persisted Command Center acceptance criteria and Stage 2 priority are represented without implementation-complete claims. No application tests were rerun because this task changes documentation only. `git diff --check` and final changed-path/privacy checks are recorded from the completed task result; no live service, production database, Gmail account, employer site or application workflow was accessed.

## Initial documentation setup verification

Scope: four new handoff files and a minimal `AGENTS.md` addition only, based on the clean `work` checkout at the shared baseline. Review checks cover local Markdown targets, table/fence consistency, privacy-sensitive patterns, whitespace and the exact proposed diff. No application tests are rerun for this documentation-only task. No application source, tests, environment configuration or production data is changed; no commit, push or PR is created.

Checks completed: `git diff --check` passed; `git diff --no-index --check /dev/null <new-file>` passed for each new Markdown file. An inline Python check of all five changed files passed for local link existence, consistent table columns, balanced fences, whitespace and targeted private-path/contact/credential patterns. Manual content review found no candidate facts, Gmail contents, credentials, production records or private local paths in the additions. These scans are scoped checks, not a guarantee against every possible secret. `git diff --cached --stat` was empty; `git branch --show-current` returned `work` and `git rev-parse HEAD` returned the shared baseline. The proposed tracked diff and each new-file diff were reviewed; only the five intended documentation paths are changed.

## Publication authorization and preflight

On 2026-10-19 the user explicitly requested committing and pushing the completed handoff. This supersedes the initial documentation phase's no-commit/no-push restriction for these five files only. `git fetch origin main` succeeded; `git rev-list --left-right --count HEAD...FETCH_HEAD` returned `0 0` at the source baseline. Local branch remained `work`; the authorized destination is remote `main`, using a normal fast-forward push. No PR, merge, force push, application work or production action is authorized. Publication completion and the resulting commit must be verified from Git; this preflight entry does not itself claim push success.

## Recording future runs

Append the date, owner, exact command and working-directory role, full tested commit (or base commit plus uncommitted changes), relevant versions, fixture/data scope, exit status, test counts, coverage and limitations. Explicitly retain failed, errored, skipped, expected-failure and unrun outcomes. Do not include private local paths, candidate facts, mail contents, credentials, production records or screenshots containing private data. Do not lower the gate or suppress failing tests to obtain a green result.
