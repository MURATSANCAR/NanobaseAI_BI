"""M7 Yazarla İlişki ve **Gelişim** Takibi: satış ve telif gidişatı, okur sesi, sadakat puanı, Zeki AI strateji önerisi.

Kaynaklar (hepsi yalnız okunur):

- **Kitaplar**: CRM eser katılımı, yazar rolü (`new_eserkatilimBase` → `new_kitapBase`), stok kodu `new_StokKodu`
  (+ e-kitap `new_EKitapStokKodu`), barkod `new_ean13`.
- **Satış**: Logo'nun yıllık satış görünümleri (`V_SatisRaporu_<yıl>`), M6 hakediş hesabıyla aynı sorgu ve katlama
  (`contracts_royalty.sales_sql` / yalnız faturalı malzeme satırı, iade düşülür). Stok kodu = Logo `[Malzeme/Hizmet Kodu]`.
- **Telif**: CRM'deki telif ödeme tablosu 2014'ten beri boş (analiz 2026-09-20); gerçek iz M6'da hesaplanıp kaydedilen
  hakedişlerdir (`semantic_contract_statements`, onaylı/ödenmiş). Oranla tahmin üretilmez; hakedişi olmayan sözleşme
  «hesaplanmadı» diye görünür.
- **Okur sesi**: timas.com.tr ürün yorumlarının özeti (SEO modülü, T-soft'tan gece okunur; yorum metni ve kişisel veri
  tutulmaz) — kitaba EAN-13 ile bağlanır; açık web taramasının model etiketleri (olumlu/olumsuz/nötr) yalnız
  `WEB_WATCH_ENABLED` ortamında. Satıcı sitelerinin yorumları (bot korumalı) okunmaz.
- **Sadakat puanı** (0–100, yalnız CRM'den, kuralı ekranda yazılı): birliktelik süresi yıl başı 3 (en çok 30),
  külliyat kitap başı 5 (en çok 25), süreklilik — son 24 ayda yeni eser ya da sözleşme 20, 24–48 ay 10 (en çok 20),
  yürürlükte sözleşme 15, birden çok sözleşme (geri dönüp yeniden imzalamış) 10. Bant: 70+ bağlı, 40–69 düzenli,
  altı zayıf. Bu yazarın yayınevine bağlılığıdır; okur sadakati değildir.
- **Strateji önerisi**: Zeki AI yalnız istenince yazar; girdi bu ekrandaki sayılar + gizli olmayan son görüşme notları.
  Her öneri girdisiyle birlikte saklanır (sonradan neye dayandığı görülür); model uydurmasın diye yalnız verilen
  sayılara dayanması istenir, sayı içermeyen iddia reddedilir değil ama «kanıt» alanı boş kalır.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

log = logging.getLogger("semantic.author_growth")
_md = sa.MetaData()

GROWTH = sa.Table(
    "semantic_author_growth", _md,               # yazar başına hesaplanmış gelişim özeti (önbellek)
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("contact_id", sa.String(40), primary_key=True),
    sa.Column("data_json", sa.Text, nullable=False),
    sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
)
ADVICE = sa.Table(
    "semantic_author_advice", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("contact_id", sa.String(40), nullable=False, index=True),
    sa.Column("input_json", sa.Text, nullable=False),
    sa.Column("output_json", sa.Text, nullable=False),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)

#: Gelişim özeti bu kadar süre taze sayılır; «Yenile» ile beklemeden okunur.
FRESH_HOURS = 12

LOYALTY = {"yearEach": 3, "yearsMax": 30, "bookEach": 5, "booksMax": 25, "recent24": 20, "recent48": 10,
           "active": 15, "returning": 10}

_GUID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_ready: set[int] = set()
_lock = threading.Lock()
_logo_lock = threading.Lock()


class GrowthError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _guid(v: Any) -> str:
    t = str(v or "").strip().strip("{}")
    if not _GUID.match(t):
        raise GrowthError("CRM kişi kimliği geçerli değil.")
    return t.lower()


def _prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise GrowthError(f"CRM şeması «{schema}» geçerli bir ad değil.", 503)
    if not sch:
        raise GrowthError("CRM şeması girilmemiş; CRM okunamıyor.", 503)
    return (f"{db}." if db else "") + f"{sch}."


def _s(v: Any) -> Optional[str]:
    t = None if v is None else str(v).strip()
    return t or None


def _f(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _day(v: Any) -> Optional[date]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v).replace(" ", "T")[:19]).date()
    except ValueError:
        return None


def _is_author(p: str, col: str) -> str:
    # Takma adlar dış sorgudakilerle çakışmasın (author_relations._is_author ile aynı ders).
    return (f"EXISTS (SELECT 1 FROM {p}new_eserkatilimBase ya_e JOIN {p}new_katilimcitipiBase ya_t"
            f" ON ya_t.new_katilimcitipiId = ya_e.new_katilimciTipi WHERE ya_e.statecode = 0 AND ya_t.new_name = N'Yazar'"
            f" AND ya_e.new_Katilimsaglayan = {col})")


# ------------------------------------------------------------------------------------------ CRM

def books_sql(schema: str, contact_id: str) -> str:
    """Yazarın yazar rolüyle katkı verdiği kitaplar: stok kodu, e-kitap stok kodu, barkod, ilk yayın."""
    p = _prefix(schema)
    return (
        "SELECT DISTINCT b.new_kitapId, b.new_name, b.new_StokKodu, b.new_EKitapStokKodu, b.new_ean13,"
        " b.new_ilkyayintarihi, e.CreatedOn"
        f" FROM {p}new_eserkatilimBase e JOIN {p}new_katilimcitipiBase t ON t.new_katilimcitipiId = e.new_katilimciTipi"
        f" JOIN {p}new_kitapBase b ON b.new_kitapId = e.new_Kitap"
        f" WHERE e.statecode = 0 AND b.statecode = 0 AND t.new_name = N'Yazar' AND e.new_Katilimsaglayan = '{_guid(contact_id)}'"
    )


def contracts_sql(schema: str, contact_id: str) -> str:
    p = _prefix(schema)
    return (
        "SELECT s.new_sozlesmeId, s.new_name, s.statuscode, s.new_SozlesmeBaslangicTarihi, s.new_SozlesmeBitisTarihi"
        f" FROM {p}new_sozlesmetarafiBase r JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = r.new_sozlesmeid"
        f" WHERE r.statecode = 0 AND s.statecode = 0 AND r.new_kisi = '{_guid(contact_id)}'"
    )


def loyalty_sql(schema: str, contact_id: Optional[str] = None) -> str:
    """Kişi başına: ilk ve son iz (yazar rolüyle eser kaydı ya da sözleşme başlangıcı), kitap ve sözleşme sayısı,
    yürürlükte sözleşme. `contact_id` yoksa bütün yazarlar (ısı haritası)."""
    p = _prefix(schema)
    one_e = f" AND e.new_Katilimsaglayan = '{_guid(contact_id)}'" if contact_id else ""
    one_r = f" AND r.new_kisi = '{_guid(contact_id)}'" if contact_id else ""
    return (
        "SELECT x.kisi, MIN(x.ilk) AS ilk, MAX(x.son) AS son, SUM(x.eser) AS eser, SUM(x.sozlesme) AS sozlesme,"
        " SUM(x.aktif) AS aktif FROM ("
        " SELECT e.new_Katilimsaglayan AS kisi, MIN(e.CreatedOn) AS ilk, MAX(e.CreatedOn) AS son,"
        " COUNT(DISTINCT e.new_Kitap) AS eser, 0 AS sozlesme, 0 AS aktif"
        f" FROM {p}new_eserkatilimBase e JOIN {p}new_katilimcitipiBase t ON t.new_katilimcitipiId = e.new_katilimciTipi"
        f" WHERE e.statecode = 0 AND t.new_name = N'Yazar'{one_e} GROUP BY e.new_Katilimsaglayan"
        " UNION ALL"
        " SELECT r.new_kisi AS kisi, MIN(s.new_SozlesmeBaslangicTarihi) AS ilk, MAX(s.new_SozlesmeBaslangicTarihi) AS son,"
        " 0 AS eser, COUNT(DISTINCT s.new_sozlesmeId) AS sozlesme,"
        " COUNT(DISTINCT CASE WHEN s.statuscode IN (100000000, 100000006, 100000007) AND (s.new_SozlesmeBitisTarihi IS NULL"
        " OR s.new_SozlesmeBitisTarihi >= CAST(GETDATE() AS date)) THEN s.new_sozlesmeId END) AS aktif"
        f" FROM {p}new_sozlesmetarafiBase r JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = r.new_sozlesmeid"
        f" WHERE r.statecode = 0 AND s.statecode = 0{one_r} AND {_is_author(p, 'r.new_kisi')} GROUP BY r.new_kisi"
        ") x WHERE x.kisi IS NOT NULL GROUP BY x.kisi"
    )


def loyalty(row: Optional[dict[str, Any]], today: Optional[date] = None) -> dict[str, Any]:
    """Sadakat puanı ve dökümü (modül başındaki kural)."""
    today = today or _now().date()
    L = LOYALTY
    if not row:
        return {"score": 0, "band": "zayif", "parts": {"years": 0, "books": 0, "recent": 0, "active": 0, "returning": 0},
                "since": None, "last": None, "books": 0, "contracts": 0, "activeContracts": 0}
    first, last = _day(row.get("ilk")), _day(row.get("son"))
    books, contracts, active = int(_f(row.get("eser"))), int(_f(row.get("sozlesme"))), int(_f(row.get("aktif")))
    years = max(0.0, (today - first).days / 365.25) if first else 0.0
    months_since = ((today - last).days / 30.44) if last else None
    parts = {
        "years": min(L["yearsMax"], int(years) * L["yearEach"]),
        "books": min(L["booksMax"], books * L["bookEach"]),
        "recent": L["recent24"] if months_since is not None and months_since <= 24
        else L["recent48"] if months_since is not None and months_since <= 48 else 0,
        "active": L["active"] if active > 0 else 0,
        "returning": L["returning"] if contracts >= 2 else 0,
    }
    score = sum(parts.values())
    band = "bagli" if score >= 70 else "duzenli" if score >= 40 else "zayif"
    return {"score": score, "band": band, "parts": parts, "since": first.isoformat() if first else None,
            "last": last.isoformat() if last else None, "years": round(years, 1), "books": books,
            "contracts": contracts, "activeContracts": active}


def loyalty_map(rows: Iterable[dict[str, Any]], today: Optional[date] = None) -> dict[str, dict[str, Any]]:
    return {str(r.get("kisi") or "").strip("{}").lower(): loyalty(r, today) for r in rows if r.get("kisi")}


# ------------------------------------------------------------------------------------------ satış

def fold_monthly(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Logo satır grupları (kod × yıl × ay × satış/iade) → ay ay ve kitap kitap net adet / net tutar / iade adedi."""
    months: dict[str, dict[str, float]] = {}
    books: dict[str, dict[str, float]] = {}
    for r in rows:
        code = str(r.get("kod") or "").strip()
        y, m = int(_f(r.get("yil"))), int(_f(r.get("ay")))
        if not code or not y or not m:
            continue
        ret = str(r.get("tur") or "").strip().replace("İ", "i").lower().startswith("iade")
        q, n = _f(r.get("miktar")), _f(r.get("net"))
        if ret:
            q, n = -abs(q), -abs(n)
        key = f"{y:04d}-{m:02d}"
        for bucket, k in ((months, key), (books, code)):
            acc = bucket.setdefault(k, {"qty": 0.0, "net": 0.0, "retQty": 0.0})
            acc["qty"] += q
            acc["net"] += n
            if ret:
                acc["retQty"] += -q
    return {"months": months, "books": books}


