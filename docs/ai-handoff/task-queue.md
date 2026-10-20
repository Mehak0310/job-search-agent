# Shared AI handoff: task queue

Updated: 2026-10-20. Priority is not authorization. The local F1–F8 remediation is explicitly authorized by the user; P1, P2 and P3 remain queued and unauthorized.

## Current authorized local remediation

| Task | Owner | Dependencies | Acceptance | State |
|---|---|---|---|---|
| Audit remediation F1–F8 for the existing application-recovery and eligibility milestone | Local Codex session | Explicit user authorization; preserve the existing milestone; local synthetic fixtures only | Preserve original evidence times; reject ambiguous/contradictory evidence; keep private discovery and Gmail references internal; require explicit India location; suppress readiness and duplicate action after any submitted outcome; interpret headcount ranges conservatively; retain all 55 tracker IDs and stages 1–8; run focused then relevant full regression | Complete and published as `4a3a3845474161764cf1aaf1578d851f56b7da29`. Latest full Python: 583 passed/91.94%; full UI: 157 passed; R1 four consecutive passes; lifecycle Python 40 passed; R2 two passed. No live verification or production activation. |

The application-recovery milestone was published as `4a3a3845474161764cf1aaf1578d851f56b7da29`; publication did not authorize production activation or live operations. Freshness policy is approved: vacancy activity and vacancy/requirements evidence 7 days; employer headcount, India-employment and payroll evidence 90 days.

## Next actionable stages

| Priority | Stage | Action | Boundary / completion evidence |
|---|---|---|---|
| Next | Stage 2 | Read-only reconciliation of the four historical applications | Requires explicit live read-only authorization; compare current tabs/forms with preserved state, perform no filling, upload or submission, and record exact blockers |
| Then | Stage 3 | Verify real vacancies and employer eligibility | Apply the approved 7-day/90-day freshness windows and 1,000 non-remote/500 remote headcount thresholds; the five-eligible-vacancy goal remains pending |
| After eligibility | Stage 4 | Prepare one verified eligible application for human review | Requires separate explicit authorization; preserve approval gates and never click final Submit |
| Following | Stage 5 | Complete Command Center production visual acceptance | Review all six workspaces on real persisted data at approved viewport sizes; functional tests alone do not grant acceptance |

Stage 2 remains next. The following approved policies define later work but do not change that priority:

| Later work | Required result | Current state |
|---|---|---|
| LinkedIn/Naukri and referral-source evaluation | Measure coverage per source; evaluate permitted alerts, public employer links and structured imports; assess TechReferrals access, structure, original LinkedIn/X provenance, timestamps, normalization, deduplication, vacancy currency and employer eligibility | Not implemented; TechReferrals is a candidate supplementary source and all resulting leads remain unverified |
| Gmail draft-only implementation | Create unsent drafts only after verified recipient/role relevance, current eligibility and employer evidence, approved-fact grounding, exact preview, persisted audit, duplicate prevention, uncertain-outcome recovery and preservation of user edits | Product policy approved; live adapter disabled; implementation, security verification and release testing pending; sending and automatic application submission prohibited |
| Command Center acceptance | Preserve the six-tab prototype and bind per-source coverage, referrals/original-source attribution, eligibility/verification and pending/prepared/created/needs-review/blocked/failed draft states to persisted data | Not implemented; no invented readiness, source coverage or recruiter details |

| Priority / task | Owner | Dependencies | Acceptance criteria | Approval / state |
|---|---|---|---|---|
| P1: Cross-platform Python browser fixtures | Unassigned; human selects Codex environment/agent | Explicit coding authorization; inspect the Windows-path fixture and all consumers; confirm available browsers and supported configuration | Portable browser discovery and explicit fixture configuration; Windows behavior preserved; affected browser/safety tests execute on Windows and Linux; focused checks before full regression; keep the 90% gate and assertions, with no skips added to hide failures; record exact commands, versions and actual coverage | Queued; not authorized by this setup; not started |
| P2: Six-tab Command Center visual refinements | Unassigned; human selects Codex environment/agent | Explicit approval of the proposed contract/screenshots, plus implementation authorization; use existing APIs and persisted data; review applicable specs | Implement the approved six-tab contract and protected workflows; real persisted projections, no invented readiness; screenshot review of all 24 subviews at 1440/768/390 widths plus blocked/error/dialog/dense states; retain actual-data screenshots privately; record unreviewed states and obtain human visual acceptance; run required functional/persistence regression | Queued; design baseline and implementation approval pending; not started |
| P3: Local/cloud parity validation | Unassigned; human selects Codex environment/agent | Explicit validation authorization; P1 for a full parity claim; P2 if validating the refined UI; comparable source revisions, dependency sets and synthetic fixtures | Record Windows/Linux Python, Node, browser and dependency versions; run comparable focused/full Python and applicable UI/R1/R2 suites; preserve failed/skipped/unrun distinctions and the 90% gate; document platform, setup and runtime limitations; do not equate isolated test success with production activation | Queued; not authorized by this setup; not started |

P2 need not wait for P1 to receive design review; a full cross-platform regression claim depends on P1. Use the [design contract](../command-center-design-contract.md), [acceptance report](../command-center-visual-acceptance.md), [redesign plan](../../specs/command-center-redesign-plan.md), [release safety](../../specs/release-safety.md) and [verification ledger](verification.md) rather than duplicating requirements here.

## Coordination and completion

Before claiming a task, verify branch/HEAD and reread the latest queue. Record the named owner, authorization reference, scope and intended branch. Use a dedicated branch or explicitly approved PR workflow for concurrent work; never independently push conflicting updates to `main`. Reconcile newer changes before editing or publishing; do not reset or overwrite another agent's work.

On completion, update [current status](current-status.md) and [verification](verification.md) with changed paths, exact commands, results, full tested commit or base commit plus uncommitted-diff scope, blockers and remaining work. Add a decision only when actually approved. Commit/push/PR, merge, deployment, production restart, external messages, submissions and schedule activation require their own explicit authorization. No such action is authorized by this queue.
