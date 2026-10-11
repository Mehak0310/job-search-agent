# Milestone 2A.2 + 2A.3 acceptance criteria

- [x] At most four source fetches run concurrently by default; global request/runtime budgets are thread-safe; results persist in stable source order through serialized SQLite transactions.
- [x] `/api/jobs` supplies page, page_size, total, pages and stable items after all filters; legacy unpaged callers have a documented compatibility path.
- [x] Query plans use justified indexes and pagination does not load the full result set.
- [x] Remote OK and We Work Remotely adapters parse mocked and verified public feeds with stable IDs, timestamps, attribution, safety limits and isolation.
- [x] All 20 requested platforms have dated official URLs and honest PUBLIC_FEED/AUTHORIZED_API/ALERT_IMPORT/MANUAL_IMPORT/RESTRICTED/UNVERIFIED classifications.
- [x] Schema v4 distinguishes published, source-updated, first-discovered and last-seen UTC timestamps with provenance/confidence; unknown remains unknown.
- [x] Freshness windows and separate discovery priority are deterministic; future/malformed/date-only timestamps are conservative.
- [x] Location normalization covers NCR, Gurgaon/Gurugram, Noida/Greater Noida, Mohali, Chandigarh, other India, remote India and unknown without conflation.
- [x] Experience interval-overlap and skill alias/any/all filters compose with all existing filters before pagination.
- [x] Dashboard defaults to 48 hours, supports pagination, clear/reset controls, persists filters, and shows distinct timestamps and salary when known.
- [x] Metrics persist freshness buckets, fresh eligible/high-match counts, unknown dates, reliable median lag and source yield with null ratios where undefined.
- [x] Existing jobs/status/history/provenance survive migration and scans; no old job is removed.
- [x] Full mocked regression and real Chrome QA pass; measured sequential/concurrent results are reported honestly.
- [x] No scheduled task, application submission, personal-account access or unauthorized extraction occurs.
