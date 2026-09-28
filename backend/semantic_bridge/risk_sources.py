"""M47 Risk göstergeleri (KRI): hesapçılar ve hazır tanım kütüphanesi (yalnız okuma).

Her gösterge = (kod, hesapçı). Hesapçı `Context` alır, `{deger, veri_son_gunu, kanit}` döner; değer okunamazsa
`SourceError` atar (ölçüm «ölçülemedi» yazılır, önceki kırmızı bozulmaz). Kaynak iki türlüdür:

- **sql** — doğrudan Logo/CRM sorgusu (`budget_sources.runner`, salt okunur bağlantı). Tanımlar mevcut ölçülerle
  aynıdır: faturalı satış satırı `STLINE` (`LINETYPE 0`, `INVOICEREF <> 0`, `CANCELLED 0`), net ciro fatura başlığında
  `INVOICE.NETTOTAL` (satış 7/8/9 artı, iade 2/3 eksi — sertifikalı `net_ciro`), karşılıksız çek olayı `CSTRANS.STATUS = 11`
  (`DEVIR 0`, `CANCELLED 0`, hareket tarihi; tutar `CSCARD.AMOUNT` çek başına bir kez — Kural 12), vadesi geçmiş alacak
  FIFO yaklaşımı (Logo'da ödeme kapama yok; bilgi paketi `vadesi-gecmis-yaslandirma-fifo`, «bugün» yerine veri son günü).
  Yıl → firma `L_CAPIPERIOD`'dan (`firms_by_year`); güncel yıl en büyük yıldır.
- **modul** — köprü içi modülün hazır sonucu; Logo'ya yeni sorgu gitmez: finansal denetimin son tamamlanan raporu
  (`app.state.financial_audit.load()`), Baskı önerisi önbelleği (`app.state.management_reports.read("baski-oneri")`),
  M46 açık sapma uyarıları (`budget.deviations`).

Logo kopyası dondurulmuş olabilir (bugün 17.08.2026). «Son N gün» pencereleri bu yüzden **veri son gününe** göre
kurulur ve her değerin yanında `veri_son_gunu` yazılır; veri gecikmesinin kendisi ayrı göstergedir.

Ölçülmemiş varsayımlar ayardır (kabul listesinde «ölçülecek»): `RISK_CHEQUE_DOCS` (müşteri çeki/senedi `CSCARD.DOC`
kodları, varsayılan 1,2 — M30 ile aynı), `RISK_LOCAL_CURRENCY_CODES` (yerel para `TRCURR` kodları, varsayılan 0,160),
`RISK_RECEIVABLE_PREFIX` (müşteri cari kodu öneki, varsayılan 120), `RISK_KVKK_CONSENT_COLUMN` /
`RISK_KVKK_DATE_COLUMN` (CRM `AccountBase` bayi başvurusu KVKK izni ve tarihi kolon adları),
`RISK_EXPIRED_SALES_DAYS` (süresi bitmiş sözleşmeli kitapta satış penceresi, varsayılan 30).
"""
from __future__ import annotations

import logging
import os
import re
import time
from datetime import date, datetime
from typing import Any, Callable, Iterable, Optional

from semantic_bridge import budget_sources as bsrc

log = logging.getLogger("semantic.risk.sources")

SourceError = bsrc.SourceError
Runner = bsrc.Runner
runner = bsrc.runner
firms_by_year = bsrc.firms_by_year
CHUNK = 800
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,127}$")


def _conf(key: str, default: str) -> str:
    try:
        from semantic_bridge import admin as admin_mod
        v = admin_mod.conf(key)
    except Exception:  # noqa: BLE001
        v = ""
    return v if v not in (None, "") else os.environ.get(key, default)


def _codes(key: str, default: str) -> list[int]:
    out = [int(x) for x in re.findall(r"\d+", _conf(key, default))]
    if not out:
        raise SourceError(f"{key} ayarı boş.")
    return out


def _ident(key: str, default: str) -> str:
    v = _conf(key, default).strip()
    if not _IDENT.match(v):
        raise SourceError(f"{key} geçerli bir kolon adı değil.")
    return v


def q(v: str) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def _num(v: Any) -> Optional[float]:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def _day(v: Any) -> Optional[date]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v)[:19]).date()
    except ValueError:
        return None


# ------------------------------------------------------------------ bağlam


