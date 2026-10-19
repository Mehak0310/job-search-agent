# Shared AI handoff: verification ledger

Recorded: 2026-10-19. Keep observed results, historical reports and unrun checks distinct. The shared baseline is `6e195c8c9ec265f8bcd9628d44c68d0e4f17fcbb`. Documentation changes in this setup do not constitute a new application test run.

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

## Initial documentation setup verification

Scope: four new handoff files and a minimal `AGENTS.md` addition only, based on the clean `work` checkout at the shared baseline. Review checks cover local Markdown targets, table/fence consistency, privacy-sensitive patterns, whitespace and the exact proposed diff. No application tests are rerun for this documentation-only task. No application source, tests, environment configuration or production data is changed; no commit, push or PR is created.

Checks completed: `git diff --check` passed; `git diff --no-index --check /dev/null <new-file>` passed for each new Markdown file. An inline Python check of all five changed files passed for local link existence, consistent table columns, balanced fences, whitespace and targeted private-path/contact/credential patterns. Manual content review found no candidate facts, Gmail contents, credentials, production records or private local paths in the additions. These scans are scoped checks, not a guarantee against every possible secret. `git diff --cached --stat` was empty; `git branch --show-current` returned `work` and `git rev-parse HEAD` returned the shared baseline. The proposed tracked diff and each new-file diff were reviewed; only the five intended documentation paths are changed.

## Publication authorization and preflight

On 2026-10-19 the user explicitly requested committing and pushing the completed handoff. This supersedes the initial documentation phase's no-commit/no-push restriction for these five files only. `git fetch origin main` succeeded; `git rev-list --left-right --count HEAD...FETCH_HEAD` returned `0 0` at the source baseline. Local branch remained `work`; the authorized destination is remote `main`, using a normal fast-forward push. No PR, merge, force push, application work or production action is authorized. Publication completion and the resulting commit must be verified from Git; this preflight entry does not itself claim push success.

## Recording future runs

Append the date, owner, exact command and working-directory role, full tested commit (or base commit plus uncommitted changes), relevant versions, fixture/data scope, exit status, test counts, coverage and limitations. Explicitly retain failed, errored, skipped, expected-failure and unrun outcomes. Do not include private local paths, candidate facts, mail contents, credentials, production records or screenshots containing private data. Do not lower the gate or suppress failing tests to obtain a green result.
