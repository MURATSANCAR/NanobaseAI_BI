"""Kitap Tasarım Stüdyosu — kapak arşivi: besleme ve köprü uçları.

Arşiv stüdyo servisinde durur (apps/editor/src/editor/production/library.py): test sunucusu da müşteri VM'i de
aynı arşivi görür. Köprü iki iş yapar:

1. **Besleme** (`feed`): SEO modülünün T-soft ürün tablosu (ad, yazar = `Model`, barkod, sitedeki kategori yolu,
   kapak görselinin adresi, satış) ile barkodla bağlı CRM kitap kartı (çizer, okur kitlesi, yaş, tür) birleşir;
   yalnız kitaplar (barkodu ISBN) girer, beslemenin tam listesinde olmayan eski kayıtlar stüdyoda gizlenir;
   stüdyoya 1000'erli gönderilir; görselleri stüdyo kendisi indirir. SEO gece işinin sonunda (T-soft eşitlemesi
   bittikten sonra) kendiliğinden koşar; yönetici ekrandan da başlatabilir. T-soft tanımlı olmayan ortamda (müşteri
   VM'i) ürün tablosu boştur, besleme hiçbir şey göndermez.
2. **Vekil uçlar**: `/api/v1/editorial/studio/library…` → stüdyonun `/v1/studio/library…` uçları. Oturum zorunlu
   (sayfa kapısı «kitap-tasarim»); beslemeyi elle başlatmak yalnız yönetici.

app.py'de SEO modülü kurulduktan sonra bağlanır:
    from semantic_bridge import editorial_studio_library
    editorial_studio_library.register(app, {"auth": _books, "audit": admin_mod.audit, "seo": app.state.seo_geo})
"""
from __future__ import annotations

import json
import logging
import re
import threading
import unicodedata
from typing import Any, Callable
from urllib.parse import urlencode

from fastapi import HTTPException, Query, Request
from fastapi.responses import Response

from semantic_bridge import editorial_studio

log = logging.getLogger(__name__)

CID = re.compile(r"^[a-z]{2,10}-[A-Za-z0-9_.-]{1,60}$")
AUDIENCES = {"CHILD", "YOUNG", "ADULT"}
BATCH = 1000
# Görselin büyükten küçüğe anahtarları (T-soft `ImageUrls` öğesi); ilk dolu olan alınır.
IMAGE_KEYS = ("Original", "Big", "Large", "ImageUrl", "Medium", "Small")
_feed_lock = threading.Lock()
feed_state: dict[str, Any] = {"running": False, "sent": 0, "startedAt": None, "finishedAt": None, "error": None,
                              "result": None}


# ------------------------------------------------------------------ besleme
def _fold(s: Any) -> str:
    return str(s or "").casefold().translate(str.maketrans("çğıöşü", "cgiosu"))


def _audience(v: Any) -> str | None:
    """CRM okur kitlesi etiket ya da sayı olarak gelir («Çocuk», 1 …)."""
    if v in AUDIENCES:
        return v
    s = _fold(v).strip()
    if s in ("1",) or s.startswith("cocuk"):
        return "CHILD"
    if s in ("2",) or s.startswith("genc"):
        return "YOUNG"
    if s in ("3",) or s.startswith("yetiskin"):
        return "ADULT"
    return None


def _split(v: Any) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x or "").strip()]
    return [x.strip() for x in re.split(r"\s*[,;]\s*", str(v or "")) if x.strip()]


def _url(raw: Any, site: str) -> str | None:
    s = str(raw or "").strip()
    if not s:
        return None
    if s.startswith("//"):
        return "https:" + s
    return s if s.startswith("http") else f"{site}/{s.lstrip('/')}"


