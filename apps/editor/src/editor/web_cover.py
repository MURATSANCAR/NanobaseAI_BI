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


def _digits(s: str) -> str:
    return re.sub(r"[^0-9Xx]", "", s or "").upper()


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
            for url in links[:60]:
                # cheap pre-filter: product pages are one path segment or end in a slug
                if url.rstrip("/").count("/") > 4 or re.search(r"\.(css|js|png|jpg|svg|ico)$", url):
                    continue
                page = await http.get(url)
                if page.status_code != 200 or isbn not in _digits(page.text):
                    continue                                   # the ISBN must be ON the page
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
                rep.update(matched_by="ISBN", crm_title=url, outcome="NO_IMAGE")
    return catalog.store_lookup(rep, "WEB")
