# M2C specification

## Requirements and design

Resume parsing is explicit, local-only and bounded to 5 MiB, 30 PDF pages, 1,000 DOCX paragraphs and 200,000 extracted characters. PDF and DOCX text is untrusted. Extraction records the resume hash, format, extractor version and page/paragraph references in ignored local storage. Proposed facts remain pending until individually accepted, edited or rejected. Employment, education, project and learning evidence are never conflated; accepted skill proposals enter project evidence, never professional tenure.

Schema v6 adds extractions, fact proposals and append-only review audit after a verified `pre-v6` backup. Existing facts are not overwritten. The dashboard exposes consent/action, profile version, proposal provenance and review controls.

The deterministic hash embedding remains default. `SentenceTransformerProvider` supports a trained local `all-MiniLM-L6-v2` model through the provider-neutral batch interface with model/revision cache provenance and offline-only loading by default. The runtime/model is not installed, so no download or trained inference occurred and no default was promoted.

Evaluation contains 60 synthetic jobs: 24 tuning and 36 held out. Labels encode target relevance, not hiring suitability. Hard eligibility gates precede semantic ranking; unknown eligibility remains a review state.

## Acceptance and validation

- Explicit parse and fact review API/UI, versioning and provenance.
- Local-only storage and no automatic fact approval.
- Hash fallback retained; trained provider failure is safe.
- At least 50 synthetic jobs with a held-out split and required ranking metrics.
- Full regression, synthetic browser QA and before/after database preservation.
- No submission, account action, scheduler, paid API, public repository or remote inference.
