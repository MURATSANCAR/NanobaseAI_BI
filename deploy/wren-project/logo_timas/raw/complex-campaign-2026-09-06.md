# Timaş Finans Copilot — karmaşık soru kampanyası (2026-09-06)

Motor: WrenAI main 0.13.4 (MDL + knowledge + LanceDB memory) + Qwen3.8-Flash-Next (A40, 24.576 bağlam) · köprü `backend/wren_bridge`.
Doğrulama: her cevap, motordan bağımsız ham T-SQL ile fiziksel Logo tablolarında yeniden hesaplandı (`complex-truth.json`).

| # | Prompt | Süre | Onarım | Satır | Sonuç |
|---|---|---|---|---|---|
| cx-01 | 2026 yılında KITAPCI, E-TICARET ve DAGITICI kanalları için ay bazında net ciro (satış eksi iade) ve her kanalın o ay içindeki payını yüzde olarak ver; ay ve kanal sırasıyla listele. | 39.2s | 0 | 24/24 | **DOĞRU** — 24 satır, tüm değerler birebir (örn. Ocak DAGITICI 7.561.917,15 TL · %11,42). Not: pay üç seçili kanalın toplamına göre; ayın tüm kanalları baz alınsaydı DAGITICI Ocak %7,65 olurdu (soru iki türlü okunabilir). |
| cx-02 | Yayınevi bazında 2026 YTD net ciro (satış satırları eksi iade satırları), satılan adet, iade adedi, adet bazlı iade oranı ve maliyetli satırlardan brüt kâr marjı; yalnız net cirosu 20 milyon TL üzerindeki yayınevleri, marja göre azalan sırada. | 43.7s | 0 | 15/15 | **DOĞRU** — 15 yayınevi, 50/50 sayısal değer birebir (net ciro, adet, iade oranı, marj). |
| cx-03 | En çok iade alan 10 müşteri: iade tutarı, aynı müşterinin 2026 satış tutarı, iade/satış oranı ve cari kartındaki kanal kodu; yalnız satışı 1 milyon TL üzerinde olanlar, iade tutarına göre azalan. | 39.7s | 0 | 10/10 | **DOĞRU** — 10 müşteri, iade/satış tutarları ve kanal kodu birebir (Turkuvaz 5.929.122,05 / 81.321.130,96). |
| cx-04 | 2026 Ocak–Ağustos için ay bazında iskonto oranı (iskonto satırları toplamı / brüt malzeme satırları toplamı) ve satış faturası başına ortalama fatura tutarı (NETTOTAL ortalaması, TRCODE 7,8,9). | 33.7s → 41.2s | 0 | 8/8 | **İLK KOŞUDA HATALI → DÜZELTİLDİ** — İskonto oranı doğruydu; 'ortalama fatura tutarı' bağımsız alt sorgu yüzünden her ayda aynı genel ortalama (13.053,59) döndü. Kural 7 + doğrulanmış CTE'li çift eklendi; yeniden koşuda Ocak 12.064,74 = DB. |
| cx-05 | Temmuz 2026'da en çok satan 15 kitap: stok kodu, kitap adı, yayınevi, satılan adet ve brüt satır tutarı; yalnız toptan satış faturaları (TRCODE 8), adede göre azalan. | 34.0s | 0 | 15/15 | **DOĞRU** — Temmuz toptan ilk 15 kitap; adet ve brüt satır tutarları birebir (ÇOK ŞIK HAYALLER 18.934 / 3.692.130). |
| cx-06 | 2026'da mal alım (TRCODE 1) ve alınan hizmet (TRCODE 4) faturalarında tedarikçi (cari) bazında toplam tutar, fatura sayısı, ilk ve son fatura tarihi; toplam tutara göre ilk 10 tedarikçi, cari unvanıyla. | 33.6s | 0 | 10/10 | **DOĞRU** — İlk 10 tedarikçi; tutar, fatura sayısı, ilk/son tarih 20/20 birebir. Not: yalnız unvanla gruplandı (aynı unvanlı iki cari birleşirdi). |
| cx-07 | Müşteri yoğunlaşması: 2026 net ciroya (satış eksi iade) göre ilk 10 müşterinin toplam net ciro içindeki payı yüzde olarak; her müşteri için net ciro, kümülatif pay ve kanal kodu. | 37.3s | 0 | 10/10 | **DOĞRU** — Kümülatif pay penceresiyle 10 müşteri; pay ve kümülatif pay birebir (8,89 → 17,26 …). |
| cx-08 | Kanal bazında brüt kâr marjı: satış hareket satırlarında (TRCODE 7,8, LINETYPE 0, maliyeti işlenmiş satırlar) faturanın cari kartındaki kanal koduna göre maliyetli ciro, maliyet ve marj yüzdesi; maliyetli cirosu 10 milyon TL üzerindeki kanallar, marja göre azalan. | 34.6s | 0 | 7/7 | **DOĞRU** — 3 tablo join (STLINE→INVOICE→CLCARD), maliyetli ciro/maliyet/marj 21/21 birebir; marj % olarak döndü. |
| cx-09 | Perakende (TRCODE 7) ile toptan (TRCODE 8) satışları 2026 ay bazında karşılaştır: her ay için fatura sayısı, NETTOTAL toplamı ve ortalama fatura tutarı; ayrıca perakendenin o ayın toplam satışındaki payı. | 39.6s | 0 | 8/8 | **DOĞRU** — Ay bazında perakende/toptan sayı, toplam, ortalama ve pay birebir (pay oran olarak döndü, % değil). |
| cx-10 | Sipariş fişlerinde (ORFICHE) 2026 ay bazında açılan sipariş sayısı ve toplam tutar; hangi kolonların tutar ve tarih olduğunu modelden bul, emin değilsen NO_SQL yaz. | 28.6s → 21.9s | 0 | 8/8 | **İLK KOŞUDA HATALI → DÜZELTİLDİ** — ORFICHE–ORFLINE join'i sonrası COUNT satırları saydı (24.425) ve ORFLINE.TOTAL topladı; doğrusu 5.794 sipariş / 5.219.018,25 TL (ORFICHE.NETTOTAL). Kural 8 + doğrulanmış çift eklendi; yeniden koşu birebir. Soru 'emin değilsen NO_SQL' dediği halde model tahmin yürüttü. |

