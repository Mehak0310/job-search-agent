# Live workflow repair

Diagnosis and repair started from the existing committed checkpoint. No repair commit, push, deployment, schedule activation, email or submission is authorized.

## Successor milestone: local recovery, eligibility and review queue

Base: `main` at `e94340d61ee88aea137a878ad1e48ca860f3e60f`; changes remain uncommitted. This section records local implementation and synthetic validation only. It does not update or revalidate the earlier production/runtime checkpoint below.

### Implemented

- Shared deterministic hard-gate assessment now requires recent HTTPS-sourced evidence for vacancy activity, India employment, employer size and direct/permanent payroll. Evidence records that are stale, missing, contradictory, unsupported or out of scope remain `UNKNOWN`, `CONFLICT` or `FAIL`, never a pass.
- Retained the specified headcount thresholds in both direct and cached checks: 1,000 employees for non-remote and 500 for remote. Cached evidence keeps its original verification timestamp rather than being made fresh by reuse.
- Require recent sourced vacancy references and an approved India location; exclude closed requisitions and aliases. Queue and browser-preparation paths use the same hard assessment. Batches remain capped at five but return fewer when fewer candidates qualify.
- Applications cards now surface the vacancy source, eligibility status and blockers, connection state, saved progress, missing answers, documents and next safe action. A saved `READY_FOR_USER_REVIEW` state is not displayed or filtered as ready while current eligibility, answers, checks or attachments remain unresolved.
- Isolate progress and Sources request failures from saved application cards; an answer dialog remains outside the replaced card list during polling.

### Verified (synthetic/local)

- `.venv\Scripts\python.exe -m pytest -q --basetemp=data\milestone-full-python`: **529 passed**, **91.84% aggregate coverage**, 509.62s.
- Changed Python module coverage in that run: `eligibility.py` **96%**, `employer_evidence.py` **100%**, `priority_queue.py` **94%**, `browser_store.py` **97%**.
- `.venv\Scripts\python.exe -m pytest tests\test_eligibility.py tests\test_employer_evidence.py tests\test_release_step1.py -q -o addopts='' --cov=job_agent.eligibility --cov=job_agent.employer_evidence --cov-report=term-missing --cov-fail-under=90 --basetemp=data\milestone-coverage-focused`: **29 passed**, focused coverage gate passed.
- `npx.cmd playwright test --config=playwright.privacy.config.ts e2e\live-workflow-repair.spec.ts`: **4 passed**, including Sources/progress failure isolation, answer-dialog draft preservation and stale-ready suppression.
- `npm.cmd run test:e2e`: **156 passed** in 4.7 minutes. An initial full run had one timeout because an existing synthetic test row omitted the newly required eligibility projection; the fixture was corrected and the full rerun passed.
- The focused recovery/eligibility regression command passed **140 tests** before two additional pure eligibility cases were added; the full Python run above includes those cases.

### Blocked / not established

- This task did not inspect production SQLite, reconnect to Chrome, re-open employer pages, or check whether any current vacancy satisfies the gates. No four-application reviewability or five-candidate success is claimed.
- Employer-specific work authorization, current employer facts, cross-portal alias equivalence beyond stable requisition identities, live ATS form read-back, production activation and visual acceptance remain unverified.
- The approved freshness policy is 7 days for vacancy activity and requirements evidence, and 90 days for employer headcount, India-employment and payroll evidence.
- All tests are synthetic. They are not live employer-form acceptance.

## Implemented

- Account for submitted history and awaiting-inspection states in the five-application summary.
- Rebind recovered target/session identifiers after switching to an existing employer tab. Bound connection attempts to ten seconds and show actionable connection errors while preserving form data.
- Exclude closed/removed vacancies and aliases of previously prepared requisitions before selecting the five ranked positions. Propagate known closure across stable requisition aliases.
- Display recorded inspection blockers and a recovery action on lost-session cards.

Existing lease fencing, one active batch, two browser actors, eligibility gates, manual declarations, submission history and uncertain-upload protection remain enforced.

## Verified and limitations

Initial focused command: `.venv\Scripts\python.exe -m pytest tests/test_live_workflow_repair.py tests/test_browser_recovery.py tests/test_browser_applications.py tests/test_review_workflow.py tests/test_priority_queue.py tests/test_r1_reliability.py tests/test_r1_workers_and_migration.py tests/test_r2.py --no-cov -q`: **119 passed**, 98.90s. Subsequent prepared-alias reproduction failed before repair; final selection checks: `.venv\Scripts\python.exe -m pytest tests/test_live_workflow_repair.py tests/test_priority_queue.py --no-cov -q`: **18 passed**, 26.39s.

