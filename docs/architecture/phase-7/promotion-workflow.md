# Promotion workflow

```text
Candidate → technical validation → Gateway → test exec → baseline
  → dependency / semantic consistency
  → Business reviewer + Technical reviewer
  → Publish (atomic: PREPARING → Qdrant → READY → active pointer → PUBLISHED)
```

API:

- `POST /api/v1/semantic/verified-query-candidates`
- `POST /api/v1/semantic/verified-query-candidates/{id}/validate`
- `POST /api/v1/semantic/promotion-requests/{id}/reviews`
- `POST /api/v1/semantic/promotion-requests/{id}/publish`
