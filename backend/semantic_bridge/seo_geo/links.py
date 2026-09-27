"""Site içi bağlantılar: taranan sayfaların birbirine verdiği bağlantılardan kurulan grafik.

Kaynak: teknik taramanın (tech.py) açtığı her sayfanın site içi bağlantıları — hedef adres (aynı alan adı, `www` farkı
yok sayılır, `#` parçası ve utm_ vb. izleme parametreleri atılır, göreli adres mutlaklaştırılır) ve bağlantı metni —
`semantic_seo_links_edges` tablosuna yazılır. Envanter: aktif ürünler (T-soft) ve yazar/kategori/yayınevi sayfaları
(T-soft `link/getLinks`). Siteye ayrıca istek gitmez; T-soft'a ve CRM'e hiçbir şey yazılmaz.

Ölçüler:
- gelen bağlantı: bir adrese bağlantı veren farklı taranmış sayfa sayısı (nofollow ayrı sayılır);
- yetim sayfa: envanterde olup taranan sayfaların hiçbirinden (izlenen) bağlantı almayan sayfa. Tarama siteyi bağlantı
  izleyerek dolaşmaz, listedeki sayfaları açar; sonuç taranan sayfalar kadar doğrudur — kapsam ekranda yazılır;
- tıklama derinliği: anasayfadan taranmış bağlantılar üzerinden en kısa yol (BFS); `DEEP_CLICKS`ten derin olanlar;
- yazar ↔ kitap: kitap sayfası yazar sayfasına, yazar sayfası yazarın kitaplarına bağlantı veriyor mu (yazar ürünün
  `ModelId`'si ile yazar sayfasının `TableId`'si). Yazar sayfası sayfalıysa yalnız ilk sayfası taranmıştır;
- dizi/seri: CRM kitap kartında (crm.py) ve T-soft ürün kaydında dizi adı alanı yok; bu denetim yapılmaz;
- bağlantı metni: "tıklayın", "detay", boş metin gibi bir şey anlatmayan metinler;
- öncelik: çok satan ama az (`WEAK_INLINKS`ten az) bağlantı alan kitaplar.
"""
from __future__ import annotations

import collections
import hashlib
import logging
import re
import threading
import time
from datetime import timezone
from typing import Any, Optional
from urllib.parse import parse_qsl, unquote, urlencode, urljoin, urlsplit

import sqlalchemy as sa
from fastapi import HTTPException, Request

from . import rules
from .pages import _num
from .store import LINKS, PRODUCTS, _md, dumps, iso, loads, now
from .tech import LINK_KIND, SNAP, TECH, TRACKING, _fold
from .tech import _key as sitemap_key
from .tech import _product_url

log = logging.getLogger("semantic.seo_geo.links")

DEEP_CLICKS = 3          # anasayfadan bundan çok tıklama uzaktaki sayfa "derinde"
WEAK_INLINKS = 3         # bundan az sayfadan bağlantı alan çok satan kitap öncelik listesine girer
RUNNING_REUSE = 600      # tarama sürerken hesap en çok bu kadar saniyede bir yenilenir (her sayfada değil)
NIGHTLY_WAIT = 8 * 3600  # gece: teknik taramanın bitmesi en çok bu kadar beklenir, sonra yine hesaplanır
NIGHTLY_POLL = 60

EDGES = sa.Table(
    "semantic_seo_links_edges", _md,  # taranan sayfadan site içi bir adrese bağlantı (hedef başına tek satır)
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("id", sa.String(40), primary_key=True),          # sha1(page_url | dst_url)
    sa.Column("page_url", sa.String(800), nullable=False),     # teknik taramadaki sayfa adresi (semantic_seo_tech.url)
    sa.Column("src_url", sa.String(800), nullable=False),      # yönlendirmeden sonra açılan adres
    sa.Column("dst_url", sa.String(800), nullable=False),      # normalleştirilmiş hedef
    sa.Column("anchor", sa.String(300)),                       # en açıklayıcı bağlantı metni
    sa.Column("anchors_json", sa.Text),                        # aynı hedefe giden bütün metinler (tekil)
    sa.Column("count", sa.Integer, nullable=False, default=1),
    sa.Column("nofollow", sa.Boolean, nullable=False, default=False),  # hepsi nofollow mu (sayfa ya da bağlantı)
    sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
    sa.Index("ix_semantic_seo_links_edges_page", "tenant_id", "page_url"),
)
SUMMARY = sa.Table(
    "semantic_seo_links_summary", _md,  # gece hesaplanan özet (gün başına tek satır; eğilim için)
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("day", sa.String(10), primary_key=True),
    sa.Column("data_json", sa.Text, nullable=False),
    sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
)

