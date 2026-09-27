"""Kitap videoları: CRM kitap kartındaki YouTube bağlantısı → VideoObject şema önerisi ve video site haritası.

Kaynak: CRM kitap kartı (`semantic_seo_crm_books.data_json` → `video`, `spot`, `summary`), T-soft ürünü (ad, adres,
kapak) ve şema taraması (`semantic_seo_schema.types_json`: sayfada VideoObject var mı). Teknik tarama iframe
kaydetmez; bu yüzden videonun sayfaya gömülü olup olmadığı bilinmez — yalnız şemada VideoObject olup olmadığı
söylenir, ek sayfa isteği yapılmaz.

Çıktılar (hiçbiri siteye yazılmaz):
- kitap başına VideoObject JSON-LD önerisi (name, description, thumbnailUrl, embedUrl, contentUrl). `uploadDate`
  Google'ın zorunlu alanıdır ama CRM'de yok; tema YouTube'dan ya da elle doldurmalı (belgede yazılı).
- video site haritası (XML, `video:` ad alanı) — site yöneticisi köke koyar ve Search Console'a bildirir.
- tema isteği bölümü (Markdown).
"""
from __future__ import annotations

import json
import re
from typing import Any, Iterable, Optional
from urllib.parse import parse_qs, urlparse
from xml.sax.saxutils import escape

import sqlalchemy as sa
from fastapi import Request

from .store import CRM_BOOKS, PRODUCTS, SCHEMA, loads

#: Google video site haritası açıklama sınırı (karakter).
SITEMAP_DESC_MAX = 2048
#: Şema açıklaması için kısaltma ölçüsü (tam metin sayfada zaten var).
JSONLD_DESC_MAX = 500
YT_HOSTS = ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be", "www.youtu.be",
            "youtube-nocookie.com", "www.youtube-nocookie.com")
_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def youtube_id(url: Any) -> Optional[str]:
    """YouTube bağlantısından 11 karakterlik video kimliği; kanal/liste bağlantısı ya da bozuk adres → None."""
    s = str(url or "").strip()
    if not s:
        return None
    if not re.match(r"^[a-z]+://", s, re.I):
        s = "https://" + s
    try:
        u = urlparse(s)
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    if host not in YT_HOSTS:
        return None
    parts = [p for p in u.path.split("/") if p]
    cand = None
    if host.endswith("youtu.be"):
        cand = parts[0] if parts else None
    elif parts and parts[0] in ("embed", "shorts", "v", "live", "e"):
        cand = parts[1] if len(parts) > 1 else None
    elif not parts or parts[0] == "watch":
        cand = (parse_qs(u.query).get("v") or [None])[0]
    elif parts and parts[0] == "attribution_link":
        inner = (parse_qs(u.query).get("u") or [""])[0]
        cand = (parse_qs(urlparse(inner).query).get("v") or [None])[0]
    return cand if cand and _ID.match(cand) else None


def thumbnail(vid: str) -> str:
    return f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"


def _short(text: Optional[str], n: int) -> Optional[str]:
    t = re.sub(r"\s+", " ", str(text or "")).strip()
    if not t:
        return None
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def description(book: dict[str, Any], name: str, n: int) -> str:
    return _short(book.get("spot") or book.get("summary") or book.get("promo"), n) or f"{name} — kitap tanıtım videosu."


def video_object(name: str, desc: str, vid: str, page_url: Optional[str]) -> dict[str, Any]:
    """VideoObject JSON-LD önerisi. `uploadDate` bilinmediği için yok (tema doldurmalı)."""
    out: dict[str, Any] = {"@context": "https://schema.org", "@type": "VideoObject", "name": f"{name} — tanıtım videosu",
                           "description": desc, "thumbnailUrl": [thumbnail(vid)],
                           "embedUrl": f"https://www.youtube.com/embed/{vid}",
                           "contentUrl": f"https://www.youtube.com/watch?v={vid}"}
    if page_url:
        out["isPartOf"] = {"@type": "WebPage", "@id": page_url}
    return out


def sitemap_xml(entries: Iterable[dict[str, Any]]) -> str:
    """Video site haritası. entries: {url, vid, title, description}. Aynı sayfanın videoları tek <url> altında."""
    by_page: dict[str, list[dict[str, Any]]] = {}
    for e in entries:
        if e.get("url") and e.get("vid"):
            by_page.setdefault(e["url"], []).append(e)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
             'xmlns:video="http://www.google.com/schemas/sitemap-video/1.1">']
    for url, vids in by_page.items():
        lines.append(f"  <url>\n    <loc>{escape(url)}</loc>")
        seen: set[str] = set()
        for v in vids:
            if v["vid"] in seen:
                continue
            seen.add(v["vid"])
            desc = _short(v.get("description"), SITEMAP_DESC_MAX) or v["title"]
            lines += ["    <video:video>",
                      f"      <video:thumbnail_loc>{escape(thumbnail(v['vid']))}</video:thumbnail_loc>",
                      f"      <video:title>{escape(v['title'])}</video:title>",
                      f"      <video:description>{escape(desc)}</video:description>",
                      f"      <video:player_loc>{escape('https://www.youtube.com/embed/' + v['vid'])}</video:player_loc>",
                      "    </video:video>"]
        lines.append("  </url>")
    lines.append("</urlset>")
    return "\n".join(lines) + "\n"


def schema_state(types: Any, checked: bool) -> str:
    """Şema taramasına göre: var | yok | bilinmiyor (taranmadı)."""
    if not checked:
        return "bilinmiyor"
    return "var" if "VideoObject" in (types or []) else "yok"