## Üretilen SQL'ler

### cx-01

```sql
SELECT 
    DATEFROMPARTS(YEAR(i."DATE_"), MONTH(i."DATE_"), 1) AS ay,
    COALESCE(NULLIF(c."SPECODE2", ''), '(boş)') AS kanal,
    SUM(CASE WHEN i."TRCODE" IN (7,8,9) THEN i."NETTOTAL" ELSE -i."NETTOTAL" END) AS net_ciro,
    SUM(CASE WHEN i."TRCODE" IN (7,8,9) THEN i."NETTOTAL" ELSE -i."NETTOTAL" END) * 100.0 / NULLIF(SUM(SUM(CASE WHEN i."TRCODE" IN (7,8,9) THEN i."NETTOTAL" ELSE -i."NETTOTAL" END)) OVER (PARTITION BY DATEFROMPARTS(YEAR(i."DATE_"), MONTH(i."DATE_"), 1)), 0) AS kanal_payi_yuzde
FROM dbo_LG_411_01_INVOICE i
JOIN dbo_LG_411_CLCARD c ON c."LOGICALREF" = i."CLIENTREF"
WHERE i."CANCELLED" = 0
  AND i."TRCODE" IN (2,3,7,8,9)
  AND i."DATE_" >= '2026-01-01'
  AND i."DATE_" < '2027-01-01'
  AND c."SPECODE2" IN ('KITAPCI', 'E-TICARET', 'DAGITICI')
GROUP BY 
    DATEFROMPARTS(YEAR(i."DATE_"), MONTH(i."DATE_"), 1),
    COALESCE(NULLIF(c."SPECODE2", ''), '(boş)')
ORDER BY 
    ay,
    kanal
```

### cx-02

