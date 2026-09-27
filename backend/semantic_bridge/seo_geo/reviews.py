"""Okur yorumları: hangi çok satan kitapta hiç yorum yok, puan dağılımı ne, yorumu olup şemada puanı görünmeyen sayfa.

Kaynak (yalnız okuma):
1. T-soft ürün kaydı (`semantic_seo_products.data_json`): `CommentCount` (yorum sayısı) ve `CommentRate` (ortalama).
   Eşitlemeyle zaten gelir; ek istek yok.
2. T-soft `product/getComments` (type=comment), gece: yorumlar sayfa sayfa okunur, **yalnız ürün başına sayı, puan
   toplamı ve yıldız dağılımı** saklanır. Yorum metni, başlığı, yorumcu adı/e-postası/müşteri numarası hiç
   saklanmaz ve ekrana gelmez.
3. Şema taraması (`semantic_seo_schema`): yorumlu kitapta `no_rating` = sayfada aggregateRating yok.

İki kaynak birlikte: kitap başına yorum sayısı ikisinin büyüğü; ortalama puan önce yorumlardan (onaylı olanlar), yoksa
ürün kaydından. Yorum isteği (satın alma sonrası e-posta vb.) site/CRM sürecidir; bu modül hiçbir şey göndermez.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Iterable, Optional

import sqlalchemy as sa
from fastapi import Request

from .store import PRODUCTS, SCHEMA, _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo")

#: Yorum isteğinde öncelik: bu kadar ya da daha çok satmış, yorumsuz kitap "öncelikli" sayılır.
PRIORITY_SALES = 100
STARS = (1, 2, 3, 4, 5)

REVIEWS = sa.Table(
    "semantic_seo_reviews", _md,  # ürün başına yorum özeti (kişisel veri yok)
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("product_id", sa.String(40), primary_key=True),
    sa.Column("comments", sa.Integer, nullable=False),        # bütün yorumlar (onaylı + bekleyen)
    sa.Column("approved", sa.Integer, nullable=False),        # sitede görünen (onay bilgisi yoksa hepsi)
    sa.Column("rated", sa.Integer, nullable=False),           # puan verilmiş onaylı yorum
    sa.Column("rate_sum", sa.Float, nullable=False),
    sa.Column("stars_json", sa.Text, nullable=False),         # {"1": n, …, "5": n} onaylılar
    sa.Column("last_at", sa.String(40)),
    sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
)
_ready: set[int] = set()
_ready_lock = threading.Lock()

RECOMMENDATIONS = [
    "Satın alma sonrası yorum isteği: sipariş tesliminden 10–14 gün sonra tek e-posta/SMS, doğrudan kitabın yorum "
    "formuna bağlantıyla. Gönderimi site (T-soft) ya da CRM kampanya süreci yapar; bu ekran hiçbir şey göndermez.",
    "Önce listedeki yorumsuz çok satan kitaplar: yorum sayısı arttıkça ürün sayfası arama sonucunda yıldızla görünür "
    "(tema aggregateRating basıyorsa).",
    "Yorum sayısı sıfır olan kitapta şemaya puan basılmamalı; sahte ya da varsayılan puan Google yönergelerine aykırıdır.",
    "Yorumlara (özellikle düşük puanlılara) yayınevi adına kısa, nazik cevap verilmesi güven sinyalidir; cevap T-soft "
    "panelinden verilir.",
    "Yorumu olup şemada puanı görünmeyen sayfalar tema isteğiyle çözülür (Şema denetimi → tema isteği).",
]


def _ensure(eng: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(eng) in _ready:
            return
        REVIEWS.create(eng, checkfirst=True)
        _ready.add(id(eng))


def _num(v: Any) -> float:
    try:
        return float(str(v).replace(",", ".")) if v not in (None, "") else 0.0
    except ValueError:
        return 0.0


def _get(r: dict[str, Any], *keys: str) -> Any:
    low = {str(k).lower(): v for k, v in r.items()}
    for k in keys:
        if k.lower() in low and low[k.lower()] not in (None, ""):
            return low[k.lower()]
    return None


def _approved(r: dict[str, Any]) -> bool:
    """Onay alanı varsa ona bakılır; yoksa yorum görünür sayılır."""
    v = _get(r, "IsApproved", "Approved", "Status", "IsActive")
    if v is None:
        return True
    return str(v).strip().lower() not in ("0", "false", "hayır", "passive", "pasif")


def _type_ok(r: dict[str, Any]) -> bool:
    t = _get(r, "Type")
    return t is None or str(t).strip().lower() == "comment"


def star(v: Any) -> Optional[int]:
    """Puan 1–5 yıldıza; 0/boş → None. 5'ten büyükse 100'lük ölçek sayılır."""
    n = _num(v)
    if n <= 0:
        return None
    if n > 5:
        n = n / 20.0
    return max(1, min(5, int(round(n))))


def aggregate(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Ham yorum satırları → ürün başına {comments, approved, rated, rateSum, stars, lastAt}. Kişisel alan okunmaz."""
    out: dict[str, dict[str, Any]] = {}
    for r in rows:
        if not isinstance(r, dict) or not _type_ok(r):
            continue
        pid = str(_get(r, "ProductId") or "").strip()
        if not pid:
            continue
        a = out.setdefault(pid, {"comments": 0, "approved": 0, "rated": 0, "rateSum": 0.0,
                                 "stars": {str(s): 0 for s in STARS}, "lastAt": None})
        a["comments"] += 1
        if not _approved(r):
            continue
        a["approved"] += 1
        s = star(_get(r, "Rate", "Rating", "Point", "Score"))
        if s:
            a["rated"] += 1
            a["rateSum"] += s
            a["stars"][str(s)] += 1
        at = _get(r, "CreateDate", "CreatedAt", "DateTime", "Date", "DateTimeStamp")
        if at is not None and (a["lastAt"] is None or str(at) > a["lastAt"]):
            a["lastAt"] = str(at)[:40]
    return out


