"""M7 çapraz yazar önerisi: e-ticarette (T-soft) aynı siparişte birlikte alınan yazarlar.

Neden sipariş: CRM'deki sınıflandırma öneri için yetmiyor (2026-09-28 ölçümü): kitaplık %96 dolu ama çok geniş
(«Çocuk Kitaplığı» 3.084 kitap; en çok kitabı olan ve «Komisyon», «Anonim» gibi kayıtlar öne çıkıyor), dizi %93
dolu ama çoğunlukla tek yazarın serisi, tür metni %44. Birlikte alınma gerçek okur davranışıdır.

- **Eşitleme** (`sync`): T-soft `order/get` (`FetchProductData`, yalnız okuma; T-soft'a yazma yasak) siparişlerinden
  yalnız sipariş no, gün, durum ve ürün satırları (ürün no, barkod, adet) saklanır. **Müşteri adı, telefonu, adresi,
  e-postası, müşteri no hiç okunmaz/saklanmaz.** İlk tur 2022-12'den bugüne; sonraki turlar son `RESCAN_DAYS` günü
  yeniden okur (iptal/iade sonradan işlenir).
- **Kitap → yazar**: ürün barkodu = CRM kitap kartının `new_ean13`'ü; yazar = eser katılımında «Yazar» rolü.
- **Birlikte alınma** (`compute`): bir siparişte **farklı kitaplarıyla** geçen iki yazar bir kez sayılır (ortak
  yazılmış tek kitap çift üretmez). İptal/iade durumundaki sipariş sayılmaz (durum adı veriden okunur).
  Eşik: en az `MIN_ORDERS` ortak sipariş ve `lift` = ortak / beklenen ≥ `MIN_LIFT` — her siparişte geçen kayıtlar
  («Anonim» gibi) beklenenden sık çıkmadığı için kendiliğinden düşer. Her çiftte en sık birlikte alınan kitaplar.
"""
from __future__ import annotations

import json
import logging
import re
import threading
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

log = logging.getLogger("semantic.author_copurchase")
_md = sa.MetaData()

START = "2022-12-01"
RESCAN_DAYS = 60
PAGE = 500
MIN_ORDERS = 3
MIN_LIFT = 1.5
PAGE_SIZE = 20
#: Sayılmayan sipariş durumları: durum adında geçen kelime (adlar T-soft'tan gelir).
EXCLUDED_STATUS = ("iptal", "iade")

ORDERS = sa.Table(
    "semantic_shop_orders", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("order_id", sa.String(40), primary_key=True),
    sa.Column("day", sa.Date, nullable=False, index=True),
    sa.Column("status_id", sa.String(20)),
    sa.Column("status", sa.String(120)),
    sa.Column("deleted", sa.Boolean, nullable=False, default=False),
    sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
)
LINES = sa.Table(
    "semantic_shop_order_lines", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("line_id", sa.String(40), primary_key=True),
    sa.Column("order_id", sa.String(40), nullable=False, index=True),
    sa.Column("product_id", sa.String(40)),
    sa.Column("barcode", sa.String(40), index=True),
    sa.Column("quantity", sa.Integer),
)
PAIRS = sa.Table(
    "semantic_author_copurchase", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("a", sa.String(40), primary_key=True),
    sa.Column("b", sa.String(40), primary_key=True),
    sa.Column("b_name", sa.String(300)),
    sa.Column("orders", sa.Integer, nullable=False),
    sa.Column("a_orders", sa.Integer, nullable=False),
    sa.Column("b_orders", sa.Integer, nullable=False),
    sa.Column("lift", sa.Float, nullable=False),
    sa.Column("books_json", sa.Text, nullable=False, default="[]"),
)
RUNS = sa.Table(
    "semantic_author_copurchase_runs", _md,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
    sa.Column("since", sa.Date),
    sa.Column("orders_read", sa.Integer),
    sa.Column("orders_total", sa.Integer),
    sa.Column("orders_counted", sa.Integer),
    sa.Column("lines", sa.Integer),
    sa.Column("lines_matched", sa.Integer),
    sa.Column("pairs", sa.Integer),
    sa.Column("error", sa.Text),
)

_ready: set[int] = set()
_lock = threading.Lock()
_running = threading.Lock()


class CopurchaseError(ValueError):
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


def ean_key(v: Any) -> str:
    return re.sub(r"[^0-9]", "", str(v or ""))


def _day(v: Any) -> Optional[date]:
    t = str(v or "").strip()
    try:
        return date.fromisoformat(t[:10])
    except ValueError:
        return None


# ------------------------------------------------------------------------------------------ eşitleme

