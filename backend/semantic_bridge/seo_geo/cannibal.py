"""Yarışan sayfalar (anahtar kelime yamyamlığı): aynı Google aramasında sitemizin iki ya da daha çok adresi gösterim
alıyorsa, Google hangisini göstereceğine karar veremiyor olabilir; gösterim ve tıklama bölünür, ikisi de geride kalır.

Kaynak: fırsat listesinin sakladığı Search Console sorgu+sayfa kırılımı (`semantic_seo_opps`, tür `query_page`, son 28
gün). Okuma anında hesaplanır; kırılım yenilenmedikçe önbellekten verilir. Search Console'a bile istek atılmaz.

Bir arama "yarışan" sayılır: en az `MIN_PAGE_IMPRESSIONS` gösterimli en az iki adresimiz var (aramanın toplamı en az
`MIN_QUERY_IMPRESSIONS`). Önem:
- `zararli`: hiçbir adres gösterimin `DOMINANT_SHARE` kadarını almıyor VE en çok gösterilen iki adres de
  `HARM_POSITION`. sıranın gerisinde.
- `izle`: baskın adres yok ama adreslerden biri ilk `HARM_POSITION` sırada.
- `baskin`: bir adres gösterimin çoğunu alıyor; bölünme küçük.

Asıl adres: en çok tıklanan (eşitse en çok gösterilen, sonra daha iyi sıradaki). Asıl adresle her öteki adres bir çift
oluşturur; çift türü ve önerilen iş:
- `kopya`: aynı yol, parametre/son "/"/büyük harf farkı (utm, seux …) → kopyadan asıla canonical; iç bağlantılar temiz adrese.
- `baski`: iki farklı ürün, aynı kitap adı (eski/yeni baskı ya da ikinci ürün kaydı) → satıştan kalkan 301 ile satıştakine;
  ikisi de satıştaysa eskisinden yenisine canonical ya da belirgin bağlantı.
- `urun_sayfa`: kitap sayfası ile yazar/kategori/yayınevi/etiket sayfası → liste sayfası genel konuya göre adlandırılsın,
  kitaba bağlantı versin.
- `sayfa_sayfa`: iki liste/içerik sayfası → birini asıl seçin; ötekinin başlığını ayrıştırın ya da canonical verin.
- `urun_urun`: farklı kitaplar → başlık/açıklamaları aramaya göre ayrıştırın, aralarında bağlantı kurun.
- `diger`: sayfa türü bilinmiyor → iki adresin içeriği ayrıştırılır ya da biri asıla bağlanır.
Ürün eşleşmesi T-soft `SeoLink` ile; sayfa türü T-soft `link/getLinks` kaydıyla (semantic_seo_links).
"""
from __future__ import annotations

import logging
import re
import threading
from typing import Any, Optional
from urllib.parse import urlsplit

import sqlalchemy as sa
from fastapi import HTTPException, Request

from . import connections
from .competitors import clean_title
from .opportunities import fold, is_brand, path_key, source
from .store import CRM_BOOKS, LINKS, PRODUCTS

log = logging.getLogger("semantic.seo_geo")

#: Eşikler (ekranda da gösterilir).
MIN_PAGE_IMPRESSIONS = 5
MIN_QUERY_IMPRESSIONS = 20
DOMINANT_SHARE = 0.8
HARM_POSITION = 5.0
EDITION_SIMILARITY = 0.8          # iki ürün adının kelime benzerliği (Jaccard) en az bu kadarsa aynı kitap sayılır

SEVERITIES = ("zararli", "izle", "baskin")
PAIR_TYPES: dict[str, str] = {
    "kopya": "Aynı sayfanın adres kopyası",
    "baski": "Aynı kitabın iki ürünü (baskı)",
    "urun_sayfa": "Kitap sayfası ↔ yazar/kategori sayfası",
    "sayfa_sayfa": "İki liste/içerik sayfası",
    "urun_urun": "Farklı kitaplar",
    "diger": "Türü bilinmeyen sayfalar",
}
LINK_LABEL = {"product": "Kitap", "model": "Yazar", "category": "Kategori", "brand": "Yayınevi", "tag": "Etiket",
              "blog": "Blog", "content": "İçerik", "page": "Sayfa"}
# Adda baskıyı/biçimi anlatan, kitabı ayırmayan kelimeler (katlanmış yazımla).
EDITION_WORDS = frozenset({"ciltli", "karton", "kapak", "baski", "baskisi", "yeni", "ozel", "cep", "boy", "kutulu",
                           "set", "seti", "sert", "kapakli", "genisletilmis", "gozden", "gecirilmis", "revize",
                           "tam", "metin", "orijinal", "buyuk", "kucuk", "ciltsiz", "numarali", "imzali"})