def product_rating(p: dict[str, Any]) -> tuple[int, Optional[float]]:
    """T-soft ürün kaydındaki (yorum sayısı, ortalama puan 1–5)."""
    count = int(_num(p.get("CommentCount")))
    rate = _num(p.get("CommentRate"))
    if rate <= 0:
        return count, None
    return count, round(rate / 20.0 if rate > 5 else rate, 2)


def merge(p: dict[str, Any], agg: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Ürün kaydı + yorum özeti → {count, average, stars, source}."""
    count, avg = product_rating(p)
    stars = None
    source = "ürün kaydı" if count else None
    if agg:
        if agg["approved"] >= count:
            count, source = agg["approved"], "yorumlar"
        if agg["rated"]:
            avg = round(agg["rateSum"] / agg["rated"], 2)
            stars = agg["stars"]
    return {"count": count, "average": avg, "stars": stars, "source": source}


def distribution(values: Iterable[Optional[float]]) -> dict[str, int]:
    """Kitap ortalamalarının yıldız kovaları (yuvarlanmış)."""
    out = {str(s): 0 for s in STARS}
    for v in values:
        s = star(v) if v else None
        if s:
            out[str(s)] += 1
    return out


class Reviews:
    def __init__(self, seo) -> None:
        self.seo = seo
        self._lock = threading.Lock()
        self.state: dict[str, Any] = {"running": False, "done": 0, "startedAt": None, "finishedAt": None, "error": None}

    def engine(self) -> sa.engine.Engine:
        e = self.seo.engine()
        _ensure(e)
        return e

    def start(self) -> bool:
        from . import connections

        if not connections.tsoft.configured():
            self.state["error"] = "T-soft bağlantısı tanımlı değil."
            return False
        if not self._lock.acquire(blocking=False):
            return False
        self.state.update(running=True, done=0, startedAt=iso(now()), finishedAt=None, error=None)
        threading.Thread(target=self._run, name="seo-reviews", daemon=True).start()
        return True

    def _run(self) -> None:
        from . import connections

        try:
            rows: list[dict[str, Any]] = []
            start = 0
            while True:
                page = connections.tsoft.call("product/getComments", {"type": "comment", "start": start,
                                                                      "limit": connections.PAGE}).get("data") or []
                page = page if isinstance(page, list) else []
                # Kişisel alanlar bellekte bile tutulmaz: yalnız sayım için gereken alanlar kalır.
                rows += [{k: v for k, v in r.items() if str(k).lower() in _KEEP} for r in page if isinstance(r, dict)]
                start += len(page)
                self.state["done"] = start
                if len(page) < connections.PAGE:
                    break
            agg = aggregate(rows)
            tenant, at = self.seo.tenant(), now()
            vals = [dict(tenant_id=tenant, product_id=pid[:40], comments=a["comments"], approved=a["approved"],
                         rated=a["rated"], rate_sum=a["rateSum"], stars_json=dumps(a["stars"]), last_at=a["lastAt"],
                         synced_at=at) for pid, a in agg.items()]
            with self.engine().begin() as c:
                c.execute(REVIEWS.delete().where(REVIEWS.c.tenant_id == tenant))
                for i in range(0, len(vals), 1000):
                    c.execute(REVIEWS.insert(), vals[i:i + 1000])
        except Exception as e:  # noqa: BLE001 — eski özet korunur, hata ekrana
            self.state["error"] = str(e)[:500]
            log.warning("seo reviews: %s", e)
        finally:
            self.state.update(running=False, finishedAt=iso(now()))
            self._lock.release()

    def rows(self) -> tuple[list[dict[str, Any]], Optional[str]]:
        """Aktif kitaplar çok satandan aza, yorum özetiyle."""
        from . import SALES, VIEWS, _image, _num as num

        tenant = self.seo.tenant()
        site = (self.seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")
        with self.engine().connect() as c:
            prods = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.name, PRODUCTS.c.data_json)
                              .where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True))
                              .order_by(SALES.desc(), VIEWS.desc(), PRODUCTS.c.product_id)).all()
            aggs = {r["product_id"]: {"comments": r["comments"], "approved": r["approved"], "rated": r["rated"],
                                      "rateSum": r["rate_sum"], "stars": loads(r["stars_json"], {})}
                    for r in c.execute(sa.select(REVIEWS).where(REVIEWS.c.tenant_id == tenant)).mappings()}
            last = c.execute(sa.select(sa.func.max(REVIEWS.c.synced_at)).where(REVIEWS.c.tenant_id == tenant)).scalar()
            no_rating = {pid for (pid,) in c.execute(sa.select(SCHEMA.c.product_id).where(
                SCHEMA.c.tenant_id == tenant, SCHEMA.c.issues.like("%,no_rating,%")))}
            checked = {pid for (pid,) in c.execute(sa.select(SCHEMA.c.product_id).where(SCHEMA.c.tenant_id == tenant))}
        out = []
        for pid, name, data in prods:
            p = loads(data, {})
            m = merge(p, aggs.get(pid))
            link = p.get("SeoLink")
            out.append({"id": pid, "name": name, "author": p.get("Model") or None, "image": _image(p, site),
                        "url": f"{site}/{str(link).strip('/')}" if link else None,
                        "sales": num(p.get("CountTotalSales")), "views": num(p.get("StatViews")),
                        **m, "schema": ("puan_yok" if pid in no_rating else "tamam" if pid in checked else "taranmadi")})
        return out, iso(last)


_KEEP = {"productid", "type", "rate", "rating", "point", "score", "isapproved", "approved", "status", "isactive",
         "createdate", "createdat", "datetime", "date", "datetimestamp"}

VIEWS_ = {"yorumsuz": "Çok satan, yorumsuz", "puansiz_sema": "Yorumlu ama şemada puan yok", "yorumlu": "Yorumlu kitaplar",
          "dusuk": "Ortalaması 3 ve altı"}


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    with_r = [r for r in rows if r["count"] > 0]
    total = sum(r["count"] for r in with_r)
    rated = [r for r in with_r if r["average"]]
    avg = round(sum(r["average"] * r["count"] for r in rated) / sum(r["count"] for r in rated), 2) if rated else None
    star_totals = {str(s): 0 for s in STARS}
    exact = False
    for r in with_r:
        if r["stars"]:
            exact = True
            for k, n in r["stars"].items():
                star_totals[k] = star_totals.get(k, 0) + int(n)
    return {"activeBooks": len(rows), "withReviews": len(with_r), "reviews": total, "average": avg,
            "reviewStars": star_totals if exact else None,
            "bookAverages": distribution(r["average"] for r in rated),
            "zeroTopSelling": sum(1 for r in rows if not r["count"] and r["sales"] >= PRIORITY_SALES),
            "schemaMissing": sum(1 for r in with_r if r["schema"] == "puan_yok"),
            "schemaUnchecked": sum(1 for r in with_r if r["schema"] == "taranmadi"),
            "prioritySales": PRIORITY_SALES}


def pick(rows: list[dict[str, Any]], view: str) -> list[dict[str, Any]]:
    if view == "yorumsuz":
        return [r for r in rows if not r["count"]]
    if view == "puansiz_sema":
        return [r for r in rows if r["count"] and r["schema"] == "puan_yok"]
    if view == "dusuk":
        return sorted([r for r in rows if r["average"] and r["average"] <= 3], key=lambda r: (r["average"], -r["sales"]))
    return sorted([r for r in rows if r["count"]], key=lambda r: (-r["count"], -r["sales"]))


def register(app, ctx) -> None:
    rv = Reviews(ctx.seo)

    @app.get("/api/v1/seo-geo/reviews")
    def seo_reviews(request: Request, view: str = "yorumsuz", q: str = "", start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        if view not in VIEWS_:
            from . import _err
            raise _err(422, "Bilinmeyen liste.")
        rows, last = rv.rows()
        summary = summarize(rows)
        items = pick(rows, view)
        if q.strip():
            needle = q.strip().casefold()
            items = [r for r in items if needle in f"{r['name']} {r['author'] or ''}".casefold()]
        s = max(0, start)
        return {"summary": {**summary, "lastRead": last, "state": rv.state}, "views": VIEWS_,
                "recommendations": RECOMMENDATIONS, "total": len(items), "start": s,
                "items": items[s:s + max(1, limit)]}

    @app.post("/api/v1/seo-geo/reviews/refresh")
    def seo_reviews_refresh(request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        started = rv.start()
        ctx.seo.audit(user, "run", "reviews", "Okur yorumları okuması", {"started": started})
        return {"started": started, "state": rv.state}

    def nightly() -> None:
        rv.start()  # arka planda; hemen döner

    ctx.seo.nightly.append(("reviews", nightly))
