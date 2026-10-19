# M2D acceptance checklist

- [x] Every named source has an honest implementation state, owner stream and bounded coverage state.
- [x] Source failure, access block or exhausted budget leaves resumable queued work and yields `PARTIAL` where applicable.
- [x] Unknown hard facts keep plausible jobs visible and pending; known failures exclude with evidence.
- [x] Portal review does not require recruiter email; email-draft readiness requires full eligibility plus verified recipient.
- [x] Generic imported `VERIFIED` cannot grant action readiness without local evidence.
- [x] Jobs retain distinct requisitions, aliases, provider IDs and cross-stream observations.
- [x] Gmail export handles received-only incremental messages, overlap, multi-job alerts and preserved cursors.
- [x] Immutable snapshots and consumer checkpoints tolerate missing/stale/partial streams.
- [x] JobQueue-v1 exports validate sheets, hyperlinks, statuses and round-trip identity.
- [x] Dashboard reports distinct jobs separately from observations and exposes queues/blockers.
- [x] Migration backup/rollback, existing data, manual statuses and history are preserved.
- [x] Focused, full and browser checks pass at 90% or greater statement coverage.
- [x] No scheduler, submission, message, Gmail draft, PR, visibility change, paid API or M3 work occurs.

Implementation acceptance passes. Operational coverage remains `PARTIAL` because inaccessible and unattempted sources are disclosed rather than treated as covered.
