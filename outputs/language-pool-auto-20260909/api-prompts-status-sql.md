# Otomatik ifade bakımı: gerçek API kontrolü

Sayısal doğruluk yalnız bağımsız gerçek DB referansı bulunan sorularda değerlendirildi.

| Kimlik | Soru | Durum | Tam sonuç satırı | Dil havuzu eşleşmesi |
|---|---|---|---:|---:|
| A01 | Satış temsilcilerinin toplam sayısı kaç? | LIVE_PASS | 1 | 0 |
| A02 | Satış temsilcilerinin kodlarını ve adlarını listele. | LIVE_PASS | 2358 | 0 |
| A03 | Üretim kaydını oluşturan kullanıcı kim? | LIVE_FAIL | — | 4 |
| A04 | Üretim kaydı ne zaman oluşturuldu? | LIVE_FAIL | — | 2 |
| A05 | Ocak 2026 için müşteri, ürün, ödeme planı, satış temsilcisi, teslimat şehri ve birim bazında satılan adet göster. | DOĞRULANAMADI | 65379 | 3 |
| A06 | Müşteri, ürün, ödeme planı, satış temsilcisi, teslimat şehri ve birim bazında Şubat 2026 satılan adet hesapla. | DOĞRULANAMADI | 76942 | 3 |
| A07 | Ocak 2024 için müşteri, ürün, ödeme planı, satış temsilcisi, teslimat şehri ve birim bazında satılan adet göster. | DOĞRULANAMADI | 61865 | 3 |
| A08 | Müşteri, ürün, ödeme planı, satış temsilcisi, teslimat şehri ve birim bazında Ocak 2024 perakende satılan adet hesapla. | DOĞRULANAMADI | 10798 | 3 |
| A09 | 2025 ve 2026 satış tutarlarını karşılaştır. | DOĞRULANAMADI | 1 | 0 |
| A10 | test | LIVE_PASS | — | 0 |

## A01





```sql
SELECT COUNT(DISTINCT "LOGICALREF") AS toplam_sayisi
FROM dbo_LG_SLSMAN
```

## A02





```sql
SELECT "CODE", "DEFINITION_"
FROM dbo_LG_SLSMAN
```

## A03

Generated phrase retrieved its schema references, but resolver asked for the meaning of an ordinary phrase word rather than resolving the requested attribute. This is not a successful end-to-end answer.

‘olusturan’ ile hangi koşulu kastediyorsunuz? Bu ifadenin hangi kayıtları seçmesi gerektiğini belirtir misiniz?

```sql
-- SQL üretilmedi
```

## A04

Generated phrase retrieved its schema references, but resolver asked for the meaning of an ordinary phrase word rather than resolving the requested attribute. This is not a successful end-to-end answer.

‘zaman’ ile hangi koşulu kastediyorsunuz? Bu ifadenin hangi kayıtları seçmesi gerektiğini belirtir misiniz?

```sql
-- SQL üretilmedi
```

## A05

Independent business/source oracle unavailable; execution and cell statistics are not correctness certification