def _sum(months: dict[str, dict[str, float]], keys: Iterable[str]) -> dict[str, float]:
    out = {"qty": 0.0, "net": 0.0, "retQty": 0.0}
    for k in keys:
        for f in out:
            out[f] += months.get(k, {}).get(f, 0.0)
    return out


def _month_keys(end: date, n: int) -> list[str]:
    y, m = end.year, end.month
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out[::-1]


def trend(months: dict[str, dict[str, float]], data_end: Optional[date]) -> dict[str, Any]:
    """Veri sonuna göre son 12 ay ve önceki 12 ay; yıllık toplamlar; son 24 ayın aylık dizisi.
    Veri sonu ayın ortasındaysa o ay yarımdır: iki pencere de aynı yerden kesilir (ay sınırında, yarım ay dahil)."""
    end = data_end or _now().date()
    last24 = _month_keys(end, 24)
    cur, prev = _sum(months, last24[12:]), _sum(months, last24[:12])
    change = None if prev["qty"] <= 0 else round((cur["qty"] - prev["qty"]) / prev["qty"] * 100, 1)
    years: dict[int, dict[str, float]] = {}
    for k, v in months.items():
        acc = years.setdefault(int(k[:4]), {"qty": 0.0, "net": 0.0, "retQty": 0.0})
        for f in acc:
            acc[f] += v[f]
    return {
        "last12": cur, "prev12": prev, "changePct": change,
        "direction": None if change is None else "artis" if change >= 10 else "dusus" if change <= -10 else "yatay",
        "series": [{"month": k, **{f: round(months.get(k, {}).get(f, 0.0), 2) for f in ("qty", "net", "retQty")}} for k in last24],
        "years": [{"year": y, **{f: round(v[f], 2) for f in v}} for y, v in sorted(years.items())],
        "window": {"from": last24[12], "to": last24[-1], "prevFrom": last24[0], "prevTo": last24[11]},
    }


