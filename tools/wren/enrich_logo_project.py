#!/usr/bin/env python3
"""Enrich the Logo/TİMAŞ Wren project so every WrenAI main-line mechanism is in use:
  * model + key column descriptions (properties.description) → better memory/get_context retrieval
  * calculated columns (INVOICE/STLINE)  → LLM never re-derives sign/cost logic
  * views (monthly sales, channel net, imprint performance) → stable query shapes
  * cubes (sales_cube on INVOICE, line_cube on STLINE) → governed measures via `wren cube query` / MCP query_cube
  * knowledge/glossary, knowledge/metrics, knowledge/caveats (Turkish, verified definitions)
  * strict mode (~/.wren/config.json) with denied functions
  * verified campaign NL→SQL pairs stored with `wren memory store`
Run on the server inside the project dir; idempotent. Then: wren context validate → build → memory index.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

P = Path(sys.argv[1] if len(sys.argv) > 1 else "/data/nanobaseai/bi/wren-project/logo_timas").resolve()
WREN = Path(sys.argv[2] if len(sys.argv) > 2 else "/data/nanobaseai/bi/wren-venv/bin/wren")
LOGS = Path("/data/nanobaseai/bi/logs")


def q(v: object) -> str:
    return json.dumps(v, ensure_ascii=False)


# ---------------------------------------------------------------- descriptions
MODEL_DESC = {
    "dbo_LG_411_01_INVOICE": "Fatura başlığı (2026, firma 411). TRCODE: 1 mal alım, 2 perakende satış iadesi, 3 toptan satış iadesi, 4 alınan hizmet, 6 alım iadesi, 7 perakende satış, 8 toptan satış, 9 verilen hizmet. Tutar NETTOTAL (KDV dahil net), tarih DATE_, cari CLIENTREF → dbo_LG_411_CLCARD. Daima CANCELLED = 0.",
    "dbo_LG_411_01_STLINE": "Malzeme hareket satırı (fatura/irsaliye satırları). LINETYPE: 0 malzeme satırı, 2 iskonto satırı (TOTAL iskonto tutarı), 4 hizmet. TRCODE satış 7/8, satış iadesi 2/3. AMOUNT adet, TOTAL satır brüt tutarı (iskonto öncesi), OUTCOST birim maliyet (satır maliyeti = AMOUNT*OUTCOST), STOCKREF → dbo_LG_411_ITEMS, INVOICEREF → dbo_LG_411_01_INVOICE. Daima CANCELLED = 0 ve DATE_ ile filtrele.",
    "dbo_LG_411_CLCARD": "Cari kart (müşteri/tedarikçi). CODE cari kodu, DEFINITION_ unvan, SPECODE2 SATIŞ KANALI (KITAPCI, E-TICARET, DAGITICI, ZINCIR, KURUM, MAGAZA, FUAR...).",
    "dbo_LG_411_ITEMS": "Malzeme kartı (kitap/ürün). CODE stok kodu, NAME kitap adı, SPECODE YAYINEVİ (imprint) özel kodu.",
    "dbo_LG_411_01_ORFICHE": "Sipariş fişi başlığı. Sipariş sayısı = COUNT(DISTINCT LOGICALREF); tutar NETTOTAL; tarih DATE_; CLIENTREF → cari. Satırlara JOIN edince satır sayısı kadar çoğalır.",
    "dbo_LG_411_01_ORFLINE": "Sipariş fişi satırı. ORDFICHEREF → dbo_LG_411_01_ORFICHE, STOCKREF → dbo_LG_411_ITEMS; AMOUNT adet, TOTAL satır brüt tutarı.",
    "dbo_LG_411_01_CLFLINE": "Cari hesap hareketi (borç/alacak). CLIENTREF → cari; tutar AMOUNT, işaret SIGN (0 borç, 1 alacak), tarih DATE_; TRCODE hareket türü.",
}
COL_DESC = {
    "dbo_LG_411_01_INVOICE": {
        "TRCODE": "Fatura türü: 1 mal alım, 2 perakende satış iadesi, 3 toptan satış iadesi, 4 alınan hizmet, 6 alım iadesi, 7 perakende satış, 8 toptan satış, 9 verilen hizmet",
        "NETTOTAL": "Fatura net toplamı (KDV dahil); ciro/satış/iade/alım tutarı bu kolondan",
        "GROSSTOTAL": "Fatura brüt toplamı (iskonto öncesi)", "TOTALDISCOUNTS": "Fatura toplam iskontosu", "TOTALVAT": "Fatura toplam KDV",
        "DATE_": "Fatura tarihi (2026)", "CANCELLED": "İptal bayrağı; daima CANCELLED = 0", "CLIENTREF": "Cari kart referansı → dbo_LG_411_CLCARD.LOGICALREF",
        "FICHENO": "Fatura numarası", "TRCURR": "Döviz türü (0 = TL)", "TRNET": "Döviz cinsinden net tutar", "LOGICALREF": "Birincil anahtar",
    },
    "dbo_LG_411_01_STLINE": {
        "LINETYPE": "Satır türü: 0 malzeme, 2 iskonto satırı, 4 hizmet", "TRCODE": "Hareket türü: 7 perakende satış, 8 toptan satış, 2/3 satış iadesi, 1 alım",
        "AMOUNT": "Adet (miktar)", "TOTAL": "Satır tutarı; LINETYPE 0 için brüt (iskonto öncesi), LINETYPE 2 için iskonto tutarı",
        "OUTCOST": "Birim maliyet (maliyetlendirme çalışmadıysa 0); satır maliyeti = AMOUNT * OUTCOST", "PRICE": "Birim fiyat",
        "DATE_": "Hareket tarihi; STLINE daima DATE_ ile filtrelenir", "CANCELLED": "İptal bayrağı; daima 0", "STOCKREF": "Malzeme referansı → dbo_LG_411_ITEMS.LOGICALREF",
        "INVOICEREF": "Fatura başlığı referansı → dbo_LG_411_01_INVOICE.LOGICALREF", "CLIENTREF": "Cari referansı → dbo_LG_411_CLCARD.LOGICALREF", "VATAMNT": "Satır KDV tutarı", "LOGICALREF": "Birincil anahtar",
    },
    "dbo_LG_411_CLCARD": {"CODE": "Cari kodu", "DEFINITION_": "Cari unvanı (müşteri/tedarikçi adı)", "SPECODE2": "Satış kanalı kodu (KITAPCI, E-TICARET, DAGITICI, ZINCIR, KURUM, MAGAZA, FUAR)", "SPECODE": "Cari özel kodu", "LOGICALREF": "Birincil anahtar", "CITY": "Şehir", "TAXNR": "Vergi numarası"},
    "dbo_LG_411_ITEMS": {"CODE": "Stok (kitap) kodu", "NAME": "Kitap / ürün adı", "SPECODE": "Yayınevi (imprint) özel kodu", "LOGICALREF": "Birincil anahtar", "PRODUCERCODE": "Üretici kodu"},
    "dbo_LG_411_01_ORFICHE": {"NETTOTAL": "Sipariş fişi net tutarı", "DATE_": "Sipariş tarihi", "CANCELLED": "İptal bayrağı; daima 0", "CLIENTREF": "Cari referansı", "LOGICALREF": "Birincil anahtar; sipariş sayısı = COUNT(DISTINCT LOGICALREF)", "TRCODE": "Sipariş türü (1 satınalma siparişi, 2 satış siparişi)"},
    "dbo_LG_411_01_ORFLINE": {"ORDFICHEREF": "Sipariş fişi referansı → dbo_LG_411_01_ORFICHE", "STOCKREF": "Malzeme referansı", "AMOUNT": "Sipariş adedi", "TOTAL": "Satır brüt tutarı", "SHIPPEDAMOUNT": "Sevk edilen adet", "DATE_": "Sipariş satır tarihi"},
    "dbo_LG_411_01_CLFLINE": {"CLIENTREF": "Cari referansı", "AMOUNT": "Hareket tutarı", "SIGN": "0 borç, 1 alacak", "DATE_": "Hareket tarihi", "TRCODE": "Hareket türü", "CANCELLED": "İptal bayrağı"},
}
CALC = {
    "dbo_LG_411_01_INVOICE": [
        ("is_sale", "BOOLEAN", 'CASE WHEN "TRCODE" IN (7,8,9) THEN 1 ELSE 0 END', "Satış faturası mı (TRCODE 7,8,9)"),
        ("is_sales_return", "BOOLEAN", 'CASE WHEN "TRCODE" IN (2,3) THEN 1 ELSE 0 END', "Satış iadesi mi (TRCODE 2,3)"),
        ("is_purchase", "BOOLEAN", 'CASE WHEN "TRCODE" IN (1,4) THEN 1 ELSE 0 END', "Mal alım / alınan hizmet mi (TRCODE 1,4)"),
        ("net_signed_total", "DOUBLE", 'CASE WHEN "TRCODE" IN (7,8,9) THEN "NETTOTAL" WHEN "TRCODE" IN (2,3) THEN -"NETTOTAL" ELSE 0 END', "Net ciroya katkı: satış +NETTOTAL, satış iadesi −NETTOTAL, diğer 0"),
        ("invoice_month", "DATE", 'DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1)', "Fatura ayı (ayın ilk günü)"),
    ],
    "dbo_LG_411_01_STLINE": [
        ("line_cost", "DOUBLE", '"AMOUNT" * "OUTCOST"', "Satır maliyeti (birim maliyet × adet); OUTCOST = 0 ise maliyetlendirilmemiş"),
        ("is_item_line", "BOOLEAN", 'CASE WHEN "LINETYPE" = 0 THEN 1 ELSE 0 END', "Malzeme satırı mı"),
        ("is_discount_line", "BOOLEAN", 'CASE WHEN "LINETYPE" = 2 THEN 1 ELSE 0 END', "İskonto satırı mı"),
        ("line_month", "DATE", 'DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1)', "Hareket ayı"),
    ],
}

def add_descriptions_and_calcs() -> None:
    for name, desc in MODEL_DESC.items():
        f = P / "models" / name / "metadata.yml"
        if not f.exists():
            continue
        s = f.read_text(encoding="utf-8")
        # model description
        if "properties:" in s.split("columns:")[0]:
            head, tail = s.split("columns:", 1)
            if '"description"' not in head:
                head = head.replace("properties:\n", "properties:\n  \"description\": %s\n" % q(desc), 1)
            s = head + "columns:" + tail
        else:
            s = s.replace("columns:", "properties:\n  \"description\": %s\ncolumns:" % q(desc), 1)
        # column descriptions
        for col, cdesc in COL_DESC.get(name, {}).items():
            pat = re.compile(r'(  - name: "%s"\n    type: "[^"]*"\n)((?:    (?!- name).*\n)*)' % re.escape(col))
            m = pat.search(s)
            if not m or '"description"' in m.group(2):
                continue
            block = m.group(2)
            if "    properties:" in block:
                block = block.replace("    properties:\n", "    properties:\n      \"description\": %s\n" % q(cdesc), 1)
            else:
                block = block + "    properties:\n      \"description\": %s\n" % q(cdesc)
            s = s[: m.start()] + m.group(1) + block + s[m.end():]
        # calculated columns
        for cname, ctype, expr, cdesc in CALC.get(name, []):
            if '  - name: "%s"' % cname in s:
                continue
            s = s.rstrip("\n") + "\n  - name: %s\n    type: %s\n    is_calculated: true\n    expression: %s\n    properties:\n      \"description\": %s\n" % (q(cname), q(ctype), q(expr), q(cdesc))
        f.write_text(s, encoding="utf-8")
    print("descriptions + calculated columns applied")


# ---------------------------------------------------------------- views + cubes
VIEWS = {
    "v_monthly_sales": ("Ay bazında satış, satış iadesi, alım tutarları ve satış fatura sayısı (fatura başlığı, CANCELLED = 0)",
        '''SELECT DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1) AS ay,
  SUM(CASE WHEN "TRCODE" IN (7,8,9) THEN "NETTOTAL" ELSE 0 END) AS satis,
  SUM(CASE WHEN "TRCODE" IN (2,3) THEN "NETTOTAL" ELSE 0 END) AS iade,
  SUM(CASE WHEN "TRCODE" IN (7,8,9) THEN "NETTOTAL" ELSE 0 END) - SUM(CASE WHEN "TRCODE" IN (2,3) THEN "NETTOTAL" ELSE 0 END) AS net_ciro,
  SUM(CASE WHEN "TRCODE" IN (1,4) THEN "NETTOTAL" ELSE 0 END) AS alim,
  SUM(CASE WHEN "TRCODE" IN (7,8,9) THEN 1 ELSE 0 END) AS satis_fatura_sayisi
FROM dbo_LG_411_01_INVOICE WHERE "CANCELLED" = 0
GROUP BY DATEFROMPARTS(YEAR("DATE_"), MONTH("DATE_"), 1)'''),
    "v_channel_net": ("Kanal (cari SPECODE2) bazında net ciro ve cari sayısı",
        '''SELECT COALESCE(NULLIF(c."SPECODE2", ''), '(boş)') AS kanal,
  SUM(CASE WHEN i."TRCODE" IN (7,8,9) THEN i."NETTOTAL" WHEN i."TRCODE" IN (2,3) THEN -i."NETTOTAL" ELSE 0 END) AS net_ciro,
  COUNT(DISTINCT i."CLIENTREF") AS cari_sayisi
FROM dbo_LG_411_01_INVOICE i JOIN dbo_LG_411_CLCARD c ON c."LOGICALREF" = i."CLIENTREF"
WHERE i."CANCELLED" = 0 AND i."TRCODE" IN (2,3,7,8,9)
GROUP BY COALESCE(NULLIF(c."SPECODE2", ''), '(boş)')'''),
    "v_imprint_perf": ("Yayınevi (ITEMS.SPECODE) bazında net ciro, satılan/iade adet, maliyetli ciro ve maliyet (satır bazlı)",
        '''SELECT COALESCE(NULLIF(it."SPECODE", ''), '(boş)') AS yayinevi,
  COUNT(DISTINCT sl."STOCKREF") AS baslik,
  SUM(CASE WHEN sl."TRCODE" IN (7,8) THEN sl."TOTAL" ELSE -sl."TOTAL" END) AS net_ciro,
  SUM(CASE WHEN sl."TRCODE" IN (7,8) THEN sl."AMOUNT" ELSE 0 END) AS satilan_adet,
  SUM(CASE WHEN sl."TRCODE" IN (2,3) THEN sl."AMOUNT" ELSE 0 END) AS iade_adet,
  SUM(CASE WHEN sl."TRCODE" IN (7,8) AND sl."OUTCOST" <> 0 THEN sl."TOTAL" ELSE 0 END) AS maliyetli_ciro,
  SUM(CASE WHEN sl."TRCODE" IN (7,8) AND sl."OUTCOST" <> 0 THEN sl."AMOUNT" * sl."OUTCOST" ELSE 0 END) AS maliyet
FROM dbo_LG_411_01_STLINE sl JOIN dbo_LG_411_ITEMS it ON it."LOGICALREF" = sl."STOCKREF"
WHERE sl."CANCELLED" = 0 AND sl."LINETYPE" = 0 AND sl."TRCODE" IN (2,3,7,8)
GROUP BY COALESCE(NULLIF(it."SPECODE", ''), '(boş)')'''),
}
CUBES = {
    "sales_cube": '''name: sales_cube
base_object: dbo_LG_411_01_INVOICE
properties:
  description: "Fatura başlığından yönetilen satış/iade/alım ölçüleri (KDV dahil NETTOTAL). Filtre CANCELLED = 0 ölçülere gömülüdür."
measures:
  - name: satis
    expression: SUM(CASE WHEN "TRCODE" IN (7,8,9) AND "CANCELLED" = 0 THEN "NETTOTAL" ELSE 0 END)
    type: DOUBLE
  - name: iade
    expression: SUM(CASE WHEN "TRCODE" IN (2,3) AND "CANCELLED" = 0 THEN "NETTOTAL" ELSE 0 END)
    type: DOUBLE
  - name: net_ciro
    expression: SUM(CASE WHEN "TRCODE" IN (7,8,9) AND "CANCELLED" = 0 THEN "NETTOTAL" WHEN "TRCODE" IN (2,3) AND "CANCELLED" = 0 THEN -"NETTOTAL" ELSE 0 END)
    type: DOUBLE
  - name: alim
    expression: SUM(CASE WHEN "TRCODE" IN (1,4) AND "CANCELLED" = 0 THEN "NETTOTAL" ELSE 0 END)
    type: DOUBLE
  - name: satis_fatura_sayisi
    expression: SUM(CASE WHEN "TRCODE" IN (7,8,9) AND "CANCELLED" = 0 THEN 1 ELSE 0 END)
    type: BIGINT
dimensions:
  - name: trcode
    expression: "TRCODE"
    type: INTEGER
time_dimensions:
  - name: fatura_tarihi
    expression: "DATE_"
    type: DATE
hierarchies:
  zaman: [fatura_tarihi]
''',
    "line_cube": '''name: line_cube
base_object: dbo_LG_411_01_STLINE
properties:
  description: "Satış hareket satırlarından brüt satır, iskonto, maliyetli ciro ve maliyet ölçüleri (TRCODE 7,8; CANCELLED = 0)."
measures:
  - name: brut_satir
    expression: SUM(CASE WHEN "LINETYPE" = 0 AND "TRCODE" IN (7,8) AND "CANCELLED" = 0 THEN "TOTAL" ELSE 0 END)
    type: DOUBLE
  - name: iskonto
    expression: SUM(CASE WHEN "LINETYPE" = 2 AND "TRCODE" IN (7,8) AND "CANCELLED" = 0 THEN "TOTAL" ELSE 0 END)
    type: DOUBLE
  - name: maliyetli_ciro
    expression: SUM(CASE WHEN "LINETYPE" = 0 AND "TRCODE" IN (7,8) AND "OUTCOST" <> 0 AND "CANCELLED" = 0 THEN "TOTAL" ELSE 0 END)
    type: DOUBLE
  - name: maliyet
    expression: SUM(CASE WHEN "LINETYPE" = 0 AND "TRCODE" IN (7,8) AND "OUTCOST" <> 0 AND "CANCELLED" = 0 THEN "AMOUNT" * "OUTCOST" ELSE 0 END)
    type: DOUBLE
  - name: satilan_adet
    expression: SUM(CASE WHEN "LINETYPE" = 0 AND "TRCODE" IN (7,8) AND "CANCELLED" = 0 THEN "AMOUNT" ELSE 0 END)
    type: DOUBLE
dimensions:
  - name: trcode
    expression: "TRCODE"
    type: INTEGER
time_dimensions:
  - name: hareket_tarihi
    expression: "DATE_"
    type: DATE
hierarchies:
  zaman: [hareket_tarihi]
''',
}

def add_views_and_cubes() -> None:
    for name, (desc, sql) in VIEWS.items():
        d = P / "views" / name; d.mkdir(parents=True, exist_ok=True)
        (d / "metadata.yml").write_text("name: %s\nproperties:\n  description: %s\nstatement: |\n%s\n" % (q(name), q(desc), "\n".join("  " + l for l in sql.splitlines())), encoding="utf-8")
    for name, body in CUBES.items():
        d = P / "cubes" / name; d.mkdir(parents=True, exist_ok=True)
        (d / "metadata.yml").write_text(body, encoding="utf-8")
    print("views:", list(VIEWS), "cubes:", list(CUBES))


# ---------------------------------------------------------------- knowledge
GLOSSARY = """# Sözlük — Logo ERP / TİMAŞ