_TOKEN = re.compile(r"[a-z0-9]+")
_cache: dict[str, Any] = {"key": None, "data": None}
_cache_lock = threading.Lock()


# ------------------------------------------------------------------------------------------------ saf işlevler

def title_tokens(name: Any) -> frozenset[str]:
    """Ürün adının kitabı belirleyen kelimeleri: parantezli ekler, baskı/biçim sözcükleri ve tek harfler atılır."""
    t = fold(clean_title(name or ""))
    return frozenset(w for w in _TOKEN.findall(t) if w not in EDITION_WORDS and (len(w) > 1 or w.isdigit()))


def same_title(a: Any, b: Any, threshold: float = EDITION_SIMILARITY) -> bool:
    ta, tb = title_tokens(a), title_tokens(b)
    if not ta or not tb:
        return False
    return len(ta & tb) / len(ta | tb) >= threshold


def has_params(url: Optional[str]) -> bool:
    return bool(urlsplit(str(url or "")).query)


def detect(rows: list[dict[str, Any]], min_page: int = MIN_PAGE_IMPRESSIONS,
           min_query: int = MIN_QUERY_IMPRESSIONS) -> list[dict[str, Any]]:
    """Search Console sorgu+sayfa satırlarından yarışan aramalar. Satır: {"keys": [sorgu, sayfa], clicks, impressions,
    position}. Sayfasız satır atlanır."""
    groups: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        keys = r.get("keys") or []
        if len(keys) < 2 or not keys[1]:
            continue
        impr = float(r.get("impressions") or 0)
        if impr < min_page:
            continue
        groups.setdefault(str(keys[0]), []).append({
            "url": str(keys[1]), "key": path_key(str(keys[1])), "clicks": float(r.get("clicks") or 0),
            "impressions": impr, "position": float(r.get("position") or 0)})
    out = []
    for q, pages in groups.items():
        if len(pages) < 2:
            continue
        impr = sum(p["impressions"] for p in pages)
        if impr < min_query:
            continue
        clicks = sum(p["clicks"] for p in pages)
        pages.sort(key=lambda p: (-p["clicks"], -p["impressions"], p["position"] or 999, p["url"]))
        for p in pages:
            p["share"] = p["impressions"] / impr
            p["clickShare"] = p["clicks"] / clicks if clicks else None
            p["ctr"] = p["clicks"] / p["impressions"] if p["impressions"] else 0.0
        out.append({"query": q, "brand": is_brand(q), "impressions": impr, "clicks": clicks, "pages": pages})
    return out


def severity(g: dict[str, Any], dominant: float = DOMINANT_SHARE, harm_pos: float = HARM_POSITION) -> str:
    top = max(p["share"] for p in g["pages"])
    if top >= dominant:
        return "baskin"
    two = sorted(g["pages"], key=lambda p: -p["impressions"])[:2]
    if all(p["position"] > harm_pos for p in two):
        return "zararli"
    return "izle"


def pair_type(a: dict[str, Any], b: dict[str, Any]) -> tuple[str, str]:
    """(tür, gerekçe). Sayfa: {"key", "url", "product": {id,name,names,active,barcode}|None, "linkType": str|None}."""
    if a.get("key") and a.get("key") == b.get("key"):
        why = "Aynı yol; " + ("adreslerden biri parametreli." if has_params(a["url"]) or has_params(b["url"])
                              else "yalnız yazım (son \"/\", büyük harf, alan adı) farkı var.")
        return "kopya", why
    pa, pb = a.get("product"), b.get("product")
    if pa and pb:
        if pa["id"] == pb["id"]:
            return "kopya", "İki adres aynı ürüne çıkıyor."
        if pa.get("barcode") and pa.get("barcode") == pb.get("barcode"):
            return "baski", "İki ürün kaydında aynı barkod."
        if any(same_title(x, y) for x in pa.get("names") or [pa.get("name")] for y in pb.get("names") or [pb.get("name")]):
            return "baski", "İki ürünün kitap adı aynı ya da çok benzer."
        return "urun_urun", "İki farklı kitap aynı aramada görünüyor."
    ta, tb = ("product" if pa else a.get("linkType")), ("product" if pb else b.get("linkType"))
    if ta and tb and (ta == "product") != (tb == "product"):
        other = tb if ta == "product" else ta
        return "urun_sayfa", f"Kitap sayfası ile {LINK_LABEL.get(other, other).lower()} sayfası."
    if ta == tb == "product":
        return "urun_urun", "İki farklı kitap adresi (ürün kaydıyla eşleşmedi)."
    if ta and tb:
        return "sayfa_sayfa", f"{LINK_LABEL.get(ta, ta)} ve {LINK_LABEL.get(tb, tb).lower()} sayfası."
    return "diger", "Adreslerden en az biri ürün ya da tanınan sayfa değil."


