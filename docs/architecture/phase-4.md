# Nanobase BI — Faz 4 FE → Nanobase API (adapter)

## Özet

- **Infra cutover (önceki):** Nginx `/bi-api` → `nanobase-bi-api` `:8790`; bridge durduruldu.
- **Bu faz:** React SPA, `VITE_API_BASE=/bi-api` + `/api/v1/bi/*` sözleşmesini **adapter katmanı** ile kullanır (path redesign yok, Keycloak yok).

## FE paket

| Parça | Yol |
|-------|-----|
| Flags / mode | `src/config/environment.ts` (`VITE_API_MODE`, feature flags) |
| Contracts | `src/api/contracts/` |
| Nanobase adapter | `src/api/adapters/nanobase/` |
| Legacy stub | `src/api/adapters/legacy/` (rollback) |
| Factory | `src/api/services.ts` |
| SSE parser | `src/lib/sse/parseSseStream.ts` |
| ApiError | `src/api/api-error.ts` |

Component’ler URL bilmez; `createDatasourceService()` mode ile adapter seçer.

## Endpoint map (korunan)

| UI | Backend |
|----|---------|
| List / upsert / activate | `GET/PUT /api/v1/bi/sources`, `POST …/activate` |
| Delete | `DELETE /api/v1/bi/sources/{id}` |
| Test | `POST /api/v1/bi/sources/{id}/test` |
| Scan + poll | `POST …/scan`, `GET /api/v1/bi/schema-scans/{id}` |
| Schema | `GET /api/v1/bi/schema` (+ refresh) |
| Chat SSE | `POST /api/v1/bi/chat/stream` |
| Feedback | `POST /api/v1/bi/query/feedback` |

Checklist’teki `/api/v1/datasources` **kullanılmaz**.

## Feature flags (`.env.example`)

```bash
VITE_API_MODE=NANOBASE          # LEGACY = rollback stub
VITE_API_BASE=/bi-api
VITE_ENABLE_SCHEMA_EXPLORER=true
VITE_ENABLE_SQL_PANEL=true
VITE_ENABLE_TEST_EXECUTION=false   # prod’da SQL Çalıştır gizli
VITE_ENABLE_FEEDBACK=true
```

## UI kabul

| Kontrol | Durum |
|---------|--------|
| FE → yalnız `/bi-api` / nanobase_api | Geçer |
| Datasource test + scan + poll COMPLETED | `BiConnectionPage` |
| Schema Explorer empty / search / refresh | `BiSchemaPage` |
| Chat SSE additive events + SQL panel + Durdur | `BiChatPanel` / `biChatStream` |
| Feedback thumbs → `/query/feedback` | `submitQueryFeedback` |
| Execute button prod | Kapalı (`enableTestExecution=false`) |
| LEGACY rollback | `VITE_API_MODE=LEGACY` — scan/delete stub; dokümante |

## Rollback

1. FE: `VITE_API_MODE=LEGACY` ile rebuild (aynı `/bi-api` path; scan UI stub).
2. Infra (gerekirse): nginx’i bridge’e geri al — bkz. önceki cutover notları / `cutover-nanobase-api.sh` rollback.

## Deploy

```bash
# FE build + rsync (mevcut portal /bi akışı)
npm run build
# ardından sunucuya dist rsync
```

Infra cutover:

```bash
./scripts/server/deploy-nanobase-api.sh
./scripts/server/cutover-nanobase-api.sh
```

## Bilinçli yapılmayanlar

- Path’leri `/api/v1/datasources` yapmak
- Keycloak
- Zustand/TanStack full rewrite
- Playwright full suite
- Production “SQL çalıştır” butonu