class Context:
    """Bir ölçüm turunun bağlamı: bağlantılar tembel açılır, aynı turda ortak ara sonuçlar bir kez okunur."""

    def __init__(self, *, logo_file: Callable[[], str], crm_file: Callable[[], str], crm_schema: Callable[[], str],
                 app_state: Any = None, engine: Any = None, tenant: str = "", asof: Optional[date] = None):
        self._logo_file, self._crm_file, self._schema = logo_file, crm_file, crm_schema
        self.state = app_state
        self.engine = engine
        self.tenant = tenant
        self.asof = asof or date.today()
        self._cache: dict[str, Any] = {}
        # Sorgu bilgisi: çalışan her SQL (bağlantı, metin, satır, süre). Aynı turda paylaşılan ara sonucun sorgusu
        # (ör. firma, son fatura günü, cari cirosu) onu kullanan her göstergeye de yazılır.
        self.touched: list[dict[str, Any]] = []
        self._by_key: dict[str, list[dict[str, Any]]] = {}

    def once(self, key: str, load: Callable[[], Any]) -> Any:
        if key not in self._cache:
            before = len(self.touched)
            self._cache[key] = load()
            self._by_key[key] = self.touched[before:]
        else:
            self.touched.extend(self._by_key.get(key, []))
        return self._cache[key]

    def _logged(self, conn: str, run: Runner) -> Runner:
        def wrapped(sql: str) -> list[dict[str, Any]]:
            t = time.monotonic()
            rows = run(sql)
            self.touched.append({"conn": conn, "sql": sql, "rows": len(rows), "dbMs": int((time.monotonic() - t) * 1000),
                                 "at": datetime.now().isoformat(timespec="seconds")})
            return rows
        return wrapped

    def logo(self) -> Runner:
        return self.once("logo", lambda: self._logged("logo", runner(self._logo_file())))

    def crm(self) -> Runner:
        return self.once("crm", lambda: self._logged("crm", runner(self._crm_file())))

    def schema(self) -> str:
        s = (self._schema() or "").strip()
        if not s:
            raise SourceError("CRM şeması tanımlı değil.")
        db, _, sch = s.rpartition(".")
        for part in (db, sch):
            if part and not _IDENT.match(part):
                raise SourceError("CRM şeması geçerli bir ad değil.")
        return s

    def firm(self) -> tuple[str, int]:
        def load() -> tuple[str, int]:
            firms = firms_by_year(self.logo())
            if not firms:
                raise SourceError("Logo'da dönem tanımı okunamadı.")
            y = max(firms)
            return firms[y], y
        return self.once("firm", load)

    def logo_last_day(self) -> date:
        """Logo'daki son (iptal edilmemiş) fatura günü: «son N gün» pencerelerinin çapası."""
        def load() -> date:
            f, _ = self.firm()
            rows = self.logo()(f"SELECT MAX(DATE_) AS son FROM dbo.LG_{f}_01_INVOICE WHERE CANCELLED = 0")
            d = _day(rows[0]["son"]) if rows else None
            if d is None:
                raise SourceError("Logo'da fatura bulunamadı.")
            return d
        return self.once("logo_last", load)


# ------------------------------------------------------------------ SQL (kabul betikleri de aynı metni kullanmaz; bağımsız yazılır)


def cost_last_sql(f: str) -> str:
    return (f"SELECT MAX(DATE_) AS son FROM dbo.LG_{f}_01_STLINE WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 "
            f"AND TRCODE IN (7,8) AND OUTCOST <> 0")


def costless_share_sql(f: str) -> str:
    """M45 kabul 4 ile aynı kapsam: faturalı satış satırı TRCODE 7/8; maliyetli = OUTCOST ≠ 0."""
    return (f"SELECT SUM(CASE WHEN OUTCOST <> 0 THEN LINENET ELSE 0 END) AS maliyetli, SUM(LINENET) AS toplam, "
            f"SUM(CASE WHEN OUTCOST <> 0 THEN 0 ELSE 1 END) AS maliyetsiz_satir, COUNT(*) AS satir "
            f"FROM dbo.LG_{f}_01_STLINE WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (7,8)")


def customer_net_sql(f: str, year: int) -> str:
    """Cari başına net ciro (fatura başlığı): satış 7/8/9 artı, iade 2/3 eksi — sertifikalı net_ciro."""
    return f"""
SELECT I.CLIENTREF AS ref, C.CODE AS kod, C.DEFINITION_ AS unvan,
  SUM(CASE WHEN I.TRCODE IN (7,8,9) THEN I.NETTOTAL ELSE -I.NETTOTAL END) AS n
FROM dbo.LG_{f}_01_INVOICE AS I
LEFT JOIN dbo.LG_{f}_CLCARD AS C ON C.LOGICALREF = I.CLIENTREF
WHERE I.CANCELLED = 0 AND I.TRCODE IN (2,3,7,8,9) AND I.DATE_ >= '{year}-01-01' AND I.DATE_ < '{year + 1}-01-01'
GROUP BY I.CLIENTREF, C.CODE, C.DEFINITION_""".strip()


