# Private publication audit

- [x] `data/`, resumes, extracted text, databases, backups, caches, embeddings, logs, environments and browser QA artifacts are ignored.
- [x] Candidate tracked files and staged history were scanned without printing secret values.
- [x] Machine-specific user paths were removed; synthetic unsafe-URL emails remain test fixtures.
- [x] Only source, specifications, synthetic samples and compact aggregate reports are tracked.
- [x] Repository visibility was verified private before the baseline push.
- [x] No force push, history rewrite, PR, public visibility or unrelated repository content.
