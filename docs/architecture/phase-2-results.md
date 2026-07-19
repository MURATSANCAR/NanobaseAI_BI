# Faz 2 — Şema indeksi + kalite

- Zaman: `2026-07-19T13:54:09.305797+00:00`
- Collection: `bi_schema_bi_reporting`
- Retrieval: **15/20**
- NL2SQL: **20/20**
- Overall: **0.875** (eş 0.8) → PASS

| ID | Ret | SQL | Score | Soru |
|----|-----|-----|-------|------|
| `q01` | Y | True | 1.00 | Kaç müşteri var? |
| `q02` | Y | True | 1.00 | Enterprise segmentindeki müşterileri listele |
| `q03` | Y | True | 1.00 | Almanya'daki müşteri sayısı |
| `q04` | Y | True | 1.00 | Ürün kategorilerine göre ürün sayısı |
| `q05` | Y | True | 1.00 | En pahalı ürün hangisi? |
| `q06` | Y | True | 1.00 | SKU-100 ürününün adı nedir? |
| `q07` | Y | True | 1.00 | Completed sipariş sayısı |
| `q08` | Y | True | 1.00 | 2026 yılı siparişlerini getir |
| `q09` | N | True | 0.50 | Pending siparişleri olan müşteriler |
| `q10` | Y | True | 1.00 | Her siparişin toplam tutarı (order_items) |
| `q11` | N | True | 0.50 | En çok satılan ürün (adet) |
| `q12` | N | True | 0.50 | Segment bazında toplam gelir |
| `q13` | Y | True | 1.00 | v_order_revenue üzerinden ülke bazında ciro |
| `q14` | N | True | 0.50 | Acme Holding'in sipariş sayısı |
| `q15` | Y | True | 1.00 | Services kategorisindeki ürünler |
| `q16` | Y | True | 1.00 | İptal edilen siparişler |
| `q17` | Y | True | 1.00 | 2026 yılındaki toplam fatura tutarı |
| `q18` | Y | True | 1.00 | Ödenmemiş faturaların kalan tutarı |
| `q19` | N | True | 0.50 | Ankara'daki müşterilere ait gecikmiş faturalar |
| `q20` | Y | True | 1.00 | İptal edilmiş faturaları hariç tutarak toplam tutar |