VIEWS = {"orphans": "Yetim sayfalar", "deep": "Derindeki sayfalar", "author": "Yazar ↔ kitap",
         "weak": "Çok satan, az bağlantılı", "anchors": "Bağlantı metni"}
KIND_FILTER = ("product", "author", "category", "brand", "home", "other")
SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "data:", "sms:", "whatsapp:", "callto:")
ASSET = re.compile(r"\.(jpe?g|png|gif|webp|avif|svg|ico|bmp|css|js|json|pdf|zip|rar|xml|txt|mp4|webm|mp3|woff2?|ttf|eot)$", re.I)
SERIES_NOTE = ("Dizi/seri denetimi yapılmadı: CRM kitap kartında ve T-soft ürün kaydında dizi adı alanı yok. Dizi bilgisi "
               "bir kaynağa eklenirse aynı dizideki kitapların birbirine bağlantı verip vermediği ölçülebilir.")


# ------------------------------------------------------------------ adres (saf, sınanır)
def _host(netloc: str) -> str:
    h = (netloc or "").lower().rsplit("@", 1)[-1]
    for port in (":80", ":443"):
        if h.endswith(port):
            h = h[: -len(port)]
    return h.removeprefix("www.")


def normalize_link(href: Optional[str], base: str, site: Optional[str] = None) -> Optional[str]:
    """Sayfadaki `href` → site içi hedefin tam adresi; dış bağlantı, dosya, API yolu ve boş/`#` bağlantı için None.

    Göreli adres sayfanın adresine göre mutlaklaştırılır; `#` parçası ve izleme parametreleri atılır, sondaki `/`
    silinir. Alan adı karşılaştırmasında `www.` ve varsayılan port yok sayılır; adres sayfanın kendi alan adıyla yazılır.
    """
    h = (href or "").strip()
    if not h or h.startswith("#") or h.lower().startswith(SKIP_SCHEMES):
        return None
    s = urlsplit(urljoin(base, h))
    if s.scheme.lower() not in ("http", "https"):
        return None
    ref = urlsplit(site if site and "://" in site else f"//{site}" if site else base)
    if _host(s.netloc) != _host(ref.netloc):
        return None
    path = re.sub(r"/{2,}", "/", s.path or "/").rstrip("/") or "/"
    if path.lower().startswith("/rest") or ASSET.search(path):
        return None
    query = urlencode([(k, v) for k, v in parse_qsl(s.query, keep_blank_values=True) if not TRACKING.match(k)])
    b = urlsplit(base)
    return f"{(b.scheme or s.scheme).lower()}://{(b.netloc or s.netloc).lower()}{path}" + (f"?{query}" if query else "")


def url_key(url: str) -> str:
    """Grafikte kimlik: `www.`, şema, sondaki `/` ve büyük/küçük harf farkı yok; parametreler korunur."""
    s = urlsplit((url or "").strip())
    path = re.sub(r"/{2,}", "/", unquote(s.path or "/")).rstrip("/").lower() or "/"
    return f"{_host(s.netloc)}{path}" + (f"?{s.query}" if s.query else "")


