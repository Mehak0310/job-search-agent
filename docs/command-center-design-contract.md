# Command Center design contract

Status: PROPOSED VISUAL BASELINE, awaiting explicit user approval, 2026-10-19. R3 functional verification remains passed; R3 visual/design acceptance is NOT COMPLETE. Production implementation has not started.

Authority: the user's full-product correction and `specs/command-center.md`. The user clarified that the earlier design was discussed in ChatGPT, with no separate approved mockup. This contract and its new screenshots are proposed for review; approval will establish the acceptance baseline. The earlier release acceptance is functional evidence, not approval of visual parity. Colors and typography below are proposed choices, never previously approved details.

Review [the six-workspace gallery](../artifacts/command-center-proposal/review.html) or [interactive prototype](prototypes/command-center.html). All prototype data is explicitly synthetic and separate from candidate evidence. Workflow buttons demonstrate presentation with explanatory dialogs; no production workflow is implemented by the prototype. Header search is illustrative, not a completed search implementation. Sidebar persistence and full production accessibility remain implementation obligations.

## Shell and navigation

Desktop (1024px and above): 232px expanded / 72px collapsed fixed sidebar, 64px header, 24px content padding. Tablet: 72px icon rail, 64px header, 20px content padding. Mobile (below 640px): full-width content, 16px padding, labeled menu button opening a modal navigation drawer; Escape, backdrop, route selection and focus return close the drawer. Six primary workspaces; Settings outside primary navigation. Active workspace and subview remain visible and survive URL reload/back. Sidebar collapse preference persists locally.

Context search is labeled with its scope. Jobs search uses existing job filters; other views search loaded records only and say so. Notifications retain existing revision-bound actions. No schedule, write or external operation occurs from navigation/search.

Desktop header: breadcrumb at left, scoped search up to 300px at right, notification and Settings buttons, local profile indicator. Mobile: menu, workspace title, notification and Settings; contextual search belongs in the workspace toolbar. Subview tabs scroll inside their own region on narrow screens, with active tab scrolled into view. Tablet icons retain accessible names and hover/focus labels. Mobile menu width 260px with backdrop; no permanently reserved 72px mobile rail.

## Visual tokens (proposed)

System UI font: Segoe UI, Inter fallback, sans-serif; body 14px/1.5, small 12px/1.5, heading 26px/1.2, section 18px, card title 16px. Text #172b36, muted #586b76, canvas #f4f6f8, white surfaces, border #dce3e8; teal #17654d primary, dark sidebar #142e32. Amber indicates unresolved attention, red failure, green verified success. Text labels always accompany state colors.

Spacing: 4/8/12/16/20/24/32px. Surface radius 12px, controls 8px. Buttons at least 36px desktop / 44px touch, inputs at least 40px. Visible 3px keyboard outline. No remote fonts or assets. Avoid decorative shadows beyond subtle surface separation.

## Workspace hierarchy

| Workspace | Views | Presentation |
|---|---|---|
| Home | Overview, My Actions, Recent Activity | Four truthful operational metrics, attention/action list, metadata activity timeline; no invented trends |
| Find Jobs | Best Matches, Shortlisted, All Jobs, Needs Verification | 42/58 list/detail desktop, single column narrow; compact selectable roles, verified fit/eligibility/gaps/evidence and direct employer link in detail |
| Applications | Priority Queue, Preparing, Ready to Review, Applied, Follow-ups | Compact queue table; five-item review group; progress, status, owner/blocker summary before expandable field inventory and manual history |
| Inbox & Drafts | Recruiter Inbox, Job Alerts, Draft Approvals, Draft History | Conversation list/detail; urgency only from retained classification/deadline, unverified leads explicit, exact preview approval unchanged, durable operation history |
| Sources & Activity | Source Health, Run History, Schedules, Verification Backlog | Searchable board health table; retained run details, disabled/unverified schedule state, source limits and evidence backlog |
| My Profile | Career Facts, Documents, Saved Answers, Preferences | Evidence/provenance, canonical availability, explicit local parser decisions, reusable answers and scoped preference editors |

Tables scroll within labeled bounded regions on narrow screens; the document itself must not overflow. Long names wrap. Cards use a single title/status/action hierarchy. Technical field inventories collapse by default, with counts in summaries. Unknown facts remain unknown. Dialogs stay within the viewport, scroll internally and retain accessible close actions; modal browser focus trapping is preserved.

## Subview content contract

