# Shared AI handoff: task queue

Updated: 2026-10-20. Priority is not authorization. The local F1–F8 remediation is explicitly authorized by the user; P1, P2 and P3 remain queued and unauthorized.

## Current authorized local remediation

| Task | Owner | Dependencies | Acceptance | State |
|---|---|---|---|---|
| Audit remediation F1–F8 for the existing application-recovery and eligibility milestone | Local Codex session | Explicit user authorization; preserve the existing dirty milestone; local synthetic fixtures only | Preserve original evidence times; reject ambiguous/contradictory evidence; keep private discovery and Gmail references internal; require explicit India location; suppress readiness and duplicate action after any submitted outcome; interpret headcount ranges conservatively; retain all 55 tracker IDs and stages 1–8; run focused then relevant full regression | Source fixes and audit completed locally. Focused/full Python, full UI and R2 passed. The fixture-only R1 termination defect is repaired; R1 passed four consecutive runs and lifecycle Python passed 40 tests. No live verification or publication. |

The earlier application-recovery milestone remains uncommitted. This remediation does not authorize the P2 visual redesign, live operations, publication or production activation. Freshness policy is approved: vacancy activity and vacancy/requirements evidence 7 days; employer headcount, India-employment and payroll evidence 90 days.

| Priority / task | Owner | Dependencies | Acceptance criteria | Approval / state |
|---|---|---|---|---|
| P1: Cross-platform Python browser fixtures | Unassigned; human selects Codex environment/agent | Explicit coding authorization; inspect the Windows-path fixture and all consumers; confirm available browsers and supported configuration | Portable browser discovery and explicit fixture configuration; Windows behavior preserved; affected browser/safety tests execute on Windows and Linux; focused checks before full regression; keep the 90% gate and assertions, with no skips added to hide failures; record exact commands, versions and actual coverage | Queued; not authorized by this setup; not started |
| P2: Six-tab Command Center visual refinements | Unassigned; human selects Codex environment/agent | Explicit approval of the proposed contract/screenshots, plus implementation authorization; use existing APIs and persisted data; review applicable specs | Implement the approved six-tab contract and protected workflows; real persisted projections, no invented readiness; screenshot review of all 24 subviews at 1440/768/390 widths plus blocked/error/dialog/dense states; retain actual-data screenshots privately; record unreviewed states and obtain human visual acceptance; run required functional/persistence regression | Queued; design baseline and implementation approval pending; not started |
| P3: Local/cloud parity validation | Unassigned; human selects Codex environment/agent | Explicit validation authorization; P1 for a full parity claim; P2 if validating the refined UI; comparable source revisions, dependency sets and synthetic fixtures | Record Windows/Linux Python, Node, browser and dependency versions; run comparable focused/full Python and applicable UI/R1/R2 suites; preserve failed/skipped/unrun distinctions and the 90% gate; document platform, setup and runtime limitations; do not equate isolated test success with production activation | Queued; not authorized by this setup; not started |

P2 need not wait for P1 to receive design review; a full cross-platform regression claim depends on P1. Use the [design contract](../command-center-design-contract.md), [acceptance report](../command-center-visual-acceptance.md), [redesign plan](../../specs/command-center-redesign-plan.md), [release safety](../../specs/release-safety.md) and [verification ledger](verification.md) rather than duplicating requirements here.

## Coordination and completion

Before claiming a task, verify branch/HEAD and reread the latest queue. Record the named owner, authorization reference, scope and intended branch. Use a dedicated branch or explicitly approved PR workflow for concurrent work; never independently push conflicting updates to `main`. Reconcile newer changes before editing or publishing; do not reset or overwrite another agent's work.

On completion, update [current status](current-status.md) and [verification](verification.md) with changed paths, exact commands, results, full tested commit or base commit plus uncommitted-diff scope, blockers and remaining work. Add a decision only when actually approved. Commit/push/PR, merge, deployment, production restart, external messages, submissions and schedule activation require their own explicit authorization. No such action is authorized by this queue.