# ------------------------------------------------------------------------------------------ bir araya getirme

def _statements(engine: sa.engine.Engine, tenant: str, crm_contract_ids: list[str]) -> list[dict[str, Any]]:
    """M6'da bu yazarın sözleşmeleri için kaydedilmiş hakedişler (iptal edilmemiş)."""
    if not crm_contract_ids:
        return []
    try:
        from semantic_bridge import contracts as C
    except Exception:  # noqa: BLE001
        return []
    ids = [i.lower() for i in crm_contract_ids]
    try:
        with engine.connect() as c:
            recs = c.execute(sa.select(C.RECORDS.c.id, C.RECORDS.c.no, C.RECORDS.c.crm_id).where(
                C.RECORDS.c.tenant_id == tenant, sa.func.lower(C.RECORDS.c.crm_id).in_(ids))).fetchall()
            if not recs:
                return []
            by_id = {r.id: r for r in recs}
            rows = c.execute(sa.select(C.STATEMENTS).where(C.STATEMENTS.c.tenant_id == tenant,
                                                           C.STATEMENTS.c.contract_id.in_(list(by_id)),
                                                           C.STATEMENTS.c.cancelled_at.is_(None))
                             .order_by(C.STATEMENTS.c.period_start)).fetchall()
    except sa.exc.SQLAlchemyError as e:   # M6 tabloları bu ortamda henüz kurulmamış olabilir
        log.info("author growth: hakediş okunamadı: %s", e)
        return []
    return [{"contractNo": by_id[r.contract_id].no, "periodStart": r.period_start, "periodEnd": r.period_end,
             "status": r.status, "gross": _f(r.gross), "net": _f(r.net), "currency": r.currency,
             "approved": r.approved_at is not None} for r in rows]