# ------------------------------------------------------------------ bağlantı metni
def _plain(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", _fold(text or ""))).strip()


GENERIC = {_plain(x) for x in (
    "tıkla", "tıklayın", "tıklayınız", "buraya tıklayın", "buraya tıklayınız", "tıklayınız", "buraya", "burada", "burası",
    "detay", "detaylar", "detaylı bilgi", "detaylı incele", "detayları gör", "ayrıntı", "ayrıntılar", "ayrıntılı bilgi",
    "incele", "hemen incele", "ürünü incele", "devamı", "devamını oku", "devamını gör", "devam", "devam et",
    "daha fazla", "daha fazlası", "daha fazla bilgi", "daha fazla göster", "tümü", "tümünü gör", "hepsini gör", "hepsi",
    "tamamı", "git", "link", "bağlantı", "sayfa", "ileri", "geri", "sonraki", "önceki", "oku", "göz at", "gözat",
    "keşfet", "satın al", "hemen al", "sepete ekle", "bilgi", "bilgi al", "gör", "görüntüle",
    "click here", "click", "here", "more", "read more", "details", "view", "view more", "see all", "see more", "shop now",
)}


def classify_anchor(text: Optional[str]) -> str:
    """empty | generic | ok. Rakam/fiyat ve tek karakter de "generic" (sayfalama, fiyat)."""
    p = _plain(text or "")
    if not p:
        return "empty"
    if p in GENERIC or len(p) <= 1 or re.fullmatch(r"[\d\s]+(tl|try)?", p):
        return "generic"
    return "ok"


def edges_from_page(anchors: list[dict[str, Any]], final: str, site: Optional[str] = None,
                    page_nofollow: bool = False) -> list[dict[str, Any]]:
    """Sayfanın bağlantıları → hedef başına tek kayıt: {dst, anchor, anchors, count, nofollow}. Kendine bağlantı atılır.

    `nofollow`: hedefe giden bütün bağlantılar nofollow ise (ya da sayfa bütünüyle nofollow ise) True.
    """
    src = url_key(final)
    grouped: dict[str, dict[str, Any]] = {}
    for a in anchors:
        dst = normalize_link(a.get("href"), final, site)
        if not dst:
            continue
        k = url_key(dst)
        if k == src:
            continue
        e = grouped.setdefault(k, {"dst": dst, "anchors": [], "count": 0, "followed": False})
        e["count"] += 1
        txt = re.sub(r"\s+", " ", a.get("text") or "").strip()[:300]
        if txt not in e["anchors"]:
            e["anchors"].append(txt)
        if not page_nofollow and "nofollow" not in (a.get("rel") or "").lower().split():
            e["followed"] = True
    out = []
    for e in grouped.values():
        best = next((x for x in e["anchors"] if classify_anchor(x) == "ok"), None) or next((x for x in e["anchors"] if x), "")
        out.append({"dst": e["dst"], "anchor": best, "anchors": e["anchors"], "count": e["count"], "nofollow": not e["followed"]})
    return out


# ------------------------------------------------------------------ grafik (saf, sınanır)
def click_depths(out: dict[str, set[str]], home: str) -> tuple[dict[str, int], dict[str, Optional[str]]]:
    """Anasayfadan BFS: adres → tıklama sayısı ve yol için bir önceki adres. Yalnız taranmış sayfaların bağlantıları."""
    depth: dict[str, int] = {home: 0}
    parent: dict[str, Optional[str]] = {home: None}
    q = collections.deque([home])
    while q:
        u = q.popleft()
        for v in sorted(out.get(u, ())):
            if v not in depth:
                depth[v] = depth[u] + 1
                parent[v] = u
                q.append(v)
    return depth, parent


def path_to(parent: dict[str, Optional[str]], k: str) -> list[str]:
    path: list[str] = []
    cur: Optional[str] = k
    while cur is not None and cur in parent and len(path) <= len(parent):
        path.append(cur)
        cur = parent[cur]
    return path[::-1]


def _book(b: dict[str, Any]) -> dict[str, Any]:
    return {"id": b["id"], "name": b["name"], "url": b["url"], "sales": b["sales"]}


def author_links(books: list[dict[str, Any]], author_pages: dict[str, dict[str, Any]], out: dict[str, set[str]],
                 crawled: set[str]) -> list[dict[str, Any]]:
    """Yazar ↔ kitap tutarlılığı. `books`: [{id, name, url, key, sales, authorId}]; `author_pages`: yazar kimliği →
    {id, name, url, key}; `out`: taranan sayfa → bağlantı verdiği adresler (anahtar); `crawled`: bağlantıları okunmuş
    sayfalar. Yalnız sorunu olan yazarlar döner, satışa göre."""
    by_author: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for b in books:
        if b.get("authorId"):
            by_author[str(b["authorId"])].append(b)
    rows = []
    for aid, bl in by_author.items():
        a = author_pages.get(aid)
        if not a:
            continue
        ak = a["key"]
        page_crawled = ak in crawled
        targets = out.get(ak, set())
        missing = [b for b in bl if b["key"] not in targets] if page_crawled else []
        base = ak.split("?", 1)[0]
        paginated = page_crawled and any("?" in t and t.split("?", 1)[0] == base for t in targets)
        crawled_books = [b for b in bl if b["key"] in crawled]
        no_back = [b for b in crawled_books if ak not in out.get(b["key"], set())]
        if not missing and not no_back:
            continue
        order = lambda x: (-x["sales"], x["name"] or "")  # noqa: E731
        rows.append({"id": aid, "kind": "author", "name": a["name"], "url": a["url"], "pageCrawled": page_crawled,
                     "books": len(bl), "sales": sum(b["sales"] for b in bl),
                     "linkedBooks": len(bl) - len(missing) if page_crawled else None,
                     "missingBooks": [_book(b) for b in sorted(missing, key=order)], "paginated": paginated,
                     "crawledBooks": len(crawled_books),
                     "booksWithoutAuthorLink": [_book(b) for b in sorted(no_back, key=order)]})
    rows.sort(key=lambda r: (-r["sales"], r["name"] or ""))
    return rows


def analyse(site: str, pages: list[dict[str, Any]], edges: list[dict[str, Any]], products: list[dict[str, Any]],
            link_pages: list[dict[str, Any]], sitemap_missing: Optional[set[str]] = None) -> dict[str, Any]:
    """Bütün ölçüler. Girdiler düz veri:

    pages: [{url, final, status, kind, productId, linksKnown}] (teknik tarama; linksKnown = bağlantıları kaydedildi)
    edges: [{src, dst, anchors, nofollow}]
    products: aktif ürünler [{id, name, url, sales, authorId, categoryId, brandId}]
    link_pages: [{type: model|category|brand, id, name, url}]
    sitemap_missing: sitemapte olmayan ürünlerin `tech._key` anahtarları (sitemap okunmadıysa None)
    """
    alias: dict[str, str] = {}
    for p in pages:
        fk = url_key(p.get("final") or p["url"])
        alias[url_key(p["url"])] = fk
        alias.setdefault(fk, fk)

    def res(u: str) -> str:
        k = url_key(u)
        return alias.get(k, k)

    crawled = {res(p["url"]) for p in pages if p.get("linksKnown")}
    page_by_key: dict[str, dict[str, Any]] = {}
    for p in pages:
        page_by_key.setdefault(res(p["url"]), p)
    url_of: dict[str, str] = {}

    by_src: dict[str, dict[str, dict[str, Any]]] = collections.defaultdict(dict)
    inl: dict[str, dict[str, dict[str, Any]]] = collections.defaultdict(dict)
    for e in edges:
        s, d = res(e["src"]), res(e["dst"])
        url_of.setdefault(s, e["src"])
        url_of.setdefault(d, e["dst"])
        if s == d:
            continue
        info = by_src[s].get(d)
        if info is None:
            info = {"anchors": [], "nofollow": True}
            by_src[s][d] = info
            inl[d][s] = info
        info["anchors"] += [a for a in (e.get("anchors") or []) if a not in info["anchors"]]
        info["nofollow"] = info["nofollow"] and bool(e.get("nofollow"))
    out = {s: {d for d, i in ds.items() if not i["nofollow"]} for s, ds in by_src.items()}

    # Envanter: ürünler + yazar/kategori/yayınevi sayfaları; sayfaların satışı kitaplarından.
    agg: dict[tuple[str, str], int] = collections.Counter()
    for pr in products:
        for t, f in (("model", "authorId"), ("category", "categoryId"), ("brand", "brandId")):
            if pr.get(f):
                agg[(t, str(pr[f]))] += pr.get("sales") or 0
    inv: list[dict[str, Any]] = []
    seen: set[str] = set()
    for pr in products:
        if pr.get("url"):
            inv.append({"key": res(pr["url"]), "url": pr["url"], "kind": "product", "id": pr["id"], "name": pr.get("name"),
                        "sales": pr.get("sales") or 0, "authorId": str(pr.get("authorId") or "") or None})
    author_pages: dict[str, dict[str, Any]] = {}
    for lp in link_pages:
        it = {"key": res(lp["url"]), "url": lp["url"], "kind": LINK_KIND.get(lp["type"], lp["type"]), "id": str(lp["id"]),
              "name": lp.get("name"), "sales": agg.get((lp["type"], str(lp["id"])), 0), "authorId": None}
        inv.append(it)
        if lp["type"] == "model" and lp.get("id"):
            author_pages[str(lp["id"])] = it
    uniq = []
    for it in inv:
        if it["key"] not in seen:
            seen.add(it["key"])
            uniq.append(it)
            url_of.setdefault(it["key"], it["url"])
    inv = uniq
    inv_by_key = {it["key"]: it for it in inv}
    for p in pages:
        url_of.setdefault(res(p["url"]), p.get("final") or p["url"])

    home = res(f"{site.rstrip('/')}/")
    home_crawled = home in crawled
    depth, parent = click_depths(out, home) if home_crawled else ({}, {})

    def counts(k: str) -> tuple[int, int]:
        srcs = inl.get(k, {})
        f = sum(1 for i in srcs.values() if not i["nofollow"])
        return f, len(srcs) - f

    def item(it: dict[str, Any]) -> dict[str, Any]:
        f, nf = counts(it["key"])
        return {"url": it["url"], "kind": it["kind"], "id": it["id"], "name": it["name"], "sales": it["sales"],
                "inlinks": f, "nofollowInlinks": nf, "depth": depth.get(it["key"]) if home_crawled else None,
                "crawled": it["key"] in crawled}

    by_sales = lambda r: (-(r.get("sales") or 0), r.get("name") or "", r["url"])  # noqa: E731

    # Yetim: envanterde, izlenen gelen bağlantısı yok.
    orphans = []
    for it in inv:
        row = item(it)
        if row["inlinks"]:
            continue
        if it["kind"] == "product":
            row["inSitemap"] = None if sitemap_missing is None else sitemap_key(it["url"]) not in sitemap_missing
            a = author_pages.get(it["authorId"] or "")
            row["authorUrl"] = a["url"] if a else None
            row["authorPageCrawled"] = (a["key"] in crawled) if a else None
        orphans.append(row)
    orphans.sort(key=by_sales)

    # Derinde: gelen bağlantısı olup anasayfadan DEEP_CLICKS'ten uzak ya da taranmış yoldan ulaşılamayan.
    deep = []
    if home_crawled:
        keys = list(inv_by_key) + [k for k in crawled if k not in inv_by_key]
        for k in keys:
            if k == home or not counts(k)[0]:
                continue
            d = depth.get(k)
            if d is not None and d <= DEEP_CLICKS:
                continue
            it = inv_by_key.get(k) or {"key": k, "url": url_of.get(k, k), "kind": (page_by_key.get(k) or {}).get("kind") or "other",
                                       "id": (page_by_key.get(k) or {}).get("productId"), "name": None, "sales": 0}
            row = item(it)
            row["path"] = [url_of.get(x, x) for x in path_to(parent, k)] if d is not None else []
            deep.append(row)
    deep.sort(key=lambda r: (r["depth"] is not None, -(r.get("sales") or 0), -(r["depth"] or 0), r["url"]))

    # Yazar ↔ kitap
    books = [it for it in inv if it["kind"] == "product"]
    author_rows = author_links(books, author_pages, out, crawled)
    authors_without_page = {b["authorId"] for b in books if b["authorId"] and b["authorId"] not in author_pages}

    # Çok satan, az bağlantılı
    weak = [item(it) for it in books]
    weak = [r for r in weak if r["inlinks"] < WEAK_INLINKS]
    weak.sort(key=by_sales)

    # Bağlantı metni
    texts: collections.Counter = collections.Counter()
    empty_links = generic_links = 0
    anchors_rows = []
    for d, srcs in inl.items():
        cls = collections.Counter()
        examples: list[str] = []
        for info in srcs.values():
            kinds = [classify_anchor(a) for a in info["anchors"]] or ["empty"]
            for a, c in zip(info["anchors"] or [""], kinds):
                if c == "generic":
                    texts["(sayı)" if re.fullmatch(r"[\d\s.,₺]+(tl|try)?", _plain(a) or a) else _plain(a)] += 1
                    generic_links += 1
                elif c == "empty":
                    empty_links += 1
                if a and c != "ok" and a not in examples:
                    examples.append(a)
            cls["ok" if "ok" in kinds else "generic" if "generic" in kinds else "empty"] += 1
        if cls["ok"] or not srcs:
            continue
        it = inv_by_key.get(d) or {"key": d, "url": url_of.get(d, d), "kind": (page_by_key.get(d) or {}).get("kind") or "other",
                                   "id": (page_by_key.get(d) or {}).get("productId"), "name": None, "sales": 0}
        row = item(it)
        row.update(anchors={"ok": cls["ok"], "generic": cls["generic"], "empty": cls["empty"]}, examples=examples)
        anchors_rows.append(row)
    anchors_rows.sort(key=lambda r: (-(r.get("sales") or 0), -(r["inlinks"] + r["nofollowInlinks"]), r["url"]))

    cov: dict[str, dict[str, int]] = {}
    for it in inv:
        c = cov.setdefault(it["kind"], {"crawled": 0, "of": 0})
        c["of"] += 1
        c["crawled"] += it["key"] in crawled
    inv_crawled = sum(c["crawled"] for c in cov.values())
    summary = {
        "crawledPages": len(crawled), "techPages": len(pages), "edges": sum(len(v) for v in by_src.values()),
        "followedEdges": sum(len(v) for v in out.values()), "homeCrawled": home_crawled,
        "inventory": len(inv), "coverage": {"byKind": cov, "crawled": inv_crawled, "of": len(inv),
                                            "share": round(inv_crawled / len(inv), 4) if inv else None},
        "counts": {"orphans": len(orphans), "orphanProducts": sum(1 for r in orphans if r["kind"] == "product"),
                   "deep": sum(1 for r in deep if r["depth"] is not None), "unreachable": sum(1 for r in deep if r["depth"] is None),
                   "author": len(author_rows), "weak": len(weak), "anchors": len(anchors_rows)},
        "anchorTexts": [{"text": t, "count": n} for t, n in texts.most_common()],
        "genericAnchorLinks": generic_links, "emptyAnchorLinks": empty_links,
        "authorsWithoutPage": len(authors_without_page),
        "deepClicks": DEEP_CLICKS, "weakInlinks": WEAK_INLINKS, "sitemapKnown": sitemap_missing is not None,
        "series": {"available": False, "note": SERIES_NOTE},
    }
    return {"summary": summary,
            "lists": {"orphans": orphans, "deep": deep, "author": author_rows, "weak": weak, "anchors": anchors_rows},
            "graph": {"alias": alias, "bySrc": by_src, "inl": inl, "crawled": crawled, "depth": depth, "parent": parent,
                      "urlOf": url_of, "inv": inv_by_key, "pages": page_by_key, "homeCrawled": home_crawled}}


def url_detail(g: dict[str, Any], u: str) -> dict[str, Any]:
    """Tek adresin gelen ve giden bağlantıları (önbellekteki grafikten)."""
    k = url_key(u)
    k = g["alias"].get(k, k)

    def who(x: str) -> dict[str, Any]:
        it = g["inv"].get(x) or {}
        p = g["pages"].get(x) or {}
        return {"url": g["urlOf"].get(x, x), "kind": it.get("kind") or p.get("kind") or "other",
                "id": it.get("id") or p.get("productId"), "name": it.get("name")}

    def link(x: str, info: dict[str, Any]) -> dict[str, Any]:
        anchors = info["anchors"]
        return {**who(x), "anchors": anchors, "nofollow": info["nofollow"],
                "anchorClass": "ok" if any(classify_anchor(a) == "ok" for a in anchors)
                else "generic" if any(classify_anchor(a) == "generic" for a in anchors) else "empty"}

    order = lambda r: (r["nofollow"], r["kind"] != "home", r["url"])  # noqa: E731
    inl = sorted((link(s, i) for s, i in g["inl"].get(k, {}).items()), key=order)
    outl = sorted((link(d, i) for d, i in g["bySrc"].get(k, {}).items()), key=order)
    page = g["pages"].get(k)
    return {"url": g["urlOf"].get(k, u), "item": who(k) if (k in g["inv"] or page) else None,
            "crawled": k in g["crawled"], "status": page.get("status") if page else None,
            "depth": g["depth"].get(k) if g["homeCrawled"] else None,
            "path": [g["urlOf"].get(x, x) for x in path_to(g["parent"], k)] if k in g["depth"] else [],
            "inlinks": inl, "outlinks": outl, "outlinksKnown": k in g["crawled"]}


# ------------------------------------------------------------------ yazma (tech.py taramasından)
_ready: set[int] = set()
_ready_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) in _ready:
            return
        for t in (EDGES, SUMMARY, TECH, SNAP):
            t.create(engine, checkfirst=True)
        _ready.add(id(engine))