STATE_LABEL = {"var": "Sayfada video şeması var", "yok": "Video şeması yok (sayfada gömülü mü bilinmiyor)",
               "bilinmiyor": "Sayfa henüz taranmadı"}


def theme_request(items: list[dict[str, Any]], site: str) -> str:
    total = len(items)
    valid = [i for i in items if i["youtubeId"]]
    missing = sum(1 for i in valid if i["schema"] != "var")
    example = next((i for i in valid), None)
    lines = [
        "# timas.com.tr — kitap videoları (VideoObject) tema isteği",
        "",
        f"CRM'de {total} satıştaki kitabın YouTube tanıtım videosu kayıtlı; {len(valid)} bağlantı geçerli bir video "
        f"kimliği taşıyor. Şema taramasına göre bunların {missing} tanesinin sayfasında VideoObject yok.",
        "",
        "## İstek",
        "",
        "1. Kitap sayfasında video, ürün görselleri ya da açıklamanın altında gömülü (YouTube iframe) gösterilsin.",
        "2. Aynı sayfaya aşağıdaki gibi `VideoObject` JSON-LD basılsın. `uploadDate` Google için zorunludur: YouTube "
        "videosunun yayın tarihi (ISO 8601). CRM'de bu tarih yok; tema YouTube'dan okumalı ya da panelde elle girilmeli.",
        "3. Video site haritası: SEO & GEO → Video ekranından indirilen `video-sitemap.xml` site köküne konsun ve "
        "robots.txt'e `Sitemap:` satırı eklensin, Search Console'a bildirilsin.",
        "",
        "Kaynak alanlar: video bağlantısı CRM kitap kartı (`new_youtubelink` / `new_ProductWebsite`); açıklama CRM kitap spotu.",
        "",
    ]
    if example:
        lines += ["Örnek (gerçek kitaptan):", "", "```json",
                  json.dumps({**example["jsonld"], "uploadDate": "YYYY-AA-GG"}, ensure_ascii=False, indent=2), "```", ""]
    lines += [f"Site: {site}", ""]
    return "\n".join(lines)


def register(app, ctx) -> None:
    seo = ctx.seo

    def site() -> str:
        return (seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")

    def items() -> list[dict[str, Any]]:
        from . import EAN, SALES, VIEWS, _image, _num

        tenant, s = seo.tenant(), site()
        data = sa.cast(CRM_BOOKS.c.data_json, sa.JSON)
        j = PRODUCTS.join(CRM_BOOKS, sa.and_(CRM_BOOKS.c.tenant_id == PRODUCTS.c.tenant_id, CRM_BOOKS.c.ean == EAN)) \
            .outerjoin(SCHEMA, sa.and_(SCHEMA.c.tenant_id == PRODUCTS.c.tenant_id, SCHEMA.c.product_id == PRODUCTS.c.product_id))
        with seo.engine().connect() as c:
            rows = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.name, PRODUCTS.c.data_json,
                                       CRM_BOOKS.c.data_json.label("crm"), SCHEMA.c.types_json, SCHEMA.c.checked_at)
                             .select_from(j)
                             .where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True),
                                    data["video"].as_string().isnot(None))
                             .order_by(SALES.desc(), VIEWS.desc(), PRODUCTS.c.product_id)).all()
        out = []
        for pid, name, pdata, crm_json, types, checked in rows:
            p, b = loads(pdata, {}), loads(crm_json, {})
            vid = youtube_id(b.get("video"))
            link = p.get("SeoLink")
            url = f"{s}/{str(link).strip('/')}" if link else None
            st = schema_state(loads(types, []), checked is not None)
            out.append({"id": pid, "name": name, "image": _image(p, s), "url": url, "sales": _num(p.get("CountTotalSales")),
                        "video": b.get("video"), "youtubeId": vid, "thumbnail": thumbnail(vid) if vid else None,
                        "schema": st, "schemaLabel": STATE_LABEL[st],
                        "description": description(b, name, SITEMAP_DESC_MAX),
                        "jsonld": video_object(name, description(b, name, JSONLD_DESC_MAX), vid, url) if vid else None})
        return out

    @app.get("/api/v1/seo-geo/video")
    def seo_video(request: Request, filter: str = "", start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        rows = items()
        summary = {"withVideo": len(rows), "valid": sum(1 for r in rows if r["youtubeId"]),
                   "invalid": sum(1 for r in rows if not r["youtubeId"]),
                   "schema": {k: sum(1 for r in rows if r["youtubeId"] and r["schema"] == k) for k in STATE_LABEL}}
        if filter == "gecersiz":
            rows = [r for r in rows if not r["youtubeId"]]
        elif filter in STATE_LABEL:
            rows = [r for r in rows if r["youtubeId"] and r["schema"] == filter]
        s = max(0, start)
        page = [{**r, "jsonld": json.dumps(r["jsonld"], ensure_ascii=False, indent=2) if r["jsonld"] else None}
                for r in rows[s:s + max(1, limit)]]
        return {"summary": summary, "labels": STATE_LABEL, "total": len(rows), "start": s, "items": page}

    @app.get("/api/v1/seo-geo/video/sitemap.xml")
    def seo_video_sitemap(request: Request):
        from fastapi.responses import Response

        ctx.gate(request)
        body = sitemap_xml({"url": r["url"], "vid": r["youtubeId"], "title": f"{r['name']} — tanıtım videosu",
                            "description": r["description"]} for r in items() if r["youtubeId"])
        return Response(body, media_type="application/xml; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="video-sitemap.xml"'})

    @app.get("/api/v1/seo-geo/video/theme-request.md")
    def seo_video_theme(request: Request):
        from fastapi.responses import Response

        ctx.gate(request)
        return Response(theme_request(items(), site()), media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="video-tema-istegi.md"'})
