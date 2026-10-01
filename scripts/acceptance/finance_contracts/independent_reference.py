"""Kabul testlerinin üründen BAĞIMSIZ referansı (2026-10-01).

Neden: 01.10 incelemesi, kabul betiklerindeki referans SQL'lerin ürünün ölçü sözleşmesindeki
(`finance_query/contracts.py` METRICS) ifadeleri birebir tekrar ettiğini gösterdi. Tanım yanlışsa ürün ve
referans birlikte yanılır, kabul PASS der. Bu modül üç şey sağlar:

1. **Karar referansı** (`decision`): ölçü ve süzgeçler kullanıcı kararlarından ve insan onaylı altın setten
   yazılır, her birinin kaynağı `source` alanında durur. Ürün kodu import edilmez, ürünün SQL'i kopyalanmaz.
2. **İkinci yol** (`cross_check_*`): aynı ölçü farklı bir nesneden yeniden hesaplanır ve 0,01 TL toleransla
   uzlaştırılır: TİMAŞ'ın kendi satış raporu görünümü `V_SatisRaporu_<firma>` (Power BI'ın okuduğu), fatura
   başlığı (`INVOICE`) ve başlık = Σ satır (VATMATRAH + VATAMNT) özdeşliği.
3. **TANIM_FARKI sınıflaması**: ürünün bugünkü tanımı, sunucuda kurulu `contracts.py` METİN olarak okunup
   (`ast`, import yok) yalnız sınıflama için kullanılır. API cevabı karar referansını tutmuyor ama ürün tanımıyla
   hesaplanan referansı tutuyorsa sonuç FAIL değil TANIM_FARKI'dır; PASS/FAIL sayımına karışmaz.

Bu dosya yalnız SELECT üretir; çağıran `composable_live.query` ile okur (o da yalnız SELECT/WITH kabul eder).
Bütün tablo okumaları WITH (NOLOCK) taşır.
"""
from __future__ import annotations

import ast
from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
import argparse
import json
import re
import sys

MONEY_TOLERANCE = Decimal("0.01")
# Başlık = Σ satır özdeşliğinde fatura başına kuruş yuvarlaması (perakende kasa faturaları, 2026-10-01 ölçümü).
# Toplam farkı 0,01'i aşar ama her fatura bu sınırın içindeyse durum YUVARLAMA'dır, UZLASTI değildir.
ROUNDING_PER_INVOICE = Decimal("0.05")
NL = "WITH (NOLOCK)"

# ---------------------------------------------------------------------------
# Karar kaynakları (her referans tanımı buradan birine dayanır)
# ---------------------------------------------------------------------------
SOURCES = {
    "K-SATIS-SATIR": "Kullanıcı kararı 2026-09-21 (bellek: sales-are-invoiced-lines): satış = faturalı satır; "
                     "STLINE INVOICEREF<>0, CANCELLED=0, LINETYPE=0; tutar LINENET (iskonto sonrası, KDV hariç).",
    "K-IADE": "Kullanıcı kararı 2026-10-01: iade 2/3 düşülür; perakende = 7 eksi 2, toptan = 8 eksi 3.",
    "K-FATURA-SAYISI": "Kullanıcı kararı 2026-10-01: fatura sayısı = INVOICE TRCODE 7/8/9, iptal değil, iadesiz "
                       "(Eylül 2026: 13.680); iade faturası sayısı ayrı ölçüdür (TRCODE 2/3, Eylül 2026: 120).",
    "G-A002": "Altın set A002 (answers-set100.json): fatura cirosu = SUM(INVOICE.NETTOTAL), CANCELLED=0, TRCODE 7/8/9.",
    "G-C040": "Altın set C040: satılan adet = faturalı satış satırı TRCODE 7/8/9, IOCODE 3/4, AMOUNT, LINETYPE 0, "
              "CANCELLED 0, INVOICEREF<>0; iade düşülmez.",
    "K-CRM-PASIF": "Kullanıcı kararı 2026-09-29: CRM'de pasif hiçbir yerde yok = statecode=0 VE durum nedeni "
                   "(statuscode) etiketi 'Pasif…'/'Inactive…' değil (StringMapBase, bütün diller).",
    "K-CRM-MUSTERI": "Kullanıcı kararı 2026-10-01: aktif müşteri = AccountBase statecode=0 VE durum nedeni etiketi "
                     "yalnız 'Aktif Müşteri' (Eylül 2026: 11.854; pasif-olmayan 12.388 değil).",
    "K-KANAL": "KAVRAM-SAHIPLIGI.md 'Kanal / müşteri grubu': Logo CLCARD.SPECODE2.",
    "K-BOS-TARIH": "Kullanıcı kararı 2026-10-01: 1899-12-30 / 1900-01-01 tarih girilmemiş demektir.",
    "YOK": "Bağımsız karar ya da altın referans yok; tanım ürünle aynı kaynaktan (ürün tanımı) — bağımsız değildir.",
}


