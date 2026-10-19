# Complete publication file proposal

Proposal only; no commit or push authorized. Exact diff/blob review uses a separate ignored index; the real staging index is untouched.

Destination: existing origin, `main` tracking `origin/main`. Proposed message: `feat: checkpoint R1-R3 with private local profile configuration`.

## Changed files versus HEAD

265 added/modified paths; 309 files in the complete proposed tree. This includes prior pending R1/R2/R3 work.

| Change | Path |
|---|---|
| A | `.github/workflows/playwright.yml` |
| M | `.gitignore` |
| A | `artifacts/command-center-proposal/application-expanded-390.png` |
| A | `artifacts/command-center-proposal/applications-applied-1440.png` |
| A | `artifacts/command-center-proposal/applications-applied-390.png` |
| A | `artifacts/command-center-proposal/applications-applied-768.png` |
| A | `artifacts/command-center-proposal/applications-follow-ups-1440.png` |
| A | `artifacts/command-center-proposal/applications-follow-ups-390.png` |
| A | `artifacts/command-center-proposal/applications-follow-ups-768.png` |
| A | `artifacts/command-center-proposal/applications-preparing-1440.png` |
| A | `artifacts/command-center-proposal/applications-preparing-390.png` |
| A | `artifacts/command-center-proposal/applications-preparing-768.png` |
| A | `artifacts/command-center-proposal/applications-priority-queue-1440.png` |
| A | `artifacts/command-center-proposal/applications-priority-queue-390.png` |
| A | `artifacts/command-center-proposal/applications-priority-queue-768.png` |
| A | `artifacts/command-center-proposal/applications-ready-to-review-1440.png` |
| A | `artifacts/command-center-proposal/applications-ready-to-review-390.png` |
| A | `artifacts/command-center-proposal/applications-ready-to-review-768.png` |
| A | `artifacts/command-center-proposal/collapsed-sidebar-1440.png` |
| A | `artifacts/command-center-proposal/home-my-actions-1440.png` |
| A | `artifacts/command-center-proposal/home-my-actions-390.png` |
| A | `artifacts/command-center-proposal/home-my-actions-768.png` |
| A | `artifacts/command-center-proposal/home-overview-1440.png` |
| A | `artifacts/command-center-proposal/home-overview-390.png` |
| A | `artifacts/command-center-proposal/home-overview-768.png` |
| A | `artifacts/command-center-proposal/home-recent-activity-1440.png` |
| A | `artifacts/command-center-proposal/home-recent-activity-390.png` |
| A | `artifacts/command-center-proposal/home-recent-activity-768.png` |
| A | `artifacts/command-center-proposal/inbox-draft-approvals-1440.png` |
| A | `artifacts/command-center-proposal/inbox-draft-approvals-390.png` |
| A | `artifacts/command-center-proposal/inbox-draft-approvals-768.png` |
| A | `artifacts/command-center-proposal/inbox-draft-history-1440.png` |
| A | `artifacts/command-center-proposal/inbox-draft-history-390.png` |
| A | `artifacts/command-center-proposal/inbox-draft-history-768.png` |
| A | `artifacts/command-center-proposal/inbox-job-alerts-1440.png` |
| A | `artifacts/command-center-proposal/inbox-job-alerts-390.png` |
| A | `artifacts/command-center-proposal/inbox-job-alerts-768.png` |
| A | `artifacts/command-center-proposal/inbox-recruiter-inbox-1440.png` |
| A | `artifacts/command-center-proposal/inbox-recruiter-inbox-390.png` |
| A | `artifacts/command-center-proposal/inbox-recruiter-inbox-768.png` |
| A | `artifacts/command-center-proposal/index.json` |
| A | `artifacts/command-center-proposal/jobs-all-jobs-1440.png` |
| A | `artifacts/command-center-proposal/jobs-all-jobs-390.png` |
| A | `artifacts/command-center-proposal/jobs-all-jobs-768.png` |
| A | `artifacts/command-center-proposal/jobs-best-matches-1440.png` |
| A | `artifacts/command-center-proposal/jobs-best-matches-390.png` |
| A | `artifacts/command-center-proposal/jobs-best-matches-768.png` |
| A | `artifacts/command-center-proposal/jobs-needs-verification-1440.png` |
| A | `artifacts/command-center-proposal/jobs-needs-verification-390.png` |
| A | `artifacts/command-center-proposal/jobs-needs-verification-768.png` |
| A | `artifacts/command-center-proposal/jobs-shortlisted-1440.png` |
| A | `artifacts/command-center-proposal/jobs-shortlisted-390.png` |
| A | `artifacts/command-center-proposal/jobs-shortlisted-768.png` |
| A | `artifacts/command-center-proposal/mobile-navigation-390.png` |
| A | `artifacts/command-center-proposal/notification-dialog-1440.png` |
| A | `artifacts/command-center-proposal/notification-dialog-390.png` |
| A | `artifacts/command-center-proposal/notification-dialog-768.png` |
| A | `artifacts/command-center-proposal/profile-career-facts-1440.png` |
| A | `artifacts/command-center-proposal/profile-career-facts-390.png` |
| A | `artifacts/command-center-proposal/profile-career-facts-768.png` |
| A | `artifacts/command-center-proposal/profile-documents-1440.png` |
| A | `artifacts/command-center-proposal/profile-documents-390.png` |
| A | `artifacts/command-center-proposal/profile-documents-768.png` |
| A | `artifacts/command-center-proposal/profile-preferences-1440.png` |
| A | `artifacts/command-center-proposal/profile-preferences-390.png` |
| A | `artifacts/command-center-proposal/profile-preferences-768.png` |
| A | `artifacts/command-center-proposal/profile-saved-answers-1440.png` |
| A | `artifacts/command-center-proposal/profile-saved-answers-390.png` |
| A | `artifacts/command-center-proposal/profile-saved-answers-768.png` |
| A | `artifacts/command-center-proposal/review.html` |
| A | `artifacts/command-center-proposal/sources-run-history-1440.png` |
| A | `artifacts/command-center-proposal/sources-run-history-390.png` |
| A | `artifacts/command-center-proposal/sources-run-history-768.png` |
| A | `artifacts/command-center-proposal/sources-schedules-1440.png` |
| A | `artifacts/command-center-proposal/sources-schedules-390.png` |
| A | `artifacts/command-center-proposal/sources-schedules-768.png` |
| A | `artifacts/command-center-proposal/sources-source-health-1440.png` |
| A | `artifacts/command-center-proposal/sources-source-health-390.png` |
| A | `artifacts/command-center-proposal/sources-source-health-768.png` |
| A | `artifacts/command-center-proposal/sources-verification-backlog-1440.png` |
| A | `artifacts/command-center-proposal/sources-verification-backlog-390.png` |
| A | `artifacts/command-center-proposal/sources-verification-backlog-768.png` |
| M | `artifacts/m2c-evaluation.json` |
| M | `artifacts/milestone-summary.json` |
| M | `config/discovery.json` |
| A | `docs/command-center-design-contract.md` |
| A | `docs/command-center-migration.md` |
| A | `docs/command-center-visual-acceptance.md` |
| A | `docs/command-center-visual-gap-report.md` |
| M | `docs/handoff.md` |
| A | `docs/implementation-checkpoint.md` |
| A | `docs/privacy-refactor-verification.md` |
| M | `docs/project-status.md` |
| A | `docs/prototypes/command-center.html` |
| M | `docs/publication-checklist.md` |
| A | `docs/publication-file-proposal.md` |
| A | `docs/publication-privacy-remediation-proposal.md` |
| A | `docs/publication-safe-checkpoint-audit.md` |
| A | `e2e/command-center.spec.ts` |
| A | `e2e/draft-policy.spec.ts` |
| A | `e2e/example.spec.ts` |
| A | `e2e/fixtures.ts` |
| A | `e2e/interactions.spec.ts` |
| A | `e2e/portal-fixture.ts` |
| A | `e2e/presentation.spec.ts` |
| A | `e2e/priority.spec.ts` |
| A | `e2e/privacy-teardown.ts` |
| A | `e2e/r1/integrated.spec.ts` |
| A | `e2e/r2/integrated.spec.ts` |
| A | `e2e/r2/orchestration.spec.ts` |
| A | `e2e/r2/teardown.ts` |
| A | `e2e/review-lifecycle.spec.ts` |
| A | `e2e/test-1.spec.ts` |
| A | `e2e/workflow.spec.ts` |
| M | `job_agent/__main__.py` |
| A | `job_agent/alert_extraction.py` |
| A | `job_agent/alert_links.py` |
| A | `job_agent/alert_redirects.py` |
| A | `job_agent/amazon_connector.py` |
| A | `job_agent/application_answers.py` |
| A | `job_agent/application_state.py` |
| A | `job_agent/automatic_drafts.py` |
| A | `job_agent/browser_applications.py` |
| A | `job_agent/browser_forms.py` |
| A | `job_agent/browser_store.py` |
| A | `job_agent/browser_workers.py` |
| M | `job_agent/candidate.py` |
| A | `job_agent/command_center.py` |
| A | `job_agent/coverage_report.py` |
| M | `job_agent/database.py` |
| M | `job_agent/discovery.py` |
| M | `job_agent/discovery_models.py` |
| M | `job_agent/discovery_store.py` |
| A | `job_agent/document_manifest.py` |
| A | `job_agent/draft_review.py` |
| A | `job_agent/email_opportunities.py` |
| A | `job_agent/email_research.py` |
| A | `job_agent/employer_evidence.py` |
| M | `job_agent/evaluation.py` |
| A | `job_agent/fact_memory.py` |
| M | `job_agent/freshness.py` |
| A | `job_agent/gmail_local.py` |
| A | `job_agent/gmail_reextract.py` |
| M | `job_agent/intelligence.py` |
| A | `job_agent/jobqueue.py` |
| A | `job_agent/m2d.py` |
| A | `job_agent/m2d_models.py` |
| A | `job_agent/m2d_sources.py` |
| A | `job_agent/m3.py` |
| A | `job_agent/m3_export.py` |
| A | `job_agent/m3_models.py` |
| M | `job_agent/main.py` |
| M | `job_agent/matching.py` |
| M | `job_agent/migrations.py` |
| A | `job_agent/orchestration.py` |
| A | `job_agent/policy_hooks.py` |
| A | `job_agent/preparation_policy.py` |
| A | `job_agent/priority_queue.py` |
| A | `job_agent/private_config.py` |
| A | `job_agent/profile_m31.py` |
| M | `job_agent/public_connectors.py` |
| A | `job_agent/reconciliation_r2.py` |
| M | `job_agent/registry.py` |
| A | `job_agent/release.py` |
| A | `job_agent/requirement_clauses.py` |
| A | `job_agent/requirement_reconciliation.py` |
| A | `job_agent/requirements.py` |
| M | `job_agent/resume_review.py` |
| A | `job_agent/review_queue.py` |
| A | `job_agent/review_workflow.py` |
| A | `job_agent/runtime_policy.py` |
| A | `job_agent/schedule_adapters.py` |
| A | `job_agent/server_runtime.py` |
| M | `job_agent/service.py` |
| A | `job_agent/smartrecruiters.py` |
| M | `job_agent/static/app.js` |
| A | `job_agent/static/command-center.css` |
| A | `job_agent/static/command-center.js` |
| M | `job_agent/static/index.html` |
| A | `job_agent/static/orchestration.js` |
| A | `job_agent/static/portal.css` |
| A | `job_agent/static/priority.js` |
| A | `job_agent/static/review.js` |
| A | `job_agent/static/spa.js` |
| M | `job_agent/static/style.css` |
| A | `job_agent/tenure.py` |
| A | `job_agent/workflow_guard.py` |
| A | `package-lock.json` |
| A | `package.json` |
| A | `playwright.config.ts` |
| A | `playwright.privacy.config.ts` |
| A | `playwright.r1.config.ts` |
| A | `playwright.r2.config.ts` |
| M | `pyproject.toml` |
| M | `requirements.lock.txt` |
| A | `scripts/capture_command_center.py` |
| A | `scripts/capture_command_center_proposal.py` |
| A | `scripts/diagnose_discovery_sources.py` |
| M | `scripts/evaluate_m2b.py` |
| A | `scripts/gmail_oauth.py` |
| A | `scripts/graceful_dashboard_stop.py` |
| A | `scripts/verify_command_center.py` |
| M | `scripts/verify_m2b_browser.py` |
| A | `scripts/verify_r2_state.py` |
| A | `specs/autonomous-orchestration.md` |
| A | `specs/browser-preparation.md` |
| A | `specs/command-center-redesign-plan.md` |
| A | `specs/command-center.md` |
| A | `specs/discovery-expansion.md` |
| M | `specs/m2c.md` |
| A | `specs/m2d-acceptance.md` |
| A | `specs/m2d-tasks.md` |
| A | `specs/m2d-traceability.md` |
| A | `specs/m2d.md` |
| A | `specs/m2d1-source-matrix.md` |
| A | `specs/m2d1.md` |
| A | `specs/m3-acceptance.md` |
| A | `specs/m3-tasks.md` |
| A | `specs/m3.1.md` |
| A | `specs/m3.md` |
| A | `specs/privacy-refactor-plan.md` |
| A | `specs/r1-reliability.md` |
| A | `specs/r2-profile-and-gmail.md` |
| A | `specs/release-safety.md` |
| M | `tests/conftest.py` |
| A | `tests/r1_fixture_server.py` |
| A | `tests/r1_fixture_worker.py` |
| A | `tests/r2_fixture_server.py` |
| A | `tests/synthetic_profile.py` |
| M | `tests/test_api.py` |
| A | `tests/test_automatic_drafts.py` |
| A | `tests/test_browser_applications.py` |
| A | `tests/test_browser_recovery.py` |
| M | `tests/test_classification.py` |
| A | `tests/test_command_center.py` |
| M | `tests/test_discovery.py` |
| M | `tests/test_discovery_conflicts.py` |
| A | `tests/test_discovery_expansion.py` |
| A | `tests/test_email_research.py` |
| M | `tests/test_entrypoint.py` |
| M | `tests/test_m2b.py` |
| M | `tests/test_m2c.py` |
| A | `tests/test_m2d.py` |
| A | `tests/test_m2d1.py` |
| A | `tests/test_m3.py` |
| A | `tests/test_m31.py` |
| A | `tests/test_m4.py` |
| M | `tests/test_milestone_2a23.py` |
| M | `tests/test_models_matching.py` |
| A | `tests/test_notification_lifecycle.py` |
| A | `tests/test_orchestration.py` |
| A | `tests/test_orchestration_login.py` |
| A | `tests/test_preparation_authorizations.py` |
| A | `tests/test_priority_queue.py` |
| A | `tests/test_privacy_config.py` |
| A | `tests/test_r1_reliability.py` |
| A | `tests/test_r1_workers_and_migration.py` |
| A | `tests/test_r2.py` |
| A | `tests/test_release_step1.py` |
| A | `tests/test_requirement_completeness.py` |
| A | `tests/test_review_workflow.py` |
| A | `tests/test_schedule_adapters.py` |
| A | `tests/test_server_runtime.py` |
| A | `tests/test_workflow_guard.py` |
| A | `tests/ui_fixture_server.py` |

