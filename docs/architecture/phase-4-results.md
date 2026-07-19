# Faz 4 — FE adapter smoke checklist / results

Date: 2026-07-19  
Scope: React → Nanobase API adapter (`/bi-api` + `/api/v1/bi/*`)

## Acceptance matrix

| Kontrol | Hedef | Sonuç |
|---------|-------|--------|
| FE → yalnız `/bi-api` / nanobase_api | Geçer | Adapter + `VITE_API_BASE=/bi-api` |
| DB-GPT key browser’da yok | Geçer | Değişmedi (cookie/bearer portal) |
| Datasource test + scan UI | Geçer | `BiConnectionPage` → `sources/{id}/test\|scan` |
| Scan polling COMPLETED | Geçer | `schema-scans/{id}` 2.5s |
| Schema Explorer refresh / empty / search | Geçer | `BiSchemaPage` + empty “henüz tarama yok” |
| Chat SSE + SQL panel | Geçer | Additive events + panel; Durdur = AbortController |
| Feedback | Geçer | `POST /api/v1/bi/query/feedback` rating ±1 |
| Tenant (JWT mode) | Backend; FE token taşır | Korundu |
| LEGACY flag rollback | Dokümante | `VITE_API_MODE=LEGACY` |
| Execute button prod | Kapalı | `VITE_ENABLE_TEST_EXECUTION=false` |

## Manuel smoke

1. Bağlantılar: kaynak seç → **Test** → SUCCESS (ham PG hatası yok).
2. **Şemayı tara** → QUEUED/RUNNING → COMPLETED + sayaçlar.
3. Schema Explorer → tablolar / arama / yenile.
4. Chat soru → status + (opsiyonel) schema_context / sql_generated / answer → SQL paneli.
5. **Durdur** → stream iptal.
6. 👍/👎 → feedback 200.
7. `VITE_API_MODE=LEGACY` rebuild → scan stub mesajı (rollback).

## Notlar

- Keycloak ertelendi.
- `/api/v1/datasources` kullanılmaz.
- Infra cutover Faz 4 öncesinde tamamlanmıştı; bu faz FE adapter evolve.