```sql
SELECT UNITSETL.[NAME] AS bir, SHIPINFO.[CITY] AS teslimat_sehr, SLSMAN.[DEFINITION_] AS satis_temsilc, PAYPLANS.[DEFINITION_] AS odem_pla, ITEMS.[NAME] AS urun, CLCARD.[DEFINITION_] AS muster, SUM(STLINE.[AMOUNT]) AS satilan_adet
FROM (SELECT '211' AS [__nb_firm], [AMOUNT], [CANCELLED], [DATE_], [INVOICEREF], [LINETYPE], [PAYDEFREF], [STOCKREF], [TRCODE], [UOMREF] FROM [dbo].[LG_211_01_STLINE] UNION ALL SELECT '411' AS [__nb_firm], [AMOUNT], [CANCELLED], [DATE_], [INVOICEREF], [LINETYPE], [PAYDEFREF], [STOCKREF], [TRCODE], [UOMREF] FROM [dbo].[LG_411_01_STLINE]) AS STLINE
LEFT JOIN (SELECT '211' AS [__nb_firm], [LOGICALREF], [NAME] FROM [dbo].[LG_211_UNITSETL] UNION ALL SELECT '411' AS [__nb_firm], [LOGICALREF], [NAME] FROM [dbo].[LG_411_UNITSETL]) AS UNITSETL ON STLINE.[UOMREF] = UNITSETL.[LOGICALREF] AND STLINE.[__nb_firm] = UNITSETL.[__nb_firm]
JOIN (SELECT '211' AS [__nb_firm], [CANCELLED], [CLIENTREF], [DATE_], [LOGICALREF], [PAYDEFREF], [SALESMANREF], [SHIPINFOREF] FROM [dbo].[LG_211_01_INVOICE] UNION ALL SELECT '411' AS [__nb_firm], [CANCELLED], [CLIENTREF], [DATE_], [LOGICALREF], [PAYDEFREF], [SALESMANREF], [SHIPINFOREF] FROM [dbo].[LG_411_01_INVOICE]) AS INVOICE ON STLINE.[INVOICEREF] = INVOICE.[LOGICALREF] AND STLINE.[__nb_firm] = INVOICE.[__nb_firm]
LEFT JOIN (SELECT '211' AS [__nb_firm], [CITY], [LOGICALREF] FROM [dbo].[VW_211_SHIPINFO] UNION ALL SELECT '411' AS [__nb_firm], [CITY], [LOGICALREF] FROM [dbo].[VW_411_SHIPINFO]) AS SHIPINFO ON INVOICE.[SHIPINFOREF] = SHIPINFO.[LOGICALREF] AND INVOICE.[__nb_firm] = SHIPINFO.[__nb_firm]
LEFT JOIN [dbo].[LG_SLSMAN] AS SLSMAN ON INVOICE.[SALESMANREF] = SLSMAN.[LOGICALREF]
LEFT JOIN (SELECT '211' AS [__nb_firm], [DEFINITION_], [LOGICALREF] FROM [dbo].[LG_211_PAYPLANS] UNION ALL SELECT '411' AS [__nb_firm], [DEFINITION_], [LOGICALREF] FROM [dbo].[LG_411_PAYPLANS]) AS PAYPLANS ON PAYPLANS.[LOGICALREF] = COALESCE(NULLIF(STLINE.[PAYDEFREF], 0), INVOICE.[PAYDEFREF]) AND INVOICE.[__nb_firm] = PAYPLANS.[__nb_firm]
JOIN (SELECT '211' AS [__nb_firm], [LOGICALREF], [NAME] FROM [dbo].[LG_211_ITEMS] UNION ALL SELECT '411' AS [__nb_firm], [LOGICALREF], [NAME] FROM [dbo].[LG_411_ITEMS]) AS ITEMS ON STLINE.[STOCKREF] = ITEMS.[LOGICALREF] AND STLINE.[__nb_firm] = ITEMS.[__nb_firm]
LEFT JOIN (SELECT '211' AS [__nb_firm], [DEFINITION_], [LOGICALREF] FROM [dbo].[LG_211_CLCARD] UNION ALL SELECT '411' AS [__nb_firm], [DEFINITION_], [LOGICALREF] FROM [dbo].[LG_411_CLCARD]) AS CLCARD ON INVOICE.[CLIENTREF] = CLCARD.[LOGICALREF] AND INVOICE.[__nb_firm] = CLCARD.[__nb_firm]
WHERE STLINE.[CANCELLED] = 0
  AND STLINE.[CANCELLED] = 0
  AND STLINE.[LINETYPE] = 0
  AND STLINE.[TRCODE] IN (7, 8)
  AND STLINE.[DATE_] >= '2026-01-01' AND STLINE.[DATE_] < '2026-02-01'
GROUP BY UNITSETL.[NAME], SHIPINFO.[CITY], SLSMAN.[DEFINITION_], PAYPLANS.[DEFINITION_], ITEMS.[NAME], CLCARD.[DEFINITION_]
ORDER BY satilan_adet DESC
```

