# Milestone 1 verification

Verified on 2026-10-10 on Windows with Python 3.12.10 via `.venv\Scripts\python.exe`.

## Results

- Final automated run: **81 passed**, one upstream warning, 6.95 seconds. **100.00% Python statement coverage**, 480/480 statements across every `job_agent` module. This is statement coverage, not exhaustive input/branch/browser coverage.
- XML coverage: `coverage.xml`. Standalone HTML coverage: `htmlcov/index.html`.
- `pip check`: no broken requirements. JavaScript syntax check via existing Node: passed.
- Real Uvicorn process started successfully on **127.0.0.1:8001**. Final smoke run after restart passed health, dashboard rendered HTML, both static assets, JSON and CSV imports, repeat-import idempotency, two-source provenance, matching explanations, manual shortlist, independently reopened SQLite state, audit events and absent submission endpoint.
- Four fictional jobs persist in `data/jobs.sqlite3`. Fit scores: 95, 86, 86, 83. Fictional AI Application Engineer is manually SHORTLISTED; submission remains unverified.
- Verification server stopped after checks. Restart: `.\.venv\Scripts\python.exe -m job_agent --port 8001`, then visit `http://127.0.0.1:8001/`.
- No installed browser automation tool was available. Interactive layout, focus behavior and browser interactions were **not verified in a real browser**. API/HTML/assets and JS syntax were verified; this is the outstanding QA limitation under conditional acceptance criterion 10.

## Acceptance outcome

Criteria 1â€“9 passed automated and/or actual server verification. Criterion 10 passed Windows README and live API/HTML checks; full interactive browser validation remains unperformed under the documented fallback. No required runtime feature is blocked.

## Commands executed

All Python commands used the workspace interpreter; project installs stayed in `.venv`.

```powershell
.\.venv\Scripts\python.exe -m pip install -e '.[test]'
# Approved retry after sandbox network denial:
.\.venv\Scripts\python.exe -m pip install --retries 0 -e '.[test]'
.\.venv\Scripts\python.exe -m pip freeze --exclude-editable | Set-Content -LiteralPath requirements.lock.txt -Encoding utf8
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe -m coverage html
.\.venv\Scripts\python.exe -m pip check
node --check job_agent/static/app.js
.\.venv\Scripts\python.exe -m job_agent
.\.venv\Scripts\python.exe -m job_agent --port 8001
.\.venv\Scripts\python.exe scripts\verify_local.py --port 8001
```

Read-only shell commands read the user attachment and skill instructions, listed workspace/spec files and attempted process inspection. `apply_patch` created/updated project files. `Stop-Process` stopped only owned verification server PIDs 17496 and 41184. No unrelated process was stopped, and no dependency/tool/extension was installed system-wide.

## Errors, causes and resolutions

| Finding | Root cause | Resolution |
|---|---|---|
| Initial pip build dependency fetch failed | Sandbox denied sockets, WinError 10013; pip's own default retries also failed | One approved out-of-sandbox installation with retries disabled succeeded |
| Initial matching tests failed | Pydantic defaults were not validated, so default skill casing differed from normalized job skills | Enable default validation; verify full scores and profile updates |
| Unsafe URL whitespace test failed | Pydantic stripped whitespace before URL checks | Validate original URL before stripping; reject non-text URLs safely |
| Large-payload parameterized fixtures errored and output became excessive | Pytest embedded multi-megabyte bytes into test IDs, exceeding Windows filesystem path limits | Generate bounded payload-length test IDs |
| Missing-route test expected 404 on a known path with an unsupported method | HTTP method mismatch correctly returns 405 | Correct the test expectation; verify absent submission/approval routes independently |
| Initial live server bind failed | Another process already occupied port 8000, WinError 10048 | Add optional local port, verify 8001; do not stop the existing process |
| Process inspection unavailable | Sandbox denied CIM access | No escalation needed; use already-known owned server PIDs only |
| Intermediate runpy warning | Test imported the module before executing it through runpy | Isolate module entrypoint execution in the test |
| Current TestClient warning | Starlette 1.7 deprecates the httpx compatibility path | Record warning; tests pass with installed FastAPI/httpx, no additional tool installed |

