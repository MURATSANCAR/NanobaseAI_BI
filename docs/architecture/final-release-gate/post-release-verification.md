# Post-release verification

First 15 min: health/readiness, API, auth, meta PG, Vault, Redis, DB-GPT, model, Qdrant, Gateway, audit, OTel.  
First hour: internal E2E, security negatives, model queue, errors, pools, memory, SSE, backup jobs.  
First 24h: SLO, security alerts, business sample, tenant isolation synthetic, masking synthetic, capacity, feedback, audit completeness.

Only then: status `POST_RELEASE_VERIFIED`.