## A06

Independent business/source oracle unavailable; execution and cell statistics are not correctness certification



```sql
SELECT UNITSETL.[NAME] AS bir, SHIPINFO.[CITY] AS teslimat_sehr, SLSMAN.[DEFINITION_] AS satis_temsilc, PAYPLANS.[DEFINITION_] AS odem_pla, ITEMS.[NAME] AS urun, CLCARD.[DEFINITION_] AS muster, SUM(STLINE.[AMOUNT]) AS satilan_adet
FROM (SELECT '211' AS [__nb_firm], [AMOUNT], [CANCELLED], [DATE_], [INVOICEREF], [LINETYPE], [PAYDEFREF], [STOCKREF], [TRCODE], [UOMREF] FROM [dbo].[LG_211_01_STLINE] UNION ALL SELECT '411' AS [__nb_firm], [AMOUNT], [CANCELLED], [DATE_], [INVOICEREF], [LINETYPE], [PAYDEFREF], [STOCKREF], [TRCODE], [UOMREF] FROM [dbo].[LG_411_01_STLINE]) AS STLINE
LEFT JOIN (SELECT '211' AS [__nb_firm], [LOGICALREF], [NAME] FROM [dbo].[LG_211_UNITSETL] UNION ALL SELECT '411' AS [__nb_firm], [LOGICALREF], [NAME] FROM [dbo].[LG_411_UNITSETL]) AS UNITSETL ON STLINE.[UOMREF] = UNITSETL.[LOGICALREF] AND STLINE.[__nb_firm] = UNITSETL.[__nb_firm]
JOIN (SELECT '211' AS [__nb_firm], [CANCELLED], [CLIENTREF], [DATE_], [LOGICALREF], [PAYDEFREF], [SALESMANREF], [SHIPINFOREF] FROM [dbo].[LG_211_01_INVOICE] UNION ALL SELECT '411' AS [__nb_firm], [CANCELLED], [CLIENTREF], [DATE_], [LOGICALREF], [PAYDEFREF], [SALESMANREF], [SHIPINFOREF] FROM [dbo].[LG_411_01_INVOICE]) AS INVOICE ON STLINE.[INVOICEREF] = INVOICE.[LOGICALREF] AND STLINE.[__nb_firm] = INVOICE.[__nb_firm]
LEFT JOIN (SELECT '211' AS [__nb_firm], [CITY], [LOGICALREF] FROM [dbo].[VW_211_SHIPINFO] UNION ALL SELECT '411' AS [__nb_firm], [CITY], [LOGICALREF] FROM [dbo].[VW_411_SHIPINFO]) AS SHIPINFO ON INVOICE.[SHIPINFOREF] = SHIPINFO.[LOGICALREF] AND INVOICE.[__nb_firm] = SHIPINFO.[__nb_firm]
LEFT JOIN [dbo].[LG_SLSMAN] AS SLSMAN ON INVOICE.[SALESMANREF] = SLSMAN.[LOGICALREF]
LEFT JOIN (SELECT '211' AS [__nb_firm], [DEFINITION_], [LOGICALREF] FROM [dbo].[LG_211_PAYPLANS] UNION ALL SELECT '411' AS [__nb_firm], [DEFINITION_], [LOGICALREF] FROM [dbo].[LG_411_PAYPLANS]) AS PAYPLANS ON PAYPLANS.[LOGICALREF] = COALESCE(NULLIF(STLINE.[PAYDEFREF], 0), INVOICE.[PAYDEFREF]) AND INVOICE.[__nb_firm] = PAYPLANS.[__nb_firm]
JOIN (SELECT '211' AS [__nb_firm], [LOGICALREF], [NAME] FROM [dbo].[LG_211_ITEMS] UNION ALL SELECT '411' AS [__nb_firm], [LOGICALREF], [NAME] FROM [dbo].[LG_411_ITEMS]) AS ITEMS ON STLINE.[STOCKREF] = ITEMS.[LOGICALREF] AND STLINE.[__nb_firm] = ITEMS.[__nb_firm]
LEFT JOIN (SELECT '211' AS [__nb_firm], [DEFINITION_], [LOGICALREF] FROM [dbo].[LG_211_CLCARD] UNION ALL SELECT '411' AS [__nb_firm], [DEFINITION_], [LOGICALREF] FROM [dbo].[LG_411_CLCARD]) AS CLCARD ON INVOICE.[CLIENTREF] = CLCARD.[LOGICALREF] AND INVOICE.[__nb_firm] = CLCARD.[__nb_firm]
WHERE STLINE.[CANCELLED] = 0
  AND STLINE.[CANCELLED] = 0
  AND STLINE.[LINETYPE] = 0
  AND STLINE.[TRCODE] IN (7, 8)
  AND STLINE.[DATE_] >= '2026-02-01' AND STLINE.[DATE_] < '2026-03-01'
GROUP BY UNITSETL.[NAME], SHIPINFO.[CITY], SLSMAN.[DEFINITION_], PAYPLANS.[DEFINITION_], ITEMS.[NAME], CLCARD.[DEFINITION_]
ORDER BY satilan_adet DESC
```