def image_url(p: dict[str, Any], site: str) -> str | None:
    """Ürünün en büyük kapak görseli. `ImageUrls` sözlük listesi; yoksa `ImageUrlCdn` / `ImageUrl` (dosya adı)."""
    imgs = p.get("ImageUrls") or []
    if imgs and isinstance(imgs[0], dict):
        for k in IMAGE_KEYS:
            if imgs[0].get(k):
                return _url(imgs[0][k], site)
    if imgs and isinstance(imgs[0], str):
        return _url(imgs[0], site)
    return _url(p.get("ImageUrlCdn") or p.get("ImageUrl"), site)


def category_path(p: dict[str, Any]) -> list[str]:
    """Sitedeki varsayılan kategori yolu: `DefaultCategoryPath` (üstler, «>» ile) + `DefaultCategoryName` (yaprak)."""
    parts = [x.strip() for x in f"{p.get('DefaultCategoryPath') or ''}>{p.get('DefaultCategoryName') or ''}".split(">")]
    out: list[str] = []
    for x in parts:
        if x and (not out or out[-1] != x):
            out.append(x)
    return out


def all_categories(p: dict[str, Any]) -> list[list[str]]:
    """`FetchAllCategories` ile gelen kategori listesi; alan adı T-soft sürümüne göre değişebildiği için bilinen
    adların hepsine bakılır. Her öğe yol metni ya da {Path/CategoryPath, Name/CategoryName} olabilir."""
    raw = next((p[k] for k in ("Categories", "AllCategories", "CategoryList", "ProductCategories")
                if isinstance(p.get(k), list)), [])
    out: list[list[str]] = []
    for c in raw[:30]:
        if isinstance(c, str):
            path = [x.strip() for x in c.split(">") if x.strip()]
        elif isinstance(c, dict):
            base = c.get("CategoryPath") or c.get("Path") or ""
            name = c.get("CategoryName") or c.get("Name") or ""
            path = [x.strip() for x in f"{base}>{name}".split(">") if x.strip()]
        else:
            continue
        if path and path not in out:
            out.append(path)
    return out


ISBN_TAIL = re.compile(r"97[89]\d{10}$")


def is_book(p: dict[str, Any]) -> bool:
    """Kitap = barkodu ISBN (978/979 ile başlayan 13 hane) ya da ISBN'le biten set barkodu («1» + ISBN). Sitede
    oyun, oyuncak, kırtasiye de satılıyor ve CRM'de stok kartları var; kapak arşivine yalnız kitaplar girer."""
    return bool(ISBN_TAIL.search(re.sub(r"\D", "", str(p.get("Barcode") or ""))))


def item(p: dict[str, Any], crm_book: dict[str, Any] | None, site: str) -> dict[str, Any] | None:
    pid = str(p.get("ProductId") or "").strip()
    title = str(p.get("ProductName") or "").strip()
    if not pid or not title:
        return None
    b = crm_book or {}
    link = p.get("SeoLink") or p.get("Url") or p.get("ProductUrl")
    active = p.get("IsActive")
    try:
        sales = int(float(str(p.get("CountTotalSales") or 0).replace(",", ".")))
    except ValueError:
        sales = 0
    return {
        "id": f"tsoft-{pid}", "title": title,
        "authors": _split(b.get("authors")) or _split(p.get("Model")),
        "illustrators": _split(b.get("illustrators")),
        "isbn": b.get("isbn") or (str(p.get("Barcode") or "").strip() or None),
        "brand": str(p.get("Brand") or "").strip() or None,
        "category": category_path(p), "categories": all_categories(p),
        "audience": _audience(b.get("audience")), "age_from": b.get("ageFrom"), "age_to": b.get("ageTo"),
        "genres": _split(b.get("genres")),
        "on_sale": True if active is None else str(active).strip().lower() in ("true", "1", "yes", "evet"),
        "sales": max(0, sales), "page_url": _url(link, site), "image_url": image_url(p, site),
    }