def action(kind: str, primary: dict[str, Any], other: dict[str, Any]) -> str:
    """Önerilen iş (ekran metni). Karar işletmenindir; hiçbir yere gönderilmez."""
    if kind == "kopya":
        return ("Kopya adres asıl adrese canonical vermeli; site içi bağlantılar ve site haritası parametresiz asıl adresi "
                "kullanmalı.")
    if kind == "baski":
        pa, pb = primary.get("product") or {}, other.get("product") or {}
        if pa.get("active") and pb.get("active") is False:
            return "Satıştan kalkan ürünün adresi 301 ile asıl (satıştaki) ürüne yönlendirilmeli."
        if pb.get("active") and pa.get("active") is False:
            return ("Asıl görünen ürün satışta değil: onun adresi 301 ile satıştaki baskıya yönlendirilmeli; tıklamalar "
                    "satıştaki sayfaya geçer.")
        return ("İkisi de satışta: eski baskıdan yeni baskıya canonical ya da sayfanın üstünde belirgin «yeni baskı» "
                "bağlantısı; başlıklarda baskı farkı (yıl, cilt) açıkça yazılsın.")
    if kind == "urun_sayfa":
        return ("Liste sayfası kitabın adıyla değil genel konuyla adlandırılsın (başlık/açıklama); oradan kitap sayfasına "
                "bu aramanın sözcükleriyle bağlantı verilsin.")
    if kind == "sayfa_sayfa":
        return ("Birini asıl seçin (daha çok tıklanan); ötekinin başlığını ve açıklamasını farklı bir konuya göre yazın "
                "ya da asıla canonical verin, aralarına bağlantı koyun.")
    if kind == "urun_urun":
        return ("Farklı kitaplar: başlık ve açıklamaları aramaya göre ayrıştırın, aramaya en uygun kitabı öne çıkarın; "
                "iki kitap sayfası birbirine bağlantı versin.")
    return "İki sayfanın içeriğini ayrıştırın ya da zayıf olandan asıl sayfaya bağlantı verin."


def annotate(groups: list[dict[str, Any]], products: dict[str, dict[str, Any]],
             links: dict[str, str]) -> list[dict[str, Any]]:
    """Her gruba önem, sayfa eşleşmesi, asıl sayfa ve çiftler eklenir. `products`: yol anahtarı → ürün;
    `links`: yol anahtarı → sayfa türü (model, category, …)."""
    out = []
    for g in groups:
        pages = []
        for i, p in enumerate(g["pages"]):
            prod = products.get(p["key"] or "")
            pages.append({**p, "primary": i == 0, "product": prod,
                          "linkType": "product" if prod else links.get(p["key"] or "")})
        primary = pages[0]
        pairs = []
        for other in pages[1:]:
            kind, why = pair_type(primary, other)
            pairs.append({"a": primary["url"], "b": other["url"], "type": kind, "why": why,
                          "action": action(kind, primary, other)})
        sev = severity(g)
        out.append({**g, "pages": pages, "severity": sev, "topShare": max(p["share"] for p in pages),
                    "types": sorted({p["type"] for p in pairs}), "pairs": pairs})
    return out


def rank(items: list[dict[str, Any]], kind: str = "zararli", brand: str = "0", type_: str = "") -> list[dict[str, Any]]:
    rows = [i for i in items if kind in ("", "hepsi") or i["severity"] == kind]
    if brand in ("0", "1"):
        rows = [i for i in rows if i["brand"] == (brand == "1")]
    if type_:
        rows = [i for i in rows if type_ in i["types"]]
    return sorted(rows, key=lambda i: (-i["impressions"], -i["clicks"], i["query"]))


def totals(items: list[dict[str, Any]]) -> dict[str, Any]:
    sev = {k: {"all": 0, "brand": 0, "nonBrand": 0, "impressions": 0} for k in SEVERITIES}
    types = {k: 0 for k in PAIR_TYPES}
    for i in items:
        s = sev[i["severity"]]
        s["all"] += 1
        s["brand" if i["brand"] else "nonBrand"] += 1
        if not i["brand"]:
            s["impressions"] += int(i["impressions"])
        for t in i["types"]:
            types[t] += 1
    return {"severity": sev, "types": types}


# ------------------------------------------------------------------------------------------------ veri