## A07

Independent business/source oracle unavailable; execution and cell statistics are not correctness certification



```sql
SELECT UNITSETL.[NAME] AS bir, SHIPINFO.[CITY] AS teslimat_sehr, SLSMAN.[DEFINITION_] AS satis_temsilc, PAYPLANS.[DEFINITION_] AS odem_pla, ITEMS.[NAME] AS urun, CLCARD.[DEFINITION_] AS muster, SUM(STLINE.[AMOUNT]) AS satilan_adet
FROM [dbo].[LG_211_01_STLINE] AS STLINE
LEFT JOIN [dbo].[LG_211_UNITSETL] AS UNITSETL ON STLINE.[UOMREF] = UNITSETL.[LOGICALREF]
JOIN [dbo].[LG_211_01_INVOICE] AS INVOICE ON STLINE.[INVOICEREF] = INVOICE.[LOGICALREF]
LEFT JOIN [dbo].[LG_211_SHIPINFO] AS SHIPINFO ON INVOICE.[SHIPINFOREF] = SHIPINFO.[LOGICALREF]
LEFT JOIN [dbo].[LG_SLSMAN] AS SLSMAN ON INVOICE.[SALESMANREF] = SLSMAN.[LOGICALREF]
LEFT JOIN [dbo].[LG_211_PAYPLANS] AS PAYPLANS ON PAYPLANS.[LOGICALREF] = COALESCE(NULLIF(STLINE.[PAYDEFREF], 0), INVOICE.[PAYDEFREF])
JOIN [dbo].[LG_211_ITEMS] AS ITEMS ON STLINE.[STOCKREF] = ITEMS.[LOGICALREF]
LEFT JOIN [dbo].[LG_211_CLCARD] AS CLCARD ON INVOICE.[CLIENTREF] = CLCARD.[LOGICALREF]
WHERE STLINE.[CANCELLED] = 0
  AND STLINE.[CANCELLED] = 0
  AND STLINE.[LINETYPE] = 0
  AND STLINE.[TRCODE] IN (7, 8)
  AND STLINE.[DATE_] >= '2024-01-01' AND STLINE.[DATE_] < '2024-02-01'
GROUP BY UNITSETL.[NAME], SHIPINFO.[CITY], SLSMAN.[DEFINITION_], PAYPLANS.[DEFINITION_], ITEMS.[NAME], CLCARD.[DEFINITION_]
ORDER BY satilan_adet DESC
```

## A08

Independent business/source oracle unavailable; execution and cell statistics are not correctness certification



