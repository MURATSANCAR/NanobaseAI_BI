#!/usr/bin/env python3
"""Logo ERP iş kurallarını semantik motorun kendi bilgi mekanizmalarına yazar:
   - instructions (isDefault=True → her soruya uygulanır)
   - sqlPairs (doğrulanmış soru→SQL çiftleri; retrieval'da örnek olarak kullanılır)
Sunucuda çalışır: python3 wren_knowledge.py   (wren-ui 127.0.0.1:3000)
Kurallar canlı LOGO_DB üzerinde doğrulanmıştır (2026-09-06)."""
import json, urllib.request

GQL = "http://127.0.0.1:3000/api/graphql"

def gql(query, variables=None):
    req = urllib.request.Request(GQL, data=json.dumps({"query": query, "variables": variables or {}}).encode(),
                                 headers={"Content-Type": "application/json"})
    d = json.loads(urllib.request.urlopen(req, timeout=300).read())
    if d.get("errors"):
        raise RuntimeError(json.dumps(d["errors"], ensure_ascii=False)[:600])
    return d["data"]

INSTRUCTIONS = [
    ("Fatura türleri (dbo_LG_411_01_INVOICE.TRCODE): 7 perakende satış, 8 toptan satış, 9 verilen hizmet = SATIŞ; "
     "2 perakende satış iadesi, 3 toptan satış iadesi = SATIŞ İADESİ; 1 mal alım, 4 alınan hizmet = SATINALMA; "
     "6 alım iadesi. Ciro/satış sorularında TRCODE IN (7,8,9), net ciro = satış − iade (TRCODE IN (2,3)). "
     "Her zaman CANCELLED = 0 filtrele. Tutar kolonu NETTOTAL (KDV dahil net), tarih DATE_.",
     ["toplam ciro", "net satış", "aylık satış", "iade tutarı"]),
    ("Malzeme hareket satırları (dbo_LG_411_01_STLINE): LINETYPE 0 = malzeme satırı, 2 = İSKONTO satırı (TOTAL'i ciro kadar büyüktür); "
     "ürün bazlı ciro/adet için LINETYPE = 0 AND CANCELLED = 0 kullan; satış TRCODE IN (7,8), satış iadesi TRCODE IN (2,3). "
     "Adet = AMOUNT, satır tutarı = TOTAL. OUTCOST BİRİM maliyettir: satır maliyeti = AMOUNT * OUTCOST; "
     "brüt kâr marjı = 1 − SUM(AMOUNT*OUTCOST)/SUM(TOTAL) yalnız OUTCOST <> 0 satırlarda. Tabloyu daima DATE_ ile filtrele.",
     ["en çok satan ürünler", "ürün bazında ciro", "brüt kâr marjı", "iskonto oranı"]),
    ("Cari kartlar (dbo_LG_411_CLCARD): SPECODE2 = SATIŞ KANALI (KITAPCI, E-TICARET, DAGITICI, ZINCIR, KURUM, MAGAZA, FUAR, YURTDIŞI...), "
     "DEFINITION_ = cari unvanı, CODE = cari kodu, CITY = şehir. Kanal soruları SPECODE2 ile gruplanır; boş değerler '(boş)' sayılır. "
     "Kişisel veri kolonlarını (TCKNO, EMAILADDR, TELNRS1/2, adres, IBAN) asla seçme.",
     ["kanal bazında satış", "müşteri bazında ciro", "şehir bazında satış"]),
    ("Malzeme kartları (dbo_LG_411_ITEMS): SPECODE = YAYINEVİ/imprint (Timaş Çocuk, Genç Timaş, Mavi Kirpi...), NAME = kitap adı, CODE = stok kodu, "
     "STGRPCODE grup kodu. Yayınevi/dizi kırılımı SPECODE ile yapılır. STLINE.STOCKREF → ITEMS.LOGICALREF, STLINE.CLIENTREF → CLCARD.LOGICALREF, "
     "INVOICE.CLIENTREF → CLCARD.LOGICALREF, STLINE.INVOICEREF → INVOICE.LOGICALREF.",
     ["yayınevi bazında satış", "en çok satan kitaplar", "kitap adına göre"]),
    ("Siparişler (dbo_LG_411_01_ORFICHE / ORFLINE): bu kurulumda TRCODE = 1 fişleri satış siparişidir (e-ticaret/pazaryeri kanalı). "
     "Açık sipariş = CANCELLED = 0 AND CLOSED = 0 AND AMOUNT > SHIPPEDAMOUNT. Sipariş modülü tüm satışları kapsamaz; ciro için fatura tablosunu kullan.",
     ["açık siparişler", "sevk edilmeyen sipariş", "sipariş tutarı"]),
    ("Veri 2026 yılına (firma 411, Ocak–Ağustos) aittir; yıl belirtilmeyen sorular 2026 YTD kabul edilir. Para birimi TL. "
     "Tarih kırılımı için EXTRACT(MONTH FROM DATE_) / EXTRACT(YEAR FROM DATE_) kullan. Türkçe yanıt ver.",
     ["bu yıl", "aylık", "geçen ay"]),
]

