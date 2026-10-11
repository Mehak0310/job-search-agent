# Source connector contract

`SourceConnector.read(payload: bytes, format: str) -> list[dict]` parses data only. `FileConnector` handles UTF-8 JSON arrays and CSV with headers. An adapter must yield the JobInput schema: source, optional source_job_id, company, title, location, work_mode, description, skills, optional application_url, optional minimum/maximum experience and is_sample.

Every adapter must declare provenance, stable source IDs, retrieval time, authorization and terms-compliant access method. No connector may execute listing instructions, bypass access controls, log secrets, or submit applications. Errors use bounded stable codes. Document-level errors abort before imports; invalid records produce row-index errors and allow other valid records. Limits: 2 MiB per file, 1000 rows, bounded fields. JSON unknown fields fail validation; CSV skills use semicolon separators.

`MatchEvaluator.evaluate(job, profile)` returns score, reasons, missing requirements and disqualifiers. A future LLM evaluator can implement this interface without altering persistence or approval enforcement.

## Milestone 2A public discovery contract

`fetch(source: SourceConfig, reader: PublicReader, checkpoint: dict) -> Batch` returns raw records plus a checkpoint, or `not_modified=true`. `normalize(source, record) -> (JobInput, listing_url, evidence)` yields validated plaintext fields and conservative requirement evidence. `PublicReader` exposes GET only and derives endpoints from strict symbolic board IDs, never arbitrary configurable URLs. Public discovery does not reuse the bounded file-upload parser.

- [Greenhouse official Job Board API](https://docs.greenhouse.io/job-board.html): `GET https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true`, no authentication. The documented jobs response is a full array; there is no documented pagination on this listing endpoint. Validate `meta.total` if supplied; reject mismatch. Use the post ID, not internal_job_id. Content is entity-decoded and converted to plaintext. Location-only evidence may leave work mode unknown.
- [Lever official Postings API](https://github.com/lever/postings-api): global `https://api.lever.co/v0/postings/{site}` or EU `https://api.eu.lever.co/v0/postings/{site}`, JSON via `mode=json`, documented `skip`/`limit` pagination. Stop at a short page (including an empty final page), reject repeated IDs/pages and excessive pages/records. Preserve `id`, `hostedUrl`, `applyUrl`, categories/allLocations, workplaceType and country when present.

Neither connector claims a provider incremental/delta API. Locally compare stable `(source_id, provider_post_id)`, raw record hash and normalized content signature. Unchanged raw records skip normalization and evaluation; 304 touches known timestamps. Greenhouse may conditionally validate its complete response. Lever uses conditional headers only when its prior complete response was a single short page: a 304 on page one of a multi-page board cannot establish that other pages are unchanged.

Honor ETag/Last-Modified, useful Cache-Control max-age, Retry-After and source cooldown. Timeouts/transient 5xx/429 have bounded backoff; 403/404/redirects are not retried. Never retry a rate limit before its indicated delay. Bound decompressed response bytes, total requests, records and runtime. Failed/oversized/truncated full batches do not partially persist records. Invalid individual rows report metadata-only rejection events while valid rows commit atomically.

Enabled initial sources verified on 2026-10-10: Netomi (`netomi`, Lever) and Prophecy (`prophecysimpledatalabs`, Greenhouse). Board availability can change. Adding a source is a user configuration decision; provider/site uniqueness and immutable configured identities protect existing provenance.