```sql
SELECT 
    COALESCE(NULLIF(it."SPECODE", ''), '(boş)') AS yayinevi,
    SUM(CASE WHEN sl."TRCODE" IN (7,8) THEN sl."TOTAL" ELSE -sl."TOTAL" END) AS net_ciro,
    SUM(CASE WHEN sl."TRCODE" IN (7,8) THEN sl."AMOUNT" ELSE 0 END) AS satilan_adet,
    SUM(CASE WHEN sl."TRCODE" IN (2,3) THEN sl."AMOUNT" ELSE 0 END) AS iade_adedi,
    SUM(CASE WHEN sl."TRCODE" IN (2,3) THEN sl."AMOUNT" ELSE 0 END) / NULLIF(SUM(CASE WHEN sl."TRCODE" IN (7,8) THEN sl."AMOUNT" ELSE 0 END), 0) AS adet_iade_orani,
    1 - SUM(CASE WHEN sl."TRCODE" IN (7,8) AND sl."OUTCOST" <> 0 THEN sl."AMOUNT" * sl."OUTCOST" ELSE 0 END) / NULLIF(SUM(CASE WHEN sl."TRCODE" IN (7,8) AND sl."OUTCOST" <> 0 THEN sl."TOTAL" ELSE 0 END), 0) AS brut_kar_marji
FROM dbo_LG_411_01_STLINE sl
JOIN dbo_LG_411_ITEMS it ON it."LOGICALREF" = sl."STOCKREF"
WHERE sl."CANCELLED" = 0 
  AND sl."LINETYPE" = 0 
  AND sl."TRCODE" IN (2,3,7,8)
  AND sl."DATE_" >= '2026-01-01' 
  AND sl."DATE_" < '2027-01-01'
GROUP BY COALESCE(NULLIF(it."SPECODE", ''), '(boş)')
HAVING SUM(CASE WHEN sl."TRCODE" IN (7,8) THEN sl."TOTAL" ELSE -sl."TOTAL" END) > 20000000
ORDER BY brut_kar_marji DESC
```

### cx-03

```sql
SELECT TOP 10
    c."CODE" AS cari_kodu,
    c."DEFINITION_" AS unvan,
    ISNULL(c."SPECODE2", '(boş)') AS satis_kanali,
    SUM(CASE WHEN i."TRCODE" IN (2,3) THEN i."NETTOTAL" ELSE 0 END) AS iade_tutari,
    SUM(CASE WHEN i."TRCODE" IN (7,8,9) THEN i."NETTOTAL" ELSE 0 END) AS satis_tutari,
    CASE 
        WHEN SUM(CASE WHEN i."TRCODE" IN (7,8,9) THEN i."NETTOTAL" ELSE 0 END) = 0 THEN 0
        ELSE SUM(CASE WHEN i."TRCODE" IN (2,3) THEN i."NETTOTAL" ELSE 0 END) / SUM(CASE WHEN i."TRCODE" IN (7,8,9) THEN i."NETTOTAL" ELSE 0 END)
    END AS iade_satis_orani
FROM dbo_LG_411_01_INVOICE i
JOIN dbo_LG_411_CLCARD c ON c."LOGICALREF" = i."CLIENTREF"
WHERE i."CANCELLED" = 0
  AND i."TRCODE" IN (2,3,7,8,9)
  AND i."DATE_" >= '2026-01-01'
  AND i."DATE_" < '2027-01-01'
GROUP BY c."CODE", c."DEFINITION_", ISNULL(c."SPECODE2", '(boş)')
HAVING SUM(CASE WHEN i."TRCODE" IN (7,8,9) THEN i."NETTOTAL" ELSE 0 END) > 1000000
ORDER BY iade_tutari DESC
```

### cx-04 (yeniden koşu)

```sql
WITH iskonto AS (
  SELECT DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1) AS ay,
         SUM(CASE WHEN "LINETYPE" = 2 THEN "TOTAL" ELSE 0 END) / NULLIF(SUM(CASE WHEN "LINETYPE" = 0 THEN "TOTAL" ELSE 0 END), 0) AS iskonto_orani
  FROM dbo_LG_411_01_STLINE 
  WHERE "CANCELLED" = 0 
    AND "TRCODE" IN (7,8) 
    AND "DATE_" >= '2026-01-01' 
    AND "DATE_" < '2026-09-01'
  GROUP BY DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1)
), fatura AS (
  SELECT DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1) AS ay, 
         AVG("NETTOTAL") AS ortalama_fatura_tutari
  FROM dbo_LG_411_01_INVOICE 
  WHERE "CANCELLED" = 0 
    AND "TRCODE" IN (7,8,9) 
    AND "DATE_" >= '2026-01-01' 
    AND "DATE_" < '2026-09-01'
  GROUP BY DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1)
)
SELECT i.ay, 
       i.iskonto_orani, 
       f.ortalama_fatura_tutari
FROM iskonto i 
JOIN fatura f ON f.ay = i.ay 
ORDER BY i.ay
```

