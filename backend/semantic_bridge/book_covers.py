"""Stok kodu → kapak görseli adresi (yalnız okuma).

Kaynak: SEO modülünün gece T-soft'tan okuduğu ürün kaydı (`semantic_seo_products`). Ürün kodu (`code` = T-soft
`ProductCode`) Logo/CRM stok koduyla aynıdır («115201.01.6677»); ilk görselin küçük boyu (≈255×400) alınır, yoksa orta
boy ya da asıl görsel. Yalnız https adresi döner; ürün sitede yoksa ya da SEO modülü kurulu değilse kitap kapaksız
kalır (tahmin/yer tutucu görsel üretilmez). CRM `new_resimurl` göreli dosya yoludur, sunucu adresi olmadan açılamaz.
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

import sqlalchemy as sa

log = logging.getLogger("semantic.book_covers")

CHUNK = 500


def pick(data: dict[str, Any]) -> str | None:
    for img in data.get("ImageUrls") or []:
        if isinstance(img, dict):
            for k in ("Small", "Medium", "ImageUrl", "Big"):
                u = str(img.get(k) or "").strip()
                if u.startswith("https://"):
                    return u
    u = str(data.get("ImageUrlCdn") or "").strip()
    return u if u.startswith("https://") else None


def by_stock_code(engine: Any, tenant: str, codes: Iterable[str | None]) -> dict[str, str]:
    """{stok kodu: kapak adresi}; eşleşmeyen kod sözlükte yoktur."""
    from semantic_bridge.seo_geo.store import PRODUCTS, loads

    want = sorted({c.strip() for c in codes if c and c.strip()})
    out: dict[str, str] = {}
    if not want:
        return out
    try:
        with engine.connect() as c:
            for i in range(0, len(want), CHUNK):
                rows = c.execute(sa.select(PRODUCTS.c.code, PRODUCTS.c.data_json).where(
                    PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.code.in_(want[i:i + CHUNK]))).all()
                for code, data in rows:
                    url = pick(loads(data, {}))
                    if url and code not in out:
                        out[code] = url
    except Exception:  # noqa: BLE001 — SEO modülü kurulu değilse kapaksız
        log.info("kapak: T-soft ürün kaydı okunamadı", exc_info=True)
    return out