def _reviews(engine: sa.engine.Engine, tenant: str, eans: dict[str, str]) -> dict[str, Any]:
    """Sitedeki yorum özeti: kitap başına sayı ve puan, yazar toplamında ağırlıklı ortalama ve yıldız dağılımı."""
    out: dict[str, Any] = {"available": False, "books": [], "comments": 0, "rated": 0, "average": None,
                           "stars": {str(s): 0 for s in range(1, 6)}}
    if not eans:
        return out
    try:
        from semantic_bridge import seo_geo as S
        from semantic_bridge.seo_geo import reviews as RV
        with engine.connect() as c:
            prods = c.execute(sa.select(S.PRODUCTS.c.product_id, S.EAN.label("ean")).where(
                S.PRODUCTS.c.tenant_id == tenant, S.EAN.in_(list(eans)))).fetchall()
            if not prods:
                out["available"] = True
                return out
            pid_ean = {p.product_id: p.ean for p in prods}
            rows = c.execute(sa.select(RV.REVIEWS).where(RV.REVIEWS.c.tenant_id == tenant,
                                                         RV.REVIEWS.c.product_id.in_(list(pid_ean)))).fetchall()
    except Exception as e:  # noqa: BLE001 — SEO modülü bu ortamda yok ya da tablo kurulmamış
        log.info("author growth: yorum özeti okunamadı: %s", e)
        return out
    out["available"] = True
    rate_sum = 0.0
    for r in rows:
        stars = json.loads(r.stars_json or "{}")
        for s in out["stars"]:
            out["stars"][s] += int(stars.get(s) or 0)
        out["comments"] += int(r.approved or 0)
        out["rated"] += int(r.rated or 0)
        rate_sum += float(r.rate_sum or 0)
        ean = pid_ean.get(r.product_id)
        out["books"].append({"title": eans.get(ean), "comments": int(r.approved or 0), "rated": int(r.rated or 0),
                             "average": round(r.rate_sum / r.rated, 2) if r.rated else None})
    out["average"] = round(rate_sum / out["rated"], 2) if out["rated"] else None
    out["books"].sort(key=lambda b: -b["comments"])
    return out


def _web_tone(engine: sa.engine.Engine, tenant: str, contact_id: str, enabled: bool) -> Optional[dict[str, int]]:
    if not enabled:
        return None
    try:
        from semantic_bridge import web_watch as W
        W.ensure(engine)
        return W._tone(engine, tenant, [sa.func.lower(W.MENTIONS.c.contact_id) == contact_id])
    except Exception as e:  # noqa: BLE001
        log.info("author growth: web tonu okunamadı: %s", e)
        return None


