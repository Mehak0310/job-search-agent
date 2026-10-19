# Route and feature migration map

| Existing route/capability | New workspace/subview | Backend retained |
|---|---|---|
| home-panel | Home / Overview, My Actions, Recent Activity | overview, browser progress, audit |
| opportunities-panel | Find Jobs / All Jobs, Shortlisted, Needs Verification | jobs filters, manual status, canonical card |
| recommended-panel | Find Jobs / Best Matches | recommendations and eligibility filters |
| browser-panel | Applications / Preparing, Ready to Review, Applied, Follow-ups | browser history, batches, recovery, answers, upload evidence |
| priority-panel | Applications / Priority Queue | persisted priority snapshot and explicit refresh |
| email-leads-panel | Inbox & Drafts / Recruiter Inbox, Job Alerts | received metadata, research, idempotent import |
| m3-panel | Inbox & Drafts / Draft Approvals, Draft History | text editing/export, exact approval, durable operations |
| discovery-panel | Sources & Activity / Source Health | board status and explicit discovery |
| m2d-panel | Sources & Activity / Verification Backlog | configured coverage, source limitations |
| professional-profile | My Profile / Career Facts, Documents, Saved Answers | approved profile, explicit parsing/fact decisions, scoped answers |
| preferences-panel, background-panel | My Profile / Preferences | deterministic matching preferences/background |
| tools-panel | Settings / Import and diagnostics | local import and metadata audit |

No legacy capability may be deleted merely because its original section is no longer primary navigation. Exact approval and answer modals remain bounded; job/text details become nonmodal drawers. Schedule status must distinguish configuration from actual registration.
