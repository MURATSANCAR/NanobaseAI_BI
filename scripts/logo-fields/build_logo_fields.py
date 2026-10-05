"""Logo satışına bağlı kartların kırılım/süzgeç olabilecek kolonlarını gerçek veriden seçer.

Neden: finans motoru yalnız elle yazılmış ~18 kırılımı tanıyordu; «vilayet bazında satış», «ödeme planına göre»,
«temsilci bazında» gibi günlük dildeki sorular veri Logo'da hazır olduğu hâlde reddediliyordu. Kolon listesi elle
seçilmez: Logo sözlüğündeki (configs/schemas/logo-ldds.json) metin ve kodlu kolonlardan, satış yapılan kayıtlarda
yeterince dolu (≥%5) ve kategorik olan (2–1000 farklı değer, kayıt başına tekil değil) kolonlar alınır. Telefon,
vergi no, e-posta, açıklama gibi her kayıtta farklı alanlar bu kuralla kendiliğinden düşer.

Bağlı kartlar (sözlükteki ilişkiler): satış satırı → müşteri kartı (CLIENTREF), ürün kartı (STOCKREF), fatura başlığı
(INVOICEREF); fatura başlığı → ödeme planı (PAYDEFREF), satış temsilcisi (SALESMANREF), teslimat adresi (SHIPINFOREF).
Ödeme planı ve temsilci küçük tablolardır: adları (DEFINITION_) faturadaki bağlantı ≥%1 doluysa alınır.

Çalıştırma (test sunucusunda, salt okuma):
    python scripts/logo-fields/build_logo_fields.py --conn /data/nanobaseai/bi/secrets/logo-mssql-connection.json \
        --firm 411 --period 01 --out configs/finance/logo-fields.json
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

LDDS = ROOT / "configs/schemas/logo-ldds.json"

# Seviye: motorun hangi tablo takma adıyla okuyacağı. Sıra modele gösterilen sıradır.
SOURCES = [
    # seviye, sözlük tablosu, kimlik öneki, Türkçe kart adı, kart kümesi (satış yapılan kayıtlar)
    ("client", "CLCARD", "client", "Müşteri kartı", "LOGICALREF IN (SELECT DISTINCT f.CLIENTREF {sales})"),
    ("item", "ITEMS", "item", "Ürün kartı", "LOGICALREF IN (SELECT DISTINCT f.STOCKREF {sales})"),
    ("invoice", "INVOICE", "invoice", "Fatura", "CANCELLED=0 AND TRCODE IN (7,8,9)"),
    ("ship", "SHIPINFO", "ship", "Teslimat adresi", "LOGICALREF IN (SELECT h.SHIPINFOREF {invoices})"),
]
LOOKUPS = [
    # seviye, sözlük tablosu, kimlik, Türkçe ad, fatura bağlantı kolonu
    ("payplan", "PAYPLANS", "payplan_name", "Ödeme planı", "PAYDEFREF"),
    ("salesman", "SLSMAN", "salesman_name", "Satış temsilcisi", "SALESMANREF"),
]
# Motorda zaten ayrı ve doğrulanmış karşılığı olan kolonlar (müşteri, kanal, kitap, kodlu alanlar, iç işaretler).
COVERED = {
    "CLCARD": {"CODE", "DEFINITION_", "SPECODE2", "ACCEPTEINV", "ISPERSCOMP", "ACTIVE", "CARDTYPE", "TEXTINC",
               "CYPHCODE", "BLOCKED", "ACCEPTEDESP", "ACCEPTEINVPUBLIC", "LOGOID", "ORGLOGOID"},
    "ITEMS": {"CODE", "NAME", "ACTIVE", "TEXTINC", "IMAGEINC", "TOOL", "AUTOINCSL", "DIVLOTSIZE", "LOCTRACKING",
              "CANUSEINTRNS", "SHELFDATE", "TRACKTYPE", "CYPHCODE", "LOGOID", "ORGLOGOID", "UNIVID"},
    "INVOICE": {"TRCODE", "EINVOICE", "EINVOICETYP", "ESTATUS", "PROFILEID", "VATEXCEPTCODE", "CANCELLEDACC",
                "GVATINC", "ENTEGSET", "TEXTINC", "CYPHCODE", "ORGLOGOID", "GENEXP1", "GENEXP2", "GENEXP3",
                "GENEXP4", "GENEXP5"},
    "SHIPINFO": {"CODE", "NAME", "CYPHCODE"},
}
MIN_FILL, MAX_DISTINCT, LOOKUP_MIN_FILL = 0.05, 1000, 0.01


def text(alias: str, col: str) -> str:
    return f"NULLIF(LTRIM(RTRIM(CAST({alias}.[{col}] AS nvarchar(400)))),'')"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--conn", required=True)
    ap.add_argument("--firm", default="411")
    ap.add_argument("--period", default="01")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    from semantic_layer.profiler.connectors import connector_from_file

    conn = connector_from_file(args.conn)

    def read(sql: str) -> list[dict]:
        res = conn.execute(sql, 1000)
        return res[1] if isinstance(res, tuple) else res

    f, p = args.firm, args.period
    tables = json.loads(LDDS.read_text())["tables"]
    phys = lambda t: f"dbo.LG_{f}_{p}_{t}" if tables[t]["level"] == "period" else (
        f"dbo.LG_{t}" if tables[t]["level"] == "system" else f"dbo.LG_{f}_{t}")
    sales = (f"FROM {phys('STLINE')} f WITH (NOLOCK) WHERE f.CANCELLED=0 AND f.LINETYPE=0 AND f.INVOICEREF<>0"
             " AND f.TRCODE IN (7,8,9)")
    invoices = f"FROM {phys('INVOICE')} h WITH (NOLOCK) WHERE h.CANCELLED=0 AND h.TRCODE IN (7,8,9)"
    fields: list[dict] = []
    for level, table, prefix, card, where in SOURCES:
        cols = tables[table]["columns"]
        cand = [n for n, c in cols.items() if n not in COVERED.get(table, set())
                and (c.get("type") == "ZString" or (c.get("values_tr") and c.get("type") in ("Integer", "Byte")))]
        cond = where.format(sales=sales, invoices=invoices)
        stats = read(f"SELECT COUNT(*) AS [_rows], " + ", ".join(
            f"COUNT({text('t', n)}) AS [{n}__fill], COUNT(DISTINCT {text('t', n)}) AS [{n}__dist]" for n in cand)
            + f" FROM {phys(table)} t WITH (NOLOCK) WHERE {cond}")[0]
        rows = stats["_rows"] or 0
        keep = [n for n in cand if rows and stats[f"{n}__fill"] / rows >= MIN_FILL
                and 2 <= stats[f"{n}__dist"] <= MAX_DISTINCT and stats[f"{n}__dist"] <= 0.5 * stats[f"{n}__fill"]]
        if not keep:
            continue
        # Bütün seçilen kolonların en sık değerleri tek taramada (kolon başına ayrı tarama zaman aşımına düşüyordu).
        unpivot = ", ".join(f"('{n}', {text('t', n)})" for n in keep)
        tops: dict[str, list] = {}
        for r in read(f"SELECT k, v FROM (SELECT x.k, x.v, ROW_NUMBER() OVER (PARTITION BY x.k ORDER BY COUNT(*) DESC) AS rn"
                      f" FROM {phys(table)} t WITH (NOLOCK) CROSS APPLY (VALUES {unpivot}) x(k, v)"
                      f" WHERE {cond} AND x.v IS NOT NULL GROUP BY x.k, x.v) y WHERE rn <= 8 ORDER BY k, rn"):
            tops.setdefault(r["k"], []).append(r)
        for n in keep:
            fill, dist = stats[f"{n}__fill"], stats[f"{n}__dist"]
            meta = cols[n]
            top = tops.get(n, [])
            values = meta.get("values_tr") if meta.get("type") in ("Integer", "Byte") else None
            fields.append({
                "id": f"{prefix}_{n.lower().rstrip('_')}", "level": level, "table": table, "column": n,
                "label": f"{card} — {meta.get('description_tr') or meta.get('description') or n}",
                "kind": "coded" if values else "text", "values": values,
                "samples": [values.get(str(r["v"]), str(r["v"])) if values else str(r["v"]) for r in top],
                "fill": round(fill / rows, 3), "distinct": dist,
            })
    for level, table, fid, card, ref in LOOKUPS:
        s = read(f"SELECT COUNT(*) AS n, SUM(CASE WHEN ISNULL(h.{ref},0)<>0 THEN 1 ELSE 0 END) AS linked {invoices}")[0]
        if not s["n"] or (s["linked"] or 0) / s["n"] < LOOKUP_MIN_FILL:
            continue
        top = read(f"SELECT TOP 8 {text('t', 'DEFINITION_')} AS v, COUNT(*) AS n {invoices.replace('WHERE', f'JOIN {phys(table)} t WITH (NOLOCK) ON t.LOGICALREF=h.{ref} WHERE')}"
                   f" GROUP BY {text('t', 'DEFINITION_')} ORDER BY COUNT(*) DESC")
        fields.append({"id": fid, "level": level, "table": table, "column": "DEFINITION_", "label": card,
                       "kind": "text", "values": None, "samples": [str(r["v"]) for r in top if r["v"]],
                       "fill": round(s["linked"] / s["n"], 3), "distinct": None})
    out = {"generated_at": dt.date.today().isoformat(), "generator": "scripts/logo-fields/build_logo_fields.py",
           "profiled": f"LG_{f}_{p} satış faturaları (TRCODE 7/8/9)", "rule": {
               "min_fill": MIN_FILL, "max_distinct": MAX_DISTINCT, "lookup_min_fill": LOOKUP_MIN_FILL},
           "fields": fields}
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n")
    print(f"{len(fields)} alan yazıldı → {args.out}")


if __name__ == "__main__":
    main()