| View group | Required content and behavior |
|---|---|
| Home / Overview | Four operational metrics; attention list with owner and direct action; recent execution timeline; freshness, worker and scheduler metadata. No invented trends or readiness. |
| Home / My Actions | Only actual human decisions, including questions, form reviews and exact draft approvals; employer research stays agent-owned. |
| Home / Recent Activity | Time, operation, result and retained evidence; manual outcomes clearly attributed to the user. Audit metadata only. |
| Jobs / Best Matches | Ranked fit order, confidence and independent eligibility; unverified roles stay visibly blocked. Fit score is not a probability. |
| Jobs / Shortlisted | Saved shortlist with consistent detail panel; selection never approves eligibility. |
| Jobs / All Jobs | Full existing filters, sort and pagination; metadata-only alerts remain separately labeled. |
| Jobs / Needs Verification | Unknown/failed evidence, exact reasons, owner and source; no eligibility relaxation. |
| Applications / Priority Queue | Rank, role, fit, eligibility, persisted reason and details; next-five preparation remains explicit and guarded. |
| Applications / Preparing | Current batch overview, processed/total, ready/answer/agent counts, compact five-card group. Each card: title, employer, status, last check, completed fields, blocker owner, next action, collapsed raw inventory/documents/history. Prior batches reachable. |
| Applications / Ready to Review | Only genuinely inspected ready forms, document acceptance and independent gates; user reviews the employer form. |
| Applications / Applied | Manual/confirmed outcome, outcome provenance, independent browser session health, immutable history. No claimed submission from a click or lost session. |
| Applications / Follow-ups | Recorded outcomes and genuine received requests; no synthetic due dates or active outreach schedule. |
| Inbox / Recruiter Inbox | Received conversation list/detail, sender, subject, time, explicit deadline and classification reason. Identity verification separate from priority classification. |
| Inbox / Job Alerts | Unverified lead state, exact vacancy/identity evidence, duplicate state, research/import controls. No blanket job-ready claims. |
| Inbox / Draft Approvals | Local text versus real Gmail draft distinction; exact recipient, source, subject, body, attachment metadata and approval snapshot. Revisions invalidate approval. Unverified recipient disables creation. |
| Inbox / Draft History | Durable operation state, returned ID or explicit absence, timestamp; historical operations survive later packet edits. |
| Sources / Source Health | Employer/board, integration state, last attempt AND last success, freshness/cooldown, failure/retry reason, retained counts and evidence. |
| Sources / Run History | Real run ID, start/finish, stages, source failures and retained checkpoints; no invented executions. |
| Sources / Schedules | Stored plan, enabled flag, actual registration evidence or unknown, no promised execution from cadence alone. |
| Sources / Verification Backlog | Unresolved evidence grouped by owner/reason; source limits, failed attempts and retry conditions. |
| Profile / Career Facts | Accepted values and provenance, professional versus project/learning evidence, revision; no inferred experience. |
| Profile / Documents | Canonical reference and availability, unchanged file bytes; explicit replace/parse actions; proposals require user decision. |
| Profile / Saved Answers | Question, value, scope, source, conflict/supersession and deliberate edit/reuse. Never auto-fill prohibited declarations. |
| Profile / Preferences | Search settings and notification controls; preferences never become career facts or schedule authorization. |

## Interaction and state contract

Selection is indicated by border, background and accessible state, not color alone. Selecting a role/conversation refreshes contextual detail without a production mutation. Preserve URL reload/back, old aliases and meaningful focus. Enter/Space activates buttons; primary nav retains keyboard arrow/Home/End compatibility. Focus is restored to the invoking control after dialogs/drawer close. Touch actions should be at least 44px; table scrolling has keyboard access. Production keyboard and screen-reader review remains required.

Loading is local to its pane, with skeleton/short status rather than blanking the workspace. Empty states explain which filters/scope produced no results and offer a safe route. Error states preserve retained data with explicit stale timestamps and local retry. Disabled actions expose their blocker. Technical errors never dominate the normal workflow. Five-card density must be tested with long titles, multiple blockers and lost sessions; counts must come from canonical projections, not fixture constants. No public or external asset requests.

Prototype simplifications: secondary subviews demonstrate hierarchy with smaller synthetic tables; source table groups latest successful attempt rather than showing the complete production freshness schema. Modal content explains intended controls and does not model real approval payloads. Those states require existing API integration and populated production review after approval.

## Acceptance protocol

Capture all 24 subviews at 1440, 768 and 390px using actual retained data, before and after (72 screenshots per phase). Also exercise dense synthetic batches, long names, blocked/error states, keyboard navigation and dialogs. Actual-data screenshot index lives under ignored `data/ui-redesign/`; candidate/mail/profile pixels must never enter Git. Proposed synthetic screenshots live in `artifacts/command-center-proposal/` and are NOT production after evidence. Automated geometry and functional tests are evidence, not visual approval. Manually inspect representative populated screens and record remaining uninspected screens honestly. User approval of this new contract/screenshots establishes the target; final acceptance additionally requires complete implemented-state review and regression.
