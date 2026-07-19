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
| Feedback | Geçer | rating `-1\|0\|1` + comment (kısmi/yanlış zorunlu) |
| Tenant (JWT mode) | Backend; FE token taşır | Korundu |
| LEGACY flag rollback | Dokümante | `VITE_API_MODE=LEGACY` |
| Execute button prod | Kapalı | `VITE_ENABLE_TEST_EXECUTION=false` |
| Connection test multi-dialect | Geçer | PG + Oracle/HANA/OData probes (`connection_probes.py`) |
| Rich SQL panel | Geçer | provenance on `done` + FE dialect/columns/assumptions/warnings |
| FE RBAC + source admin API | Geçer | `biCapabilities` + `require_source_admin` on write/test/scan |

## Manuel smoke

1. Bağlantılar: kaynak seç → **Test** → SUCCESS (ham PG hatası yok); Oracle/HANA/OData probe path (secret varsa).
2. **Şemayı tara** → QUEUED/RUNNING → COMPLETED + sayaçlar.
3. Schema Explorer → tablolar / arama / yenile.
4. Chat soru → status + plan_ready + sql_generated / answer → SQL paneli (dialect, assumptions, warnings).
5. **Durdur** → stream iptal.
6. Doğru / Kısmen / Yanlış → feedback 200 (kısmi/yanlışta açıklama).
7. `qa` rolü: SQL paneli ve sources write gizli; JWT `DATA_ANALYST` → sources test 403.
8. `VITE_API_MODE=LEGACY` rebuild → scan stub mesajı (rollback).

## Notlar

- Keycloak ertelendi; portal role → JWT roles `normalize_roles` ile genişletilir.
- `/api/v1/datasources` kullanılmaz.
- Infra cutover Faz 4 öncesinde tamamlanmıştı; ürün boşlukları (connection/feedback/SQL/RBAC) 2026-07-19 kapatıldı.