def supplier_net_sql(f: str, year: int) -> str:
    """Tedarikçi başına alış (mal alım 1, alınan hizmet 4) fatura net tutarı."""
    return f"""
SELECT I.CLIENTREF AS ref, C.CODE AS kod, C.DEFINITION_ AS unvan, SUM(I.NETTOTAL) AS n
FROM dbo.LG_{f}_01_INVOICE AS I
LEFT JOIN dbo.LG_{f}_CLCARD AS C ON C.LOGICALREF = I.CLIENTREF
WHERE I.CANCELLED = 0 AND I.TRCODE IN (1,4) AND I.DATE_ >= '{year}-01-01' AND I.DATE_ < '{year + 1}-01-01'
GROUP BY I.CLIENTREF, C.CODE, C.DEFINITION_""".strip()


def overdue_fifo_sql(f: str, year: int, asof: date, prefix: str) -> str:
    """Bilgi paketi FIFO yaşlandırması, fiziksel tablolarla ve «bugün» yerine veri son günüyle."""
    d = asof.isoformat()
    return f"""
WITH B AS (SELECT L.CLIENTREF, SUM(CASE WHEN L.SIGN = 0 THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye
  FROM dbo.LG_{f}_01_CLFLINE L JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = L.CLIENTREF
  WHERE L.CANCELLED = 0 AND C.CODE LIKE {q(prefix + '%')} AND L.DATE_ >= '{year}-01-01' AND L.DATE_ <= '{d}'
  GROUP BY L.CLIENTREF),
P AS (SELECT P.CARDREF, P.DATE_, P.TOTAL,
    SUM(P.TOTAL) OVER (PARTITION BY P.CARDREF ORDER BY P.DATE_ DESC, P.LOGICALREF DESC ROWS UNBOUNDED PRECEDING) AS kumulatif
  FROM dbo.LG_{f}_01_PAYTRANS P WHERE P.CANCELLED = 0 AND P.SIGN = 0 AND P.CARDREF IN (SELECT CLIENTREF FROM B WHERE bakiye > 0)),
A AS (SELECT P.CARDREF, P.DATE_,
    CASE WHEN B.bakiye >= P.kumulatif THEN P.TOTAL WHEN B.bakiye > P.kumulatif - P.TOTAL THEN B.bakiye - (P.kumulatif - P.TOTAL) ELSE 0 END AS acik
  FROM P JOIN B ON B.CLIENTREF = P.CARDREF)
SELECT kova, SUM(acik) AS tutar, COUNT(DISTINCT CARDREF) AS cari_sayisi FROM (
  SELECT A.CARDREF, A.acik, CASE WHEN DATEDIFF(day, A.DATE_, '{d}') <= 0 THEN '0 vadesi gelmemiş'
    WHEN DATEDIFF(day, A.DATE_, '{d}') <= 30 THEN '1 1-30 gün'
    WHEN DATEDIFF(day, A.DATE_, '{d}') <= 60 THEN '2 31-60 gün'
    WHEN DATEDIFF(day, A.DATE_, '{d}') <= 90 THEN '3 61-90 gün' ELSE '4 90+ gün' END AS kova
  FROM A WHERE A.acik > 0) x GROUP BY kova ORDER BY kova""".strip()


def bounced_cheque_sql(f: str, year: int, docs: list[int]) -> str:
    """Kural 12: yıl içinde karşılıksız düşen çek (olay), tutar kart başına bir kez."""
    return f"""
SELECT COUNT(*) AS adet, SUM(K.AMOUNT) AS tutar
FROM dbo.LG_{f}_01_CSCARD AS K
WHERE K.CANCELLED = 0 AND K.DOC IN ({', '.join(str(d) for d in docs)})
  AND EXISTS (SELECT 1 FROM dbo.LG_{f}_01_CSTRANS AS T WHERE T.CSREF = K.LOGICALREF AND T.STATUS = 11
              AND T.DEVIR = 0 AND T.CANCELLED = 0 AND T.DATE_ >= '{year}-01-01' AND T.DATE_ < '{year + 1}-01-01')""".strip()


def fx_invoice_sql(f: str, local: list[int]) -> str:
    return (f"SELECT TRCURR AS doviz, COUNT(*) AS adet, SUM(NETTOTAL) AS tl FROM dbo.LG_{f}_01_INVOICE "
            f"WHERE CANCELLED = 0 AND TRCURR NOT IN ({', '.join(str(c) for c in local)}) GROUP BY TRCURR")


