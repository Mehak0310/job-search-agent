# M2D traceability matrix

| Requirement | Implementation | Verification |
|---|---|---|
| Four streams and ownership | `m2d_sources`, seeded matrix, `M2DEngine` | source ownership and matrix tests |
| Persistent discovery/verification queues | `m2d_tasks` with lease, attempts, cursor, due time | restart, fairness and bounded continuation tests |
| Coverage denominators and seven-day state | source coverage API/report | attempted/meaningful/exhaustive distinction tests |
| Separate lifecycle/eligibility/verification/readiness | `job_operational_state`, conservative classifier | unknown/headcount/contact/status mapping tests |
| Shared identity and provenance | stable JobKey plus `job_observations` | alias/provider/cross-stream identity tests |
| Immutable run handoff | `m2d_snapshots`, checksum, consumer checkpoints | stale/partial/idempotent checkpoint tests |
| Gmail local boundary/export | `GmailAdapter`, synthetic JSON import | received-only, pagination and multi-job tests |
| JobQueue-v1 XLSX | `jobqueue.py` export/import and manifest | sheets, hyperlinks, statuses and round-trip tests |
| Dashboard visibility | M2D summary, coverage, queue and readiness APIs/UI | synthetic browser checks |
| Data and privacy preservation | v7/v8 backups, ignored exports/mail/resume data | rollback, row counts, integrity and Git audit |
| Resume setup | filename-only candidate scan; M2C workflow reuse | user selection pending for multiple candidates |
| M3 boundary | structured Draft Inputs only | no prose/draft/send/submit endpoints |
