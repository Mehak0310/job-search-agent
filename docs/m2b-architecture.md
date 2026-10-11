# M2B architecture

`CandidateProfile` is the reviewed source of truth. `RecommendationEngine` reads a bounded top-K job set, applies `gate`, then fetches or creates embeddings and persists a recommendation snapshot. SQLite serialization plus cache uniqueness prevents duplicate persisted inference. Changed content produces a new hash; unchanged content hits cache. Provider failure records deterministic fallback output.

The dashboard reads `/api/recommendations`, while existing `/api/jobs`, discovery and manual statuses remain independent. Resume bytes stay in ignored local storage. Audit entries contain format, size, version and counts only.

Scaling beyond a local corpus would use a real local embedding provider behind the same interface, batch workers, an approximate-nearest-neighbor index, change queues and versioned background recomputation. Hard gates and content hashes remain before expensive inference.