def expired_contract_books_sql(schema: str) -> str:
    """Süresi bitmiş, süresiz olmayan etkin telif alış sözleşmesine bağlı kitaplar; kitabın yürürlükte (süresiz ya da
    bitişi bugün/sonra) başka bir telif alış sözleşmesi varsa kitap listeye girmez."""
    p = schema + "."
    return f"""
SELECT k.new_StokKodu AS stok, k.new_name AS ad, s.new_SozlesmeKodu AS sozlesme, s.new_SozlesmeBitisTarihi AS bitis
FROM {p}new_sozlesmeBase s
JOIN {p}new_new_sozlesme_new_kitapBase sk ON sk.new_sozlesmeid = s.new_sozlesmeId
JOIN {p}new_kitapBase k ON k.new_kitapId = sk.new_kitapid
WHERE s.statecode = 0 AND s.new_SozlesmeTipi = 5 AND ISNULL(s.new_suresizsozlesme, 0) = 0
  AND s.new_SozlesmeBitisTarihi < CAST(GETDATE() AS date) AND k.new_StokKodu IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM {p}new_new_sozlesme_new_kitapBase sk2
    JOIN {p}new_sozlesmeBase s2 ON s2.new_sozlesmeId = sk2.new_sozlesmeid
    WHERE sk2.new_kitapid = sk.new_kitapid AND s2.statecode = 0 AND s2.new_SozlesmeTipi = 5
      AND (ISNULL(s2.new_suresizsozlesme, 0) = 1 OR s2.new_SozlesmeBitisTarihi >= CAST(GETDATE() AS date)))""".strip()


def recent_sales_sql(f: str, codes: list[str], last: date, days: int) -> str:
    return f"""
SELECT I.CODE AS stok, SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.AMOUNT ELSE 0 END) AS adet
FROM dbo.LG_{f}_01_STLINE AS L JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = L.STOCKREF
WHERE L.CANCELLED = 0 AND L.LINETYPE = 0 AND L.INVOICEREF <> 0 AND L.TRCODE IN (7,8,9)
  AND L.DATE_ > DATEADD(day, -{int(days)}, '{last.isoformat()}') AND L.DATE_ <= '{last.isoformat()}'
  AND I.CODE IN ({', '.join(q(c) for c in codes)})
GROUP BY I.CODE HAVING SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.AMOUNT ELSE 0 END) > 0""".strip()


def kvkk_sql(schema: str, consent: str, when: str) -> str:
    return (f"SELECT COUNT(*) AS n, SUM(CASE WHEN {consent} = 1 THEN 1 ELSE 0 END) AS izinli "
            f"FROM {schema}.AccountBase WHERE statecode = 0 AND {consent} = 1 AND {when} IS NULL")


# ------------------------------------------------------------------ hesapçılar


def _out(v: Optional[float], last: Optional[date], kanit: dict[str, Any]) -> dict[str, Any]:
    return {"deger": v, "veri_son_gunu": last.isoformat() if last else None, "kanit": kanit}


def k_data_delay(ctx: Context) -> dict[str, Any]:
    last = ctx.logo_last_day()
    f, y = ctx.firm()
    return _out(float((ctx.asof - last).days), last, {"sonFatura": last.isoformat(), "firma": f, "yil": y, "bugun": ctx.asof.isoformat()})


def k_cost_delay(ctx: Context) -> dict[str, Any]:
    f, y = ctx.firm()
    last = ctx.logo_last_day()
    rows = ctx.logo()(cost_last_sql(f))
    c = _day(rows[0]["son"]) if rows else None
    if c is None:
        raise SourceError("Maliyeti girilmiş satış satırı yok.")
    return _out(float((last - c).days), last, {"sonMaliyetliSatir": c.isoformat(), "sonFatura": last.isoformat(), "firma": f, "yil": y})


def k_costless_share(ctx: Context) -> dict[str, Any]:
    f, y = ctx.firm()
    r = (ctx.logo()(costless_share_sql(f)) or [{}])[0]
    tot, cost = _num(r.get("toplam")), _num(r.get("maliyetli")) or 0.0
    if not tot:
        raise SourceError("Faturalı satış satırı yok.")
    return _out(round((1 - cost / tot) * 100, 4), ctx.logo_last_day(),
                {"netSatis": round(tot, 2), "maliyetliNetSatis": round(cost, 2), "maliyetsizSatir": int(_num(r.get("maliyetsiz_satir")) or 0),
                 "satir": int(_num(r.get("satir")) or 0), "firma": f, "yil": y})


def _concentration(ctx: Context, key: str, sql: Callable[[str, int], str], n: int) -> dict[str, Any]:
    f, y = ctx.firm()
    rows = ctx.once(key, lambda: ctx.logo()(sql(f, y)))
    vals = sorted(((_num(r.get("n")) or 0.0, r) for r in rows), key=lambda x: -x[0])
    total = sum(v for v, _ in vals)
    if total <= 0:
        raise SourceError("Pay hesaplanacak toplam yok.")
    top = vals[:n]
    return _out(round(sum(v for v, _ in top) / total * 100, 4), ctx.logo_last_day(),
                {"toplam": round(total, 2), "ilk": [{"kod": r.get("kod"), "unvan": r.get("unvan"), "tutar": round(v, 2),
                                                    "pay": round(v / total * 100, 2)} for v, r in top],
                 "cariSayisi": len(vals), "firma": f, "yil": y})