@dataclass(frozen=True)
class Measure:
    """İşaret haritası: TRCODE -> +1/-1. `sales_iocodes`: pozitif kodlarda istenen IOCODE (altın C040)."""
    column: str
    signs: dict
    unit: str
    sources: tuple
    sales_iocodes: tuple = ()

    @property
    def trcodes(self):
        return tuple(sorted(self.signs))


LOGO_MEASURES = {
    "sales_amount": Measure("LINENET", {7: 1, 8: 1, 9: 1}, "TRY", ("K-SATIS-SATIR",)),
    "return_amount": Measure("LINENET", {2: 1, 3: 1}, "TRY", ("K-SATIS-SATIR", "K-IADE")),
    "net_sales": Measure("LINENET", {7: 1, 8: 1, 9: 1, 2: -1, 3: -1}, "TRY", ("K-SATIS-SATIR", "K-IADE")),
    "retail_net_sales": Measure("LINENET", {7: 1, 2: -1}, "TRY", ("K-SATIS-SATIR", "K-IADE")),
    "wholesale_net_sales": Measure("LINENET", {8: 1, 3: -1}, "TRY", ("K-SATIS-SATIR", "K-IADE")),
    "retail_sales_amount": Measure("LINENET", {7: 1}, "TRY", ("K-SATIS-SATIR", "K-IADE")),
    "wholesale_sales_amount": Measure("LINENET", {8: 1}, "TRY", ("K-SATIS-SATIR", "K-IADE")),
    "sold_quantity": Measure("AMOUNT", {7: 1, 8: 1, 9: 1}, "quantity", ("G-C040",), sales_iocodes=(3, 4)),
    "net_quantity": Measure("AMOUNT", {7: 1, 8: 1, 9: 1, 2: -1, 3: -1}, "quantity", ("G-C040", "K-IADE"), sales_iocodes=(3, 4)),
}
# Fatura başlığı ölçüleri (satır değil belge).
HEADER_MEASURES = {
    "invoice_count": dict(trcodes=(7, 8, 9), agg="COUNT", unit="count", sources=("K-FATURA-SAYISI",)),
    "return_invoice_count": dict(trcodes=(2, 3), agg="COUNT", unit="count", sources=("K-FATURA-SAYISI",)),
    "invoice_amount": dict(trcodes=(7, 8, 9), agg="NETTOTAL", unit="TRY", sources=("G-A002",)),
}
# Tahsilat için karar ya da altın referans yok: tanım ürünle aynıdır, bağımsız değildir (envanterde böyle yazılır).
NON_INDEPENDENT = {"collections": "YOK"}

POPULATION = ("CANCELLED=0", "LINETYPE=0", "INVOICEREF<>0")  # K-SATIS-SATIR


def population_where(alias="S", trcodes=(2, 3, 7, 8, 9)):
    a = alias + "." if alias else ""
    return " AND ".join([a + p for p in POPULATION] + [f"{a}TRCODE IN ({','.join(map(str, sorted(trcodes)))})"])


def decision_measure_sql(name, alias="S"):
    """Karar işaret haritasından SQL ifadesi. Biçim bilerek ürünün CASE yazımından farklıdır (TRCODE başına dal)."""
    m = LOGO_MEASURES[name]
    a = alias + "." if alias else ""
    whens = []
    for code in sorted(m.signs):
        sign = m.signs[code]
        cond = f"{a}TRCODE={code}"
        if sign > 0 and m.sales_iocodes:
            cond += f" AND {a}IOCODE IN ({','.join(map(str, m.sales_iocodes))})"
        whens.append(f"WHEN {cond} THEN {'-' if sign < 0 else ''}{a}{m.column}")
    return "SUM(CASE " + " ".join(whens) + " ELSE 0 END)"


# ---------------------------------------------------------------------------
# Ürünün bugünkü tanımı: yalnız TANIM_FARKI sınıflaması için, METİN olarak okunur (import yok)
# ---------------------------------------------------------------------------
PRODUCT_ROOT = Path("/data/nanobaseai/bi/frontend/backend")


def product_metric_expressions(root=PRODUCT_ROOT):
    """Kurulu contracts.py içindeki METRICS ifadeleri; `ast` ile okunur, çalıştırılmaz."""
    path = Path(root) / "semantic_bridge/finance_query/contracts.py"
    tree = ast.parse(path.read_text())
    out = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "METRICS" for t in node.targets) \
                and isinstance(node.value, ast.Dict):
            for key, value in zip(node.value.keys, node.value.values):
                if isinstance(key, ast.Constant) and isinstance(value, ast.Call) and len(value.args) >= 4 \
                        and isinstance(value.args[3], ast.Constant):
                    out[key.value] = value.args[3].value
    if not out:
        raise RuntimeError("Ürün METRICS ifadeleri okunamadı; TANIM_FARKI sınıflaması yapılamaz")
    return out


def product_measure_sql(name, alias="S", root=PRODUCT_ROOT, _cache={}):
    key = str(root)
    if key not in _cache:
        _cache[key] = product_metric_expressions(root)
    expr = _cache[key].get(name)
    if expr is None:
        raise KeyError(f"Üründe {name} ölçüsü yok")
    return re.sub(r"\bf\.", (alias + ".") if alias else "", expr)