def _edge_id(page_url: str, dst: str) -> str:
    return hashlib.sha1(f"{page_url}|{dst}".encode("utf-8")).hexdigest()


def record(engine: sa.engine.Engine, tenant: str, site: str, page_url: str, final: Optional[str],
           page: Optional[dict[str, Any]]) -> Optional[int]:
    """Taranan sayfanın bağlantılarını yazar (eskisini siler). `final` None: sayfa açılmadı, bağlantıları silinir.
    Dönen: yazılan hedef sayısı (None: silindi)."""
    ensure(engine)
    rows: list[dict[str, Any]] = []
    if final and page is not None:
        words = " ".join(page.get("robots") or []).lower().replace(",", " ").split()
        nofollow = "nofollow" in words or "none" in words
        at = now()
        for e in edges_from_page(page.get("anchors") or [], final, site, nofollow):
            rows.append(dict(tenant_id=tenant, id=_edge_id(page_url, e["dst"]), page_url=page_url[:800], src_url=final[:800],
                             dst_url=e["dst"][:800], anchor=(e["anchor"] or "")[:300] or None, anchors_json=dumps(e["anchors"]),
                             count=e["count"], nofollow=e["nofollow"], seen_at=at))
    with engine.begin() as c:
        c.execute(EDGES.delete().where(EDGES.c.tenant_id == tenant, EDGES.c.page_url == page_url[:800]))
        for i in range(0, len(rows), 1000):
            c.execute(EDGES.insert(), rows[i:i + 1000])
    return len(rows) if final and page is not None else None