def _since(engine: sa.engine.Engine, tenant: str) -> date:
    with engine.connect() as c:
        last = c.execute(sa.select(sa.func.max(ORDERS.c.day)).where(ORDERS.c.tenant_id == tenant)).scalar()
    if not last:
        return date.fromisoformat(START)
    last = last if isinstance(last, date) else date.fromisoformat(str(last)[:10])
    return last - timedelta(days=RESCAN_DAYS)


def _order_rows(o: dict[str, Any], tenant: str, now: datetime) -> tuple[Optional[dict[str, Any]], list[dict[str, Any]]]:
    """T-soft sipariş kaydı → saklanan alanlar. Müşteriye ait hiçbir alan okunmaz."""
    oid = str(o.get("OrderId") or "").strip()
    day = _day(o.get("OrderDate"))
    if not oid or day is None:
        return None, []
    order = {"tenant_id": tenant, "order_id": oid, "day": day, "status_id": str(o.get("OrderStatusId") or "")[:20] or None,
             "status": (str(o.get("OrderStatus") or "")[:120] or None), "deleted": str(o.get("IsDeleted") or "0") == "1",
             "synced_at": now}
    lines = []
    for i, d in enumerate(o.get("OrderDetails") or []):
        if not isinstance(d, dict):
            continue
        lid = str(d.get("OrderProductId") or f"{oid}-{i}")
        try:
            qty = int(float(d.get("Quantity") or 0))
        except (TypeError, ValueError):
            qty = None
        lines.append({"tenant_id": tenant, "line_id": lid[:40], "order_id": oid, "product_id": str(d.get("ProductId") or "")[:40] or None,
                      "barcode": ean_key(d.get("Barcode"))[:40] or None, "quantity": qty})
    return order, lines


def sync(engine: sa.engine.Engine, tenant: str, call: Callable[[str, dict[str, Any]], dict[str, Any]],
         since: Optional[date] = None, now: Optional[datetime] = None) -> dict[str, Any]:
    """Siparişleri `since` gününden bugüne sayfa sayfa okur; her siparişin satırları baştan yazılır."""
    now = now or _now()
    since = since or _since(engine, tenant)
    start, read, lines_n, total = 0, 0, 0, None
    while True:
        data = call("order/get", {"OrderDateTimeStart": f"{since.isoformat()} 00:00:00", "FetchProductData": True,
                                  "start": start, "limit": PAGE})
        rows = data.get("data") or []
        if total is None and isinstance(data.get("summary"), dict):
            try:
                total = int(data["summary"].get("totalRecordCount"))
            except (TypeError, ValueError):
                total = None
        parsed = [_order_rows(o, tenant, now) for o in rows if isinstance(o, dict)]
        parsed = [(o, ls) for o, ls in parsed if o]
        if parsed:
            ids = [o["order_id"] for o, _ in parsed]
            with engine.begin() as c:
                c.execute(LINES.delete().where(LINES.c.tenant_id == tenant, LINES.c.order_id.in_(ids)))
                c.execute(ORDERS.delete().where(ORDERS.c.tenant_id == tenant, ORDERS.c.order_id.in_(ids)))
                c.execute(ORDERS.insert(), [o for o, _ in parsed])
                all_lines = [l for _, ls in parsed for l in ls]
                # Aynı satır kimliği iki kez gelirse (T-soft sayfalama kayması) sonuncusu kalır.
                uniq = {l["line_id"]: l for l in all_lines}
                if uniq:
                    c.execute(LINES.insert(), list(uniq.values()))
                lines_n += len(uniq)
        read += len(rows)
        if len(rows) < PAGE:
            break
        start += PAGE
    return {"since": since.isoformat(), "read": read, "total": total, "lines": lines_n}


# ------------------------------------------------------------------------------------------ CRM eşlemesi

def book_authors_sql(schema: str) -> str:
    """Barkod (EAN-13) → kitap adı ve «Yazar» rolündeki kişiler. Pasif kitap da eşlenir (geçmiş siparişler için)."""
    from semantic_bridge.editorial import _prefix
    p = _prefix(schema)
    return (
        "SELECT b.new_ean13 AS ean, b.new_name AS kitap, e.new_Katilimsaglayan AS kisi, k.FullName AS ad"
        f" FROM {p}new_kitapBase b"
        f" JOIN {p}new_eserkatilimBase e ON e.new_Kitap = b.new_kitapId AND e.statecode = 0"
        f" JOIN {p}new_katilimcitipiBase t ON t.new_katilimcitipiId = e.new_katilimciTipi AND t.new_name = N'Yazar'"
        f" JOIN {p}ContactBase k ON k.ContactId = e.new_Katilimsaglayan"
        " WHERE b.new_ean13 IS NOT NULL AND e.new_Katilimsaglayan IS NOT NULL"
    )