def k_customer_top4(ctx: Context) -> dict[str, Any]:
    return _concentration(ctx, "customer_net", customer_net_sql, 4)


def k_customer_top10(ctx: Context) -> dict[str, Any]:
    return _concentration(ctx, "customer_net", customer_net_sql, 10)


def k_supplier_top4(ctx: Context) -> dict[str, Any]:
    return _concentration(ctx, "supplier_net", supplier_net_sql, 4)


def k_overdue_90(ctx: Context) -> dict[str, Any]:
    f, y = ctx.firm()
    last = ctx.logo_last_day()
    prefix = _conf("RISK_RECEIVABLE_PREFIX", "120").strip() or "120"
    rows = ctx.logo()(overdue_fifo_sql(f, y, last, prefix))
    buckets = [{"kova": r["kova"][2:], "tutar": round(_num(r.get("tutar")) or 0.0, 2), "cari": int(_num(r.get("cari_sayisi")) or 0)}
               for r in rows]
    over = next((b for b in buckets if b["kova"].startswith("90+")), {"tutar": 0.0, "cari": 0})
    return _out(over["tutar"], last, {"kovalar": buckets, "yontem": "FIFO yaklaşımı (Logo'da ödeme kapama yok)",
                                      "cariOneki": prefix, "firma": f, "yil": y, "asOf": last.isoformat()})


def k_bounced_cheques(ctx: Context) -> dict[str, Any]:
    f, y = ctx.firm()
    docs = _codes("RISK_CHEQUE_DOCS", "1,2")
    r = (ctx.logo()(bounced_cheque_sql(f, y, docs)) or [{}])[0]
    return _out(float(_num(r.get("adet")) or 0), ctx.logo_last_day(),
                {"tutar": round(_num(r.get("tutar")) or 0.0, 2), "belgeTurleri": docs, "firma": f, "yil": y})


def k_fx_invoices(ctx: Context) -> dict[str, Any]:
    f, y = ctx.firm()
    local = _codes("RISK_LOCAL_CURRENCY_CODES", "0,160")
    rows = ctx.logo()(fx_invoice_sql(f, local))
    by = [{"doviz": int(_num(r.get("doviz")) or 0), "adet": int(_num(r.get("adet")) or 0), "tlTutar": round(_num(r.get("tl")) or 0.0, 2)}
          for r in rows]
    return _out(float(sum(b["adet"] for b in by)), ctx.logo_last_day(),
                {"dovizler": by, "yerelKodlar": local, "tlToplam": round(sum(b["tlTutar"] for b in by), 2), "firma": f, "yil": y})


def k_expired_selling(ctx: Context) -> dict[str, Any]:
    schema = ctx.schema()
    books: dict[str, dict[str, Any]] = {}
    for r in ctx.crm()(expired_contract_books_sql(schema)):
        code = str(r.get("stok") or "").strip()
        if not code:
            continue
        b = books.setdefault(code, {"stok": code, "ad": r.get("ad"), "sozlesmeler": []})
        end = _day(r.get("bitis"))
        b["sozlesmeler"].append({"kod": r.get("sozlesme"), "bitis": end.isoformat() if end else None})
    f, _ = ctx.firm()
    last = ctx.logo_last_day()
    days = int(float(_conf("RISK_EXPIRED_SALES_DAYS", "30") or 30))
    codes = sorted(books)
    sold: dict[str, float] = {}
    for i in range(0, len(codes), CHUNK):
        for r in ctx.logo()(recent_sales_sql(f, codes[i:i + CHUNK], last, days)):
            sold[str(r["stok"])] = _num(r.get("adet")) or 0.0
    rows = [{**books[c], "adet": sold[c]} for c in codes if c in sold]
    rows.sort(key=lambda x: -x["adet"])
    return _out(float(len(rows)), last, {"kitaplar": rows, "suresiBitenKitap": len(codes), "pencereGun": days,
                                         "pencereSonu": last.isoformat(), "kural": "Başka yürürlükte telif alış sözleşmesi olan kitap sayılmaz."})


def k_contracts_expiring(ctx: Context) -> dict[str, Any]:
    from semantic_bridge import editorial as editorial_mod

    days = int(float(_conf("EDITORIAL_CONTRACT_WARN_DAYS", "60") or 60))
    try:
        sql = editorial_mod.summary_sql(ctx.schema(), days)
    except Exception as e:  # noqa: BLE001 — şema hatası
        raise SourceError(str(e)) from None
    r = (ctx.crm()(sql) or [{}])[0]
    return _out(float(_num(r.get("yaklasan")) or 0), None,
                {"gun": days, "yururlukte": int(_num(r.get("yururlukte")) or 0), "toplam": int(_num(r.get("toplam")) or 0),
                 "kaynak": "Telif ve sözleşmeler (CRM)"})