def _maps(seo) -> tuple[dict[str, dict[str, Any]], dict[str, str]]:
    tenant = seo.tenant()
    data = sa.cast(PRODUCTS.c.data_json, sa.JSON)
    with seo.engine().connect() as c:
        prows = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.name, PRODUCTS.c.active,
                                    data["SeoLink"].as_string(), data["Barcode"].as_string()).where(
            PRODUCTS.c.tenant_id == tenant)).all()
        crm = dict(c.execute(sa.select(CRM_BOOKS.c.ean, CRM_BOOKS.c.name).where(CRM_BOOKS.c.tenant_id == tenant)).all())
        lrows = c.execute(sa.select(LINKS.c.link, LINKS.c.type).where(LINKS.c.tenant_id == tenant)).all()
    products: dict[str, dict[str, Any]] = {}
    for pid, name, active, link, barcode in prows:
        k = path_key(link)
        if not k or k == "/":
            continue
        ean = re.sub(r"[^0-9]", "", str(barcode or ""))
        names = [n for n in (name, crm.get(ean)) if n]
        products.setdefault(k, {"id": pid, "name": name, "names": names, "active": bool(active), "barcode": ean or None})
    links: dict[str, str] = {}
    for link, typ in lrows:
        k = path_key(link)
        if k and k != "/":
            links.setdefault(k, typ)
    return products, links


def computed(seo) -> dict[str, Any]:
    src = source(seo)
    key = (seo.tenant(), src["from"], src["savedAt"])
    with _cache_lock:
        if _cache["key"] == key and _cache["data"] is not None:
            return _cache["data"]
    items: list[dict[str, Any]] = []
    if src["from"] == "query_page":
        groups = detect(src["rows"])
        if groups:
            products, links = _maps(seo)
            items = annotate(groups, products, links)
    data = {"source": {k: v for k, v in src.items() if k != "rows"} | {"rowCount": len(src["rows"])}, "items": items,
            "totals": totals(items)}
    with _cache_lock:
        _cache.update(key=key, data=data)
    return data


def _page_view(p: dict[str, Any]) -> dict[str, Any]:
    prod = p.get("product")
    return {"url": p["url"], "primary": p["primary"], "clicks": int(p["clicks"]), "impressions": int(p["impressions"]),
            "position": p["position"], "ctr": p["ctr"], "share": p["share"], "clickShare": p["clickShare"],
            "params": has_params(p["url"]), "linkType": p["linkType"],
            "linkLabel": LINK_LABEL.get(p["linkType"] or "", None),
            "productId": prod["id"] if prod else None, "productName": prod["name"] if prod else None,
            "productActive": prod["active"] if prod else None}


# ------------------------------------------------------------------------------------------------ uçlar

def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


def register(app, ctx) -> None:
    seo = ctx.seo

    @app.get("/api/v1/seo-geo/cannibal")
    def seo_cannibal(request: Request, kind: str = "zararli", brand: str = "0", type: str = "", start: int = 0,
                     limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        if kind not in (*SEVERITIES, "hepsi"):
            raise _err(404, "Bilinmeyen önem süzgeci.")
        if type and type not in PAIR_TYPES:
            raise _err(404, "Bilinmeyen çift türü.")
        connected = bool(connections.service_account_email())
        data = computed(seo)
        ranked = rank(data["items"], kind, brand, type)
        start = max(0, start)
        page = ranked[start:start + max(1, limit)]
        src = data["source"]
        reason = None
        if not connected and src["from"] != "query_page":
            reason = ("Search Console bağlı değil. Bağlantı Yönetim → SEO & GEO ekranından kurulur; sonra her gece son 28 "
                      "günün arama–sayfa kırılımı okunur.")
        elif src["from"] != "query_page":
            reason = ("Hangi aramada hangi sayfanın göründüğü henüz okunmadı. Fırsatlar ekranında «Search Console’dan yeniden "
                      "oku»ya basın ya da gece okumasını bekleyin.")
        return {"kind": kind, "brand": brand, "type": type, "start": start, "total": len(ranked), "connected": connected,
                "ready": src["from"] == "query_page", "reason": reason, "source": src, "totals": data["totals"],
                "items": [{"query": i["query"], "brand": i["brand"], "impressions": int(i["impressions"]),
                           "clicks": int(i["clicks"]), "severity": i["severity"], "topShare": i["topShare"],
                           "types": i["types"], "pages": [_page_view(p) for p in i["pages"]], "pairs": i["pairs"]}
                          for i in page],
                "pairTypes": [{"id": k, "label": v} for k, v in PAIR_TYPES.items()],
                "thresholds": {"minPageImpressions": MIN_PAGE_IMPRESSIONS, "minQueryImpressions": MIN_QUERY_IMPRESSIONS,
                               "dominantShare": DOMINANT_SHARE, "harmPosition": HARM_POSITION,
                               "editionSimilarity": EDITION_SIMILARITY}}