Focused browser command: `npx.cmd playwright test --config=playwright.privacy.config.ts e2e/live-workflow-repair.spec.ts e2e/review-lifecycle.spec.ts`: **6 passed**, 15.7s, no uncaught JavaScript errors. All employer navigation/mutations intercepted. Windows PowerShell blocks `npx.ps1`; use `npx.cmd`.

Integrated R2 command: `npx.cmd playwright test --config=playwright.r2.config.ts`: **2 passed**, 21.7s. Integrated R1 command: `npx.cmd playwright test --config=playwright.r1.config.ts`: sandboxed fixture termination failed; the isolated rerun with process-control access **passed 1 test**, 31.1s. Its disposable worker tree from the failed run was explicitly identified and cleaned up; production processes were excluded.

Final full Python command: `.venv\Scripts\python.exe -m pytest -q`: **508 passed**, **91.53%** aggregate line coverage, 274.19s. Required 90% retained. `data/live-repair-python-final.log`. The preceding 507-test run passed at 91.41%; the final run includes the subsequently reproduced prepared-alias defect and fix. One upstream Starlette/httpx deprecation warning remains. No runtime model call or live provider adapter was used as acceptance evidence.

Complete UI command: `npx.cmd playwright test --config=playwright.privacy.config.ts`: **154 passed**, 3.0 minutes. `data/live-repair-ui.log`. These tests use disposable synthetic state and intercept external actions. `.venv\Scripts\python.exe -m pip check`: no broken requirements. `git diff --check`: passed.

Actual line coverage limits: browser runtime 66.84%, browser store 96.83%, workers 98.18%, priority 93.55%, API 85.63%, runtime policy 97.62%; outcome projection, requirements, preparation policy, fact memory and review workflow each 100%. Line coverage is not proof of universal ATS compatibility or eligibility quality.

Local test logs, backups and preservation evidence are ignored runtime data and are not included in this report or Git.

## Production diagnosis and remaining work

The backend initially ran older source than the workspace, and the dedicated Chrome endpoint refused connections. No active worker lease or verified eligible pending candidate was present. The selected batch contained four lost sessions and one manually reported outcome; that report is not independent submission evidence. Older form progress, approved files and uncertain upload journals remained saved. Per-application operational evidence remains private and is not reproduced here.

## Verified activation and approved read-only smoke

The outdated local backend was stopped gracefully after checking worker state, workspace/database identity and a backup; it was not force-killed. The local dashboard was restarted against the same database, and its source matched the workspace at activation. Submission remained disabled. No schedule was activated.

Before the approved read-only inspection, protected database and document state was compared with its backup and database integrity passed. Four saved application URLs were opened in new tabs; none of the original form tabs restored. Non-GET requests were blocked during inspection. No values were copied, no uploads or consent occurred, and Submit was not clicked. All four pages responded successfully and exposed supported form controls. This does not prove eligibility or recover browser-held form values lost before repair. Original local partial-form snapshots remained unchanged.

All four application-tab switch requests returned `TAB_SELECTED` and the tabs remained open. One browser probe reported a target-closed error during disconnect; a later switch to the same tab succeeded. No uncaught dashboard JavaScript errors or failed dashboard API responses were observed. At the latest recorded checkpoint, four applications were connected and awaiting inspection/eligibility verification; one was manually reported submitted but not independently verified; zero employer forms were ready for review; and zero verified eligible pending candidates were available for a fresh batch of five. The four forms still require comparison with saved progress and eligibility verification.

Post-smoke preservation checks found no changes to original documents, form snapshots, jobs, profiles, status history, operations or uncertain-upload state. Browser session metadata and inspection events changed as expected during the approved smoke. Additional protected profile facts, packet history, draft approvals and schedule plans were compared with the backup and remained unchanged. Detailed local evidence remains private and is not included in Git.

## Blocked and planned

A working **eligible five-application batch is not achieved**: four applications are connected and awaiting inspection/eligibility verification; one application is manually reported submitted but not independently verified; zero employer forms are ready for review; and zero verified eligible pending candidates are available for a fresh batch. Missing employer/payroll/India or mandatory-clause evidence remains unresolved. Do not reopen reported-submitted history for a repeat application, infer successful submission, repeat uploads or substitute fixture results for this live gate. Agent-owned eligibility verification and separately authorized form preparation remain required before a fresh batch can become ready.
