# Decision log

- Choose sqlite3 and static frontend to reduce infrastructure and make local setup transparent.
- Use stable normalized identity plus source IDs and URL evidence; reject contradictory identifiers. Preserve source references without silently overwriting descriptions on duplicate imports.
- Manual status changes allow any listed status from any other listed status, because the user may import historical outcomes or correct tracking. They never authorize/send applications.
- Profile is matching preference configuration, not a resume or assertion of experience. Default experience is unknown.
- Use metadata-only audit records with immutable database triggers, within the same transaction as state mutations. Immutability protects normal application operations, not a local administrator editing the database file.
- Browser automation is unavailable; verify served HTML/assets and API and explicitly retain a browser QA limitation.
- Port 8000 was occupied (WinError 10048); add `--port` while retaining a fixed loopback host and verify on 8001. Leave the unrelated process untouched.
- Disable CDN-backed Swagger/ReDoc pages because the local CSP blocks remote assets; retain `/openapi.json` for the machine-readable API contract.
- Normalize identity field casing in content signatures so harmless capitalization does not become a content conflict. Compare incoming content with canonical stored job data; source content hashes retain the originally imported fingerprint rather than becoming mutable authorization signals.
- Capture exact installed dependencies in requirements.lock.txt, including transitive test dependencies. No extra tool was installed to resolve the upstream TestClient deprecation warning.
- Milestone 2A reuses Milestone 1 file imports, matching preferences and manual statuses. A separate structured live-search background preserves compatibility while representing the user-authorized 7 total years / 3–4 backend years and evidence distinctions.
- Use fixed read-only public API hosts with httpx already installed; promote it to runtime dependency. No new dependency or system tool is needed. Greenhouse full-board listing and Lever skip/limit are documented public contracts; do not claim provider-supported incremental discovery.
- Verify seed boards with actual public GETs. Netomi and Prophecy succeeded. Postman's old board returned 404 and is excluded, rather than invented/retried.
- SQLite schema version 2 uses a stable pre-upgrade backup and atomic migration. Stop running services for first upgrade. Preserve existing profile edits/statuses/audit/history; runtime run exclusivity uses a persistent expiring lease.
- Discovery runs are sequential (concurrency 1), bounded and backgrounded by a single worker; deterministic Python suffices. No LangGraph, multiagent or LLM runtime.
- Source raw hashes skip normalization/evaluation; canonical content signatures distinguish material updates. The first live source owns canonical updates, secondary conflicts require review. User-managed statuses are never overwritten.
- Conservative skill extraction separates explicit required/preferred/negated mentions; unknown evidence stays unknown. AI keywords alone do not promote product-manager roles, and junior/level-I frontend scope requires seniority review. Legitimate transition-friendly AI engineering remains eligible for high scores.
- Registry toggles persist across restart; editing JSON enabled flags applies only on explicit --sync-sources, avoiding accidental re-enable during server startup.
- The PowerShell task script was blocked by existing execution policy. Do not change or bypass that policy. Add a stdlib Python planner using native Task Scheduler XML and schtasks; preview succeeds, registration requires explicit approval. Actual registration remains unperformed.
- Keep local-only dashboard validation through actual API/HTML/assets and JS syntax. Browser automation remains unavailable; no browser-validation claim.


## 2026-10-10 ? Milestone 2A.1
- Use three evidence-backed eligibility states; generic remote is UNKNOWN.
- Persist verification evidence and enable only successful public boards with observed India vacancies; retain verified empty boards disabled on longer cooldowns.
- Require two successful misses before CLOSED; one miss is POSSIBLY_CLOSED and transient failures do not count.
- Use installed Chrome plus project-local Playwright for real browser QA.
- Keep source execution deterministic and sequential for this release; expose a bounded concurrency setting while deferring safe parallel write orchestration.


## 2026-10-10 ? Milestones 2A.2/2A.3
- Fetch concurrently up to four sources with a locked global budget; persist in sorted registry order to keep SQLite/audit behavior deterministic.
- Add page/offset pagination with stable ID tie-breakers and indexed common orderings.
- Treat publication time as source evidence, separate from discovery/update time; unknown dates never receive recency credit.
- Integrate only documented Remote OK JSON and WWR RSS; classify the other 18 platforms without automated extraction.
- Normalize location buckets and skill aliases while preserving original source text and separate hard eligibility from soft location preference.