### cx-05

```sql
SELECT TOP 15
    it."CODE" AS stok_kodu,
    it."NAME" AS kitap_adi,
    COALESCE(NULLIF(it."SPECODE", ''), '(boş)') AS yayinevi,
    SUM(sl."AMOUNT") AS satilan_adet,
    SUM(sl."TOTAL") AS brut_satir_tutari
FROM dbo_LG_411_01_STLINE sl
JOIN dbo_LG_411_ITEMS it ON it."LOGICALREF" = sl."STOCKREF"
WHERE sl."CANCELLED" = 0
  AND sl."LINETYPE" = 0
  AND sl."TRCODE" = 8
  AND sl."DATE_" >= '2026-07-01'
  AND sl."DATE_" < '2026-08-01'
GROUP BY it."CODE", it."NAME", COALESCE(NULLIF(it."SPECODE", ''), '(boş)')
ORDER BY SUM(sl."AMOUNT") DESC
```

### cx-06

```sql
SELECT TOP 10
    "CLCARD"."DEFINITION_" AS "CARI_UNVANI",
    SUM("INVOICE"."NETTOTAL") AS "TOPLAM_TUTAR",
    COUNT("INVOICE"."LOGICALREF") AS "FATURA_SAYISI",
    MIN("INVOICE"."DATE_") AS "ILK_FATURA_TARIHI",
    MAX("INVOICE"."DATE_") AS "SON_FATURA_TARIHI"
FROM "dbo_LG_411_01_INVOICE" AS "INVOICE"
INNER JOIN "dbo_LG_411_CLCARD" AS "CLCARD"
    ON "INVOICE"."CLIENTREF" = "CLCARD"."LOGICALREF"
WHERE "INVOICE"."CANCELLED" = 0
    AND "INVOICE"."TRCODE" IN (1, 4)
    AND "INVOICE"."DATE_" >= '2026-01-01'
    AND "INVOICE"."DATE_" < '2027-01-01'
GROUP BY "CLCARD"."DEFINITION_"
ORDER BY SUM("INVOICE"."NETTOTAL") DESC
```

### cx-07

```sql
WITH customer_net AS (
    SELECT 
        c."CODE" AS cari_kodu,
        c."DEFINITION_" AS unvan,
        COALESCE(NULLIF(c."SPECODE2", ''), '(boş)') AS kanal_kodu,
        SUM(CASE WHEN i."TRCODE" IN (7,8,9) THEN i."NETTOTAL" ELSE -i."NETTOTAL" END) AS net_ciro
    FROM dbo_LG_411_01_INVOICE i
    JOIN dbo_LG_411_CLCARD c ON c."LOGICALREF" = i."CLIENTREF"
    WHERE i."CANCELLED" = 0
      AND i."TRCODE" IN (2,3,7,8,9)
      AND i."DATE_" >= '2026-01-01'
      AND i."DATE_" < '2027-01-01'
    GROUP BY c."CODE", c."DEFINITION_", COALESCE(NULLIF(c."SPECODE2", ''), '(boş)')
),
ranked AS (
    SELECT 
        cari_kodu,
        unvan,
        kanal_kodu,
        net_ciro,
        SUM(net_ciro) OVER (ORDER BY net_ciro DESC ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS kumulatif_ciro,
        SUM(net_ciro) OVER () AS toplam_net_ciro
    FROM customer_net
)
SELECT TOP 10
    cari_kodu,
    unvan,
    kanal_kodu,
    net_ciro,
    (net_ciro / NULLIF(toplam_net_ciro, 0)) * 100 AS pay_yuzde,
    (kumulatif_ciro / NULLIF(toplam_net_ciro, 0)) * 100 AS kumulatif_pay_yuzde
FROM ranked
ORDER BY net_ciro DESC
```

### cx-08