def book_map(rows: Iterable[dict[str, Any]]) -> tuple[dict[str, set[str]], dict[str, str], dict[str, str]]:
    """(barkod → yazar kimlikleri, barkod → kitap adı, yazar → ad)."""
    authors: dict[str, set[str]] = defaultdict(set)
    titles: dict[str, str] = {}
    names: dict[str, str] = {}
    for r in rows:
        r = {str(k).lower(): v for k, v in r.items()}
        ean = ean_key(r.get("ean"))
        kid = str(r.get("kisi") or "").strip().lower()
        if not ean or not kid:
            continue
        authors[ean].add(kid)
        if r.get("kitap"):
            titles.setdefault(ean, str(r["kitap"]).strip())
        if r.get("ad"):
            names.setdefault(kid, str(r["ad"]).strip())
    return authors, titles, names


# ------------------------------------------------------------------------------------------ hesap

def _same_name(x: Optional[str], y: Optional[str]) -> bool:
    fold = lambda v: re.sub(r"\s+", " ", (v or "").replace("İ", "i").replace("I", "ı").lower()).strip()  # noqa: E731
    return bool(x) and fold(x) == fold(y)


def counted(status: Optional[str], deleted: bool) -> bool:
    # Türkçe küçük harf: «İptal».casefold() «i̇ptal» (ek noktalı) verir ve «iptal» ile eşleşmez.
    s = (status or "").replace("İ", "i").replace("I", "ı").lower()
    return not deleted and not any(w in s for w in EXCLUDED_STATUS)


def orders_stmt(tenant: str):
    """Eşitlenmiş e-ticaret siparişleri (yalnız no, durum, silinme)."""
    return sa.select(ORDERS.c.order_id, ORDERS.c.status, ORDERS.c.deleted).where(ORDERS.c.tenant_id == tenant)


def lines_stmt(tenant: str):
    """Sipariş satırlarının barkodu (kitap → yazar eşlemesi barkodla)."""
    return sa.select(LINES.c.order_id, LINES.c.barcode).where(LINES.c.tenant_id == tenant)


def compute(engine: sa.engine.Engine, tenant: str, authors: dict[str, set[str]], titles: dict[str, str],
            names: dict[str, str]) -> dict[str, Any]:
    """Bütün saklı siparişlerden yazar çiftleri; tablo baştan yazılır."""
    with engine.connect() as c:
        orders = {r.order_id: counted(r.status, bool(r.deleted)) for r in c.execute(orders_stmt(tenant))}
        by_order: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
        lines = matched = 0
        for oid, bc in c.execute(lines_stmt(tenant)):
            if not orders.get(oid):
                continue
            lines += 1
            for a in authors.get(bc or "", ()):
                by_order[oid][a].add(bc)
            if bc in authors:
                matched += 1
    n: Counter = Counter()
    pair: Counter = Counter()
    books: dict[tuple[str, str], Counter] = defaultdict(Counter)
    for oid, amap in by_order.items():
        for a in amap:
            n[a] += 1
        ks = sorted(amap)
        for i, a in enumerate(ks):
            for b in ks[i + 1:]:
                # Aynı ortak kitap tek başına çift üretmez: iki yazarın en az birer farklı kitabı olmalı.
                sa_, sb_ = amap[a], amap[b]
                if sa_ == sb_ and len(sa_) == 1:
                    continue
                pair[(a, b)] += 1
                for x in sa_ - sb_ or sa_:
                    for y in sb_ - sa_ or sb_:
                        if x != y:
                            books[(a, b)][(x, y)] += 1
    total = len(by_order)
    out = []
    for (a, b), k in pair.items():
        if k < MIN_ORDERS:
            continue
        # CRM'de aynı yazar için mükerrer kişi kaydı var (2026-09-28: «Metin Özdamarlar» kendine öneriliyordu).
        if _same_name(names.get(a), names.get(b)):
            continue
        lift = (k * total) / (n[a] * n[b]) if n[a] and n[b] else 0.0
        if lift < MIN_LIFT:
            continue
        top = books[(a, b)].most_common(3)
        ab = [{"a": titles.get(x), "b": titles.get(y), "orders": c_} for (x, y), c_ in top]
        ba = [{"a": titles.get(y), "b": titles.get(x), "orders": c_} for (x, y), c_ in top]
        out.append({"tenant_id": tenant, "a": a, "b": b, "b_name": names.get(b), "orders": k, "a_orders": n[a],
                    "b_orders": n[b], "lift": lift, "books_json": json.dumps(ab, ensure_ascii=False)})
        out.append({"tenant_id": tenant, "a": b, "b": a, "b_name": names.get(a), "orders": k, "a_orders": n[b],
                    "b_orders": n[a], "lift": lift, "books_json": json.dumps(ba, ensure_ascii=False)})
    with engine.begin() as c:
        c.execute(PAIRS.delete().where(PAIRS.c.tenant_id == tenant))
        for i in range(0, len(out), 1000):
            c.execute(PAIRS.insert(), out[i:i + 1000])
    return {"orders_counted": total, "lines": lines, "lines_matched": matched, "pairs": len(out) // 2,
            "orders_total": sum(1 for v in orders.values() if v)}


