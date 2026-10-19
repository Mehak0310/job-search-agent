# M2C specification

## Requirements and design

Resume parsing is explicit, local-only and bounded to 5 MiB, 30 PDF pages, 1,000 DOCX paragraphs and 200,000 extracted characters. PDF and DOCX text is untrusted. Extraction records the resume hash, format, extractor version and page/paragraph references in ignored local storage. Proposed facts remain pending until individually accepted, edited or rejected. Employment, education, project and learning evidence are never conflated; accepted skill proposals enter project evidence, never professional tenure.

Schema v6 adds extractions, fact proposals and append-only review audit after a verified `pre-v6` backup. Existing facts are not overwritten. The dashboard exposes consent/action, profile version, proposal provenance and review controls.

The deterministic hash embedding remains default. `SentenceTransformerProvider` supports a trained local `all-MiniLM-L6-v2` model through the provider-neutral batch interface with model/revision cache provenance and offline-only loading by default. The optional runtime is isolated in the project virtual environment. Evaluation loads cached revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41` with network access disabled. The trained provider is not promoted automatically.

Evaluation contains 60 synthetic jobs: 24 tuning and 36 held out. Labels encode target relevance, not hiring suitability. Hard eligibility gates precede semantic ranking; unknown eligibility remains a review state.

## Acceptance and validation

- Explicit parse and fact review API/UI, versioning and provenance.
- Local-only storage and no automatic fact approval.
- Hash fallback retained; trained provider failure is safe.
- At least 50 synthetic jobs with a held-out split and required ranking metrics.
- Full regression, synthetic browser QA and before/after database preservation.
- No submission, account action, scheduler, paid API, public repository or remote inference.

## M2C completion verification

Implemented: repeat parsing is idempotent without replacing extraction parents; proposal queries include extraction provenance and only the currently attached resume; accepted facts may be edited; empty accepted values are rejected; the resume review state completes after every proposal has a decision; trained and hash providers share the same evaluation path.

Verified on 2026-10-14:

- `.venv\Scripts\python.exe -m pytest tests/test_m2c.py -q -o addopts=""` - 6 focused tests passed.
- `.venv\Scripts\python.exe -m pytest -q` - 205 tests passed with 99.06% coverage and one upstream TestClient deprecation warning.
- `$env:HF_HUB_OFFLINE='1'; $env:TRANSFORMERS_OFFLINE='1'; .venv\Scripts\python.exe -m scripts.evaluate_m2b` - cached trained revision and hash fallback evaluated once, with zero LLM calls.
- `.venv\Scripts\python.exe -m scripts.verify_m2b_browser` - 11/11 synthetic Chrome scenarios passed with no console errors.
- `.venv\Scripts\python.exe -m pip check` and `node --check job_agent/static/app.js` - passed.

The trained and hash providers tied on the 36-job synthetic held-out split at precision@5 1.0, recall@10 0.476 and NDCG@10 1.0, with zero hard-gate violations. The trained section strategy took 0.3303 seconds cold and 0.0104 seconds warm, plus 5.0512 seconds to load; hashing took 0.0048 seconds cold and 0.0021 seconds warm. This small templated corpus demonstrates no trained-model quality gain, so hashing remains the default.

Blocked: no actual resume is attached in local storage, so real proposals cannot be prepared. User review remains required for every future proposal. No facts were approved for the user.