## Ciro / Net ciro
Satış faturalarının (TRCODE 7 perakende, 8 toptan, 9 verilen hizmet) NETTOTAL toplamı = satış; net ciro = satış − satış iadesi (TRCODE 2, 3). KDV dahildir.

## Satış iadesi
TRCODE 2 (perakende iade) ve 3 (toptan iade) faturaları; iade oranı = iade / satış.

## Satınalma
Mal alım (TRCODE 1) + alınan hizmet (TRCODE 4). Alım iadesi TRCODE 6 ayrıdır.

## Kanal
Cari kartındaki SPECODE2: KITAPCI, E-TICARET, DAGITICI, ZINCIR, KURUM, MAGAZA, FUAR; boş kod "(boş)".

## Yayınevi (imprint)
Malzeme kartındaki SPECODE (ITEMS.SPECODE); "Timaş Çocu", "İlk Genç T", "Genç Timaş" gibi.

## Başlık
Belirli dönemde hareket görmüş farklı malzeme (STOCKREF) sayısı.

## İskonto satırı
STLINE LINETYPE 2 satırları; TOTAL iskonto tutarıdır. Malzeme satırı LINETYPE 0.

## Maliyetlendirme
OUTCOST birim maliyet; Logo maliyetlendirme aylık gecikmeli çalışır, OUTCOST = 0 satırlar maliyetlendirilmemiştir.
"""
METRICS = """# Metrik tanımları (doğrulanmış, 2026-09-06)