def run(engine: sa.engine.Engine, tenant: str, call: Callable[[str, dict[str, Any]], dict[str, Any]],
        fetch_all: Callable[[str], list[dict[str, Any]]], schema: str) -> dict[str, Any]:
    """Gece turu: eşitle, CRM eşlemesini oku, çiftleri hesapla. Aynı anda ikinci tur başlamaz."""
    if not _running.acquire(blocking=False):
        return {"skipped": "Tur zaten sürüyor."}
    try:
        ensure(engine)
        with engine.begin() as c:
            rid = c.execute(RUNS.insert().values(tenant_id=tenant, started_at=_now())).inserted_primary_key[0]
        try:
            s = sync(engine, tenant, call)
            authors, titles, names = book_map(fetch_all(book_authors_sql(schema)))
            r = compute(engine, tenant, authors, titles, names)
            with engine.begin() as c:
                c.execute(RUNS.update().where(RUNS.c.id == rid).values(
                    finished_at=_now(), since=date.fromisoformat(s["since"]), orders_read=s["read"], **r))
            return dict(s, **r)
        except Exception as e:
            log.exception("copurchase run failed")
            with engine.begin() as c:
                c.execute(RUNS.update().where(RUNS.c.id == rid).values(finished_at=_now(), error=str(e)[:2000]))
            raise
    finally:
        _running.release()


def last_run_stmt(tenant: str):
    return (sa.select(RUNS).where(RUNS.c.tenant_id == tenant, RUNS.c.finished_at.isnot(None), RUNS.c.error.is_(None))
            .order_by(RUNS.c.id.desc()).limit(1))


def related_stmts(tenant: str, contact_id: str, page: int) -> dict[str, Any]:
    """Birlikte alınan yazarlar: toplam, sayfa (beklenenden fazla ortak siparişe göre), yazarın kendi sipariş sayısı."""
    where = [PAIRS.c.tenant_id == tenant, PAIRS.c.a == contact_id]
    excess = PAIRS.c.orders - PAIRS.c.orders / PAIRS.c.lift
    return {
        "total": sa.select(sa.func.count()).select_from(PAIRS).where(*where),
        "rows": (sa.select(PAIRS).where(*where).order_by(excess.desc(), PAIRS.c.orders.desc(), PAIRS.c.b)
                 .offset(max(0, int(page)) * PAGE_SIZE).limit(PAGE_SIZE)),
        "own": sa.select(PAIRS.c.a_orders).where(*where).limit(1),
    }


def last_run(engine: sa.engine.Engine, tenant: str) -> Optional[dict[str, Any]]:
    with engine.connect() as c:
        r = c.execute(last_run_stmt(tenant)).first()
    if r is None:
        return None
    m = r._mapping
    return {"at": m["finished_at"].isoformat() if m["finished_at"] else None, "orders": m["orders_counted"],
            "linesMatched": m["lines_matched"], "lines": m["lines"], "pairs": m["pairs"]}


def related(engine: sa.engine.Engine, tenant: str, contact_id: str, page: int = 0) -> dict[str, Any]:
    """Bir yazarla birlikte alınan yazarlar: beklenenden fazla ortak siparişe göre, sayfa sayfa (toplam sayı ile)."""
    cid = (contact_id or "").strip().lower()
    if not re.match(r"^[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}$", cid):
        raise CopurchaseError("CRM kişi kimliği geçerli değil.")
    p = max(0, int(page))
    # Sıra: beklenenden fazla ortak sipariş = ortak × (1 − 1/lift). Yalnız ortak sayıya göre sıralanınca her
    # yazarın başına aynı çok satanlar geliyordu (2026-09-28 ölçümü: lift ~1,7); bu sıra yazara özgü birlikteliği öne alır.
    st = related_stmts(tenant, cid, p)
    with engine.connect() as c:
        total = c.execute(st["total"]).scalar() or 0
        rows = c.execute(st["rows"]).fetchall()
        own = c.execute(st["own"]).scalar()
    items = [{"contactId": r.b, "name": r.b_name, "orders": r.orders, "theirOrders": r.b_orders, "lift": round(r.lift, 2),
              "excess": round(r.orders - r.orders / r.lift) if r.lift else 0,
              "share": round(100 * r.orders / r.a_orders, 1) if r.a_orders else None,
              "books": json.loads(r.books_json or "[]")} for r in rows]
    return {"items": items, "total": int(total), "page": p, "pageSize": PAGE_SIZE, "authorOrders": own,
            "minOrders": MIN_ORDERS, "minLift": MIN_LIFT, "run": last_run(engine, tenant)}
