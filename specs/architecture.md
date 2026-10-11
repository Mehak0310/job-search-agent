# Architecture

FastAPI serves a static HTML/CSS/JavaScript dashboard and JSON API. Pydantic validates input. Python sqlite3 provides parameterized SQL, foreign keys, transactions and WAL. A file database defaults to ignored `data/jobs.sqlite3`. Tests inject temporary database paths.

Modules: models (validation), matching (pure evaluator), connectors (parser contract and file implementation), database (schema/transactions), service (import/status/profile orchestration), main (HTTP boundary). No frontend build, ORM, worker queue or LLM SDK is needed.

Identity: hash normalized company/title/location/work mode, plus use normalized application URLs and source IDs as additional identity evidence. Identity conflicts reject the record rather than merging different jobs. Missing/reused identity data can produce false deduplication; future connector IDs improve specificity. One job retains multiple source references. Duplicate records do not overwrite job details; changed source content is counted as a conflict. Same-file repeated records are duplicates.

All successful import writes and their audit events commit atomically. Per-record validation failures do not prevent valid records being imported; malformed documents cause no job writes. Status and history/event writes share a transaction. Profile changes rescore existing jobs transactionally. Foreign keys and uniqueness protect integrity. Audit and status history reject update/delete via SQLite triggers.

Local HTTP defenses: trusted hosts, browser-origin checks on mutations, bounded streamed uploads, no CORS allowance, content security policy, escaped text in the UI. Raw job text is never rendered as HTML. Default server is loopback; this service has no authentication and must remain local.

## Milestone 2A extension

Version 2 migration adds registry, run/source metrics, lease, structured live-search background, job classification/timestamps/listing URL, and per-reference hashes/timestamps/snapshots. SQLite backup `data/jobs.sqlite3.pre-v2.bak` precedes atomic ALTER/CREATE operations; failures roll back. Version 1 profile, job IDs, manual statuses/history and immutable audit are retained. Stop application/CLI processes before the first upgrade; supported ongoing concurrency is after schema initialization.

`public_connectors.py` handles GET-only HTTPS I/O and normalization; `registry.py` holds persistent source config/health; `discovery.py` coordinates sequential bounded runs; `discovery_store.py` handles incremental writes; `classification.py` extracts conservative evidence and ranks live jobs. `discover.py` is the standalone CLI. `scheduling.py` builds and explicitly registers a Windows task only with --register. Static frontend adds polling and source/category controls without a build system.

Keep legacy `Profile` and deterministic file-import matcher unchanged. New `SearchBackground` stores the authorized approximately 7 total years / 3.5 backend years and user-reported frontend strengths versus additional/developing areas. Individual academic/project/professional evidence is unspecified unless supplied; do not invent it. Live ranking uses this background plus shared work-mode/exclusion preferences. Broad role families are built into deterministic classification, not an LLM. Background/profile changes rescore cached live evaluations without changing listing-change timestamps or statuses.

One cross-process SQLite lease guards both CLI/scheduled and API runs. HTTP POST claims a run and dispatches a single-worker thread, returning 202 and run ID immediately. Poll reads persisted results. Lease expires after configured runtime plus 60 seconds grace; recovery marks the old run INTERRUPTED. Process shutdown waits for bounded worker completion. A sequential concurrency limit of 1 deliberately avoids network races; values above 1 are rejected rather than silently ignored.

A source fetch completes before its transaction begins. A batch transaction covers canonical jobs, source snapshots, and listing audit. Per-record savepoints prevent invalid rows from discarding good rows. Source-run outcome, source health/checkpoint and overall metrics persist in subsequent transactions; they are not one distributed atomic commit with the fetch. A crash can leave an interrupted run but idempotent replay recovers existing jobs.

Source IDs are authoritative for updates, so title/location/description changes retain the stable job ID. Identity/URL matching detects cross-source copies. Contradictory identities/content and multiple same-source IDs with identical natural identity are rejected for review. The first accepted live source owns canonical updates; matching secondary snapshots add provenance without overwriting primary data. Secondary conflicting changes are rejected. This avoids alternating provider descriptions rewriting each other. Removed jobs are retained with historical last-seen; automatic closure/expiry is deferred.

Only relevant listing content, URL or eligibility evidence changes reevaluate that job. Provider-only timestamp changes update raw hash and last-seen without changing match/status. Actual user status and history never change from a discovery scan.


## Milestone 2A.1
Schema v3 stores eligibility, seniority, lifecycle, duplicate-group, canonical-link and source-verification fields. Classification remains deterministic and keeps score, eligibility, priority and confidence separate. Listings become possibly closed after one complete successful miss and closed after two; failures never advance lifecycle.


## Milestones 2A.2/2A.3
Discovery separates bounded concurrent network fetch from deterministic source-ordered persistence. Schema v4 adds source publication/update evidence, freshness priority, normalized location, structured requirements/compensation and a persistent platform matrix. The jobs API performs SQL filtering/counting/pagination with stable ID tie-breaking.