# ------------------------------------------------------------------ çalışan kısım
def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


class Links:
    def __init__(self, seo: Any) -> None:
        self.seo = seo
        self._lock = threading.Lock()
        self._cache: Optional[dict[str, Any]] = None
        self.state: dict[str, Any] = {"computedAt": None, "seconds": None, "error": None}

    def engine(self) -> sa.engine.Engine:
        eng = self.seo.engine()
        ensure(eng)
        return eng

    def site(self) -> str:
        return (self.seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")

    def _crawl_running(self) -> bool:
        tech = getattr(self.seo, "tech", None)
        return bool(tech and tech.state.get("running"))

    def _fingerprint(self, c: Any, tenant: str) -> tuple:
        e = c.execute(sa.select(sa.func.count(), sa.func.max(EDGES.c.seen_at)).where(EDGES.c.tenant_id == tenant)).first()
        t = c.execute(sa.select(sa.func.count(), sa.func.max(TECH.c.checked_at)).where(TECH.c.tenant_id == tenant)).first()
        p = c.execute(sa.select(sa.func.count(), sa.func.max(PRODUCTS.c.synced_at)).where(PRODUCTS.c.tenant_id == tenant)).first()
        l = c.execute(sa.select(sa.func.count(), sa.func.max(LINKS.c.synced_at)).where(LINKS.c.tenant_id == tenant)).first()
        s = c.execute(sa.select(SNAP.c.saved_at).where(SNAP.c.tenant_id == tenant, SNAP.c.kind == "sitemaps")).scalar()
        return tuple(iso(x) if hasattr(x, "tzinfo") else x for x in (*e, *t, *p, *l, s))

    def load(self) -> dict[str, Any]:
        tenant, site = self.seo.tenant(), self.site()
        with self.engine().connect() as c:
            trows = c.execute(sa.select(TECH.c.url, TECH.c.kind, TECH.c.product_id, TECH.c.status, TECH.c.data_json,
                                        TECH.c.checked_at).where(TECH.c.tenant_id == tenant)).all()
            erows = c.execute(sa.select(EDGES.c.src_url, EDGES.c.dst_url, EDGES.c.anchors_json, EDGES.c.nofollow)
                              .where(EDGES.c.tenant_id == tenant)).all()
            prows = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.name, PRODUCTS.c.data_json)
                              .where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True))).all()
            lrows = c.execute(sa.select(LINKS.c.link, LINKS.c.type, LINKS.c.table_id, LINKS.c.title)
                              .where(LINKS.c.tenant_id == tenant, LINKS.c.type.in_(list(LINK_KIND)))).all()
            smap = c.execute(sa.select(SNAP.c.data_json).where(SNAP.c.tenant_id == tenant, SNAP.c.kind == "sitemaps")).scalar()
        pages, last = [], None
        for url, kind, pid, status, dj, at in trows:
            d = loads(dj, {})
            known = "internalLinks" in d
            pages.append({"url": url, "final": d.get("finalUrl") or url, "status": status, "kind": kind, "productId": pid,
                          "linksKnown": known})
            if known and at is not None and (last is None or at > last):
                last = at
        edges = [{"src": s, "dst": d, "anchors": loads(a, []), "nofollow": bool(nf)} for s, d, a, nf in erows]
        products = []
        for pid, name, dj in prows:
            p = loads(dj, {})

            def ref(key: str) -> Optional[str]:
                v = str(p.get(key) or "").strip()
                return v if v and v != "0" else None

            products.append({"id": pid, "name": name or rules.text_of(p.get("ProductName")), "url": _product_url(p, site),
                             "sales": _num(p.get("CountTotalSales")), "authorId": ref("ModelId"),
                             "categoryId": ref("DefaultCategoryId"), "brandId": ref("BrandId")})
        link_pages = [{"type": t, "id": str(tid or ""), "url": f"{site}/{str(l).strip('/')}",
                       "name": rules.text_of(title).split("|")[0].strip() or str(l).strip("/").replace("-", " ").title()}
                      for l, t, tid, title in lrows if l]
        sm = loads(smap, None) if smap else None
        missing = {sitemap_key(m["url"]) for m in (sm.get("missing") or []) if m.get("url")} if sm and sm.get("totalUrls") else None
        return {"site": site, "pages": pages, "edges": edges, "products": products, "linkPages": link_pages,
                "sitemapMissing": missing, "lastCrawl": last, "sitemapPartial": bool(sm and sm.get("partial"))}

    def result(self, force: bool = False) -> dict[str, Any]:
        tenant = self.seo.tenant()
        with self._lock:
            c = self._cache
            if c and not force and c["tenant"] == tenant and self._crawl_running() \
                    and time.monotonic() - c["at"] < RUNNING_REUSE:
                return c["data"]
            with self.engine().connect() as conn:
                fp = self._fingerprint(conn, tenant)
            if c and not force and c["tenant"] == tenant and c["fp"] == fp:
                return c["data"]
            t0 = time.monotonic()
            try:
                src = self.load()
                data = analyse(src["site"], src["pages"], src["edges"], src["products"], src["linkPages"],
                               src["sitemapMissing"])
            except Exception as e:  # noqa: BLE001
                self.state["error"] = str(e)[:500]
                raise
            data["summary"].update(computedAt=iso(now()), lastCrawl=iso(src["lastCrawl"]), sitemapPartial=src["sitemapPartial"])
            self.state.update(computedAt=data["summary"]["computedAt"], seconds=round(time.monotonic() - t0, 1), error=None)
            self._cache = {"tenant": tenant, "fp": fp, "at": time.monotonic(), "data": data}
            return data

    def snapshot(self) -> dict[str, Any]:
        """Gece: yeniden hesaplar, günün özetini kaydeder (eğilim için)."""
        s = self.result(force=True)["summary"]
        compact = {"counts": s["counts"], "coverage": {"crawled": s["coverage"]["crawled"], "of": s["coverage"]["of"],
                                                       "share": s["coverage"]["share"]},
                   "crawledPages": s["crawledPages"], "edges": s["edges"], "homeCrawled": s["homeCrawled"]}
        tenant, day = self.seo.tenant(), now().astimezone(timezone.utc).date().isoformat()
        with self.engine().begin() as c:
            n = c.execute(SUMMARY.update().where(SUMMARY.c.tenant_id == tenant, SUMMARY.c.day == day)
                          .values(data_json=dumps(compact), saved_at=now())).rowcount
            if not n:
                c.execute(SUMMARY.insert().values(tenant_id=tenant, day=day, data_json=dumps(compact), saved_at=now()))
        return compact

    def history(self) -> list[dict[str, Any]]:
        with self.engine().connect() as c:
            rows = c.execute(sa.select(SUMMARY.c.day, SUMMARY.c.data_json).where(SUMMARY.c.tenant_id == self.seo.tenant())
                             .order_by(SUMMARY.c.day)).all()
        return [{"day": d, **loads(j, {})} for d, j in rows]