def build(seo) -> tuple[list[dict[str, Any]], int]:
    """SEO modülünün tablolarından arşiv kayıtları (T-soft ürünü + barkodla CRM kartı) ve atılan kitap dışı ürün sayısı."""
    import sqlalchemy as sa

    from semantic_bridge.seo_geo import crm as crm_mod
    from semantic_bridge.seo_geo.store import CRM_BOOKS, PRODUCTS

    eng, tenant = seo.engine(), seo.tenant()
    site = (seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")
    with eng.connect() as c:
        books = {r.ean: json.loads(r.data_json) for r in
                 c.execute(sa.select(CRM_BOOKS.c.ean, CRM_BOOKS.c.data_json).where(CRM_BOOKS.c.tenant_id == tenant))}
        products = [json.loads(r.data_json) for r in
                    c.execute(sa.select(PRODUCTS.c.data_json).where(PRODUCTS.c.tenant_id == tenant))]
    out, not_books = [], 0
    for p in products:
        if not is_book(p):
            not_books += 1
            continue
        it = item(p, books.get(crm_mod.ean_key(p.get("Barcode"))), site)
        if it:
            out.append(it)
    return out, not_books


def header_name(name: str) -> str:
    """X-Editor HTTP başlığıdır; başlık yalnız ASCII taşır («zamanlayıcı» → «zamanlayici»)."""
    s = unicodedata.normalize("NFKD", str(name or "").translate(str.maketrans("ıİ", "iI")))
    return "".join(ch for ch in s if ord(ch) < 128 and not unicodedata.combining(ch)).strip()[:200] or "zamanlayici"


def feed(seo, editor: str = "zamanlayici") -> dict[str, Any]:
    """Arşivi besler. Aynı anda ikinci besleme başlamaz; ürün yoksa (T-soft tanımlı değil) hiçbir şey göndermez."""
    from datetime import datetime, timezone

    if not _feed_lock.acquire(blocking=False):
        return {"started": False, "reason": "besleme sürüyor"}
    feed_state.update(running=True, sent=0, startedAt=datetime.now(timezone.utc).isoformat(), finishedAt=None,
                      error=None, result=None)
    try:
        items, not_books = build(seo)
        if not items:
            feed_state["result"] = {"items": 0, "note": "T-soft ürünü yok"}
            return {"started": True, "items": 0}
        total = {"stored": 0, "new": 0, "skipped": 0}
        for i in range(0, len(items), BATCH):
            r = editorial_studio.post_json("/v1/studio/library/items", {"items": items[i:i + BATCH]}, header_name(editor),
                                           timeout=300)
            for k in total:
                total[k] += int(r.get(k) or 0)
            feed_state["sent"] = min(len(items), i + BATCH)
        # Tam liste: listede olmayan eski kayıtlar (kitap olmayan ürün, T-soft'tan silinen ürün) stüdyoda gizlenir.
        kept = editorial_studio.post_json("/v1/studio/library/retain", {"source": "tsoft", "ids": [x["id"] for x in items]},
                                          header_name(editor), timeout=300)
        with_image = sum(1 for x in items if x["image_url"])
        with_crm = sum(1 for x in items if x["audience"] or x["illustrators"] or x["genres"])
        feed_state["result"] = {"items": len(items), "notBooks": not_books, "withImage": with_image, "withCrm": with_crm,
                                **total, "hidden": kept.get("hidden", 0), **({"retainSkipped": kept["skipped"]}
                                                                              if kept.get("skipped") else {})}
        log.info("kapak arşivi beslendi: %s", feed_state["result"])
        return {"started": True, **feed_state["result"]}
    except Exception as e:  # noqa: BLE001
        feed_state["error"] = str(e)[:500]
        log.exception("kapak arşivi beslemesi başarısız")
        raise
    finally:
        feed_state.update(running=False, finishedAt=datetime.now(timezone.utc).isoformat())
        _feed_lock.release()


# ------------------------------------------------------------------ vekil
def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    q = {k: v for k, v in (params or {}).items() if v is not None and v != ""}
    if params and params.get("cat") == "":
        q["cat"] = ""                                   # boş kategori = kategorisiz kapaklar
    return editorial_studio.get_json("/v1/studio/library" + path + (("?" + urlencode(q)) if q else ""))


def _cid(cid: str) -> str:
    if not CID.match(cid or ""):
        raise ValueError("Kapak bulunamadı.")
    return cid


def register(app, deps: dict[str, Any]) -> None:
    auth: Callable[[Request], Any] = deps["auth"]
    audit: Callable[..., None] = deps.get("audit") or (lambda *a, **k: None)
    seo = deps.get("seo")

    if seo is not None:
        seo.nightly.append(("cover-library", lambda: feed(seo)))

    def call(fn, *a):
        try:
            return fn(*a)
        except editorial_studio.StudioError as e:
            raise HTTPException(e.status if e.status in (400, 404, 409, 413) else 400, str(e)) from None
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        except Exception:  # noqa: BLE001 — ayrıntı günlükte; teknik hata metni ekrana gitmez
            log.exception("studio library call failed")
            raise HTTPException(502, "Kapak arşivi şu an açılamıyor.") from None

    @app.get("/api/v1/editorial/studio/library")
    def editorial_studio_library_stats(request: Request) -> dict[str, Any]:
        auth(request)
        return {**call(_get, ""), "feed": dict(feed_state)}

    @app.get("/api/v1/editorial/studio/library/categories")
    def editorial_studio_library_categories(request: Request, audience: str | None = None) -> Any:
        auth(request)
        return call(_get, "/categories", {"audience": audience if audience in AUDIENCES else None})

    @app.get("/api/v1/editorial/studio/library/covers")
    def editorial_studio_library_covers(request: Request, cat: str | None = Query(None, max_length=600),
                                        q: str | None = Query(None, max_length=200), audience: str | None = None,
                                        sort: str = "sales", page: int = Query(1, ge=1),
                                        size: int = Query(60, ge=1, le=120)) -> Any:
        auth(request)
        return call(_get, "/covers", {"cat": cat, "q": q, "audience": audience if audience in AUDIENCES else None,
                                      "sort": sort if sort in ("sales", "title") else "sales", "page": page,
                                      "size": size})

    @app.get("/api/v1/editorial/studio/library/covers/{cid}")
    def editorial_studio_library_cover(cid: str, request: Request) -> Any:
        auth(request)
        return call(lambda c: _get(f"/covers/{_cid(c)}"), cid)

    @app.get("/api/v1/editorial/studio/library/covers/{cid}/image")
    def editorial_studio_library_image(cid: str, request: Request, w: int = Query(360, ge=64, le=2400)):
        auth(request)
        data, mime = call(lambda c: editorial_studio.get_bytes(f"/v1/studio/library/covers/{_cid(c)}/image?w={w}",
                                                                {"image/webp", "image/png", "image/jpeg"}), cid)
        # Kapak görseli değişince adres değişmez; tarayıcıda bir gün kalması yeter (gece beslemesi günde bir).
        return Response(content=data, media_type=mime, headers={"Cache-Control": "private, max-age=86400"})

    @app.post("/api/v1/editorial/studio/library/refresh")
    def editorial_studio_library_refresh(request: Request) -> dict[str, Any]:
        engine, _tenant, user, is_admin = auth(request)
        if not is_admin:
            raise HTTPException(403, "Kapak arşivini yalnız yönetici yeniler.")
        if seo is None:
            raise HTTPException(409, "Bu ortamda besleme kaynağı yok.")
        if feed_state["running"]:
            return {"started": False, "feed": dict(feed_state)}
        threading.Thread(target=lambda: _safe_feed(seo, user), name="cover-library-feed", daemon=True).start()
        audit(engine, user, "update", "studio_library", "feed", "kapak arşivi beslemesi başlatıldı", None)
        return {"started": True}


def _safe_feed(seo, user: str) -> None:
    try:
        feed(seo, user)
    except Exception:  # noqa: BLE001 — feed_state.error ekranda görünür
        pass