SQL_PAIRS = [
    # Bu MSSQL yolunda EXTRACT/DATE_PART çevrilemiyor: ay kırılımı tarih aralığı ile yapılır.
    ("2026 yılında aylık net satış tutarı nedir?",
     'SELECT ' + ', '.join(
         f'SUM(CASE WHEN "DATE_" >= \'2026-{m:02d}-01\' AND "DATE_" < \'{2027 if m == 12 else 2026}-{1 if m == 12 else m + 1:02d}-01\' '
         f'AND "TRCODE" IN (7,8,9) THEN "NETTOTAL" ELSE 0 END) - '
         f'SUM(CASE WHEN "DATE_" >= \'2026-{m:02d}-01\' AND "DATE_" < \'{2027 if m == 12 else 2026}-{1 if m == 12 else m + 1:02d}-01\' '
         f'AND "TRCODE" IN (2,3) THEN "NETTOTAL" ELSE 0 END) AS ay_{m:02d}' for m in range(1, 13)) +
     ' FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 0 AND "TRCODE" IN (2,3,7,8,9)'),
    ("Ağustos 2026 net satış tutarı nedir?",
     'SELECT SUM(CASE WHEN "TRCODE" IN (7,8,9) THEN "NETTOTAL" ELSE -"NETTOTAL" END) AS net_ciro '
     'FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 0 AND "TRCODE" IN (2,3,7,8,9) '
     'AND "DATE_" >= \'2026-08-01\' AND "DATE_" < \'2026-09-01\''),
    ("Günlük satış tutarı (son günler) nedir?",
     'SELECT CAST("DATE_" AS DATE) AS gun, SUM("NETTOTAL") AS satis FROM dbo_LG_411_01_INVOICE '
     'WHERE "CANCELLED" = 0 AND "TRCODE" IN (7,8,9) AND "DATE_" >= \'2026-08-01\' GROUP BY CAST("DATE_" AS DATE) ORDER BY 1'),
    ("Kanal bazında net ciro nedir?",
     'SELECT COALESCE(NULLIF(c."SPECODE2", \'\'), \'(boş)\') AS kanal, '
     'SUM(CASE WHEN i."TRCODE" IN (7,8,9) THEN i."NETTOTAL" ELSE -i."NETTOTAL" END) AS net_ciro, COUNT(DISTINCT i."CLIENTREF") AS cari_sayisi '
     'FROM dbo_LG_411_01_INVOICE i JOIN dbo_LG_411_CLCARD c ON c."LOGICALREF" = i."CLIENTREF" '
     'WHERE i."CANCELLED" = 0 AND i."TRCODE" IN (2,3,7,8,9) GROUP BY 1 ORDER BY net_ciro DESC'),
    ("En çok satan 10 kitap hangileri (adet)?",
     'SELECT it."CODE" AS stok_kodu, it."NAME" AS kitap, SUM(sl."AMOUNT") AS adet, SUM(sl."TOTAL") AS tutar '
     'FROM dbo_LG_411_01_STLINE sl JOIN dbo_LG_411_ITEMS it ON it."LOGICALREF" = sl."STOCKREF" '
     'WHERE sl."CANCELLED" = 0 AND sl."LINETYPE" = 0 AND sl."TRCODE" IN (7,8) GROUP BY it."CODE", it."NAME" ORDER BY adet DESC LIMIT 10'),
    ("En çok iade alan 10 müşteri kimler?",
     'SELECT c."CODE" AS cari_kodu, c."DEFINITION_" AS unvan, SUM(i."NETTOTAL") AS iade_tutari, COUNT(*) AS iade_faturasi '
     'FROM dbo_LG_411_01_INVOICE i JOIN dbo_LG_411_CLCARD c ON c."LOGICALREF" = i."CLIENTREF" '
     'WHERE i."CANCELLED" = 0 AND i."TRCODE" IN (2,3) GROUP BY c."CODE", c."DEFINITION_" ORDER BY iade_tutari DESC LIMIT 10'),
    ("2026 iskonto oranı nedir?",
     'SELECT SUM(CASE WHEN "LINETYPE" = 0 THEN "TOTAL" ELSE 0 END) AS brut, SUM(CASE WHEN "LINETYPE" = 2 THEN "TOTAL" ELSE 0 END) AS iskonto, '
     'SUM(CASE WHEN "LINETYPE" = 2 THEN "TOTAL" ELSE 0 END) / NULLIF(SUM(CASE WHEN "LINETYPE" = 0 THEN "TOTAL" ELSE 0 END), 0) AS iskonto_orani '
     'FROM dbo_LG_411_01_STLINE WHERE "CANCELLED" = 0 AND "TRCODE" IN (7,8) AND "DATE_" >= \'2026-01-01\''),
    ("Yayınevi bazında net ciro ve brüt kâr marjı nedir?",
     'SELECT COALESCE(NULLIF(it."SPECODE", \'\'), \'(boş)\') AS yayinevi, '
     'SUM(CASE WHEN sl."TRCODE" IN (7,8) THEN sl."TOTAL" ELSE -sl."TOTAL" END) AS net_ciro, '
     '1 - SUM(CASE WHEN sl."TRCODE" IN (7,8) AND sl."OUTCOST" <> 0 THEN sl."AMOUNT" * sl."OUTCOST" ELSE 0 END) '
     '/ NULLIF(SUM(CASE WHEN sl."TRCODE" IN (7,8) AND sl."OUTCOST" <> 0 THEN sl."TOTAL" ELSE 0 END), 0) AS brut_kar_marji '
     'FROM dbo_LG_411_01_STLINE sl JOIN dbo_LG_411_ITEMS it ON it."LOGICALREF" = sl."STOCKREF" '
     'WHERE sl."CANCELLED" = 0 AND sl."LINETYPE" = 0 AND sl."TRCODE" IN (2,3,7,8) GROUP BY 1 ORDER BY net_ciro DESC'),
]

existing_i = {i["instruction"][:60] for i in (gql("query { instructions { id instruction } }")["instructions"] or [])}
for text, qs in INSTRUCTIONS:
    if text[:60] in existing_i:
        print("  = instruction var:", text[:50]); continue
    gql("mutation($d: CreateInstructionInput!) { createInstruction(data: $d) { id } }",
        {"d": {"instruction": text, "questions": qs, "isDefault": True}})
    print("  + instruction:", text[:50])

existing_q = {p["question"] for p in (gql("query { sqlPairs { id question } }")["sqlPairs"] or []) if p}
for q, sql in SQL_PAIRS:
    if q in existing_q:
        print("  = sqlPair var:", q); continue
    gql("mutation($d: CreateSqlPairInput!) { createSqlPair(data: $d) { id } }", {"d": {"question": q, "sql": sql}})
    print("  + sqlPair:", q)
print("bitti")