def k_stock_urgent(ctx: Context) -> dict[str, Any]:
    reports = getattr(ctx.state, "management_reports", None) if ctx.state is not None else None
    if reports is None:
        raise SourceError("Baskı önerisi raporu bu kurulumda yok.")
    snap = reports.read("baski-oneri")
    data = snap.get("data") if snap else None
    if not data:
        raise SourceError("Baskı önerisi raporu henüz hazır değil.")
    view = next((v for v in data.get("views", []) if v.get("id") == "tekrar"), None)
    if view is None:
        raise SourceError("Baskı önerisi raporunda «Baskı Tekrar» görünümü yok.")
    keys = [c["key"] for c in view["columns"]]
    if "oneri" not in keys:
        raise SourceError("Baskı önerisi raporunda öneri kolonu yok.")
    oi = keys.index("oneri")
    pick = [k for k in ("stok_kodu", "urun_adi") if k in keys]
    rows = [r for r in view["rows"] if r[oi] == "Risk/Acil"]
    upd = snap.get("updatedAt")
    last = datetime.fromtimestamp(upd).date() if upd else None
    return _out(float(len(rows)), last, {"kitaplar": [{k: r[keys.index(k)] for k in pick} for r in rows],
                                         "raporGuncelleme": last.isoformat() if last else None, "oneri": "Risk/Acil"})


def k_audit_findings(ctx: Context) -> dict[str, Any]:
    snaps = getattr(ctx.state, "financial_audit", None) if ctx.state is not None else None
    if snaps is None:
        raise SourceError("Finansal denetim bu kurulumda yok.")
    rep = snaps.load()
    if not rep:
        raise SourceError("Finansal denetimin tamamlanmış raporu henüz yok.")
    main = [{"id": c.get("id"), "baslik": c.get("title"), "etkilenen": c.get("affected")} for c in rep.get("checks", []) if c.get("status") == "finding"]
    deep = [{"id": c.get("id"), "baslik": c.get("title"), "etkilenen": c.get("affected")}
            for c in (rep.get("deepAudit") or {}).get("checks", []) if c.get("status") == "finding"]
    return _out(float(len(main) + len(deep)), _day(rep.get("lastDate")),
                {"temel": main, "derin": deep, "raporId": rep.get("runId"), "hesaplanma": rep.get("computedAt"),
                 "not": "Bulgular inceleme adayıdır; denetim görüşü değildir."})


def k_budget_deviations(ctx: Context) -> dict[str, Any]:
    from semantic_bridge import budget as budget_mod

    if ctx.engine is None:
        raise SourceError("Katalog veritabanı yok.")
    budget_mod.ensure(ctx.engine)
    year = ctx.asof.year
    d = budget_mod.deviations(ctx.engine, ctx.tenant, year, status="acik")
    return _out(float(d["total"]), None, {"yil": year, "kaynak": "Bütçe ve hedefler — açık sapma uyarıları"})


def k_kvkk_consent(ctx: Context) -> dict[str, Any]:
    consent = _ident("RISK_KVKK_CONSENT_COLUMN", "new_bayibasvurusukvkkizni")
    when = _ident("RISK_KVKK_DATE_COLUMN", "new_bayibasvurusukvkkizintarihi")
    r = (ctx.crm()(kvkk_sql(ctx.schema(), consent, when)) or [{}])[0]
    return _out(float(_num(r.get("n")) or 0), None, {"izinKolonu": consent, "tarihKolonu": when,
                                                     "tanim": "KVKK izni işaretli, izin tarihi boş etkin firma kaydı"})


# ------------------------------------------------------------------ kütüphane