## Files created

- Root: `AGENTS.md`, `.gitignore`, `pyproject.toml`, `requirements.lock.txt`, `README.md`.
- Specs: `requirements.md`, `architecture.md`, `security-and-approvals.md`, `acceptance-criteria.md`, `milestone-1-plan.md`, `decision-log.md`, `source-connector-contract.md`, `verification.md`.
- Python package: `job_agent/__init__.py`, `__main__.py`, `models.py`, `matching.py`, `connectors.py`, `approvals.py`, `database.py`, `service.py`, `main.py`.
- Dashboard: `job_agent/static/index.html`, `style.css`, `app.js`.
- Fictional fixtures: `samples/jobs.json`, `samples/jobs.csv`.
- Tests: `tests/conftest.py`, `test_models_matching.py`, `test_connectors.py`, `test_service_database.py`, `test_api.py`, `test_entrypoint.py`.
- Live smoke script: `scripts/verify_local.py`.
- Ignored generated state: SQLite files in `data/`, coverage XML/HTML, pytest/cache/bytecode files and editable package metadata. The preexisting `.venv` gained isolated dependencies.

## Known limitations and deferred work

- Matching is deterministic and literal; include explicit country text in locations. No geocoding, inferred skills/experience or interview probability. Deduplication may collapse distinct vacancies with identical identity fields, and differing updated descriptions require manual review rather than automatic overwrite.
- Job list responses cap at 1,000 matching jobs; overview counts reflect loaded rows. Pagination and comprehensive aggregate counts are deferred. File imports also cap at 1,000 rows each.
- No browser QA, authentication, real portal connectors, document generation or live application actions. Local users/processes can access the loopback app. Audit immutability protects ordinary application writes, not a privileged local administrator changing the file.
- Approval fingerprint is a tested pure primitive and architecture foundation, not a production approval grant. Versioned job packages, document hashes, explicit user grants, expiry/revocation, single-use consumption and submission adapters belong to Milestone 2.
- No user approval decisions remain for Milestone 1. External accounts, paid services, system changes, GitHub PRs and real submissions still require explicit future authorization.

# Milestone 2A verification

Verified 2026-10-10 in the same Windows workspace, Python 3.12.10 and editable local-job-agent 0.2.0. Historical Milestone 1 results above are retained; current results below supersede its deferred-connector and coverage counts.

## Automated validation

Final full suite: **184 passed**, **100.00% Python statement coverage**, **1,373/1,373 statements**, 17.11 seconds. All 81 legacy tests remain and pass. One existing upstream Starlette/httpx TestClient deprecation warning remains; no extra package was installed to suppress it. Coverage includes all runtime Python modules, CLI and Python scheduling planner, not browser JavaScript or the optional PowerShell script.

Tests cover public parsing, plaintext sanitization, whole-board validation, Lever pagination/repeated pages, caching/304, timeout/network/HTTP errors, Retry-After/backoff, endpoint restrictions, byte/record/request/runtime limits, registry/toggles, migration backup/rollback/version protection, stable hashes/IDs, cross-source conflicts, unchanged-record normalization skipping, updates preserving status/history, source failure isolation, metrics/audit, lease recovery, asynchronous API polling/overlap, category/seniority/India eligibility and scheduling XML/idempotency. An autouse fixture blocks real HTTPTransport in automated tests; only MockTransport/TestClient transports are used.

JavaScript `node --check`: passed. PowerShell script parsed without syntax errors. `pip check`: no broken requirements. Runtime httpx was already installed by Milestone 1 tests; project metadata now declares it directly. The editable local package was refreshed to 0.2.0; dependency lock versions remain unchanged.

