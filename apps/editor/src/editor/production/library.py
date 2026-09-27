"""Kapak arşivi: yayınevinin yayımlanmış kitap kapakları, sitedeki kategori ağacıyla (tablo ed.cover_library).

Köprü besler (`upsert`): T-soft ürünü (ad, yazar, barkod, sitedeki kategori yolu, kapak görselinin adresi, satış) ile
barkodla bağlı CRM kitap kartı (çizer, okur kitlesi, yaş, tür). Görseli stüdyo kendisi indirir (`fetch_pending`):
GPU ile köprü arasındaki tünel saniyede ~0,8 MB taşır, binlerce kapağı oradan geçirmek saatler sürerdi; yayınevinin
sitesi ise GPU'dan doğrudan açılıyor (web_cover.py aynı yolu kullanıyor).

Kategori ağacı ürünün sitedeki VARSAYILAN kategori yolundan kurulur («Çocuk Kitapları > Masal»). Ürünün bağlı
olduğu öteki yollar (`categories`) saklanır ama ağaca girmez: «Çok Satanlar», «Yeni Çıkanlar» gibi vitrin
kategorileri her kitabı ikinci kez sayar ve ağacı tür yerine kampanyaya böler.

Ekran binlerce kaydı süzer ve sayfalar; bütün arşiv bellekte tutulur (on binlerce küçük kayıt) ve tablonun son
değişikliği değişince yeniden okunur. Kayıt silinmez: satıştan kalkan kitabın kapağı da arşivin parçasıdır.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import re
import threading
import unicodedata
from pathlib import Path
from typing import Any

import httpx

from .. import db
from ..config import settings

log = logging.getLogger("editor.library")

ID = re.compile(r"^[a-z]{2,10}-[A-Za-z0-9_.-]{1,60}$")
AUDIENCES = ("CHILD", "YOUNG", "ADULT")
SEP = " > "
UA = {"user-agent": "Mozilla/5.0 (editor-cover-library)"}
MAX_BYTES = 25 * 1024 * 1024
PARALLEL = 4                       # yayınevinin sitesine aynı anda en çok bu kadar istek
BATCH = 200
EXT = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}

_state_lock = threading.Lock()
_fetch = {"running": False, "done": 0, "failed": 0, "started": None, "finished": None}
_cache: dict[str, Any] = {"stamp": None, "rows": []}
_cache_lock = threading.Lock()


def root() -> Path:
    d = Path(settings().storage) / "library" / "covers"
    d.mkdir(parents=True, exist_ok=True)
    return d


# ------------------------------------------------------------------ yardımcılar
ASCII = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def fold(s: str | None) -> str:
    """Arama için: Türkçe harf ASCII'ye, büyük/küçük ve noktalama farkı yok («Şükrü» = «sukru»)."""
    s = unicodedata.normalize("NFKC", s or "").casefold().translate(ASCII)
    s = "".join(ch for ch in unicodedata.normalize("NFKD", s) if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def _text(v: Any, n: int = 500) -> str | None:
    s = re.sub(r"\s+", " ", str(v or "")).strip()
    return s[:n] or None


def _names(v: Any) -> list[str]:
    if isinstance(v, str):
        v = re.split(r"\s*[,;]\s*", v)
    if not isinstance(v, list):
        return []
    out: list[str] = []
    for x in v:
        t = _text(x, 200)
        if t and t not in out:
            out.append(t)
    return out


def _path(v: Any) -> list[str]:
    """«A > B > C» ya da ["A","B","C"] → ["A","B","C"]; boş parçalar ve art arda tekrar (A > A) düşer."""
    parts = v if isinstance(v, list) else str(v or "").split(">")
    out: list[str] = []
    for p in parts:
        t = _text(p, 120)
        if t and (not out or out[-1] != t):
            out.append(t)
    return out[:8]


def _int(v: Any) -> int | None:
    try:
        return int(float(str(v).replace(",", ".")))
    except (TypeError, ValueError):
        return None


def clean(raw: dict) -> dict | None:
    """Köprünün gönderdiği kaydı doğrular; kimliği ya da adı olmayan kayıt alınmaz."""
    if not isinstance(raw, dict):
        return None
    cid, title = str(raw.get("id") or ""), _text(raw.get("title"))
    if not ID.match(cid) or not title:
        return None
    url = _text(raw.get("image_url"), 1000)
    if url and not url.startswith(("http://", "https://")):
        url = None
    page = _text(raw.get("page_url"), 1000)
    audience = raw.get("audience") if raw.get("audience") in AUDIENCES else None
    cats = raw.get("categories") if isinstance(raw.get("categories"), list) else []
    return {
        "id": cid, "source": cid.split("-", 1)[0], "source_id": cid.split("-", 1)[1], "title": title,
        "authors": _names(raw.get("authors")), "illustrators": _names(raw.get("illustrators")),
        "isbn": _text(raw.get("isbn"), 20), "brand": _text(raw.get("brand"), 200),
        "category": _path(raw.get("category")),
        "categories": [p for p in (_path(c) for c in cats[:30]) if p],
        "audience": audience, "age_from": _int(raw.get("age_from")), "age_to": _int(raw.get("age_to")),
        "genres": _names(raw.get("genres"))[:20], "on_sale": bool(raw.get("on_sale", True)),
        "sales": max(0, _int(raw.get("sales")) or 0),
        "page_url": page if page and page.startswith(("http://", "https://")) else None,
        "image_url": url,
    }


# ------------------------------------------------------------------ besleme
UPSERT = """
INSERT INTO cover_library (id, source, source_id, title, authors, illustrators, isbn, brand, category, categories,
                           audience, age_from, age_to, genres, on_sale, sales, page_url, image_url, status)
VALUES (%(id)s, %(source)s, %(source_id)s, %(title)s, %(authors)s, %(illustrators)s, %(isbn)s, %(brand)s,
        %(category)s, %(categories)s, %(audience)s, %(age_from)s, %(age_to)s, %(genres)s, %(on_sale)s, %(sales)s,
        %(page_url)s, %(image_url)s, CASE WHEN %(image_url)s::text IS NULL THEN 'none' ELSE 'pending' END)
ON CONFLICT (id) DO UPDATE SET
  title=EXCLUDED.title, authors=EXCLUDED.authors, illustrators=EXCLUDED.illustrators, isbn=EXCLUDED.isbn,
  brand=EXCLUDED.brand, category=EXCLUDED.category, categories=EXCLUDED.categories, audience=EXCLUDED.audience,
  age_from=EXCLUDED.age_from, age_to=EXCLUDED.age_to, genres=EXCLUDED.genres, on_sale=EXCLUDED.on_sale,
  sales=EXCLUDED.sales, page_url=EXCLUDED.page_url, image_url=EXCLUDED.image_url, source_seen=now(),
  status = CASE WHEN cover_library.image_url IS NOT DISTINCT FROM EXCLUDED.image_url THEN cover_library.status
                WHEN EXCLUDED.image_url IS NULL THEN 'none' ELSE 'pending' END,
  updated_at = now()
RETURNING (xmax = 0) AS inserted
"""


def upsert(items: list[dict]) -> dict:
    """Kayıtları yazar; görsel adresi değişen kayıt yeniden indirilmek üzere `pending` olur."""
    rows = [r for r in (clean(x) for x in items) if r]
    new = 0
    with db.tx() as c:
        for r in rows:
            p = {**r, **{k: db.J(r[k]) for k in ("authors", "illustrators", "category", "categories", "genres")}}
            if c.execute(UPSERT, p).fetchone()["inserted"]:
                new += 1
    return {"received": len(items), "stored": len(rows), "new": new, "skipped": len(items) - len(rows)}


# ------------------------------------------------------------------ görsel indirme
def fetch_state() -> dict:
    with _state_lock:
        return dict(_fetch)


def claim_fetch() -> bool:
    with _state_lock:
        if _fetch["running"]:
            return False
        from datetime import datetime, timezone
        _fetch.update(running=True, done=0, failed=0, started=datetime.now(timezone.utc).isoformat(), finished=None)
        return True


def _store_image(cid: str, data: bytes) -> dict:
    from PIL import Image
    im = Image.open(io.BytesIO(data))
    im.load()
    fmt = EXT.get(im.format or "", "")
    if not fmt:
        raise ValueError(f"desteklenmeyen biçim {im.format}")
    name = f"{cid}.{fmt}"
    dest = root() / name
    tmp = dest.with_name(f".{name}.tmp")
    tmp.write_bytes(data)
    tmp.replace(dest)
    for old in root().glob(f"{cid}.*"):          # biçimi değişen görselin eski dosyası kalmasın
        if old.name != name:
            old.unlink(missing_ok=True)
    return {"image_file": name, "image_sha": hashlib.sha256(data).hexdigest(), "image_w": im.width,
            "image_h": im.height}


async def _one(http: httpx.AsyncClient, row: dict) -> bool:
    try:
        r = await http.get(row["image_url"])
        r.raise_for_status()
        if len(r.content) > MAX_BYTES:
            raise ValueError("görsel çok büyük")
        meta = await asyncio.to_thread(_store_image, row["id"], r.content)
        await asyncio.to_thread(db.one, "UPDATE cover_library SET status='ok', error=NULL, fetched_at=now(), "
                                "updated_at=now(), image_file=%s, image_sha=%s, image_w=%s, image_h=%s "
                                "WHERE id=%s AND image_url=%s RETURNING id",
                                meta["image_file"], meta["image_sha"], meta["image_w"], meta["image_h"],
                                row["id"], row["image_url"])
        return True
    except Exception as e:  # noqa: BLE001 — kayıt başına hata; iş sürer
        await asyncio.to_thread(db.one, "UPDATE cover_library SET status='failed', error=%s, fetched_at=now(), "
                                "updated_at=now() WHERE id=%s AND image_url=%s RETURNING id",
                                f"{type(e).__name__}: {e}"[:300], row["id"], row["image_url"])
        return False


async def fetch_pending(retry_failed: bool = False) -> None:
    """`pending` (istenirse `failed`) kayıtların görselini indirir; `claim_fetch()` ile başlatılmış olmalı."""
    try:
        if retry_failed:
            await asyncio.to_thread(db.one, "UPDATE cover_library SET status='pending' WHERE status='failed' "
                                    "AND image_url IS NOT NULL RETURNING 1")
        sem = asyncio.Semaphore(PARALLEL)
        async with httpx.AsyncClient(headers=UA, follow_redirects=True, timeout=40) as http:
            seen: set[str] = set()
            while True:
                rows = await asyncio.to_thread(db.all_rows, "SELECT id, image_url FROM cover_library "
                                               "WHERE status='pending' AND image_url IS NOT NULL "
                                               "ORDER BY sales DESC, id LIMIT %s", BATCH)
                rows = [r for r in rows if r["id"] not in seen]
                if not rows:
                    break
                seen.update(r["id"] for r in rows)

                async def go(r):
                    async with sem:
                        ok = await _one(http, r)
                    with _state_lock:
                        _fetch["done" if ok else "failed"] += 1

                await asyncio.gather(*(go(r) for r in rows))
    except Exception:  # noqa: BLE001
        log.exception("kapak arşivi indirmesi yarıda kaldı")
    finally:
        from datetime import datetime, timezone
        with _state_lock:
            _fetch.update(running=False, finished=datetime.now(timezone.utc).isoformat())


# ------------------------------------------------------------------ okuma (bellekte)
COLS = ("id, title, authors, illustrators, isbn, brand, category, audience, age_from, age_to, genres, on_sale, "
        "sales, page_url, image_file, image_w, image_h, status")


def _rows() -> list[dict]:
    stamp = db.one("SELECT count(*) AS n, max(updated_at) AS t FROM cover_library")
    key = (stamp["n"], stamp["t"])
    with _cache_lock:
        if _cache["stamp"] == key:
            return _cache["rows"]
    rows = db.all_rows(f"SELECT {COLS} FROM cover_library")
    for r in rows:
        r["_q"] = fold(" ".join([r["title"], *r["authors"], *r["illustrators"], r["isbn"] or "", *r["genres"]]))
        r["_cat"] = SEP.join(r["category"])
    with _cache_lock:
        _cache.update(stamp=key, rows=rows)
    return rows


def stats() -> dict:
    counts = {r["status"]: r["n"] for r in db.all_rows("SELECT status, count(*) AS n FROM cover_library GROUP BY 1")}
    last = db.one("SELECT max(source_seen) AS fed FROM cover_library")
    return {"total": sum(counts.values()), "ok": counts.get("ok", 0), "pending": counts.get("pending", 0),
            "failed": counts.get("failed", 0), "none": counts.get("none", 0),
            "lastFeed": last["fed"].isoformat() if last and last["fed"] else None, "fetch": fetch_state()}


def _visible(rows: list[dict], audience: str | None = None) -> list[dict]:
    return [r for r in rows if r["status"] == "ok" and (not audience or r["audience"] == audience)]


def tree(audience: str | None = None) -> dict:
    """Kategori ağacı: her düğümde kendisi ve altındaki kapak sayısı; kardeşler çoktan aza, sonra ada göre."""
    top: dict = {"children": {}}
    uncategorized = 0
    for r in _visible(_rows(), audience):
        if not r["category"]:
            uncategorized += 1
            continue
        node = top
        for depth, name in enumerate(r["category"]):
            ch = node["children"].setdefault(name, {"name": name, "path": SEP.join(r["category"][:depth + 1]),
                                                    "count": 0, "children": {}})
            ch["count"] += 1
            node = ch

    def out(n: dict) -> list[dict]:
        kids = sorted(n["children"].values(), key=lambda c: (-c["count"], fold(c["name"])))
        return [{"name": c["name"], "path": c["path"], "count": c["count"], "children": out(c)} for c in kids]

    rows = _visible(_rows())
    aud = {a: sum(1 for r in rows if r["audience"] == a) for a in AUDIENCES}
    return {"categories": out(top), "uncategorized": uncategorized, "total": len(rows), "audiences": aud}


def view(r: dict) -> dict:
    return {"id": r["id"], "title": r["title"], "authors": r["authors"], "illustrators": r["illustrators"],
            "isbn": r["isbn"], "brand": r["brand"], "category": r["category"], "audience": r["audience"],
            "ageFrom": r["age_from"], "ageTo": r["age_to"], "genres": r["genres"], "onSale": r["on_sale"],
            "pageUrl": r["page_url"], "w": r["image_w"], "h": r["image_h"]}


SORTS = {
    "sales": lambda r: (-r["sales"], fold(r["title"])),
    "title": lambda r: fold(r["title"]),
}


def covers(cat: str | None = None, q: str | None = None, audience: str | None = None, sort: str = "sales",
           page: int = 1, size: int = 60) -> dict:
    """Kategori (yolun kendisi ya da altı), arama (ad, yazar, çizer, ISBN, tür) ve okur kitlesiyle süzülmüş liste."""
    rows = _visible(_rows(), audience)
    if cat == "":
        rows = [r for r in rows if not r["category"]]
    elif cat:
        rows = [r for r in rows if r["_cat"] == cat or r["_cat"].startswith(cat + SEP)]
    words = fold(q).split() if q else []
    if words:
        rows = [r for r in rows if all(w in r["_q"] for w in words)]
    rows = sorted(rows, key=SORTS.get(sort, SORTS["sales"]))
    size = max(1, min(size, 120))
    pages = max(1, -(-len(rows) // size))
    page = max(1, min(page, pages))
    return {"total": len(rows), "page": page, "size": size, "pages": pages,
            "items": [view(r) for r in rows[(page - 1) * size: page * size]]}


def get(cid: str) -> dict | None:
    if not ID.match(cid):
        return None
    r = next((x for x in _rows() if x["id"] == cid), None)
    return view(r) if r else None


def image_path(cid: str) -> Path | None:
    """Sayfa başına onlarca küçük görsel istenir: veritabanına sormadan diskteki dosya (kimlik + biçim uzantısı)."""
    if not ID.match(cid):
        return None
    return next((p for p in root().glob(f"{cid}.*") if p.suffix.lstrip(".") in EXT.values()), None)