def _match(row: dict[str, Any], q: str) -> bool:
    f = _fold(q).strip()
    return not f or f in _fold(f"{row.get('name') or ''} {row.get('url') or ''}")


def register(app, ctx) -> None:
    links = Links(ctx.seo)
    ctx.seo.links = links  # başka özellikler (ürün denetimi, izleme) tek adresin bağlantılarına buradan ulaşabilir

    @app.get("/api/v1/seo-geo/links")
    def seo_links(request: Request, view: str = "orphans", kind: str = "", q: str = "", start: int = 0,
                  limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        if view not in VIEWS:
            raise _err(422, "Bilinmeyen görünüm.")
        if kind and kind not in KIND_FILTER:
            raise _err(422, "Bilinmeyen sayfa türü.")
        data = links.result()
        rows = [r for r in data["lists"][view] if (not kind or r.get("kind") == kind) and _match(r, q)]
        tech = getattr(ctx.seo, "tech", None)
        start = max(0, start)
        return {"summary": data["summary"], "view": view, "views": VIEWS, "total": len(rows), "start": start,
                "items": rows[start:start + max(1, limit)], "crawl": tech.state if tech else None,
                "state": links.state, "history": links.history()}

    @app.get("/api/v1/seo-geo/links/url")
    def seo_links_url(request: Request, u: str = "") -> dict[str, Any]:
        ctx.gate(request)
        if not u.strip():
            raise _err(422, "Adres gerekli.")
        site = links.site()
        target = u.strip() if "://" in u else f"{site}/{u.strip().lstrip('/')}"
        return url_detail(links.result()["graph"], target)

    def nightly() -> None:
        """Teknik taramanın bu geceki turu bitince (en çok NIGHTLY_WAIT) grafiği yeniden hesaplar ve özeti kaydeder.
        Arka planda koşar; gece işini bekletmez."""
        tech = getattr(ctx.seo, "tech", None)

        def run() -> None:
            t0 = tech.state.get("startedAt") if tech else None
            deadline = time.monotonic() + NIGHTLY_WAIT
            while tech and time.monotonic() < deadline:
                st = tech.state
                if st.get("startedAt") != t0 and not st.get("running"):
                    break
                time.sleep(NIGHTLY_POLL)
            try:
                links.snapshot()
            except Exception:  # noqa: BLE001
                log.exception("seo links snapshot failed")

        threading.Thread(target=run, name="seo-links-nightly", daemon=True).start()

    ctx.seo.nightly.append(("links", nightly))
