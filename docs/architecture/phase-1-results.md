# Faz 1 — Kabul sonuçları (Nanobase prod mapping)

**Verdict: PASS**

- Zaman: `2026-07-19T12:19:24.759154+00:00`
- Test DB: `bi_reporting :5435` RO=`bi_reporting_ro`
- Qwen: `nanobase-qwen36-35b-a3b-mtp`
- NL2SQL: nanobase_api (nl2sql-plan → query_gateway → result-explain)
- RO flags: SELECT_ALLOWED=True UPDATE_DENIED=True CREATE_DENIED=True

> Plan’daki `nanobase_test` / `:5433` isimleri bu ortamda **bi_reporting :5435** olarak map edildi.

| Test | Beklenen | Sonuç | Not |
|------|----------|-------|-----|
| DB-GPT sürümü | 0.8.1 | **PASS** | 0.8.1 |
| Qwen model listesi | HTTP 200 | **PASS** | nanobase-qwen36-35b-a3b-mtp |
| Qwen streaming | Token akışı | **PASS** | SSE ok |
| BGE-M3 embedding | 1024 boyut | **PASS** | dim=1024 |
| Qdrant | reachable | **PASS** | :6333 |
| Qdrant collection detail | green + cosine + points>0 | **PASS** | status=green size=1024 dist=cosine points=100 |
| Qdrant schema collections | bi_schema_* | **PASS** | ['bi_schema_erp', 'bi_schema_bi_reporting', 'bi_schema_sigorta', 'contract_nodes'] |
| Test datasource | bi_reporting listed | **PASS** | ['bi_reporting', 'erp', 'sigorta'] |
| Metadata Postgres | healthy | **PASS** | nanobase-bi-meta-db |
| Reporting/test Postgres | healthy | **PASS** | nanobase-bi-reporting-db |
| RO SELECT | Başarılı | **PASS** | 8 |
| RO UPDATE | Engellendi | **PASS** | ERROR:  permission denied for view invoices |
| RO CREATE | Engellendi | **PASS** | ERROR:  permission denied for schema public
LINE 1: CREATE TABLE unauthorized_test(id bigint);
                     ^ |
| İlk NL→SQL (4 soru) | Çalışan SQL | **PASS** | 4/4 |
| Türkçe açıklama | Üretildi | **PASS** | reply text |
| Takip sorusu (ödenmemiş) | Çalıştı | **PASS** | Bunun ödenmemiş kısmı ne kadar? |

## NL2SQL detay

### Q1
- Soru: 2026 yılındaki toplam fatura tutarı nedir?
- OK: True (56.53s)
- SQL: `SELECT SUM(gross_amount) AS total_invoice_amount FROM analytics.invoices WHERE EXTRACT(YEAR FROM invoice_date) = 2026 LIMIT 500`
- Rows: `[{"total_invoice_amount": "86748.00"}]`
- Reply: 2026 yılındaki toplam fatura tutarı 86.748,00'dir.

SQL:
SELECT SUM(gross_amount) AS total_invoice_amount FROM analytics.invoices WHERE EXTRACT(YEAR FROM invoice_date) = 2026 LIMIT 500

EXPLAIN:
Limit  (cost=18.41..18.42 rows=1 width=32)
  ->  Aggregate  (cost=18.41..18.42 rows=1

### Q2
- Soru: Bunun ödenmemiş kısmı ne kadar?
- OK: True (52.32s)
- SQL: `SELECT SUM(remaining_amount) AS total_unpaid FROM analytics.invoices WHERE status IN ('open', 'partial', 'overdue') LIMIT 500`
- Rows: `[{"total_unpaid": "28500.00"}]`
- Reply: Ödenmemiş kısmın toplam tutarı 28.500,00 TL'dir.

SQL:
SELECT SUM(remaining_amount) AS total_unpaid FROM analytics.invoices WHERE status IN ('open', 'partial', 'overdue') LIMIT 500

EXPLAIN:
Limit  (cost=17.72..17.73 rows=1 width=32)
  ->  Aggregate  (cost=17.72..17.73 rows=1 wid

### Q3
- Soru: Ankara'daki müşterilere ait gecikmiş faturaları göster.
- OK: True (130.96s)
- SQL: `WITH open_invoices AS (SELECT i.invoice_id, i.order_id, i.gross_amount, i.remaining_amount, i.status, i.invoice_date, i.due_date, c.customer_name, ca.city FROM analytics.invoices AS i JOIN analytics.sales_orders AS so ON i.order_id = so.order_id JOIN analytics.customers AS c ON so.customer_id = c.customer_id JOIN analytics.customer_addresses AS ca `
- Rows: `[{"invoice_id": 3, "customer_name": "Beta Lojistik", "invoice_date": "2026-02-21", "due_date": "2026-03-21", "gross_amount": "11905.00", "remaining_amount": "5000.00", "status": "partial"}]`
- Reply: Ankara'daki müşterilere ait gecikmiş veya açık kalan faturalar listelenmiştir. Örnek veri olarak 'Beta Lojistik' müşterisine ait, 21 Mart 2026 tarihinde son ödemeli ve 5.000,00 TL kalan borcu olan kısmi ödemeli (partial) bir fatura bulunmaktadır. Sorgu, Ankara'daki birincil adres

### Q4
- Soru: İptal edilmiş faturaları hesaba katmadan toplam tutarı hesapla.
- OK: True (69.05s)
- SQL: `SELECT SUM(gross_amount) AS total_amount FROM analytics.invoices WHERE status <> 'cancelled' LIMIT 500`
- Rows: `[{"total_amount": "86748.00"}]`
- Reply: İptal edilmiş faturalar hariç tutularak hesaplanan toplam tutar 86,748.00'dir.

SQL:
SELECT SUM(gross_amount) AS total_amount FROM analytics.invoices WHERE status <> 'cancelled' LIMIT 500

EXPLAIN:
Limit  (cost=18.39..18.41 rows=1 width=32)
  ->  Aggregate  (cost=18.39..18.41 row

