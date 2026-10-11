# M2B requirements

Status: implemented. The system keeps a versioned, reviewed local candidate profile with employment, project and learning evidence separated. A local PDF/DOCX may be stored under ignored `data/resumes/`; it is hashed, never parsed automatically, and never changes the original.

Recommendations use four stages: deterministic hard gates, cached local embeddings, optional bounded LLM analysis, and explainable hybrid ranking. Confirmed India ineligibility, closed listings, explicit exclusions, unrelated role families and substantially excessive experience requirements are hard exclusions. Unknown eligibility remains unverified. Scores are ranking signals, not hiring probabilities.

No application, account, message, paid API, scheduled search or external model call is authorized. Existing discovery, filters, pagination, status tracking and data must remain intact.