def measure_sql(name, alias="S", variant="decision"):
    return decision_measure_sql(name, alias) if variant == "decision" else product_measure_sql(name, alias)


def product_has(name):
    try:
        product_measure_sql(name)
        return True
    except Exception:
        return False


# Kırılımlar: kanal K-KANAL, kitap Logo ITEMS kodu ve adı, gün/ay satır tarihi.
DIMENSION_SQL = {
    "channel": dict(select=["C.SPECODE2 channel"], group=["C.SPECODE2"], order=["C.SPECODE2"],
                    join="LEFT JOIN dbo.LG_{firm}_CLCARD C WITH (NOLOCK) ON C.LOGICALREF=S.CLIENTREF"),
    "book": dict(select=["LTRIM(RTRIM(I.CODE)) book_code", "I.NAME book_name"], group=["I.CODE", "I.NAME"],
                 order=["I.CODE", "I.NAME"], join="LEFT JOIN dbo.LG_{firm}_ITEMS I WITH (NOLOCK) ON I.LOGICALREF=S.STOCKREF"),
    "day": dict(select=["CONVERT(varchar(10),S.DATE_,23) day"], group=["CONVERT(varchar(10),S.DATE_,23)"],
                order=["CONVERT(varchar(10),S.DATE_,23)"], join=""),
    "month": dict(select=["CONVERT(varchar(7),S.DATE_,23) month"], group=["CONVERT(varchar(7),S.DATE_,23)"],
                  order=["CONVERT(varchar(7),S.DATE_,23)"], join=""),
}


def sales_select(firm, start, end, metrics, dims=(), variant="decision", top=None, order_metric=None,
                 channel=None, extra_columns=(), require_trcodes=None):
    """Karar popülasyonu (K-SATIS-SATIR) üzerinde satış ölçüleri. Ürünün SQL kurucusu kullanılmaz.
    `require_trcodes`: kırılım satırı yalnız bu TRCODE'lardan en az bir satır varsa gelir (ör. yalnız iadesi olan kanal
    'satılan adet' listesine 0 ile girmez)."""
    if not re.fullmatch(r"\d{3}", str(firm)):
        raise ValueError("firma numarası")
    dims = list(dims)
    if channel is not None and "channel" not in dims:
        joins = [DIMENSION_SQL["channel"]["join"]]
    else:
        joins = []
    select, group, order = [], [], []
    for d in dims:
        spec = DIMENSION_SQL[d]
        select += spec["select"]; group += spec["group"]; order += spec["order"]
        if spec["join"] and spec["join"] not in joins:
            joins.append(spec["join"])
    select += list(extra_columns)
    select += [f"COALESCE({measure_sql(m, 'S', variant)},0) {m}" for m in metrics]
    sql = "SELECT " + (f"TOP ({int(top)}) " if top else "") + ",".join(select)
    sql += f" FROM dbo.LG_{firm}_01_STLINE S WITH (NOLOCK) " + " ".join(j.format(firm=firm) for j in joins)
    sql += f" WHERE {population_where('S')} AND S.DATE_>='{_ymd(start)}' AND S.DATE_<'{_ymd(end)}'"
    if channel is not None:
        sql += " AND C.SPECODE2=N'" + str(channel).replace("'", "''") + "'"
    if group:
        sql += " GROUP BY " + ",".join(group)
        if require_trcodes:
            sql += f" HAVING SUM(CASE WHEN S.TRCODE IN ({','.join(map(str, require_trcodes))}) THEN 1 ELSE 0 END)>0"
    if top:
        sql += f" ORDER BY {measure_sql(order_metric or metrics[0], 'S', variant)} DESC" + "".join("," + o + " DESC" for o in order)
    return sql