```sql
SELECT UNITSETL.[NAME] AS bir, SHIPINFO.[CITY] AS teslimat_sehr, SLSMAN.[DEFINITION_] AS satis_temsilc, PAYPLANS.[DEFINITION_] AS odem_pla, ITEMS.[NAME] AS urun, CLCARD.[DEFINITION_] AS muster, SUM(STLINE.[AMOUNT]) AS satilan_adet
FROM [dbo].[LG_211_01_STLINE] AS STLINE
LEFT JOIN [dbo].[LG_211_UNITSETL] AS UNITSETL ON STLINE.[UOMREF] = UNITSETL.[LOGICALREF]
JOIN [dbo].[LG_211_01_INVOICE] AS INVOICE ON STLINE.[INVOICEREF] = INVOICE.[LOGICALREF]
LEFT JOIN [dbo].[LG_211_SHIPINFO] AS SHIPINFO ON INVOICE.[SHIPINFOREF] = SHIPINFO.[LOGICALREF]
LEFT JOIN [dbo].[LG_SLSMAN] AS SLSMAN ON INVOICE.[SALESMANREF] = SLSMAN.[LOGICALREF]
LEFT JOIN [dbo].[LG_211_PAYPLANS] AS PAYPLANS ON PAYPLANS.[LOGICALREF] = COALESCE(NULLIF(STLINE.[PAYDEFREF], 0), INVOICE.[PAYDEFREF])
JOIN [dbo].[LG_211_ITEMS] AS ITEMS ON STLINE.[STOCKREF] = ITEMS.[LOGICALREF]
LEFT JOIN [dbo].[LG_211_CLCARD] AS CLCARD ON INVOICE.[CLIENTREF] = CLCARD.[LOGICALREF]
WHERE STLINE.[CANCELLED] = 0
  AND STLINE.[CANCELLED] = 0
  AND STLINE.[LINETYPE] = 0
  AND STLINE.[TRCODE] IN (7, 8)
  AND STLINE.[TRCODE] IN (7)
  AND STLINE.[DATE_] >= '2024-01-01' AND STLINE.[DATE_] < '2024-02-01'
GROUP BY UNITSETL.[NAME], SHIPINFO.[CITY], SLSMAN.[DEFINITION_], PAYPLANS.[DEFINITION_], ITEMS.[NAME], CLCARD.[DEFINITION_]
ORDER BY satilan_adet DESC
```

## A09

Independent business/source oracle unavailable; execution and cell statistics are not correctness certification



```sql
SELECT SUM(CASE WHEN (INVOICE.[DATE_] >= '2025-01-01' AND INVOICE.[DATE_] < '2026-01-01') THEN CASE WHEN INVOICE.[TRCODE] IN (7, 8, 9) THEN INVOICE.[NETTOTAL] ELSE 0 END END) AS d2025_satis_tutar, SUM(CASE WHEN (INVOICE.[DATE_] >= '2026-01-01' AND INVOICE.[DATE_] < '2027-01-01') THEN CASE WHEN INVOICE.[TRCODE] IN (7, 8, 9) THEN INVOICE.[NETTOTAL] ELSE 0 END END) AS d2026_satis_tutar
FROM (SELECT [CANCELLED], [DATE_], [NETTOTAL], [TRCODE] FROM [dbo].[LG_211_01_INVOICE] UNION ALL SELECT [CANCELLED], [DATE_], [NETTOTAL], [TRCODE] FROM [dbo].[LG_411_01_INVOICE]) AS INVOICE
WHERE INVOICE.[CANCELLED] = 0
  AND INVOICE.[TRCODE] IN (2, 3, 7, 8, 9)
  AND ((INVOICE.[DATE_] >= '2025-01-01' AND INVOICE.[DATE_] < '2026-01-01') OR (INVOICE.[DATE_] >= '2026-01-01' AND INVOICE.[DATE_] < '2027-01-01'))
```

## A10

Non-data request must not generate SQL

Ben ZEKİ AI. İş zekâsı modülünde satış, finans, stok ve müşteri verilerinizi analiz etmek ve raporlamak için buradayım. Verilerinizle ilgili ne öğrenmek istersiniz?

```sql
-- SQL üretilmedi
```