def compute(schema: str, run_crm: Callable[[str], dict[str, Any]], logo: Callable[[list[str], date, date], tuple[list[dict[str, Any]], Optional[date], list[int]]],
            engine: sa.engine.Engine, tenant: str, contact_id: str, *, web_enabled: bool,
            today: Optional[date] = None, books_rows: Optional[list[dict[str, Any]]] = None,
            loyalty_row: Optional[dict[str, Any]] = None, prepared: bool = False) -> dict[str, Any]:
    """Yazarın gelişim özeti. `logo(kodlar, başlangıç, bitiş)` → (satır grupları, veri sonu günü, eksik yıllar).
    `prepared`: kitaplar, sadakat izi ve satış önceden hazırlanmış parçadan gelir (author_snapshots); CRM'e yalnız
    kişinin sözleşme listesi sorulur."""
    cid = _guid(contact_id)
    today = today or _now().date()
    books_raw = books_rows if prepared else (run_crm(books_sql(schema, cid)).get("records") or [])
    books: dict[str, dict[str, Any]] = {}
    for b in books_raw:
        bid = str(b.get("new_kitapId") or "").lower()
        if not bid or bid in books:
            continue
        books[bid] = {"id": bid, "title": _s(b.get("new_name")), "stockCode": _s(b.get("new_StokKodu")),
                      "ebookCode": _s(b.get("new_EKitapStokKodu")), "ean": re.sub(r"[^0-9]", "", str(b.get("new_ean13") or "")),
                      "firstPublished": (_day(b.get("new_ilkyayintarihi")) or _day(b.get("CreatedOn")) or None)}
    code_book = {}
    for b in books.values():
        for k in (b["stockCode"], b["ebookCode"]):
            if k:
                code_book[k] = b["id"]
    notes: list[str] = []
    sales = {"months": {}, "books": {}}
    data_end, missing = None, []
    if code_book:
        start = date(max(2015, today.year - 5), 1, 1)
        rows, data_end, missing = logo(sorted(code_book), start, today)
        sales = fold_monthly(rows)
    else:
        notes.append("Yazarın CRM'deki kitaplarında stok kodu yok; Logo satışı okunamadı.")
    if missing:
        notes.append(f"Logo'da {', '.join(map(str, missing))} yılının satış görünümü yok; o yıllar okunmadı.")
    per_book: dict[str, dict[str, float]] = {}
    for code, v in sales["books"].items():
        bid = code_book.get(code)
        if not bid:
            continue
        acc = per_book.setdefault(bid, {"qty": 0.0, "net": 0.0, "retQty": 0.0})
        for f in acc:
            acc[f] += v[f]
    book_list = []
    for b in books.values():
        s = per_book.get(b["id"], {"qty": 0.0, "net": 0.0, "retQty": 0.0})
        book_list.append({"id": b["id"], "title": b["title"], "stockCode": b["stockCode"], "hasCode": bool(b["stockCode"] or b["ebookCode"]),
                          "firstPublished": b["firstPublished"].isoformat() if b["firstPublished"] else None,
                          "qty": round(s["qty"], 2), "net": round(s["net"], 2), "retQty": round(s["retQty"], 2)})
    book_list.sort(key=lambda x: (-x["net"], x["title"] or ""))
    new_by_year: dict[int, int] = {}
    for b in books.values():
        if b["firstPublished"]:
            new_by_year[b["firstPublished"].year] = new_by_year.get(b["firstPublished"].year, 0) + 1

    contracts = run_crm(contracts_sql(schema, cid)).get("records") or []
    contract_ids = [str(r.get("new_sozlesmeId") or "") for r in contracts if r.get("new_sozlesmeId")]
    loy_rows = ([loyalty_row] if loyalty_row else []) if prepared else (run_crm(loyalty_sql(schema, cid)).get("records") or [])
    eans = {b["ean"]: b["title"] for b in books.values() if len(b["ean"]) >= 8}
    return {
        "contactId": cid,
        "books": book_list, "booksTotal": len(book_list), "booksWithCode": sum(1 for b in book_list if b["hasCode"]),
        "newBooksByYear": [{"year": y, "count": n} for y, n in sorted(new_by_year.items())],
        "sales": trend(sales["months"], data_end), "dataEnd": data_end.isoformat() if data_end else None,
        "royalty": {"statements": _statements(engine, tenant, contract_ids), "contracts": len(contract_ids)},
        "readers": {"site": _reviews(engine, tenant, eans), "web": _web_tone(engine, tenant, cid, web_enabled)},
        "loyalty": loyalty(loy_rows[0] if loy_rows else None, today),
        "notes": notes,
        "computedAt": _now().isoformat(),
    }


def cached(engine: sa.engine.Engine, tenant: str, contact_id: str, build: Callable[[], dict[str, Any]], *,
           refresh: bool = False) -> dict[str, Any]:
    cid = _guid(contact_id)
    with engine.connect() as c:
        row = c.execute(sa.select(GROWTH).where(GROWTH.c.tenant_id == tenant, GROWTH.c.contact_id == cid)).first()
    if row and not refresh:
        at = row.computed_at if row.computed_at.tzinfo else row.computed_at.replace(tzinfo=timezone.utc)
        if _now() - at < timedelta(hours=FRESH_HOURS):
            return dict(json.loads(row.data_json), cached=True)
    with _logo_lock:          # aynı anda tek yazar okunur: Logo'nun yıllık görünümleri ağırdır
        data = build()
    with engine.begin() as c:
        c.execute(GROWTH.delete().where(GROWTH.c.tenant_id == tenant, GROWTH.c.contact_id == cid))
        c.execute(GROWTH.insert().values(tenant_id=tenant, contact_id=cid, data_json=json.dumps(data, ensure_ascii=False, default=str),
                                         computed_at=_now()))
    return dict(data, cached=False)


