# Milestone 2A.1 acceptance criteria

- [x] Every enabled source has persisted provider identity, official career/board URLs, verification time/status/evidence, and a successful bounded endpoint verification proving company ownership.
- [x] Coverage is materially broader than two employers; the 30–50 target is reported honestly against verified availability.
- [ ] Discovery has pooled clients, source-specific cooldowns, request/runtime/size limits, retry backoff, conditional requests, and checkpoints. Parallel source fetching remains deferred; execution is sequential.
- [x] Eligibility is exactly `ELIGIBLE`, `INELIGIBLE`, or `UNKNOWN`, with explanation, evidence, confidence, and evaluated time. Ambiguous remote is `UNKNOWN`.
- [x] Category, priority, score, confidence, and seniority compatibility are separate and explainable. Frontend leadership and transition-friendly applied AI rank appropriately; deep backend and AI research mismatches are reduced.
- [x] Total and technology-specific experience are distinguished; ranges and junior/mid/senior/lead/staff/principal/architect/manager titles are handled conservatively.
- [x] Jobs retain stable source IDs, canonical URLs, hashes, timestamps, duplicate groups, and ACTIVE/POSSIBLY_CLOSED/CLOSED/UNKNOWN lifecycle. One failed scan cannot close a listing.
- [x] Existing jobs, provenance, history, shortlist, and manual statuses survive migration and scans.
- [x] Persistent run metrics include configured/verified/enabled/healthy sources, eligibility/category counts, new/updated/unchanged/duplicates, failed/retries/bytes, and nullable per-new-relevant efficiency ratios.
- [x] Dashboard filters eligibility/category/priority/seniority/employer/activity, sorts score/freshness, and exposes evidence, explanations, source health, verification, scan state, and metrics.
- [x] Mocked tests cover verification, bad/empty boards, cooldowns, eligibility, seniority, relevant experience, ranking, lifecycle, transient failures, deduplication, metrics, API/UI, and status persistence without live CI calls.
- [x] Actual browser interaction covers the 18 requested scenarios with screenshots; any unavailable scenario is named as failed with its exact blocker.
- [x] Two bounded live scans confirm real storage, repeat behavior, and preserved manual status. Full tests pass with at least 90% coverage for changed Python code.
- [x] Local-only binding remains; no account access, submission, email, security bypass, scheduled task registration, or PR occurs.
