# M2B ranking evaluation

The reproducible fixture has 12 invented jobs: five strong target matches, two borderline/stale or unknown cases, ML research, data science, excessive seniority, US-only remote and misleading AI/prompt-injection text. Labels and descriptions are synthetic.

Run `python -m scripts.evaluate_m2b`. Metrics include Precision@5/10, Recall@10, NDCG@10, hard-gate violations, grounding, cache reuse and LLM calls. Whole-description and section-aware strategies tied in the current fixture; section-aware is the default because it explicitly limits boilerplate influence. These metrics measure ranking on a small synthetic set and do not predict hiring outcomes.

See `artifacts/m2b-evaluation.json` for measured results. Optional LLM mode remains disabled, so its measured invocation count is zero; no claim that an LLM improves ranking is made.