#: Hazır gösterge tanımları. Eşik ve sahip bilinçli olarak YOK: sayı uydurulmaz, sahibi önerir, başka biri onaylar.
LIBRARY: list[dict[str, Any]] = [
    {"kod": "logo_veri_gecikmesi", "ad": "Logo veri gecikmesi", "birim": "gun", "yon": "artis_kotu", "siklik": "gunluk", "kaynak_turu": "sql",
     "kaynak_ref": "Logo INVOICE — MAX(DATE_), iptal hariç", "kategori": "bt", "ekran": "/finansal-denetim",
     "aciklama": "Bugün ile Logo'daki son fatura günü arasındaki gün. Kopya dondurulmuşsa bütün raporlar bu kadar eskidir."},
    {"kod": "maliyet_gecikmesi", "ad": "Maliyetlendirme gecikmesi", "birim": "gun", "yon": "artis_kotu", "siklik": "haftalik", "kaynak_turu": "sql",
     "kaynak_ref": "Logo STLINE — son fatura günü − son maliyeti girilmiş satış satırı günü", "kategori": "finansal", "ekran": "/fiyatlama",
     "aciklama": "Maliyet (OUTCOST) girişinin satışın ne kadar gerisinde kaldığı; kâr raporlarının güvenilirliği."},
    {"kod": "maliyetsiz_satis_payi", "ad": "Maliyetsiz satış payı", "birim": "yuzde", "yon": "artis_kotu", "siklik": "haftalik", "kaynak_turu": "sql",
     "kaynak_ref": "Logo STLINE faturalı satış (TRCODE 7,8) — OUTCOST = 0 satırların net satış payı", "kategori": "finansal", "ekran": "/fiyatlama",
     "aciklama": "Güncel yılın faturalı satış satırlarında maliyeti girilmemiş olanların net satıştaki payı."},
    {"kod": "musteri_yogunlasmasi_ilk4", "ad": "Müşteri yoğunlaşması (ilk 4)", "birim": "yuzde", "yon": "artis_kotu", "siklik": "haftalik",
     "kaynak_turu": "sql", "kaynak_ref": "Logo INVOICE net ciro × cari (satış 7/8/9 − iade 2/3)", "kategori": "finansal", "ekran": "/genel-bakis",
     "aciklama": "Güncel yıl net cirosunun en büyük 4 cariden gelen payı."},
    {"kod": "musteri_yogunlasmasi_ilk10", "ad": "Müşteri yoğunlaşması (ilk 10)", "birim": "yuzde", "yon": "artis_kotu", "siklik": "haftalik",
     "kaynak_turu": "sql", "kaynak_ref": "Logo INVOICE net ciro × cari (satış 7/8/9 − iade 2/3)", "kategori": "finansal", "ekran": "/genel-bakis",
     "aciklama": "Güncel yıl net cirosunun en büyük 10 cariden gelen payı."},
    {"kod": "vadesi_gecmis_alacak_90", "ad": "90 günü geçmiş alacak", "birim": "tl", "yon": "artis_kotu", "siklik": "haftalik", "kaynak_turu": "sql",
     "kaynak_ref": "Logo CLFLINE + PAYTRANS — FIFO yaklaşımı, veri son gününe göre", "kategori": "finansal", "ekran": "/saha",
     "aciklama": "Müşteri bakiyesi en yeni vadelerden geriye dağıtılır; 90 günden eski vadeye düşen açık tutar. Yaklaşıktır."},
    {"kod": "karsiliksiz_cek", "ad": "Karşılıksız çıkan çek (bu yıl)", "birim": "adet", "yon": "artis_kotu", "siklik": "gunluk", "kaynak_turu": "sql",
     "kaynak_ref": "Logo CSTRANS STATUS 11 (olay) — tutar CSCARD", "kategori": "finansal", "ekran": "/saha",
     "aciklama": "Güncel yılda karşılıksız durumuna düşen müşteri çeki/senedi; sonradan iade edilmiş olsa da sayılır. Tutar kanıtta."},
    {"kod": "doviz_faturasi", "ad": "Döviz cinsinden fatura", "birim": "adet", "yon": "artis_kotu", "siklik": "haftalik", "kaynak_turu": "sql",
     "kaynak_ref": "Logo INVOICE — TRCURR yerel para dışı", "kategori": "finansal", "ekran": "/finansal-denetim",
     "aciklama": "Güncel yılın döviz cinsinden faturaları (kur riski); döviz kırılımı ve TL karşılığı kanıtta."},
    {"kod": "tedarikci_yogunlasmasi_ilk4", "ad": "Tedarikçi yoğunlaşması (ilk 4)", "birim": "yuzde", "yon": "artis_kotu", "siklik": "aylik",
     "kaynak_turu": "sql", "kaynak_ref": "Logo INVOICE alış (TRCODE 1,4) × cari", "kategori": "operasyonel", "ekran": "/uretim",
     "aciklama": "Güncel yıl mal ve hizmet alımlarının en büyük 4 tedarikçiden gelen payı (matbaa, kâğıt bağımlılığı)."},
    {"kod": "suresi_bitmis_satan_kitap", "ad": "Sözleşmesi bitmiş ama satan kitap", "birim": "adet", "yon": "artis_kotu", "siklik": "haftalik",
     "kaynak_turu": "sql", "kaynak_ref": "CRM telif alış sözleşmesi (tip 5) bitişi × Logo son 30 gün faturalı satış", "kategori": "yasal",
     "ekran": "/telif-sozlesme",
     "aciklama": "Telif alış sözleşmesinin süresi bitmiş, yürürlükte başka sözleşmesi olmayan ve veri son gününden geriye pencerede satışı olan kitap. İnceleme adayıdır."},
    {"kod": "sozlesme_bitiyor", "ad": "Süresi yaklaşan sözleşme", "birim": "adet", "yon": "artis_kotu", "siklik": "gunluk", "kaynak_turu": "sql",
     "kaynak_ref": "CRM new_sozlesmeBase — yürürlükte, süresiz değil, bitişi uyarı penceresinde", "kategori": "yasal", "ekran": "/telif-sozlesme",
     "aciklama": "Telif ve sözleşmeler ekranındaki «yaklaşan bitiş» sayısıyla aynı tanım."},
    {"kod": "stok_risk_acil", "ad": "Stokta «Risk/Acil» kitap", "birim": "adet", "yon": "artis_kotu", "siklik": "gunluk", "kaynak_turu": "modul",
     "kaynak_ref": "Baskı önerisi — Baskı Tekrar görünümü, öneri «Risk/Acil»", "kategori": "operasyonel", "ekran": "/yonetim-raporlari/baski-oneri",
     "aciklama": "Baskı önerisinin son hazır raporunda stoğu tükenmek üzere olan kitap sayısı; Logo'ya ayrıca sorgu gitmez."},
    {"kod": "denetim_inceleme_adayi", "ad": "Finansal denetim inceleme adayı", "birim": "adet", "yon": "artis_kotu", "siklik": "gunluk",
     "kaynak_turu": "modul", "kaynak_ref": "Finansal denetim — son tamamlanan rapor (temel + derin kontrol, durum «inceleme adayı»)",
     "kategori": "finansal", "ekran": "/finansal-denetim",
     "aciklama": "Finansal denetimin son raporunda inceleme adayı çıkan kontrol sayısı; hazır rapor okunur."},
    {"kod": "butce_sapmasi", "ad": "Açık bütçe sapma uyarısı", "birim": "adet", "yon": "artis_kotu", "siklik": "gunluk", "kaynak_turu": "modul",
     "kaynak_ref": "Bütçe ve hedefler — açık sapma uyarıları (bu yıl)", "kategori": "finansal", "ekran": "/butce",
     "aciklama": "Satış hedefinin eşik altına düştüğü ya da departman bütçesini aşan açık uyarı sayısı."},
    {"kod": "kvkk_izin_tarihsiz", "ad": "Tarihsiz KVKK izni", "birim": "adet", "yon": "artis_kotu", "siklik": "haftalik", "kaynak_turu": "sql",
     "kaynak_ref": "CRM AccountBase — bayi başvurusu KVKK izni işaretli, izin tarihi boş", "kategori": "yasal", "ekran": "",
     "aciklama": "İzin işaretli ama izin tarihi (kanıtı) olmayan etkin firma kaydı. Kolon adları ayardır (ölçülecek)."},
]

