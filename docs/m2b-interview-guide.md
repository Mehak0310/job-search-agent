# M2B interview guide

## Embeddings and semantic similarity
Mental model: an embedding maps text to a numeric direction; cosine compares directions, while keywords compare literal tokens. Code: `intelligence.embed`, `cosine`, `LocalEmbeddingProvider`. Trade-off: the bundled deterministic hash model is cheap and offline but less semantic than a trained model. Interview answer: the provider boundary permits a stronger local model without changing ranking or cache rules.

## Hybrid ranking and score meaning
Mental model: gates decide whether a job may compete; weighted signals order the survivors. Code: `gate` and `RecommendationEngine.score`. Trade-off: explicit weights are auditable but require evaluation. Interview answer: cosine and the final 0–100 score are ranking features, never probabilities of interview or hire.

## Caching and staged cost
Mental model: content plus model identity is the cache address. Code: `_cached` and `refresh`. Hard gates precede inference, top-K bounds work, batch providers are supported, and run metrics count cache hits, calls, fallback and elapsed time. Changed text or model version invalidates naturally.

## Structured LLM and prompt injection
Mental model: the model is an optional parser behind a typed boundary. Code: `llm.RequirementAnalysis` and `SelectiveAnalyzer`. Job text is nested as untrusted JSON data; output rejects extra or malformed fields. Strict request/token budgets default to zero. The LLM cannot override gates or perform actions.

## Evaluation
Mental model: rank known synthetic cases and measure the top of the list. Code: `evaluation.evaluate`. Precision measures useful results shown; recall measures relevant jobs recovered; NDCG rewards correct ordering; gate violations catch unsafe recommendations. The held-out-style synthetic cases include keyword traps and injection text.

## Failure and scale
If embeddings fail, legacy deterministic score and a visible unavailable state are persisted. If the LLM fails, deterministic ranking remains. For many more jobs, process change events, batch embeddings, store vectors in an ANN index and recompute only affected profile/model versions while retaining gates and evidence.
