# Project status

## Implemented

Milestones 1-2B provide local job imports and discovery, India eligibility, freshness, pagination, manual tracking, versioned candidate profiles, hard gates, cached deterministic embeddings, hybrid explanations and optional zero-budget LLM analysis. M2C adds explicit PDF/DOCX resume parsing, source-referenced fact proposals, human review, schema v6 audit, an optional trained local embedding provider and a 60-job synthetic evaluation with tuning and held-out splits.

## Verified

M2B baseline commit: `2f658eda6f25a08c4c228a275c505ef6e70b8aef`. M2C implementation commit: `097e33a13e8e4493768fc707d649f9238af905cc`. Local verification: 203 tests passed at 98.74% coverage, 7/7 synthetic Chrome scenarios passed, dependency and JavaScript checks passed, and database migration preserved 3,116 jobs, 5 shortlists, 3,125 history rows, 25 sources and 3,384 audit rows. Run `.venv\Scripts\python.exe -m pytest -q`, `.venv\Scripts\python.exe -m scripts.evaluate_m2b`, and `.venv\Scripts\python.exe -m scripts.verify_m2b_browser`.

## Limitations and planned work

Actual resume facts await user review. The trained model/runtime is unavailable and was not downloaded, so its benchmark is blocked and the deterministic hash provider remains default. Synthetic evaluation does not predict hiring outcomes. M3 is truthful application preparation with a missing-information queue and explicit approval; submission remains out of scope.