class CrossChecks:
    """İkinci yol uzlaşmalarını firma-dönem başına bir kez hesaplar. Gün düzeyi dönem içinde bulunduğu ay(lar)la
    denetlenir (tanım doğrulaması nüfus düzeyindedir, gün değil)."""

    def __init__(self, query, conn):
        self.query, self.conn, self.cache, self.errors = query, conn, {}, []

    @staticmethod
    def _months(start, end):
        from datetime import date
        a, b = date.fromisoformat(str(start)[:10]), date.fromisoformat(str(end)[:10])
        if (b - a).days >= 28:
            return [(a.isoformat(), b.isoformat())]
        first = date(a.year, a.month, 1)
        last = date(b.year + (b.month == 12), b.month % 12 + 1, 1) if b.day != 1 else b
        return [(first.isoformat(), last.isoformat())]

    def check(self, firm, start, end, dimension=None):
        out = []
        for a, b in self._months(start, end):
            key = (str(firm), a, b, dimension)
            if key not in self.cache:
                try:
                    sales = cross_check_sales(self.query, self.conn, firm, a, b, dimension)
                    invoices = cross_check_invoices(self.query, self.conn, firm, a, b)
                    versus = product_vs_decision(self.query, self.conn, firm, a, b)
                    self.cache[key] = dict(firm=str(firm), start=a, end=b, sales=sales, invoices=invoices, productVsDecision=versus)
                except Exception as exc:
                    self.cache[key] = dict(firm=str(firm), start=a, end=b, error=type(exc).__name__ + ": " + str(exc)[:300])
            out.append(self.cache[key])
        return out

    @staticmethod
    def summary(checks, metrics):
        """Bir vakanın kullandığı ölçüler için durum özeti: {ölçü: [durum,...]}, TANIM_FARKI ayrı listede."""
        status, definition = {}, {}
        for c in checks:
            if "error" in c:
                for m in metrics:
                    status.setdefault(m, []).append("IKINCI_YOL_HATA")
                continue
            for m in metrics:
                found = c["sales"]["measures"].get(m) or c["invoices"].get(m)
                status.setdefault(m, []).append(found["status"] if found else "IKINCI_YOL_YOK")
                pv = c["productVsDecision"].get(m) if isinstance(c.get("productVsDecision"), dict) else None
                if pv and pv.get("status") == "TANIM_FARKI":
                    definition[m] = jsonable(pv)
            if c["sales"].get("channel"):
                status.setdefault("channel", []).append(c["sales"]["channel"]["status"])
        return dict(status=status, definitionDifferences=definition,
                    reconciled=all(s in ("UZLASTI", "ACIKLANDI", "ACIKLANDI_TARIH", "YUVARLAMA") for v in status.values() for s in v))


# ---------------------------------------------------------------------------
# CRM etkin kayıt tanımı
# ---------------------------------------------------------------------------
def _entity(table):
    t = table.strip("[]").split(".")[-1]
    return t[:-4].lower() if t.lower().endswith("base") else t.lower()


def crm_active(table, alias, variant="decision", role="customer"):
    """`decision`: K-CRM-PASIF (statecode=0 ve durum nedeni etiketi Pasif/Inactive değil).
    `product`: ürünün bugünkü davranışı (executor.crm_status / crm_reports.rows / eski kabul): kitap, kişi ve
    marka için Aktif/Etkin etiketi (=1), müşteri için yalnız 'Aktif Müşteri' (100000000), diğerleri statecode=0.
    `product` yalnız TANIM_FARKI sınıflamasında kullanılır, beklenen değer olarak asla.
    Müşteri kartında karar K-CRM-MUSTERI'dir: yalnız 'Aktif Müşteri' etiketi (etiketten, kod sabiti yazılmadan).
    `role='party'`: sözleşme tarafı gibi müşteri olmayan kurum; genel K-CRM-PASIF kuralı."""
    entity = _entity(table)
    if variant == "product":
        if entity in ("new_kitap", "contact", "new_marka"):
            return f"{alias}.statecode=0 AND {alias}.statuscode=1"
        if entity == "account":
            return f"{alias}.statecode=0 AND {alias}.statuscode=100000000"
        return f"{alias}.statecode=0"
    if entity == "account" and variant == "decision" and role == "customer":
        customer = ("SELECT M.AttributeValue FROM dbo.StringMapBase M WITH (NOLOCK) JOIN dbo.EntityView E WITH (NOLOCK) "
                    "ON E.ObjectTypeCode=M.ObjectTypeCode WHERE M.AttributeName='statuscode' "
                    "AND LOWER(E.Name)='account' AND LTRIM(RTRIM(M.Value)) IN (N'Aktif Müşteri', N'Active Customer')")
        return f"{alias}.statecode=0 AND {alias}.statuscode IN ({customer})"
    passive = ("SELECT M.AttributeValue FROM dbo.StringMapBase M WITH (NOLOCK) JOIN dbo.EntityView E WITH (NOLOCK) "
               "ON E.ObjectTypeCode=M.ObjectTypeCode WHERE M.AttributeName='statuscode' "
               f"AND LOWER(E.Name)='{entity}' AND (LTRIM(M.Value) LIKE N'Pasif%' OR LTRIM(M.Value) LIKE N'Inactive%')")
    return f"{alias}.statecode=0 AND ({alias}.statuscode IS NULL OR {alias}.statuscode NOT IN ({passive}))"


CRM_STATUS_TABLES = ("new_kitapBase", "ContactBase", "AccountBase", "new_markaBase", "new_sozlesmeBase",
                     "new_eserkatilimBase", "new_isplaniBase", "new_projeBase", "new_sozlesmetarafiBase",
                     "new_katilimcitipiBase", "new_yaynevialtmarkaBase", "new_kitapgecmisiBase")