## Explicit local-only exclusions

Private data/configuration/backups, environments, credentials, original documents, authentication/browser profiles, baseline screenshots, generated logs/reports/traces and the two exact archive paths remain excluded. No local artifact is deleted.

### Raw operational reports

- `docs/audit-defect-register.md`
- `docs/autonomous-orchestration.md`
- `docs/draft-policy-and-opportunities.md`
- `docs/m4-runbook.md`
- `docs/orchestration-continuation.md`
- `docs/preparation-review-update.md`
- `docs/priority-employer-research.md`
- `docs/public-discovery-interface-research.md`
- `docs/r1-implementation-report.md`
- `docs/r1-mandatory-completeness.md`
- `docs/r2-implementation-report.md`
- `docs/r3-final-verification.md`
- `docs/release-step1-results.md`
- `docs/source-coverage-expansion.md`
- `docs/spa-workflow-update.md`
- `docs/step1-continuation.md`
- `docs/ui-interaction-coverage.md`
- `docs/ui-testing.md`
- `docs/command-center-acceptance.md`

### Personal one-shot scripts

- `scripts/cache_step1_mail.py`
- `scripts/fill_gitlab_saved_answers.py`
- `scripts/inspect_gitlab_portal.py`
- `scripts/prepare_gitlab_portal.py`
- `scripts/prepare_step1_review.py`
- `scripts/repair_gitlab_upload.py`
- `scripts/replay_step1_mail.py`
- `scripts/verify_spa_browser.py`
- `scripts/verify_step1_browser.py`
- `scripts/verify_step1_state.py`
- `scripts/verify_packet_cards.py`
- `scripts/verify_r1_activation.py`
- `scripts/verify_r2_activation.py`

### Operational evidence embedded in old specifications

- `specs/m4.md`
- `specs/release-step1.md`

Original notes and specifications are preserved under ignored local data. Published handoffs and generic release/profile contracts contain no personal confirmation or application-history narrative.

See [verification](privacy-refactor-verification.md) for actual checks, limits and this-refactor file list. All private confirmations remain local. Production visual acceptance is pending.