# ------------------------------------------------------------------------------------------ Zeki AI önerisi

ADVICE_SYSTEM = (
    "Bir yayınevinin editoryal ekibine yazar ilişkisi danışmanısın. Sana bir yazarın yayınevindeki verisi verilecek: "
    "satış gidişatı, kitapları, sözleşme durumu, sadakat puanı, ilişki ısısı, okur puanı ve son görüşme notları. "
    "Yalnız bu veriye dayan; veride olmayan bir sayı, olay ya da kişi uydurma. Türkçe, kısa ve somut yaz. "
    "Cevabı yalnız şu JSON olarak ver: "
    '{"ozet": "iki cümlelik durum", "oneriler": [{"baslik": "...", "neden": "hangi veriye dayandığı, sayıyla", '
    '"ne_zaman": "bu hafta | bu ay | bu çeyrek"}], "riskler": ["..."]} '
    "«kismi_yil» işaretli yıl veri sonuna kadardır; onu tam yıllarla karşılaştırma, son 12 ay ile önceki 12 ayı kullan. "
    "En çok 4 öneri. Puanları (sadakat, ısı) yıl ya da adet gibi okuma; süreyi yalnız «birlikte_gecen_yil»dan al. "
    "Teknoloji ya da model adı yazma."
)


def advice_input(name: str, growth: dict[str, Any], relation: dict[str, Any]) -> dict[str, Any]:
    """Modele giden girdi: yalnız sayılar ve gizli olmayan son notlar (en yeni 5, 600 karakter)."""
    s = growth.get("sales") or {}
    notes = [m for m in (relation.get("timeline") or []) if m.get("status") == "yapildi" and not m.get("private") and not m.get("hidden")]
    return {
        "yazar": name,
        "satis": {"son12_adet": (s.get("last12") or {}).get("qty"), "onceki12_adet": (s.get("prev12") or {}).get("qty"),
                  "degisim_yuzde": s.get("changePct"), "veri_sonu": growth.get("dataEnd"),
                  # Veri sonunun yılı yarımdır: model onu tam yıllarla kıyaslamasın (2026-09-28 kabulünde «tarihin en düşüğü» dedi).
                  "yillik": [dict(y, kismi_yil=bool(growth.get("dataEnd")) and str(y.get("year")) == str(growth.get("dataEnd"))[:4])
                             for y in (s.get("years") or [])]},
        "kitaplar": [{"ad": b["title"], "net_adet": b["qty"], "ilk_yayin": b["firstPublished"]} for b in (growth.get("books") or [])],
        "yeni_kitap_yillara_gore": growth.get("newBooksByYear"),
        # Puan dökümü (years=30 gibi) modele gitmez: 2026-09-28 kabulünde model süre puanını «30 yıllık» diye okudu.
        "sadakat": _loyalty_facts(growth.get("loyalty") or {}),
        "okur": {"site_ortalama": ((growth.get("readers") or {}).get("site") or {}).get("average"),
                 "site_yorum": ((growth.get("readers") or {}).get("site") or {}).get("comments"),
                 "web_ton": (growth.get("readers") or {}).get("web")},
        "iliski_isisi": (relation.get("heat") or {}).get("score"),
        "son_gorusme_gun_once": (relation.get("heat") or {}).get("daysSince"),
        "siradaki_randevu": (relation.get("heat") or {}).get("next"),
        "asama": (relation.get("card") or {}).get("stageLabel"),
        "son_notlar": [{"tarih": m.get("date"), "konu": m.get("topic"), "ton": m.get("toneLabel"),
                        "not": (m.get("notes") or "")[:600], "siradaki_adim": m.get("nextStep")} for m in notes[:5]],
    }


def _loyalty_facts(l: dict[str, Any]) -> dict[str, Any]:
    band = {"bagli": "bağlı", "duzenli": "düzenli", "zayif": "zayıf bağ"}.get(l.get("band"), l.get("band"))
    return {"puan_100_uzerinden": l.get("score"), "bant": band, "birlikte_gecen_yil": l.get("years"),
            "ilk_iz": l.get("since"), "son_iz": l.get("last"), "yazar_oldugu_kitap": l.get("books"),
            "toplam_sozlesme": l.get("contracts"), "yururlukte_sozlesme": l.get("activeContracts")}