def crm_population_diff(query, conn, tables=CRM_STATUS_TABLES):
    """Tablo başına karar ve ürün etkin kayıt sayısı; fark varsa farkı oluşturan durum nedenleri."""
    out = {}
    for table in tables:
        try:
            row = query(conn, f"SELECT SUM(X.d) decision_count, SUM(X.p) product_count FROM (SELECT"
                              f" CASE WHEN {crm_active(table, 'T')} THEN 1 ELSE 0 END d,"
                              f" CASE WHEN {crm_active(table, 'T', 'product')} THEN 1 ELSE 0 END p"
                              f" FROM dbo.{table} T {NL}) X")[0]
        except Exception as exc:  # tablo yoksa ölçüm dışı
            out[table] = {"error": str(exc)[:200]}
            continue
        item = {"decision": int(row["decision_count"] or 0), "product": int(row["product_count"] or 0)}
        if item["decision"] != item["product"]:
            item["differingStatus"] = query(conn, f"SELECT X.statecode, X.statuscode, COUNT_BIG(*) n,"
                f" MAX(X.d) in_decision, MAX(X.p) in_product FROM (SELECT T.statecode, T.statuscode,"
                f" CASE WHEN {crm_active(table, 'T')} THEN 1 ELSE 0 END d,"
                f" CASE WHEN {crm_active(table, 'T', 'product')} THEN 1 ELSE 0 END p"
                f" FROM dbo.{table} T {NL}) X WHERE X.d=1 OR X.p=1 GROUP BY X.statecode, X.statuscode")
            item["differingStatus"] = [r for r in item["differingStatus"] if r["in_decision"] != r["in_product"]]
        item["status"] = "AYNI" if item["decision"] == item["product"] else "TANIM_FARKI"
        out[table] = item
    return out


# ---------------------------------------------------------------------------
# İkinci yol: satış satırı ↔ TİMAŞ satış raporu görünümü ↔ fatura başlığı
# ---------------------------------------------------------------------------
VIEW_TYPES = {"Perakende Satış Faturası": 7, "Toptan Satış Faturası": 8,
              "Perakende Satış İade Faturası": 2, "Toptan Satış İade Faturası": 3}
D = lambda v: Decimal(str(v or 0))


def _ymd(day):
    return str(day).replace("-", "")


def _measure_value(m, by, sign_filter=None):
    total = Decimal(0)
    for code, sign in m.signs.items():
        r = by.get(code)
        if not r or (sign_filter and sign not in sign_filter):
            continue
        value = D(r["amount_out"]) if (sign > 0 and m.sales_iocodes and m.column == "AMOUNT") else D(r[m.column.lower()])
        total += sign * value
    return total