COMPUTERS: dict[str, Callable[[Context], dict[str, Any]]] = {
    "logo_veri_gecikmesi": k_data_delay, "maliyet_gecikmesi": k_cost_delay, "maliyetsiz_satis_payi": k_costless_share,
    "musteri_yogunlasmasi_ilk4": k_customer_top4, "musteri_yogunlasmasi_ilk10": k_customer_top10,
    "vadesi_gecmis_alacak_90": k_overdue_90, "karsiliksiz_cek": k_bounced_cheques, "doviz_faturasi": k_fx_invoices,
    "tedarikci_yogunlasmasi_ilk4": k_supplier_top4, "suresi_bitmis_satan_kitap": k_expired_selling,
    "sozlesme_bitiyor": k_contracts_expiring, "stok_risk_acil": k_stock_urgent, "denetim_inceleme_adayi": k_audit_findings,
    "butce_sapmasi": k_budget_deviations, "kvkk_izin_tarihsiz": k_kvkk_consent,
}
BY_CODE = {x["kod"]: x for x in LIBRARY}
assert set(COMPUTERS) == set(BY_CODE), "her hazır tanımın bir hesapçısı olmalı"


def measure(ctx: Context, kod: str) -> dict[str, Any]:
    """Tek göstergeyi ölçer. Okuma hatası sonucu bozmaz: `deger` None, `hata` metni döner."""
    fn = COMPUTERS.get(kod)
    if fn is None:
        return {"deger": None, "hata": "Bu göstergenin hesapçısı yok."}
    ctx.touched = []
    try:
        out = fn(ctx)
    except SourceError as e:
        out = {"deger": None, "hata": str(e)}
    except Exception as e:  # noqa: BLE001 — beklenmeyen hata da ölçümü durdurmaz, kaydı düşer
        log.exception("risk göstergesi %s ölçülemedi", kod)
        out = {"deger": None, "hata": f"Ölçüm hata verdi: {str(e)[:200]}"}
    seen, used = set(), []
    for q in ctx.touched:  # aynı metin bir kez
        if q["sql"] not in seen:
            seen.add(q["sql"])
            used.append(q)
    return {**out, "sorgular": used}


def measure_many(ctx: Context, codes: Iterable[str]) -> dict[str, dict[str, Any]]:
    return {k: measure(ctx, k) for k in codes}
