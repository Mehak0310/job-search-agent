# Milestone 1 requirements

The user researches India-based GenAI, AI application, applied AI and AI software engineering roles across remote, hybrid and onsite work. Initial skills are matching preferences, not verified professional claims.

- Persist jobs, source references, candidate configuration, status history and append-only audit events in SQLite.
- Import UTF-8 JSON arrays and CSV files with bounded uploads, field validation, normalization, per-record errors, deterministic deduplication and cross-source provenance. Imports are idempotent; sample jobs are visibly fictional.
- Match deterministically using title, skills, geography, mode, experience when known and exclusions. Explain scores, missing requirements and disqualifiers. Scores are heuristic fit, not interview probabilities.
- Provide a responsive dashboard for importing, searching, filtering, details, shortlisting, status tracking, profile preferences and recent audit events.
- All statuses are manual tracking. No submission or approval grant exists in this milestone.
- Run locally without an LLM, external accounts or portal scraping.

Out of scope: resume generation, document storage, account integrations, live portals, real approval grants and submission.
