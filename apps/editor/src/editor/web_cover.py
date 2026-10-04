"""Cover from the publisher's public web site, matched by ISBN.

The site is configuration (EDITOR_COVER_WEB_SEARCH, a URL with {isbn}), not code.
A product page counts as the book only if the book's ISBN is on that page; the
cover is the largest image the page itself declares as the product image
(JSON-LD `image`, og:image). No ISBN in the card, no match, no page with the
ISBN -> nothing is stored and the lookup says why."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlparse

import httpx
import pymupdf

from . import catalog, db

UA = {"user-agent": "Mozilla/5.0 (editor-cover-sync)"}
_LINK = re.compile(r'href="([^"#?]+)"')
_OG = re.compile(r'<meta[^>]+property="og:image"[^>]+content="([^"]+)"', re.I)
_LD = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.I | re.S)


def _slug_words(s: str) -> list[str]:
    s = (s or "").casefold().translate(str.maketrans("çğıöşüâîû", "cgiosuaiu")).replace("i̇", "i")
    return [w for w in re.split(r"[^a-z0-9]+", s) if len(w) > 2]


def _digits(s: str) -> str:
    return re.sub(r"[^0-9Xx]", "", s or "").upper()


def _ld_products(html: str) -> list[dict]:
    """JSON-LD objects of the page that carry a book/product identifier."""
    found: list[dict] = []

    def walk(o):
        if isinstance(o, dict):
            if any(k in o for k in ("isbn", "gtin13", "gtin", "sku", "mpn")):
                found.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for block in _LD.findall(html):
        try:
            walk(json.loads(block.strip()))
        except json.JSONDecodeError:
            continue
    return found


def _is_product_page(html: str, isbn: str) -> bool:
    """The page is ABOUT this ISBN (its structured data says so), not a list that
    merely mentions it."""
    return any(_digits(str(o.get(k, ""))) == isbn for o in _ld_products(html)
               for k in ("isbn", "gtin13", "gtin", "sku", "mpn"))


def _ld_images(html: str) -> list[str]:
    out: list[str] = []

    def walk(o):
        if isinstance(o, dict):
            img = o.get("image")
            if isinstance(img, str):
                out.append(img)
            elif isinstance(img, list):
                out.extend(x if isinstance(x, str) else x.get("url", "") for x in img)
            elif isinstance(img, dict) and img.get("url"):
                out.append(img["url"])
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    for block in _LD.findall(html):
        try:
            walk(json.loads(block.strip()))
        except json.JSONDecodeError:
            continue
    return [u for u in out if u]


async def sync_book(book_id: str) -> dict:
    template = os.environ.get("EDITOR_COVER_WEB_SEARCH", "")
    card = db.one("SELECT title, metadata FROM book_card WHERE book_id=%s AND is_current", book_id)
    isbns = [_digits(x["value"]) for x in ((card or {}).get("metadata") or {}).get("ISBN", [])]
    rep = {"book_id": book_id, "matched_by": "NONE", "candidates": [], "outcome": "NO_MATCH"}
    if not template or not isbns:
        rep["detail"] = "arama adresi ayarlı değil" if not template else "kartta doğrulanmış ISBN yok"
        return catalog.store_lookup(rep, "WEB")
    site = urlparse(template).netloc.removeprefix("www.")
    async with httpx.AsyncClient(headers=UA, follow_redirects=True, timeout=40) as http:
        for isbn in isbns:
            search = await http.get(template.format(isbn=isbn))
            links = []
            for href in _LINK.findall(search.text):
                url = urljoin(str(search.url), href)
                if urlparse(url).netloc.removeprefix("www.") == site and url not in links:
                    links.append(url)
            # Try every link of the result page, the ones whose address shares words with
            # the book's title first (so the product page is usually the first request).
            words = set(_slug_words(card["title"]))
            links.sort(key=lambda u: -len(words & set(_slug_words(urlparse(u).path))))
            for url in links:
                if re.search(r"\.(css|js|png|jpe?g|svg|ico|webp|pdf|xml)$", urlparse(url).path):
                    continue
                page = await http.get(url)
                if page.status_code != 200 or not _is_product_page(page.text, isbn):
                    continue                  # the page's own structured data must name this ISBN
                imgs = list(dict.fromkeys(_ld_images(page.text) + _OG.findall(page.text)))
                best = None
                for iu in imgs:
                    r = await http.get(urljoin(url, iu))
                    if r.status_code != 200 or not r.headers.get("content-type", "").startswith("image/"):
                        continue
                    try:
                        pm = pymupdf.Pixmap(r.content)
                    except Exception:  # noqa: BLE001 - not a readable image
                        continue
                    lm = r.headers.get("last-modified")
                    when = parsedate_to_datetime(lm) if lm else datetime.now(timezone.utc)
                    cand = {"kind": "web_product_image", "path": str(r.url), "name": url,
                            "date": when.isoformat(), "pixels": pm.width * pm.height, "_data": r.content}
                    rep["candidates"].append({k: v for k, v in cand.items() if k != "_data"})
                    if best is None or cand["pixels"] > best["pixels"]:
                        best = cand
                if best:
                    rep.update(matched_by="ISBN", crm_title=url, outcome="STORED",
                               chosen={k: v for k, v in best.items() if k != "_data"},
                               file_name=urlparse(best["path"]).path.rsplit("/", 1)[-1])
                    return catalog.store_lookup(rep, "WEB", best["_data"])
                rep.update(matched_by="ISBN", crm_title=url, outcome="NO_IMAGE")   # keep looking
    return catalog.store_lookup(rep, "WEB")


# ------------------------------------------------------------------ yayınevi sitesinin kapak arşivinden
# Kullanıcı 2026-10-04: «bir şekilde bul getir». CRM kapakların yalnız dosya yolunu tutuyor ve o klasörlere erişim
# yok; sitedeki (timas.com.tr) yayımlanmış kapaklar ise kapak arşivinde (ed.cover_library, stüdyo her gece indirir)
# hazır duruyor. Kitap arşivdeki ürüne önce ISBN ile (CRM kaydının ve künyenin ISBN'i = ürün barkodu), yoksa adla
# (ürün adının tamamı ya da ilk parçası kitabın adına birebir eşit) bağlanır; görsel kitabın klasörüne kopyalanır,
# kaynak WEB. CRM kapağı (CRM_IMAGE_ROOTS açılınca) ve elle yüklenen kapak bunun önüne geçer (catalog.PRIORITY).
LIBRARY_ADDED_BY = "site-library"


def library_index():
    """Kapak arşivinde görseli hazır ürünler (gizlenmemiş, `ok`)."""
    from . import recommend
    rows = db.all_rows("SELECT id, title, authors, isbn, category, categories, page_url, sales, image_file,"
                       " fetched_at FROM cover_library WHERE status='ok' AND image_file IS NOT NULL")
    return recommend.SiteIndex(rows)


def library_match(c, book_id: str, ix) -> dict | None:
    """Kitabın kapak arşivindeki ürünü ({'row', 'by'}) ya da None. ISBN önce; ad eşleşmesi yalnız ürün adı (ya da
    ilk parçası) kitabın bugünkü adına ya da CRM kaydının adına birebir eşitse — tahmin yok."""
    from . import book_title, recommend
    rows = book_title.books(c, book_id)
    if not rows:
        return None
    row, ev = rows[0], book_title.evidence(c, book_id)
    names = [n for n in [row["title"], (ev.get("crm") or {}).get("title")] if n]
    m = recommend.match(ix, ev.get("isbns", []), names, ev.get("authors", []))
    if m and m["by"] != "ISBN" and book_title.key(m["row"]["title"]) not in {book_title.key(n) for n in names}:
        m = None
    if m is None and (ev.get("crm") or {}).get("by") != "SAME_NAME":
        # adı CRM'de birden çok farklı kaydın ortak adından gelen kitap («Genç Houdini») ilk parçayla eşlenmez
        m = _by_first_segment(ix, row["title"], (ev.get("crm") or {}).get("title"))
    return m


def _by_first_segment(ix, title: str, crm_title: str | None) -> dict | None:
    """Ürün adının ilk parçası kitabın adına eşit («Acı Biber Çatçat» = «Acı Biber Çatçat - Mini Masallar 2»). Kapakta
    yanlış kitap ağır bir hata olduğu için iki koşul: o ilk parça sitede TEK bir kitaba karşılık gelir (notlar —
    «(Ciltli)», «(Gençlik Klasikleri)» — atılınca tek ad), ve kitabın CRM adı seri adından fazlasını söylemez («Şirin»,
    «Kağan», «Kutü'l Amare» gibi seri adı taşıyan kitap serinin rastgele bir kitabının kapağını almaz)."""
    from . import book_title
    if crm_title and len(book_title.segments(crm_title)) > 1:
        return None
    want = book_title.key(title)
    if not want:
        return None
    hit = [r for r in ix.rows if book_title.key((book_title.segments(book_title.site_name(r["title"])) or [""])[0]) == want]
    books = {book_title.key(" ".join(book_title.segments(r["title"]))) for r in hit}
    if not hit or len(books) != 1:
        return None
    return {"row": max(hit, key=lambda r: (r.get("sales") or 0, str(r["id"]))), "by": "SEGMENT"}


def from_library(book_id: str, ix=None, apply: bool = True) -> dict:
    """Kitaba kapak arşivinden kapak. Kitabın kapağı varsa ve kaynağı WEB'den güçlüyse (CRM, elle yükleme) dokunulmaz;
    aynı görsel zaten kapaksa yeniden yazılmaz. Döner {'book_id', 'outcome', ...}."""
    from .production import library
    ix = ix or library_index()
    cur = catalog.current_cover(book_id)
    if cur and catalog.PRIORITY.get(cur["source"], 0) > catalog.PRIORITY["WEB"]:
        return {"book_id": book_id, "outcome": "KEPT_" + cur["source"]}
    with db.tx() as c:
        m = library_match(c, book_id, ix)
    if not m:
        return {"book_id": book_id, "outcome": "NO_MATCH"}
    r = m["row"]
    path = library.image_path(r["id"])
    if path is None or not path.is_file():
        return {"book_id": book_id, "outcome": "NO_IMAGE", "library_id": r["id"]}
    out = {"book_id": book_id, "outcome": "WOULD_STORE", "by": m["by"], "library_id": r["id"], "title": r["title"]}
    if not apply:
        return out
    when = r.get("fetched_at") or datetime.now(timezone.utc)
    rep = {"book_id": book_id, "matched_by": m["by"], "crm_title": r["title"], "outcome": "STORED",
           "file_name": path.name, "candidates": [],
           "chosen": {"kind": "site_library", "path": r.get("page_url") or r["id"], "name": r["title"],
                      "date": when.isoformat(), "library_id": r["id"]},
           "detail": "kapak arşivi (yayınevi sitesi)"}
    res = catalog.store_lookup(rep, "WEB", path.read_bytes())
    return {**out, "outcome": res["outcome"]}


def main(argv: list[str] | None = None) -> int:
    import argparse
    import collections
    ap = argparse.ArgumentParser(prog="python -m editor.web_cover")
    sub = ap.add_subparsers(dest="cmd", required=True)
    lib = sub.add_parser("library", help="kapağı olmayan kitaplara kapak arşivinden kapak (varsayılan kuru koşu)")
    lib.add_argument("--apply", action="store_true", help="gerçekten yaz")
    lib.add_argument("--json", action="store_true", help="kitap başına JSON satırı")
    a = ap.parse_args(argv)
    ix = library_index()
    seen = collections.Counter()
    for b in db.all_rows("SELECT id FROM book ORDER BY id"):
        res = from_library(str(b["id"]), ix, apply=a.apply)
        seen[(res["outcome"], res.get("by"))] += 1
        if a.json:
            print(json.dumps(res, ensure_ascii=False, default=str), flush=True)
    print(("Yazıldı: " if a.apply else "Kuru koşu: ") + ", ".join(f"{o}{'/' + b if b else ''} {n}"
          for (o, b), n in seen.most_common()), file=__import__("sys").stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