## net_ciro
Σ NETTOTAL (TRCODE 7,8,9) − Σ NETTOTAL (TRCODE 2,3), CANCELLED = 0. Kaynak dbo_LG_411_01_INVOICE. Cube: sales_cube.net_ciro. Görünüm: v_monthly_sales.net_ciro.

## iade_orani
Σ NETTOTAL (2,3) / Σ NETTOTAL (7,8,9).

## iskonto_yuku
Σ TOTAL (LINETYPE 2) / Σ TOTAL (LINETYPE 0), TRCODE 7,8. Kaynak dbo_LG_411_01_STLINE. Cube: line_cube.iskonto / line_cube.brut_satir.

## brut_kar_marji
1 − Σ(AMOUNT × OUTCOST) / Σ TOTAL, LINETYPE 0, TRCODE 7,8, OUTCOST ≠ 0 (iskonto öncesi brüt marj). Cube: 1 − line_cube.maliyet / line_cube.maliyetli_ciro.

## satinalma
Σ NETTOTAL (TRCODE 1,4). Cube: sales_cube.alim.

## siparis_sayisi
COUNT(DISTINCT dbo_LG_411_01_ORFICHE.LOGICALREF), CANCELLED = 0; tutar = ORFICHE.NETTOTAL.

## kanal_net_ciro
Görünüm v_channel_net; cari kartı SPECODE2 üzerinden.