## Public sources and measured live results

Official API contracts researched before implementation: [Greenhouse Job Board API](https://docs.greenhouse.io/job-board.html), [Lever Postings API](https://github.com/lever/postings-api). Enabled board IDs were confirmed with actual permitted public HTTPS GETs before seeding. [Netomi public board](https://jobs.lever.co/netomi/) uses `netomi`; [Prophecy public board](https://job-boards.greenhouse.io/prophecysimpledatalabs) uses `prophecysimpledatalabs`. Postman's old `postman` board returned 404 and was excluded.

| Run | Worker runtime | Requests | Bodies/records fetched | New | Updated | Unchanged | Rejected / retries / failed sources |
|---|---:|---:|---:|---:|---:|---:|---|
| First live run | 6.360 s | 2 | 26 records | 26 | 0 | 0 | 0 / 0 / 0 |
| Repeat live run | 2.468 s | 2 | 0 (conditional 304s) | 0 | 0 | 26 | 0 / 0 / 0 |

First run ID: `2e4347a8757c4632a0faca46ffa9d255`. Repeat: `007436e9601544979e58bb3c8459adbc`. Metrics persist in SQLite and ignored `data/milestone-2a-live-verification.json`. Both source health statuses are SUCCESS with persisted last attempts/successes/checkpoints. No source failures, HTTP errors, rejected records or new duplicate jobs in these two discovery runs.

| Source | Real listings | First worker runtime | Repeat worker runtime |
|---|---:|---:|---:|
| Netomi / Lever | 23 | 5.343 s | 1.219 s |
| Prophecy / Greenhouse | 3 | 0.531 s | 0.453 s |

Final stored categories after correcting non-engineering AI titles and junior scope: AI_GENAI 5; FRONTEND 2; DATA_PYTHON_SQL 4; OTHER 15; FRONTEND_LEADERSHIP, CONSULTING, FULLSTACK_AI and BACKEND each 0. Role categories with zero live records are covered by mocked fixtures. Of the 26 real listings, 11 indicate India eligibility and 15 are flagged ineligible. Prophecy's current three listings are US-only according to the API locations; none is misrepresented as India eligible. This is a small verified board set, not comprehensive discovery.

No employer content changed between live runs: updated count was actually 0. Update detection and status preservation on changed descriptions are verified with mocked fixtures, not falsely reported as a live employer update. Live repeat used true conditional cache validations, not a claimed provider delta API. Final background rescore refreshed category/seniority rules locally without mutating listing-change timestamps or statuses.

## Migration, dashboard and scheduling

- Actual local database upgraded **version 1 -> 2**. `data/jobs.sqlite3.pre-v2.bak` independently reports schema 1. Current database reports 2 and `PRAGMA integrity_check = ok`.
- All four legacy fictional job IDs/statuses/history survived the upgrade and both runs. The live integration script asserts baseline statuses/history; subsequent final API checks confirm preservation. Existing shortlist remains manual; every live job reports submission_verified=false.
- Final code launched successfully at **http://127.0.0.1:8001/**. Actual HTTP checks verified rendered dashboard, static assets, 26 live jobs, categories/priorities/source filters, details/employer links, matching explanations, healthy sources, persistent repeat metrics and absence of a submission endpoint. The original Milestone 1 live smoke script also passed against the final application.
- No browser automation tool is exposed in this session (rechecked). Interactive browser validation was **not performed**. API/HTML/assets and JS syntax are the fallback evidence.
- Final owned server PID 15488 was stopped after verification; intermediate owned PIDs 32356 and 13200 were also stopped. Unrelated services were not stopped.
- Python scheduling preview succeeded with next default trigger **2026-10-11 08:00 IST**, explicit +05:30 offset, current-user/least-privilege context and `will_register=false`. Scheduling XML round-trips, idempotent updates, UTF-16 handling and unrelated-name protections are mocked-tested. Native registration/execution were deliberately **not performed**; separate approval is required.
- PowerShell script execution failed under the existing execution policy. No policy was changed. The supported stdlib Python planner provides preview and native XML/schtasks registration without depending on PowerShell script execution. Microsoft time-zone behavior was checked against [StartBoundary documentation](https://learn.microsoft.com/en-us/windows/win32/taskschd/trigger-startboundary).

## Commands executed for this milestone

```powershell
git status --short
.\.venv\Scripts\python.exe -m pytest -q --tb=short
.\.venv\Scripts\python.exe -m coverage html
.\.venv\Scripts\python.exe -m pip check
node --check job_agent/static/app.js
.\.venv\Scripts\python.exe -m pip install --retries 0 --no-deps -e .
.\.venv\Scripts\python.exe scripts\verify_discovery.py
.\.venv\Scripts\python.exe scripts\verify_discovery.py --repeat
.\.venv\Scripts\python.exe -m job_agent --port 8001
.\.venv\Scripts\python.exe scripts\verify_local.py --port 8001
.\.venv\Scripts\python.exe -m job_agent.scheduling
```

Additional read-only commands inspected specs/modules/tests, parsed PowerShell syntax and independently checked SQLite backup/version/integrity. Bounded public board probes and live scripts used approved network escalation after the sandbox's socket denial. Local HTTP checks used httpx against loopback only. The background was explicitly rescored after final ranking adjustments. No scheduler --register invocation occurred outside mocked tests.

## Significant findings and resolutions

| Finding | Cause | Resolution |
|---|---|---|
| Git status unavailable | Workspace was never initialized as a Git repository | Preserve files; no initialization/reset/PR |
| Initial public probe failed | Sandbox socket restriction, WinError 10013 | Approved bounded public read succeeded |
| Postman board returned 404 | Public board identifier no longer resolves | Exclude; verify Prophecy instead |
| First expanded suite: 165 passed, one failed lease-recovery test | Second discovery instance accidentally omitted mocked client, producing denied network attempts and PARTIAL | Inject the same mocked client; add a suite-wide real-transport prohibition; final tests make no live calls |
| Cross-source evidence differences initially risked a canonical rewrite | Secondary provider links/country metadata differ despite same content | First accepted source owns canonical updates; new matching provenance does not overwrite it |
| Agentic product-manager title ranked too highly; SDE I frontend got full seniority credit | Unqualified title keyword promotion and minimum-only experience matching | Require engineering-related AI title; review junior scope and lower its priority/score; rescore existing live data |
| PowerShell setup blocked | Existing execution policy disallows .ps1 | Leave policy unchanged; supported Python task planner preview verified |
| Task XML portability risk | Declaration/output encoding and query stdout may differ on Windows | UTF-16 declaration/BOM and bytes-aware parsing tested; native task creation remains unverified |
| Large Retry-After values can overflow dates | Malformed external delay larger than datetime range | Clamp next eligible date to datetime.max rather than retry early or abort other sources |

## Modified and added files

Modified: `job_agent/database.py`, `service.py`, `main.py`; all three static dashboard assets; `pyproject.toml`; `tests/conftest.py`; `README.md`; `specs/architecture.md`, `source-connector-contract.md`, `security-and-approvals.md`, `decision-log.md`, `verification.md`.

Added: `job_agent/candidate.py`, `classification.py`, `migrations.py`, `discovery_models.py`, `registry.py`, `public_connectors.py`, `discovery_store.py`, `discovery.py`, `discover.py`, `scheduling.py`; `config/discovery.json`; `scripts/verify_discovery.py`, `setup-discovery-task.ps1`; `tests/test_public_connectors.py`, `test_classification.py`, `test_discovery.py`, `test_discovery_conflicts.py`, `test_discover_cli.py`, `test_scheduling.py`; `specs/milestone-2a-plan.md`, `milestone-2a-acceptance-criteria.md`.

Generated/ignored state: migrated SQLite database and pre-v2 backup, persistent real-listing/run/source records, live verification JSON, coverage XML/HTML, caches and refreshed editable package metadata. No user data was deleted.

## Acceptance and remaining work

All twelve Milestone 2A acceptance criteria are implemented and have the stated automated/live/API evidence. Both provider live integrations succeeded; none is blocked. Required Windows setup is documented and previewed; actual task installation is outside completed work until explicit approval. Interactive browser QA remains unverified under the documented fallback. No application has been submitted, no account accessed, no persistent task registered, no security setting changed and no PR created.

Known limits: two employer boards; conservative location/requirements heuristics; unknown individual skill evidence; no automatic expiry/closure; first-source ownership of conflicting updates; 1,000-row list cap; sequential source scans; unauthenticated loopback access; task requires logged-in user. Milestone 2B seams include evaluator/provider abstraction, richer evidence, generated/reviewed documents, evaluation versioning, immutable approved packages and explicit approval invalidation on material LIVE_JOB_UPDATED events. Submission remains separately authorized and out of scope.


# Milestone 2A.1 verification (2026-10-10)

Schema v3 adds explicit eligibility evidence/confidence/evaluation time, seniority level, activity lifecycle, canonical URL/content hash/duplicate group, source verification evidence, source cooldowns, response bytes, and nullable efficiency ratios. The v2 database was backed up at `data/jobs.sqlite3.pre-v3.bak`; current `PRAGMA integrity_check` is `ok`. Existing sample records, status history, and manual statuses survived.

A bounded evaluation checked 50 candidate identifiers. Twenty-two returned valid public feeds and the previously verified Prophecy board brings the registry to 23 verified sources. Twenty-one with India-located vacancies are enabled; Airtable and Asana are retained disabled with seven-day cooldowns. The raw success/failure evidence is in `data/milestone-2a1-source-evaluation.json`; failed/guessed identifiers were not configured.

First expanded scan `902cd22c16a645508380dd120ffd299d`: 21 requests, 3,003 fetched records, 2,898 new, 26 unchanged, 105 safely rejected malformed/conflicting records, no retries or failed sources, 44,364,785 response bytes, 93.703 seconds. Repeat `ba71754f40e5485cb7ad463f14d11a70`: 21 requests, zero new/updated, 2,924 unchanged, 8 rejected, no retries/failures, 2,502,453 bytes, 11.500 seconds. Conditional responses account for the reduction. Current live store: 2,924 jobs; eligibility 592 eligible, 321 ineligible, 2,011 unknown; all active. Categories: OTHER 2,675; AI_GENAI 99; BACKEND 43; DATA_PYTHON_SQL 38; CONSULTING 37; FRONTEND 22; FRONTEND_LEADERSHIP 7; FULLSTACK_AI 3.

Automated regression: 184 passed, 100.00% Python statement coverage (1,352/1,352); `node --check`, `pip check`, migration and integrity checks passed. One upstream Starlette TestClient deprecation warning remains.

Real installed-Chrome QA used project-local Playwright and passed 18/18 scenarios: dashboard/listings, AI and frontend filters, India eligibility, score sort, details, external employer page HTTP 200, shortlist and refresh persistence, dashboard discovery/progress/metrics, source health, 768px layout, console, and local network failures. Console errors: 0; failed local requests: 0. Evidence: `artifacts/browser-qa/report.json`, `dashboard.png`, `india-eligible.png`, `job-detail.png`, `responsive-768.png`.

No scheduled task, account access, application submission, email, security-policy change, system-wide dependency, or PR occurred. The dashboard intentionally returns at most 1,000 rows per query; pagination remains deferred. Discovery has a configurable concurrency ceiling but the current deterministic worker processes sources sequentially, so true parallel fetching remains deferred rather than falsely claimed. Greenhouse supplied rejected records on some large boards; these were isolated and recorded without failing healthy sources.


# Milestones 2A.2 + 2A.3 verification (2026-10-10)

Schema v4 migrated safely from v3 with `data/jobs.sqlite3.pre-v4.bak` (59,400,192 bytes). Integrity is `ok`; 2,928 pre-migration jobs and the status distribution (2,923 NEW, 5 SHORTLISTED) survived. Current state after feed discovery/browser QA is 3,116 jobs (3,112 live), 3,117 references and 3,382 audit events. No records were deleted.

## Discovery and sources

The fetch phase now uses a configurable four-worker pool and a locked global request/runtime budget. Results are persisted afterward in stable registry order through independent serialized SQLite transactions. The cross-process lease still prevents overlapping runs. A mocked four-source test observed exactly two workers for a configured limit of two and four successful serialized writes.

All 20 requested platforms are persisted in `source_platforms` and documented in `source-platform-matrix.md`. Only official documented public feeds were connected: Remote OK JSON and We Work Remotely RSS. Official feed probes returned HTTP 200 (570,478 and 787,253 bytes). LinkedIn is RESTRICTED because its official crawling terms require express permission. Other platforms remain AUTHORIZED_API, ALERT_IMPORT, MANUAL_IMPORT, RESTRICTED or UNVERIFIED; none is scraped.

Remote OK added 99 jobs. WWR's first run safely rejected 89 items because RSS uses `guid` rather than `id`; the adapter was corrected and the bounded retry added all 89 with zero rejections. Full concurrent repeat `c9cb37b1eefd4b7d8031e7009d32b973`: 23 requests, 1,357,731 bytes, 3,112 unchanged, zero new/updated/rejected/retries/failures, 4.797 seconds. The prior comparable sequential repeat used 21 sources, 2,502,453 bytes and 11.500 seconds. This is a measured 58.3% runtime reduction but not a controlled identical-payload benchmark.

## Freshness, filters and data

Publication time, source update, first discovery and last seen are separate UTC fields with provenance/confidence; the UI renders Asia/Kolkata. Current publication counts: 15 within 1/6 hours, 28 within 12/24 hours, 44 within 48 hours, and 2,924 unknown. Unknown is never displayed as recent. Current live eligibility: 594 eligible; 2,181 unknown; the remainder ineligible. Preferred-location bucket matches: 162. Listings whose reliable required-experience interval includes seven years: 121.

The paginated API applies title, category, company, platform, source, required-skill any/all, seniority, experience overlap, normalized location, work mode, eligibility, score, freshness, activity and tracking status before `LIMIT/OFFSET`. It returns total/pages/navigation metadata with job ID as stable tie-breaker. The eligibility/priority query uses `jobs_priority_v4`; 200 page queries at offset 500 took 1,023.305 ms total (about 5.12 ms/query) on the current database.

## Validation

Final automated suite and coverage are recorded below. Real installed-Chrome QA passed 19/19 checks (the requested pagination case is split into availability and navigation): totals, freshness, newest sort, eligibility, preferred locations, Gurgaon/Gurugram, experience, skills, combined filters, clear/reset persistence, timestamp details, links, shortlist persistence, discovery progress, and console/network health. Evidence: `artifacts/browser-qa-2a23/report.json`, `detail.png`, `dashboard-mobile.png`. Console errors and failed local requests: zero.

No scheduler task, email/account access, submission, paid service, system security change or PR occurred. Salary remains unknown where feeds do not expose structured compensation. Alert-email support remains file import only. Pagination uses page/offset rather than cursors; very deep pages may eventually need keyset pagination.

Final regression: **188 passed**, **99.74% Python statement coverage** (1,526/1,530 statements), one upstream Starlette TestClient deprecation warning. `pip check` and JavaScript syntax passed. Browser-created shortlist states were reverted through the normal audited status API after persistence was proven, restoring the pre-milestone status distribution (2,923 legacy jobs plus newly discovered jobs: 5 SHORTLISTED total).