def cross_check_sales(query, conn, firm, start, end, dimension=None):
    """Bir firma-dönem için satış ölçülerinin karar değeri + ikinci yol uzlaşması.

    İkinci yol TİMAŞ'ın kendi satış raporu görünümüdür (V_SatisRaporu_<firma>, malzeme satırları). Görünüm dönemi
    fatura tarihine, karar referansı satır tarihine (STLINE.DATE_) bakar; tutarı VATMATRAH'tır, karar LINENET.
    Uzlaşma durumları:
      UZLASTI          |Δ| <= 0,01 ve satır kümesi birebir
      ACIKLANDI        satır kümesi birebir; Δ yalnız LINENET−VATMATRAH sütun farkı (ayrıca raporlanır)
      ACIKLANDI_TARIH  fatura tarihine göre satır kümesi birebir; Δ = satır/fatura tarihi farkı + sütun farkı
      UZLASMADI        yukarıdakilerin hiçbiri; IKINCI_YOL_YOK görünüm okunamadı."""
    if not re.fullmatch(r"\d{3}", str(firm)):
        raise ValueError("firma numarası")
    s, e = _ymd(start), _ymd(end)
    cols = (" COUNT_BIG(*) n, SUM(S.LINENET) linenet, SUM(S.VATMATRAH) vatmatrah, SUM(S.AMOUNT) amount,"
            " SUM(CASE WHEN S.IOCODE IN (3,4) THEN S.AMOUNT ELSE 0 END) amount_out")
    lines = query(conn, f"SELECT S.TRCODE trcode,{cols} FROM dbo.LG_{firm}_01_STLINE S {NL} WHERE {population_where('S')}"
                        f" AND S.DATE_>='{s}' AND S.DATE_<'{e}' GROUP BY S.TRCODE")
    by = {int(r["trcode"]): r for r in lines}
    decision = {name: _measure_value(m, by) for name, m in LOGO_MEASURES.items()}
    view = None
    try:
        view_rows = query(conn, f"SELECT V.[Fatura Türü] ftype, COUNT_BIG(*) n, COUNT(DISTINCT V.[Fatura No]) invoices,"
                                f" SUM(V.Miktar) qty, SUM(V.[Net Tutar]) net FROM dbo.V_SatisRaporu_{firm} V {NL}"
                                f" WHERE V.[Fatura Tarihi]>='{s}' AND V.[Fatura Tarihi]<'{e}' AND V.[Satır Türü]=N'Malzeme'"
                                f" GROUP BY V.[Fatura Türü]")
        view, unmapped = {}, []
        for r in view_rows:
            code = VIEW_TYPES.get(r["ftype"])
            if code is None:
                unmapped.append(r)
            else:
                view[code] = r
        header_lines = query(conn, f"SELECT S.TRCODE trcode,{cols} FROM dbo.LG_{firm}_01_STLINE S {NL}"
                                   f" JOIN dbo.LG_{firm}_01_INVOICE I {NL} ON I.LOGICALREF=S.INVOICEREF"
                                   f" WHERE {population_where('S')} AND I.DATE_>='{s}' AND I.DATE_<'{e}' GROUP BY S.TRCODE")
        hby = {int(r["trcode"]): r for r in header_lines}
    except Exception as exc:
        view, view_error = None, str(exc)[:300]
    checks = {}
    if view is not None:
        population = {}
        for code in (2, 3, 7, 8):
            a, h, b = by.get(code, {}), hby.get(code, {}), view.get(code, {})
            p = dict(lines=int(a.get("n") or 0), headerDateLines=int(h.get("n") or 0), viewLines=int(b.get("n") or 0),
                     quantity=D(a.get("amount")), headerDateQuantity=D(h.get("amount")), viewQuantity=abs(D(b.get("qty"))),
                     vatmatrah=D(a.get("vatmatrah")), headerDateVatmatrah=D(h.get("vatmatrah")), viewNet=abs(D(b.get("net"))),
                     linenetMinusVatmatrah=D(h.get("linenet")) - D(h.get("vatmatrah")))
            p["sameRows"] = p["lines"] == p["viewLines"] and p["quantity"] == p["viewQuantity"] \
                and abs(p["vatmatrah"] - p["viewNet"]) <= MONEY_TOLERANCE
            p["sameRowsByInvoiceDate"] = p["headerDateLines"] == p["viewLines"] and p["headerDateQuantity"] == p["viewQuantity"] \
                and abs(p["headerDateVatmatrah"] - p["viewNet"]) <= MONEY_TOLERANCE
            population[code] = p
        nine = by.get(9) or hby.get(9)
        for name, m in LOGO_MEASURES.items():
            if m.column == "LINENET":
                second = sum(sign * population[c]["viewNet"] for c, sign in m.signs.items() if c in population)
                column_bridge = sum(sign * population[c]["linenetMinusVatmatrah"] for c, sign in m.signs.items() if c in population)
            else:
                second = sum(sign * population[c]["viewQuantity"] for c, sign in m.signs.items() if c in population)
                # altın C040 satışta IOCODE 3/4 ister; görünüm miktarı IOCODE süzmez
                column_bridge = -sum(sign * (D(hby.get(c, {}).get("amount")) - D(hby.get(c, {}).get("amount_out")))
                                     for c, sign in m.signs.items() if sign > 0 and m.sales_iocodes and c in hby)
            date_bridge = decision[name] - _measure_value(m, hby)
            delta = decision[name] - second
            codes = [c for c in m.signs if c in population]
            exact_rows = all(population[c]["sameRows"] for c in codes)
            invoice_rows = all(population[c]["sameRowsByInvoiceDate"] for c in codes)
            if nine and D(nine.get(m.column.lower())) and 9 in m.signs:
                exact_rows = invoice_rows = False  # görünüm hizmet faturasını (9) içermez
            residual = delta - date_bridge - column_bridge
            if abs(delta) <= MONEY_TOLERANCE and exact_rows:
                status = "UZLASTI"
            elif invoice_rows and abs(residual) <= MONEY_TOLERANCE:
                status = "ACIKLANDI" if abs(date_bridge) <= MONEY_TOLERANCE and exact_rows else "ACIKLANDI_TARIH"
            else:
                status = "UZLASMADI"
            checks[name] = dict(decision=decision[name], secondPath=second, delta=delta, columnBridge=column_bridge,
                                dateBridge=date_bridge, residual=residual, status=status,
                                secondPathName=f"V_SatisRaporu_{firm} [Net Tutar]/[Miktar] (Satır Türü=Malzeme)")
        result = dict(population=population, unmappedViewTypes=unmapped)
    else:
        result = dict(viewError=view_error)
        for name in LOGO_MEASURES:
            checks[name] = dict(decision=decision[name], status="IKINCI_YOL_YOK", secondPathName=f"V_SatisRaporu_{firm}")
    result.update(firm=firm, start=start, end=end, measures=checks)
    if dimension == "channel" and view is not None:
        result["channel"] = cross_check_channel(query, conn, firm, s, e)
    return result


