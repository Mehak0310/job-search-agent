# M2B design

Schema v5 is additive and backed up to `jobs.sqlite3.pre-v5.bak` before migration. It adds a versioned candidate profile, embedding cache, recommendation snapshots, optional LLM cache and run metrics; existing jobs and append-only history are unchanged.

`intelligence.py` defines a provider-neutral batch embedding contract. The bundled offline provider uses deterministic token hashing, alias normalization and cosine similarity. Cache keys include normalized content hash, model ID/version and strategy. Hard gates run before embeddings. Section-aware text weights title and requirements more than boilerplate; evaluation selects it when quality is at least whole-description quality.

Hybrid weights: role 22%, required skills 18%, eligibility 18%, semantics 18%, location 10%, freshness 8%, source reliability 6%. Exclusions bypass the formula. Explanations contain only profile categories, extracted requirements, eligibility state and excerpts from the job text.

`llm.py` provides an optional adapter with strict Pydantic output, request/token budgets and an explicit untrusted-data prompt boundary. Runtime defaults to zero requests, so normal scoring makes no LLM calls.
