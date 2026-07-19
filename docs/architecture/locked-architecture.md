# Locked architecture (Java hariç) — 2026-07-19

## Kilit kararlar

1. **DB-GPT v0.8.1** + **Qdrant** (Chroma→Qdrant migration yok)
2. **Orkestrasyon sahibi:** `nanobase_api` (FastAPI)
3. **Müşteri SQL execute:** yalnız **Query Gateway** (`:8792`)
4. Backend: **Python FastAPI** (Spring/Java yok)
5. Secrets: **file** varsayılan; **Vault** opsiyonel (`VAULT_ADDR` + `VAULT_TOKEN`)

## Kontrollü workflow’lar

```
question
  → nanobase-nl2sql-plan   (SQL üretir, DB’ye dokunmaz)
  → Query Gateway validate/execute
  → nanobase-result-explain (Türkçe cevap, DB’ye dokunmaz)
```

API:

- `POST /api/v1/bi/workflows/nl2sql-plan`
- `POST /api/v1/bi/workflows/result-explain`
- Chat stream aynı zinciri kullanır (`sql_source` / `workflows` alanında görünür)

DB-GPT `chat_with_db_execute` production chat’te **kullanılmaz**.

## Metadata

| Depo | İçerik |
|------|--------|
| `bi_meta` PG `:5434` | ürün: sources, glossary, metrics, verified_sql, budgets, alerts, feedback |
| DB-GPT meta | teknik/geçici; silinip kurulabilir |
| Qdrant | şema chunk’ları — ham transaction yok |

## Reporting test DB

Zengin şema: `infra/sql/08-reporting-rich-schema.sql`

```bash
./scripts/server/apply-rich-schema.sh
sudo systemctl restart nanobase-query-gateway nanobase-bi-api
```

Tablolar: companies, branches, customer_addresses, sales_orders/items, invoices, payments, currency_rates, returns + legacy orders.

## Secrets

```bash
# file (default)
SECRETS_ROOT=/data/nanobaseai/bi/secrets

# optional Vault
export VAULT_ADDR=https://vault.example:8200
export VAULT_TOKEN=...
# ref: vault:secret/data/bi/reporting#password
GET /api/v1/bi/secrets/status
```