## yayinevi_performans
Görünüm v_imprint_perf: net_ciro (satır bazlı), satilan_adet, iade_adet, maliyetli_ciro, maliyet.
"""
CAVEATS = """# Veri uyarıları (Logo LOGO_DB, firma 411 = 2026)

- NETTOTAL KDV dahildir; 2026 satışlarında KDV payı ≈ %0,5 (KDV hariç ≈ 917,9 M TL).
- Fatura başlığı (INVOICE) ile hareket satırı (STLINE) toplamları arasında ≈ %0,6 fark vardır (hizmet satırları, yuvarlama); kartlar başlıktan, marj/iskonto satırdan hesaplanır.
- STLINE.TOTAL iskonto ÖNCESİ brüt tutardır; iskontolar ayrı satırlarda (LINETYPE 2). Marj iskonto öncesidir; iskonto sonrası marj ≈ %75.
- Maliyetlendirme 30.06.2026'ya kadar işlenmiştir; sonraki satırların OUTCOST = 0 → marj hesaplarına girmez (≈ 404 M TL satır cirosu maliyetsiz).
- TRCODE 6 (alım iadesi, ≈ 20 M TL) satınalma tutarından düşülmez.
- Döviz faturaları (TRCURR ≠ 0, 74 adet) TL karşılığıyla dahildir.
- Aylık/gruplu ortalama için bağımsız skaler alt sorgu yazma (her satıra aynı değeri döndürür); aynı GROUP BY veya CTE kullan.
- Başlık tablosundan sayım yaparken satır tablosuna JOIN etme veya COUNT(DISTINCT başlık.LOGICALREF) kullan (fan-out).
- Firma 411 yalnız 2026-01..08 içerir; 2021-2025 ayrı firmada (211) tutulur, bu projede yoktur.
"""

def add_knowledge() -> None:
    for sub, fn, body in (("glossary", "logo-timas.md", GLOSSARY), ("metrics", "logo-timas.md", METRICS), ("caveats", "logo-timas.md", CAVEATS)):
        d = P / "knowledge" / sub; d.mkdir(parents=True, exist_ok=True)
        (d / fn).write_text(body, encoding="utf-8")
    print("knowledge glossary/metrics/caveats written")


# ---------------------------------------------------------------- strict mode
def strict_mode() -> None:
    cfg = Path.home() / ".wren" / "config.json"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({"strict_mode": True, "denied_functions": ["openrowset", "opendatasource", "openquery", "xp_cmdshell", "sp_executesql"]}, indent=1), encoding="utf-8")
    print("strict mode on:", cfg)


# ---------------------------------------------------------------- verified pairs
def store_verified_pairs() -> None:
    results = {r["id"]: r for r in json.load(open(LOGS / "complex-results.json", encoding="utf-8"))}
    retest = {r["id"]: r for r in json.load(open(LOGS / "retest-results.json", encoding="utf-8"))} if (LOGS / "retest-results.json").exists() else {}
    ok_ids = ["cx-01", "cx-02", "cx-03", "cx-05", "cx-06", "cx-07", "cx-08", "cx-09"]
    existing = " ".join(p.read_text(encoding="utf-8") for p in (P / "knowledge" / "sql").glob("*.md"))
    n = 0
    for cid in ok_ids:
        r = retest.get(cid) or results[cid]
        if r.get("q", "")[:40] in existing:
            continue
        out = subprocess.run([str(WREN), "memory", "store", "--nl", r["q"], "--sql", r["sql"].strip(), "--tags", "verified-2026-09-06,campaign"], cwd=P, capture_output=True, text=True)
        if out.returncode == 0:
            n += 1
        else:
            print("  store failed", cid, (out.stdout + out.stderr).strip()[:200])
    print("stored verified pairs:", n)


def run(*args: str) -> str:
    out = subprocess.run([str(WREN), *args], cwd=P, capture_output=True, text=True)
    txt = (out.stdout + out.stderr).strip()
    return txt


if __name__ == "__main__":
    add_descriptions_and_calcs()
    add_views_and_cubes()
    add_knowledge()
    strict_mode()
    print("== validate"); print("\n".join(run("context", "validate").splitlines()[-6:]))
    print("== build"); print("\n".join(run("context", "build").splitlines()[-3:]))
    store_verified_pairs()
    print("== index"); print("\n".join(run("memory", "index", "--mdl", "target/mdl.json").splitlines()[-3:]))
    print("== cube list"); print(run("cube", "list")[:400])
    print("== memory status"); print(run("memory", "status")[:300])