```sql
SELECT 
    COALESCE(NULLIF(c."SPECODE2", ''), '(boş)') AS kanal,
    SUM(s."TOTAL") AS maliyetli_ciro,
    SUM(s."AMOUNT" * s."OUTCOST") AS toplam_maliyet,
    (1 - SUM(s."AMOUNT" * s."OUTCOST") / NULLIF(SUM(s."TOTAL"), 0)) * 100 AS brut_kar_marji_yuzde
FROM dbo_LG_411_01_STLINE s
JOIN dbo_LG_411_01_INVOICE i ON i."LOGICALREF" = s."INVOICEREF"
JOIN dbo_LG_411_CLCARD c ON c."LOGICALREF" = i."CLIENTREF"
WHERE s."CANCELLED" = 0
  AND s."LINETYPE" = 0
  AND s."OUTCOST" <> 0
  AND i."CANCELLED" = 0
  AND i."TRCODE" IN (7, 8)
GROUP BY COALESCE(NULLIF(c."SPECODE2", ''), '(boş)')
HAVING SUM(s."TOTAL") > 10000000
ORDER BY brut_kar_marji_yuzde DESC
```

### cx-09

```sql
SELECT 
    DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1) AS ay,
    SUM(CASE WHEN "TRCODE" = 7 THEN 1 ELSE 0 END) AS perakende_fatura_sayisi,
    SUM(CASE WHEN "TRCODE" = 7 THEN "NETTOTAL" ELSE 0 END) AS perakende_toplam,
    SUM(CASE WHEN "TRCODE" = 7 THEN "NETTOTAL" ELSE 0 END) / NULLIF(SUM(CASE WHEN "TRCODE" = 7 THEN 1 ELSE 0 END), 0) AS perakende_ortalama,
    SUM(CASE WHEN "TRCODE" = 8 THEN 1 ELSE 0 END) AS toptan_fatura_sayisi,
    SUM(CASE WHEN "TRCODE" = 8 THEN "NETTOTAL" ELSE 0 END) AS toptan_toplam,
    SUM(CASE WHEN "TRCODE" = 8 THEN "NETTOTAL" ELSE 0 END) / NULLIF(SUM(CASE WHEN "TRCODE" = 8 THEN 1 ELSE 0 END), 0) AS toptan_ortalama,
    SUM(CASE WHEN "TRCODE" = 7 THEN "NETTOTAL" ELSE 0 END) / NULLIF(SUM(CASE WHEN "TRCODE" IN (7,8) THEN "NETTOTAL" ELSE 0 END), 0) AS perakende_payi
FROM dbo_LG_411_01_INVOICE
WHERE "CANCELLED" = 0
  AND "TRCODE" IN (7, 8)
  AND "DATE_" >= '2026-01-01'
  AND "DATE_" < '2027-01-01'
GROUP BY DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1)
ORDER BY 1
```

### cx-10 (yeniden koşu)

```sql
SELECT DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1) AS ay,
       COUNT(DISTINCT "LOGICALREF") AS siparis_sayisi,
       SUM("NETTOTAL") AS toplam_tutar
FROM dbo_LG_411_01_ORFICHE
WHERE "CANCELLED" = 0
  AND "DATE_" >= '2026-01-01'
  AND "DATE_" < '2027-01-01'
GROUP BY DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1)
ORDER BY ay
```

## Sistem davranışı

- 10/10 soru SQL üretti, dry-run onarım döngüsü hiç tetiklenmedi; aşamalar: bağlam 0,1–3,7 s · LLM 12–27 s · sorgu 0,3–1,6 s · özet 7–13 s.
- İstem boyutu 2,6–4,1k token; şema bağlamı `get_context` (LanceDB) + anımsanan doğrulanmış çiftlerin kolonlarından kuruluyor.
- İki hata sınıfı: (1) korelasyonsuz skaler alt sorgu, (2) başlık→satır join fan-out. Her ikisi de `knowledge/rules/logo-erp.md` (Kural 7, 8) + `knowledge/sql/` doğrulanmış çiftleriyle kapatıldı, `wren memory index` yenilendi.
- Öneri: yeni kritik metrikleri MDL hesaplanmış alan / cube olarak tanımlayıp LLM'in formül türetmesini azaltmak; her doğrulanan cevabı `wren memory store` ile çift olarak saklamak.