def cross_check_channel(query, conn, firm, s, e):
    """Kanal kırılımı: CLCARD.SPECODE2 (K-KANAL) ↔ görünümün KANAL sütunu. Görünümle aynı ölçekte karşılaştırılır:
    VATMATRAH (görünüm Net Tutar) ve fatura tarihi; satır/fatura tarihi ve LINENET farkı cross_check_sales'ta ayrıca ölçülür."""
    ours = query(conn, f"SELECT C.SPECODE2 channel, SUM(CASE WHEN S.TRCODE IN (2,3) THEN -S.VATMATRAH ELSE S.VATMATRAH END) net,"
                       f" COUNT_BIG(*) n FROM dbo.LG_{firm}_01_STLINE S {NL} JOIN dbo.LG_{firm}_01_INVOICE I {NL}"
                       f" ON I.LOGICALREF=S.INVOICEREF LEFT JOIN dbo.LG_{firm}_CLCARD C {NL}"
                       f" ON C.LOGICALREF=S.CLIENTREF WHERE {population_where('S', (2, 3, 7, 8))}"
                       f" AND I.DATE_>='{s}' AND I.DATE_<'{e}' GROUP BY C.SPECODE2")
    theirs = query(conn, f"SELECT V.KANAL channel, SUM(V.[Net Tutar]) net, COUNT_BIG(*) n FROM dbo.V_SatisRaporu_{firm} V {NL}"
                         f" WHERE V.[Fatura Tarihi]>='{s}' AND V.[Fatura Tarihi]<'{e}' AND V.[Satır Türü]=N'Malzeme'"
                         f" GROUP BY V.KANAL")
    norm = lambda v: (str(v).strip() if v is not None and str(v).strip() else None)
    a = defaultdict(lambda: [Decimal(0), 0]); b = defaultdict(lambda: [Decimal(0), 0])
    for r in ours:
        a[norm(r["channel"])][0] += D(r["net"]); a[norm(r["channel"])][1] += int(r["n"])
    for r in theirs:
        b[norm(r["channel"])][0] += D(r["net"]); b[norm(r["channel"])][1] += int(r["n"])
    diffs = {str(k): dict(ours=a[k][0], view=b[k][0], oursLines=a[k][1], viewLines=b[k][1])
             for k in set(a) | set(b) if abs(a[k][0] - b[k][0]) > MONEY_TOLERANCE or a[k][1] != b[k][1]}
    return dict(status="UZLASTI" if not diffs else "UZLASMADI", channels=len(set(a) | set(b)), differences=diffs)


def cross_check_invoices(query, conn, firm, start, end):
    """Fatura başlık ölçüleri: karar (INVOICE) ↔ ikinci yol.
    invoice_count: başlık sayısı = görünümde malzeme satırı olan farklı fatura + malzeme satırı olmayan başlık.
    invoice_amount: Σ NETTOTAL = Σ (satır VATMATRAH + VATAMNT), aynı başlıkların iptal olmayan bütün satırları."""
    s, e = _ymd(start), _ymd(end)
    head = query(conn, f"SELECT H.trcode, COUNT_BIG(*) n, SUM(H.nettotal) nettotal, SUM(H.without_material) without_material"
                       f" FROM (SELECT I.TRCODE trcode, I.NETTOTAL nettotal,"
                       f" CASE WHEN NOT EXISTS (SELECT 1 FROM dbo.LG_{firm}_01_STLINE L {NL} WHERE L.INVOICEREF=I.LOGICALREF"
                       f" AND L.CANCELLED=0 AND L.LINETYPE=0) THEN 1 ELSE 0 END without_material"
                       f" FROM dbo.LG_{firm}_01_INVOICE I {NL} WHERE I.CANCELLED=0 AND I.TRCODE IN (2,3,7,8,9)"
                       f" AND I.DATE_>='{s}' AND I.DATE_<'{e}') H GROUP BY H.trcode")
    lines = query(conn, f"SELECT X.trcode, SUM(X.lt) line_total, SUM(CASE WHEN ABS(X.nt-X.lt)>0.005 THEN 1 ELSE 0 END) diff_n,"
                        f" MAX(ABS(X.nt-X.lt)) max_diff FROM (SELECT I.LOGICALREF ref, I.TRCODE trcode, MAX(I.NETTOTAL) nt,"
                        f" COALESCE(SUM(L.VATMATRAH+L.VATAMNT),0) lt FROM dbo.LG_{firm}_01_INVOICE I {NL}"
                        f" LEFT JOIN dbo.LG_{firm}_01_STLINE L {NL} ON L.INVOICEREF=I.LOGICALREF AND L.CANCELLED=0"
                        f" WHERE I.CANCELLED=0 AND I.TRCODE IN (2,3,7,8,9) AND I.DATE_>='{s}' AND I.DATE_<'{e}'"
                        f" GROUP BY I.LOGICALREF, I.TRCODE) X GROUP BY X.trcode")
    view = {}
    try:
        for r in query(conn, f"SELECT V.[Fatura Türü] ftype, COUNT(DISTINCT V.[Fatura No]) invoices FROM dbo.V_SatisRaporu_{firm} V {NL}"
                             f" WHERE V.[Fatura Tarihi]>='{s}' AND V.[Fatura Tarihi]<'{e}' AND V.[Satır Türü]=N'Malzeme'"
                             f" GROUP BY V.[Fatura Türü]"):
            if r["ftype"] in VIEW_TYPES:
                view[VIEW_TYPES[r["ftype"]]] = int(r["invoices"])
        view_ok = True
    except Exception:
        view_ok = False
    h = {int(r["trcode"]): r for r in head}
    lt = {int(r["trcode"]): D(r["line_total"]) for r in lines}
    per_invoice = {int(r["trcode"]): (int(r["diff_n"] or 0), D(r["max_diff"])) for r in lines}
    out = {}
    for name, spec in HEADER_MEASURES.items():
        codes = spec["trcodes"]
        if spec["agg"] == "COUNT":
            decision = sum(int(h[c]["n"]) for c in codes if c in h)
            if view_ok:
                second = sum(view.get(c, 0) + int(h[c]["without_material"]) for c in codes if c in h)
                status = "UZLASTI" if second == decision else "UZLASMADI"
            else:
                second, status = None, "IKINCI_YOL_YOK"
            out[name] = dict(decision=decision, secondPath=second, status=status,
                             secondPathName="görünümde malzeme satırlı farklı fatura no + malzeme satırsız başlık",
                             byTrcode={c: int(h[c]["n"]) for c in codes if c in h})
        else:
            decision = sum(D(h[c]["nettotal"]) for c in codes if c in h)
            second = sum(lt.get(c, Decimal(0)) for c in codes if c in h)
            diff_n = sum(per_invoice.get(c, (0, 0))[0] for c in codes)
            max_diff = max([per_invoice.get(c, (0, Decimal(0)))[1] for c in codes] or [Decimal(0)])
            status = "UZLASTI" if abs(decision - second) <= MONEY_TOLERANCE else \
                "YUVARLAMA" if max_diff <= ROUNDING_PER_INVOICE else "UZLASMADI"
            out[name] = dict(decision=decision, secondPath=second, delta=decision - second, status=status,
                             invoicesWithDifference=diff_n, maxInvoiceDifference=max_diff,
                             secondPathName="Σ STLINE (VATMATRAH+VATAMNT) aynı başlıklar, iptal olmayan bütün satır türleri")
    out["firm"], out["start"], out["end"] = firm, start, end
    return out