def parse_advice(text: str) -> dict[str, Any]:
    t = (text or "").strip()
    m = re.search(r"\{.*\}", t, re.S)
    if not m:
        raise GrowthError("Zeki AI önerisi okunamadı; tekrar deneyin.", 502)
    try:
        data = json.loads(m.group(0))
    except ValueError:
        raise GrowthError("Zeki AI önerisi okunamadı; tekrar deneyin.", 502) from None
    recs = []
    for r in (data.get("oneriler") or [])[:4]:
        if isinstance(r, dict) and str(r.get("baslik") or "").strip():
            recs.append({"title": str(r["baslik"]).strip()[:200], "why": str(r.get("neden") or "").strip()[:600],
                         "when": str(r.get("ne_zaman") or "").strip()[:40]})
    if not recs:
        raise GrowthError("Zeki AI öneri üretmedi; tekrar deneyin.", 502)
    return {"summary": str(data.get("ozet") or "").strip()[:600], "recommendations": recs,
            "risks": [str(x).strip()[:300] for x in (data.get("riskler") or []) if str(x).strip()][:4]}


# ---- sayı denetimi (rakamı model üretmez; `marketing/guard.py` kalıbı)

_SENT = re.compile(r"(?<=[.!?…])\s+(?=\S)")


def _norm_num(n: str) -> str:
    return n.lstrip("0") or "0"


def _walk_numbers(v: Any, out: set[str]) -> None:
    from semantic_bridge.marketing import guard
    if isinstance(v, bool) or v is None:
        return
    if isinstance(v, (int, float)):
        # Olgunun yuvarlanmışı olgudur («14,7 yıl» → «yaklaşık 15 yıl»); işaret yazıyla söylenir («%30 düşüş»).
        for x in (v, round(v), round(v, 1), abs(v), round(abs(v)), round(abs(v), 1)):
            out |= {_norm_num(n) for n in guard.numbers_in(str(x))}
        return
    if isinstance(v, dict):
        for k, x in v.items():
            _walk_numbers(str(k), out)      # «son12_adet», «puan_100_uzerinden»: pencere ve ölçek de olgudur
            _walk_numbers(x, out)
        return
    if isinstance(v, (list, tuple)):
        for x in v:
            _walk_numbers(x, out)
        return
    out |= {_norm_num(n) for n in guard.numbers_in(str(v))}


def advice_numbers(inp: dict[str, Any]) -> set[str]:
    """Öneri metninde geçebilecek sayılar: girdideki her değer (tarih parçaları, notlardaki sayılar dahil) ve
    sayısal değerlerin yuvarlanmışı."""
    out: set[str] = set()
    _walk_numbers(inp, out)
    _walk_numbers(ADVICE_SYSTEM, out)       # istemin kendi söylediği pencere («son 12 ay»)
    return out


def _clean_text(text: str, allowed: set[str], dropped: list[dict[str, Any]]) -> str:
    """Cümle cümle: girdide olmayan sayı ya da teknoloji adı taşıyan cümle düşer."""
    from semantic_bridge.marketing import guard
    kept = []
    for sent in _SENT.split(str(text or "")):
        s = sent.strip()
        if not s:
            continue
        bad = sorted({n for n in guard.numbers_in(s) if _norm_num(n) not in allowed})
        if bad:
            dropped.append({"cumle": s[:600], "neden": "kaynaksiz-rakam", "sayilar": bad})
            continue
        if guard.has_tech_name(s):
            dropped.append({"cumle": s[:600], "neden": "teknoloji-adi"})
            continue
        kept.append(s)
    return " ".join(kept)


def _fmt_qty(v: Any) -> str:
    return f"{int(round(float(v))):,}".replace(",", ".")


def rule_summary(inp: dict[str, Any]) -> str:
    """Model özeti tutmazsa: aynı girdiden kuralla yazılan özet (her sayı girdiden)."""
    s = inp.get("satis") or {}
    parts = []
    cur, prev, pct = s.get("son12_adet"), s.get("onceki12_adet"), s.get("degisim_yuzde")
    if cur is not None:
        t = f"Son 12 ayda {_fmt_qty(cur)} adet net satış"
        if prev is not None:
            t += f", önceki 12 ayda {_fmt_qty(prev)} adet"
        if pct is not None:
            t += f" ({'artış' if pct > 0 else 'düşüş' if pct < 0 else 'değişim'} %{str(abs(pct)).replace('.', ',')})"
        parts.append(t + ".")
    days = inp.get("son_gorusme_gun_once")
    parts.append(f"Son görüşme {days} gün önce." if days is not None else "Kayıtlı görüşme yok.")
    loy = inp.get("sadakat") or {}
    if loy.get("puan_100_uzerinden") is not None:
        parts.append(f"Sadakat puanı {loy['puan_100_uzerinden']}/100" + (f" ({loy['bant']})." if loy.get("bant") else "."))
    return " ".join(parts)


