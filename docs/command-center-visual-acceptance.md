# Command Center visual acceptance

Status: NOT COMPLETE. R3 functional verification remains PASSED at its historical checkpoint. The user explicitly requested contract/screenshots and design approval before full implementation. No visual parity is claimed.

## Milestones

| Milestone | Status |
|---|---|
| Current-product audit and baseline | Complete within recorded inspection limits |
| Proposed contract and isolated prototype | Implemented and checked locally |
| User approval of new visual baseline | PENDING |
| Production shell | Planned after approval |
| Six production workspaces / all subviews | Planned after approval |
| Production visual review and full regression | Planned; NOT COMPLETE |

## Before / proposal / after index

- Actual before: `data/ui-redesign/before/index.json` (ignored/private), 24 subviews at 1440/768/390px = 72 screenshots.
- Synthetic proposal: [gallery](../artifacts/command-center-proposal/review.html) and [index](../artifacts/command-center-proposal/index.json), 72 subview screenshots plus 6 interaction states.
- Production after: NOT captured. Running UI/backend unchanged.

Supplemental proposal states: three notification dialogs, mobile menu, collapsed desktop rail and expanded field inspection. Actual candidate/mail/profile pixels remain private. Prototype uses fictional demonstration data, never actual candidate evidence.

## Explicit pass/fail checklist

| Check | Status / limits |
|---|---|
| Historical R3 functional checkpoint | PASSED; previous evidence retained |
| R3 visual/design acceptance | NOT COMPLETE; supersedes prior blanket design-complete language |
| Baseline populated capture | 72 screenshots; zero page errors/document overflow/blocked request attempts |
| Proposed shell dimensions | Geometry checked: desktop 232px sidebar/64px header/24px padding, tablet 72px rail, mobile full width |
| All proposed subviews at three widths | 72 captures; zero page errors, document overflow or out-of-viewport headings/buttons outside intentional scrolling regions |
| Five-card batch / dense blocked state | Five cards, long title, answer blocker, research blocker, lost session; raw field details closed by default and expandable |
| Dialog bounds, Escape and focus return | Checked at three widths using native modal behavior |
| Mobile menu and collapsed rail | Open/Escape/focus return and 72px desktop collapse checked |
| Role and conversation selection | Checked locally; unresolved eligibility stays blocked |
| Network | Proposal made zero HTTP/HTTPS requests |
| Manual screenshot review | Six main desktop and six main mobile screens inspected; Home tablet inspected; all remaining screens captured, not all manually inspected |
| Actual production state/error/loading/a11y review | PENDING implementation; synthetic states are not production behavior proof |
| New baseline approved by user | PENDING |
| Final production parity | NOT COMPLETE |

## Actual commands and validation limits

- `.venv\Scripts\python.exe scripts/capture_command_center.py --phase before`: 72 actual screenshots, zero page errors/overflow/blocked attempts. First attempt hit CSP's string-evaluation restriction; changed the capture script to locator assertions and reran. CSP was never relaxed.
- `.venv\Scripts\python.exe scripts/capture_command_center_proposal.py`: synthetic captures plus geometry, batch disclosure, dialog/focus/navigation and detail-selection checks. Rerun after proposal refinements; no repeated backend/model evaluation.
- `.venv\Scripts\python.exe -m pytest tests/test_command_center.py -q --no-cov`: 3 passed in 1.31s; one existing Starlette/httpx deprecation warning. No new coverage percentage measured.
- `node --check data/ui-redesign/proposal-syntax.js`: passed on the extracted prototype script. Local gallery link validation: 97 links checked, none missing. Focused tracked-document `git diff --check` passed.

Full Python, Playwright and R1/R2 integrated suites were not rerun for this isolated design artifact. Historical results remain historical. Full regression, actual production screenshots, read-only database/document preservation checks and manual accessibility review remain required after implementation. Prototype workflow buttons open explanatory dialogs; search is illustrative; no production capability is implemented by those controls.

Protected workflows: production UI/backend untouched; no automatic submission, email send, Gmail draft creation, schedule activation, fact approval, document replacement, direct database write, commit, push or deployment. HEAD `5eb64454f4e04c0e0bfe624c2d70380e7cc2346f`; existing dirty work retained; no new commit.
