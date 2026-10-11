# Milestone 2A execution plan

| Task | Status |
|---|---|
| Read existing architecture, tests, verification and inspect Git | Complete |
| Verify official public provider contracts; define acceptance criteria | Complete |
| Add backup-protected schema migration and candidate search profile | Complete: v1 backup/v2 integrity/status checks passed |
| Implement registry, HTTPS connectors, bounded discovery and metrics | Complete |
| Extend deterministic classification/matching and dashboard | Complete |
| Implement manual CLI and reviewable Windows schedule setup | Complete: Python preview verified; task remains unregistered |
| Add mocked tests; run all regressions and coverage | Complete: 184 passed, 100% Python statements |
| Verify small live boards, repeat scan, API/HTML and preserved statuses | Complete: 26 real jobs, repeat 26 unchanged, statuses preserved |
| Update documentation and final measurable verification report | Complete |

Inspection: workspace has no Git repository (`git status` reports not a repository). Preserve all existing files and data; do not initialize Git or reset anything. Reuse JobInput, SQLite transactions, source references, JobService, deterministic matching, local HTTP defenses and static frontend. No subagents, LLMs, personal accounts or persistent task registration.

Research: official Greenhouse Job Board API documents public GET listing with content=true and a complete jobs array, without listing pagination. Official Lever Postings API documents published postings, global/EU hosts, skip/limit pagination and JSON mode. Read only listing endpoints. Sources must be confirmed against actual public API before they are enabled in seed config.

Verified initial source metadata: Netomi Lever returned HTTP 200 (one-record probe); Prophecy Greenhouse `prophecysimpledatalabs` returned HTTP 200 and 3 listings. Postman's old board returned 404 and is excluded. Sandbox outbound socket error 10013 was resolved with approved public-read escalation. Regression/new mocked tests and full live verification remain.

Final checkpoint (2026-10-10): 184 tests passed, 1,373/1,373 Python statements covered. Live first run: 26 new jobs, 2 GETs, 6.360 seconds; repeat: 26 unchanged, 0 new, 2 conditional GETs, 2.468 seconds. Both providers healthy. Four legacy sample jobs/statuses/history retained; database integrity OK, v1 backup retained. Final categories after ranking review: 5 AI_GENAI, 2 FRONTEND, 4 DATA_PYTHON_SQL, 15 OTHER. Of 26 public listings, 11 show India eligibility and 15 are flagged ineligible; no global-remote assumptions. Dashboard/API/filter/asset checks passed on 127.0.0.1:8001 and owned verification server stopped. Browser automation unavailable. Scheduler preview passed without registration or policy changes; actual registration/execution remains approval-gated and unverified. No accounts, application submissions or PRs.
