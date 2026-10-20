# Shared AI handoff: current status

Updated: 2026-10-20. Audience: ChatGPT, ChatGPT Codex and local VS Code Codex.

## Superseding local milestone checkpoint

The 2026-10-19 snapshot below is historical where it conflicts with this section. It is retained so earlier coordination claims are not silently erased.

| Item | Current evidence |
|---|---|
| Repository checkout | `main`, base HEAD `e94340d61ee88aea137a878ad1e48ca860f3e60f` |
| Working tree | Local application-recovery/eligibility milestone plus F1–F8 audit remediation are uncommitted; no commit, push, branch operation or publication occurred |
| Authorization | The user authorized local source, synthetic tests and directly related documentation only; production/browser/Gmail/employer/schedule/submission actions remain prohibited |
| Implemented | F1–F8 remediation addresses evidence timestamp reuse, fail-closed evidence interpretation, Applications privacy projection, country-aware locations, submission/readiness consistency, headcount ranges, policy documentation and regressions |
| Verified | Independent F1–F8 audit corrections completed. Requirement provenance now requires credential-free HTTPS and its focused suite passed 99 tests. The latest full Windows Python run passed 583 tests at 91.94% aggregate coverage; the full synthetic UI passed 157 tests. The preceding F1–F8 run passed 576 Python tests at the same coverage. R2 passed 2 tests. The fixture-only R1 termination defect was repaired and R1 passed four consecutive isolated runs; relevant lifecycle Python passed 40 tests. Changed Python modules: eligibility 96%, employer evidence 100%, requirement clauses 100%, M2D 98%, browser store 97%, priority queue 94%. Exact commands and limitations are in [verification](verification.md). |
| Blocked | No production database, current applications, live employer evidence or live form acceptance were inspected; no genuinely eligible five-candidate batch is established. |
| Planned | Complete a final read-only publication review; separately authorize any production evidence check, service activation or live form acceptance; preserve the six-tab design approval boundary. |

The approved freshness policy is 7 days for vacancy activity and vacancy/requirements evidence, and 90 days for employer headcount, India-employment and payroll evidence. Reuse preserves original verification times; missing, stale, contradictory, future-dated or unverifiable evidence remains unresolved. Synthetic test results do not establish live eligibility or employer-form acceptance.

The original snapshot's `work` branch, pre-handoff baseline, pending publication and docs-only task statements are stale for this checkout. They remain below as historical coordination evidence. The prior live application counts are not revalidated by this local milestone.

## Authority and checkout

This directory is a coordination index, not a second requirements specification. Follow [AGENTS.md](../../AGENTS.md), the applicable project specifications and explicit human approvals. Read all four handoff files before work: this status, [decisions](decisions.md), [task queue](task-queue.md) and [verification](verification.md). If evidence conflicts, record the discrepancy and resolve it before dependent work; do not silently replace a newer decision.

| Item | Evidence and status |
|---|---|
| Repository | `Mehak0310/job-search-agent` |
| Source baseline / pre-handoff HEAD | `6e195c8c9ec265f8bcd9628d44c68d0e4f17fcbb`; resolve the handoff commit with Git after publication |
| Observed local branch | `work`; verify branch and full HEAD again at each task start |
| Source checkpoint | R1/R2/R3 source checkpoint published. Before handoff publication, `git fetch origin main` confirmed remote `main` matches the source baseline, with zero ahead/behind. Baseline subject: `feat: checkpoint job agent R1-R3 with privacy-safe defaults`. |
| Current work | Shared handoff documentation and minimal operating-rule integration only; user explicitly authorized committing and pushing these five documentation files on 2026-10-19 |
| Production | Per user update, backend has not been restarted to activate the privacy refactor. No live production state was inspected in this task. Source publication is not runtime activation. |

## Milestones and blockers

- R1/R2/R3 functionality and privacy refactor are present in the source checkpoint. Windows verification is historical reported evidence; cloud Linux verification was observed in the preceding setup session. See [verification](verification.md) for exact outcomes and limits.
- Production Command Center visual acceptance remains **pending**. The [six-tab design contract](../command-center-design-contract.md), [interactive proposal](../prototypes/command-center.html), [visual acceptance report](../command-center-visual-acceptance.md) and [redesign plan](../../specs/command-center-redesign-plan.md) are available. The contract still labels its proposed visual baseline as awaiting approval; functional test passes do not grant that approval.
- Linux Python browser fixtures hardcode a Windows Chrome executable. A separate authorized coding task is required. Do not lower the 90% coverage gate or skip failing tests to obtain a green result.
- Private candidate configuration remains local and excluded from Git. This handoff contains no candidate facts, mail contents, credentials, production records or private local paths.

## Next action and scope

Publish only the reviewed five-file documentation change through a normal push to `main`, as explicitly authorized by the user on 2026-10-19. No PR, merge, force push, deployment or production activation is authorized. P1, P2 and P3 are queued, not started; obtain explicit task authorization before implementation. P2 additionally requires explicit approval of the visual contract/screenshots. Future sessions must verify the resulting branch and full commit rather than treating the source baseline as the current HEAD.

The older [project status](../project-status.md), [handoff](../handoff.md) and [privacy verification report](../privacy-refactor-verification.md) describe the pre-publication phase. Their publication-pending language and earlier HEAD are historical; the user's published-checkpoint update above is the current coordination status. Their verification evidence remains useful and is not rewritten as a fresh test run.

Before a handoff update, inspect branch, HEAD, status and the current diff again. Incorporate newer work rather than replacing whole files from an older snapshot. Use dedicated branches or an approved PR workflow for concurrent changes; two agents must not independently push to `main`.
