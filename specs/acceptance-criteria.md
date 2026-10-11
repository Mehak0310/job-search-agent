# Acceptance criteria (defined before implementation)

1. `.venv\Scripts\python.exe -m job_agent` starts on 127.0.0.1:8000, health returns OK and dashboard HTML/assets are accessible.
2. Fictional JSON and CSV fixtures import successfully with a visible sample flag, persistent source references and deterministic scores in [0,100]. Reimport creates no additional jobs/references.
3. Normalization, source ID/URL and identity-based deduplication work across sources. Ambiguous conflicting identity is reported safely. Malformed documents and invalid rows yield bounded errors without leaking uploaded text.
4. Matching explains title, skills, location, mode, known experience and exclusions. Unknown experience is not invented. Candidate configuration persists and updates existing scores.
5. Search, status/mode/minimum-score filters, details and shortlist/status controls are usable. Supported manual transitions persist with history; no-op changes create no history. Unknown statuses fail validation.
6. Import/duplicates/errors/profile/status events persist. Audit/history cannot be edited/deleted. Database writes maintain atomicity.
7. No live submission/approval endpoint, runtime LLM calls, external accounts or scraping. A manual SUBMITTED status never implies verified submission. Material application changes alter future approval fingerprints.
8. Unsafe URLs, unexpected fields, oversized uploads, invalid content/encoding, untrusted origins/hosts and script-bearing text are handled safely.
9. Meaningful pytest suite passes with >=90% statement coverage (target 100%) over implemented Python modules. Record coverage gaps honestly.
10. README documents Windows installation/run/test/import and local-only restrictions. Verify a real running server/API; if browser automation is unavailable, verify HTML/assets and report that interactive browser QA is incomplete.