def product_vs_decision(query, conn, firm, start, end, root=PRODUCT_ROOT):
    """Ürün ifadesi (kurulu contracts.py metni) ile karar ifadesi aynı satır kümesinde aynı sayıyı veriyor mu."""
    s, e = _ymd(start), _ymd(end)
    out = {}
    try:
        product = product_metric_expressions(root)
    except Exception as exc:
        return {"error": str(exc)[:200]}
    names = [n for n in LOGO_MEASURES if n in product]
    cols = ",".join(f"{decision_measure_sql(n)} [d_{n}],{product_measure_sql(n, root=root)} [p_{n}]" for n in names)
    row = query(conn, f"SELECT {cols} FROM dbo.LG_{firm}_01_STLINE S {NL} WHERE {population_where('S')}"
                      f" AND S.DATE_>='{s}' AND S.DATE_<'{e}'")[0]
    for n in names:
        d, p = D(row[f"d_{n}"]), D(row[f"p_{n}"])
        tol = MONEY_TOLERANCE if LOGO_MEASURES[n].unit == "TRY" else Decimal(0)
        out[n] = dict(decision=d, product=p, delta=d - p, status="AYNI" if abs(d - p) <= tol else "TANIM_FARKI",
                      decisionSources=list(LOGO_MEASURES[n].sources))
    return out


# ---------------------------------------------------------------------------
# Kabul betiklerinin ortak sınıflaması
# ---------------------------------------------------------------------------
def classify(decision_errors, product_errors):
    """PASS: karar referansı tutuyor. TANIM_FARKI: karar tutmuyor, ürün tanımıyla referans tutuyor. FAIL: ikisi de tutmuyor."""
    if not decision_errors:
        return "PASS"
    if product_errors is not None and not product_errors:
        return "TANIM_FARKI"
    return "FAIL"


def jsonable(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    return value


def main():
    """Canlı öz-denetim: yalnız referans sorgularını koşar, API'ye istek göndermez."""
    p = argparse.ArgumentParser()
    p.add_argument("--firm", default="411")
    p.add_argument("--start", default="2026-09-01")
    p.add_argument("--end", default="2026-10-01")
    p.add_argument("--crm", action="store_true", help="CRM etkin kayıt karar/ürün farkını da ölç")
    p.add_argument("--channel", action="store_true")
    a = p.parse_args()
    if sys.platform != "linux":
        raise SystemExit("Yalnız test sunucusunda")
    sys.path.insert(0, str(Path(__file__).parent))
    from composable_live import connect, query
    logo = connect("/data/nanobaseai/bi/secrets/logo-mssql-connection.json")
    report = {"sources": SOURCES,
              "sales": cross_check_sales(query, logo, a.firm, a.start, a.end, "channel" if a.channel else None),
              "invoices": cross_check_invoices(query, logo, a.firm, a.start, a.end),
              "productVsDecision": product_vs_decision(query, logo, a.firm, a.start, a.end)}
    if a.crm:
        crm = connect("/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
        report["crmActive"] = crm_population_diff(query, crm)
    print(json.dumps(jsonable(report), ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