def rule_recommendations(inp: dict[str, Any]) -> list[dict[str, str]]:
    """Model önerilerinin hiçbiri denetimden geçmezse: girdiden kuralla çıkan öneriler."""
    s = inp.get("satis") or {}
    loy = inp.get("sadakat") or {}
    pct, days = s.get("degisim_yuzde"), inp.get("son_gorusme_gun_once")
    recs = []
    if pct is not None and pct <= -10:
        recs.append({"title": "Satıştaki düşüşü yazarla konuşun",
                     "why": f"Son 12 ay {_fmt_qty(s.get('son12_adet') or 0)} adet, önceki 12 ay "
                            f"{_fmt_qty(s.get('onceki12_adet') or 0)} adet.", "when": "bu ay"})
    if days is None or days > 90:
        recs.append({"title": "Görüşme planlayın",
                     "why": f"Son görüşme {days} gün önce." if days is not None else "Kayıtlı görüşme yok.",
                     "when": "bu ay"})
    if loy.get("yururlukte_sozlesme") == 0 and (loy.get("toplam_sozlesme") or 0) > 0:
        recs.append({"title": "Sözleşme durumunu gözden geçirin",
                     "why": f"Yürürlükte sözleşme yok; toplam {loy['toplam_sozlesme']} sözleşme.", "when": "bu çeyrek"})
    if not recs:
        recs.append({"title": "Yazar kartını bir sonraki görüşmede birlikte gözden geçirin", "why": rule_summary(inp),
                     "when": "bu çeyrek"})
    return recs


def guard_advice(out: dict[str, Any], inp: dict[str, Any]) -> dict[str, Any]:
    """Modelin önerisini girdideki olgularla denetler. Sayısı tutmayan cümle düşer; başlığı tutmayan öneri bütünüyle
    düşer; özet ya da öneri listesi boşalırsa yerine aynı girdiden kural metni konur (işaretlenir)."""
    allowed = advice_numbers(inp)
    dropped: list[dict[str, Any]] = []
    summary = _clean_text(out.get("summary") or "", allowed, dropped)
    recs = []
    for r in out.get("recommendations") or []:
        before = len(dropped)
        title = _clean_text(r["title"], allowed, dropped)
        if len(dropped) > before or not title:
            continue
        recs.append({"title": title, "why": _clean_text(r.get("why") or "", allowed, dropped), "when": r.get("when") or ""})
    risks = [x for x in (_clean_text(r, allowed, dropped) for r in out.get("risks") or []) if x]
    rule_s, rule_r = not summary, not recs
    return {"summary": summary or rule_summary(inp), "recommendations": recs or rule_recommendations(inp), "risks": risks,
            "guard": {"dropped": len(dropped), "droppedSentences": dropped, "ruleSummary": rule_s,
                      "ruleRecommendations": rule_r}}


def make_advice(engine: sa.engine.Engine, tenant: str, user: str, contact_id: str, inp: dict[str, Any],
                chat: Callable[[list[dict[str, str]]], str]) -> dict[str, Any]:
    cid = _guid(contact_id)
    text = chat([{"role": "system", "content": ADVICE_SYSTEM},
                 {"role": "user", "content": json.dumps(inp, ensure_ascii=False, default=str)}])
    out = guard_advice(parse_advice(text), inp)
    rid = uuid.uuid4().hex
    now = _now()
    with engine.begin() as c:
        c.execute(ADVICE.insert().values(id=rid, tenant_id=tenant, contact_id=cid,
                                         input_json=json.dumps(inp, ensure_ascii=False, default=str),
                                         output_json=json.dumps(out, ensure_ascii=False), created_by=user, created_at=now))
    return dict(out, id=rid, createdBy=user, createdAt=now.isoformat(), input=inp,
                inputHash=hashlib.sha256(json.dumps(inp, sort_keys=True, default=str).encode()).hexdigest()[:12])


def latest_advice(engine: sa.engine.Engine, tenant: str, contact_id: str) -> Optional[dict[str, Any]]:
    cid = _guid(contact_id)
    with engine.connect() as c:
        r = c.execute(sa.select(ADVICE).where(ADVICE.c.tenant_id == tenant, ADVICE.c.contact_id == cid)
                      .order_by(ADVICE.c.created_at.desc()).limit(1)).first()
    if not r:
        return None
    at = r.created_at if r.created_at.tzinfo else r.created_at.replace(tzinfo=timezone.utc)
    return dict(json.loads(r.output_json), id=r.id, createdBy=r.created_by, createdAt=at.isoformat(),
                input=json.loads(r.input_json))
