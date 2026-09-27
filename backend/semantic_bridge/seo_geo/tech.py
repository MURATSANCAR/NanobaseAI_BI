"""Teknik SEO sağlığı: canlı sayfaların teknik denetimi, sitemap ve robots.txt (yapay zekâ botları).

Sayfalar yalnız okunur: açık kimlik (`schema.USER_AGENT`), robots.txt'e uyulur, istekler arası bekleme (≥1 sn), tur başına
süre bütçesi. `/rest` yollarına hiç gidilmez. T-soft'a ve CRM'e hiçbir şey yazılmaz.

(a) Sayfa denetimi — ürün sayfaları (çok satandan), yazar/kategori/yayınevi sayfaları (T-soft `link/getLinks`) ve
    anasayfa. Yönlendirmeler elle izlenir (zincir kaydedilir; döngü koruması `MAX_HOPS`). Sayfa başına: son durum kodu,
    zincir, canonical (mutlak mı, kendini mi gösteriyor, başka adrese mi, o adres açılıyor mu), meta robots ve
    X-Robots-Tag, hreflang, başlık uzunluğu, h1 sayısı, taranan sayfalarda yinelenen başlık, izleme parametreleri
    (canonical ve site içi bağlantılarda), görseller (alt metni, anlamsız dosya adı, boyut), kapak görselinin alt metni.
    Sıra: hiç bakılmamış ya da en eski bakılan önce; bütçe dolunca durur, sonraki tur kaldığı yerden sürer (tavan yok).
(b) Sitemap — robots.txt'teki `Sitemap:` satırları (yoksa /sitemap.xml), dizin dosyaları iç içe (gzip dahil), sitemap
    başına adres sayısı ve en yeni lastmod (30 günden eski ya da açılmayan işaretlenir), sitemaplerden örneklem
    denetimi (örneklem büyüklüğü parametre; sonuç "örneklem" diye raporlanır), aktif ürünlerden sitemapte olmayanlar.
(c) robots.txt ve yapay zekâ botları — RFC 9309 kuralıyla (en uzun eşleşme, eşitlikte Allow; `*` ve `$`): her bot ×
    temsilî yol için açık/kapalı. Yapay zekâ aramasında görünürlüğü etkileyenlerle yalnız model eğitimine veri
    toplayanlar ayrılır; karar işletmenindir, ekran yalnız öneri yazar.
"""
from __future__ import annotations

import collections
import gzip
import logging
import random
import re
import threading
import time
import unicodedata
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from typing import Any, Callable, Optional
from urllib.parse import parse_qsl, urljoin, urlsplit

import httpx
import sqlalchemy as sa
from fastapi import HTTPException, Request

from . import rules, schema
from .store import LINKS, PRODUCTS, _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo.tech")

MAX_HOPS = 10          # yönlendirme döngüsü koruması (tavan değil: 10 adımdan uzun zincir zaten döngü sayılır)
STALE_DAYS = 30        # sitemap'in en yeni lastmod'u bundan eskiyse "bayat"
REDIRECT_CODES = {301, 302, 303, 307, 308}

TECH = sa.Table(
    "semantic_seo_tech", _md,  # canlı sayfanın teknik denetimi (yalnız okunarak tarandı)
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("url", sa.String(800), primary_key=True),
    sa.Column("kind", sa.String(16), nullable=False),          # product | category | brand | author | home
    sa.Column("product_id", sa.String(40)),
    sa.Column("status", sa.Integer),                          # son durum kodu; 0 = açılamadı
    sa.Column("chain_json", sa.Text),                         # [{url, status, location}]
    sa.Column("issues", sa.String(600), nullable=False, default=""),  # ",noindex,img_no_alt,"
    sa.Column("title", sa.String(500)),                       # yinelenen başlık denetimi için
    sa.Column("data_json", sa.Text),
    sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
)
SNAP = sa.Table(
    "semantic_seo_tech_snap", _md,  # sitemap ve robots.txt son okuması
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kind", sa.String(16), primary_key=True),      # sitemaps | robots
    sa.Column("data_json", sa.Text, nullable=False),
    sa.Column("saved_at", sa.DateTime(timezone=True), nullable=False),
)

#: Denetim → (önem, kısa ad, neden). `IMAGE_CHECKS` görseller sekmesinde ayrıca gösterilir.
CHECKS: dict[str, tuple[str, str, str]] = {
    "fetch_error": ("kritik", "Sayfa açılamadı", "Sayfa bağlantı hatası ya da 200 dışı bir kod (403, 429…) döndü."),
    "not_found": ("kritik", "Sayfa bulunamadı (404/410)", "Satıştaki bir sayfa açılmıyor; arama motoru dizinden düşürür."),
    "server_error": ("kritik", "Sunucu hatası (5xx)", "Sayfa sunucu hatası verdi; sürerse dizinden düşer."),
    "redirect_loop": ("kritik", "Yönlendirme döngüsü", "Yönlendirmeler birbirini gösteriyor ya da bitmiyor; sayfa hiç açılmaz."),
    "redirect_chain": ("yüksek", "Yönlendirme zinciri", "İki ya da daha çok yönlendirme art arda; tarama bütçesi harcanır, "
                                                      "bağlantı değeri zayıflar. Bağlantı doğrudan son adrese gitmeli."),
    "redirected": ("orta", "Adres yönlendiriliyor", "Ürünün/sayfanın kayıtlı adresi başka adrese yönleniyor; bağlantılar "
                                                    "ve sitemap son adresi göstermeli."),
    "not_html": ("orta", "Sayfa HTML değil", "Adres bir web sayfası döndürmüyor."),
    "noindex": ("kritik", "Sayfa dizine kapalı (meta)", "robots meta etiketi noindex içeriyor; sayfa aramada çıkmaz."),
    "header_noindex": ("kritik", "Sayfa dizine kapalı (başlık)", "Sunucu X-Robots-Tag: noindex gönderiyor; sayfa aramada çıkmaz."),
    "nofollow": ("orta", "Bağlantılar izlenmiyor (nofollow)", "Sayfadaki bağlantılar arama motoruna kapalı; iç bağlantı değeri akmaz."),
    "no_canonical": ("orta", "Canonical yok", "Aynı içeriğin parametreli kopyaları ayrı sayfa sayılabilir."),
    "canonical_multiple": ("yüksek", "Birden çok canonical", "Sayfada birden fazla canonical var; arama motoru hepsini yok sayabilir."),
    "canonical_relative": ("düşük", "Canonical göreli adres", "Canonical tam adres (https://…) olmalı."),
    "canonical_other": ("yüksek", "Canonical başka adresi gösteriyor",
                        "Sayfa kendini değil başka bir adresi asıl sayfa gösteriyor; bu sayfa dizinde yer almaz."),
    "canonical_broken": ("kritik", "Canonical açılmayan/yönlenen adreste",
                         "Canonical'ın gösterdiği adres 200 dönmüyor ya da yönlendiriliyor."),
    "canonical_tracking": ("yüksek", "Canonical'da izleme parametresi", "Canonical adresi utm_ vb. parametre taşıyor; "
                                                                         "her kampanya ayrı sayfa sayılır."),
    "tracking_links": ("orta", "İç bağlantılarda izleme parametresi", "Site içi bağlantılar utm_ vb. parametreyle; aynı sayfanın "
                                                                      "parametreli kopyaları taranır."),
    "title_missing": ("yüksek", "Sayfa başlığı yok", "Canlı sayfada <title> boş."),
    "title_length": ("orta", "Sayfa başlığı uzunluğu uygun değil", "Kısa başlık az şey anlatır, uzunu Google keser."),
    "duplicate_title": ("orta", "Yinelenen sayfa başlığı", "Taranan başka bir sayfa da aynı başlığı taşıyor."),
    "h1_missing": ("orta", "H1 başlığı yok", "Sayfanın ana başlığı (h1) yok."),
    "h1_multiple": ("düşük", "Birden çok H1", "Sayfada birden fazla h1 var; ana konu belirsizleşir."),
    "img_no_alt": ("orta", "Görselde alt metni yok", "alt özniteliği olmayan görsel; görme engelli okur ve görsel arama için boş."),
    "img_empty_alt": ("düşük", "Görselde boş alt metni", "alt=\"\" yalnız süs görselinde doğrudur; içerik görselinde açıklama olmalı."),
    "img_bad_name": ("düşük", "Görsel dosya adı anlamsız", "Dosya adı yalnız rakam ya da karma dizi; ad görsel aramada ipucudur."),
    "img_no_size": ("düşük", "Görselde boyut yok", "width/height yok; sayfa yüklenirken içerik kayar (CLS)."),
    "main_img_alt": ("yüksek", "Kapak görselinin alt metni kitap adını taşımıyor",
                     "Ana ürün görselinin alt metni kitabın adını içermiyor; görsel aramada ve yapay zekâ cevaplarında "
                     "kapak kitapla eşleşmez."),
}
IMAGE_CHECKS = ("img_no_alt", "img_empty_alt", "img_bad_name", "img_no_size", "main_img_alt")
#: Taranan sayfaların en az bu oranında (ve en az CHROME_MIN_PAGES sayfada) aynı adresle geçen görsel sitenin
#: şablonudur (logo, simge, ödeme rozeti): sayfa uyarısı sayılmaz, tema isteğinde tek madde olur. İlk canlı
#: taramada (2026-09-27, 70 sayfa) şablon görselleri yüzünden görsel uyarıları 66/70 sayfada çıkıyordu.
CHROME_SHARE, CHROME_MIN_PAGES = 0.30, 5
_IMG_KEYS = (("img_no_alt", "noAlt"), ("img_empty_alt", "emptyAlt"), ("img_bad_name", "badName"), ("img_no_size", "noSize"))


def chrome_images(pages: list[dict[str, Any]]) -> set[str]:
    """Şablon görselleri: sayfa başına tekil sayılır; `pages` her sayfanın `images` özeti (noAlt, emptyAlt…)."""
    n = len(pages)
    if n < CHROME_MIN_PAGES:
        return set()
    seen: collections.Counter = collections.Counter()
    for img in pages:
        seen.update({src for _, k in _IMG_KEYS for src in (img.get(k) or [])})
    need = max(CHROME_MIN_PAGES, CHROME_SHARE * n)
    return {src for src, c in seen.items() if c >= need}


def without_chrome(images: dict[str, Any], chrome: set[str]) -> tuple[dict[str, Any], set[str]]:
    """Şablon görselleri ayıklanmış özet ve kalan görsel sorunları."""
    out = dict(images)
    flags = set()
    for key, k in _IMG_KEYS:
        raw = images.get(k + "All", images.get(k)) or []
        kept = [s for s in raw if s not in chrome]
        out[k + "All"], out[k] = raw, kept
        if kept:
            flags.add(key)
    out["chrome"] = sorted({s for _, k in _IMG_KEYS for s in (images.get(k + "All", images.get(k)) or []) if s in chrome})
    return out, flags
KINDS = {"product": "Ürün", "category": "Kategori", "brand": "Yayınevi", "author": "Yazar", "home": "Anasayfa"}
LINK_KIND = {"model": "author", "category": "category", "brand": "brand"}

TRACKING = re.compile(r"^(utm_.*|gclid|gbraid|wbraid|fbclid|yclid|msclkid|dclid|mc_cid|mc_eid|_ga|_gl|srsltid|igshid|seux.*)$", re.I)


# ------------------------------------------------------------------ yardımcılar (saf, sınanır)
def _norm_url(u: str) -> str:
    s = urlsplit(u.strip())
    path = s.path.rstrip("/") or "/"
    return f"{s.scheme.lower()}://{s.netloc.lower()}{path}" + (f"?{s.query}" if s.query else "")


def tracking_params(url: str) -> list[str]:
    return [k for k, _ in parse_qsl(urlsplit(url).query, keep_blank_values=True) if TRACKING.match(k)]


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", (s or "").replace("İ", "i").replace("I", "ı")).casefold().replace("ı", "i")
    return "".join(ch for ch in s if not unicodedata.combining(ch))


def _tokens(s: str) -> set[str]:
    return {w for w in re.findall(r"\w+", _fold(s)) if len(w) >= 3}


def alt_matches_name(alt: Optional[str], name: str) -> bool:
    """Alt metni ürün adının anlamlı kelimelerinin en az %60'ını taşıyor mu."""
    want = _tokens(name)
    if not want:
        return True
    have = _tokens(alt or "")
    return len(want & have) / len(want) >= 0.6


def bad_image_name(src: str) -> bool:
    base = urlsplit(src).path.rsplit("/", 1)[-1]
    stem = base.rsplit(".", 1)[0] if "." in base else base
    if not stem:
        return False
    return bool(re.fullmatch(r"[\d_\-x]+", stem, re.I) or re.fullmatch(r"[0-9a-f]{12,}", stem, re.I)
                or re.fullmatch(r"(img|image|dsc|photo|foto|resim|urun)[_\-]?\d+", stem, re.I))


class _Page(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: Optional[str] = None
        self._title: Optional[list[str]] = None
        self.robots: list[str] = []
        self.canonicals: list[str] = []
        self.hreflang: list[dict[str, str]] = []
        self.h1 = 0
        self.images: list[dict[str, Any]] = []
        self.links: list[str] = []
        self.og_image: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        a = {k.lower(): (v if v is not None else "") for k, v in attrs}
        if tag == "title" and self.title is None and self._title is None:
            self._title = []
        elif tag == "meta":
            name, prop = a.get("name", "").lower(), a.get("property", "").lower()
            if name in ("robots", "googlebot"):
                self.robots.append(a.get("content", ""))
            if prop == "og:image" and not self.og_image:
                self.og_image = a.get("content") or None
        elif tag == "link":
            rels = a.get("rel", "").lower().split()
            if "canonical" in rels:
                self.canonicals.append(a.get("href", "").strip())
            if "alternate" in rels and a.get("hreflang"):
                self.hreflang.append({"lang": a["hreflang"], "href": a.get("href", "")})
        elif tag == "h1":
            self.h1 += 1
        elif tag == "img":
            src = a.get("data-src") or a.get("data-original") or a.get("data-lazy") or a.get("src") or ""
            self.images.append({"src": src.strip(), "alt": a["alt"] if "alt" in a else None,
                                "width": a.get("width") or None, "height": a.get("height") or None})
        elif tag == "a" and a.get("href"):
            self.links.append(a["href"].strip())

    def handle_endtag(self, tag: str) -> None:
        if tag == "title" and self._title is not None and self.title is None:
            self.title = re.sub(r"\s+", " ", "".join(self._title)).strip()
            self._title = None

    def handle_data(self, data: str) -> None:
        if self._title is not None:
            self._title.append(data)


def parse_page(html: str) -> dict[str, Any]:
    p = _Page()
    try:
        p.feed(html)
        p.close()
    except Exception:  # noqa: BLE001 — bozuk HTML'de o ana kadar okunan kalır
        pass
    if p.title is None and p._title is not None:
        p.title = re.sub(r"\s+", " ", "".join(p._title)).strip()
    return {"title": p.title, "robots": [r for r in p.robots if r], "canonicals": p.canonicals, "hreflang": p.hreflang,
            "h1": p.h1, "images": p.images, "links": p.links, "ogImage": p.og_image}


def canonical_kind(canonical: Optional[str], final_url: str) -> str:
    """missing | relative | self | other (göreli olan mutlaklaştırılıp karşılaştırılır; `relative` ayrıca işaretlenir)."""
    if not canonical:
        return "missing"
    absolute = canonical.lower().startswith(("http://", "https://"))
    target = canonical if absolute else urljoin(final_url, canonical)
    if _norm_url(target) != _norm_url(final_url):
        return "other"
    return "self" if absolute else "relative"


def chain_issues(chain: list[dict[str, Any]]) -> list[str]:
    """Yönlendirme zinciri ([{url, status, location, loop?}]) → sorunlar."""
    if not chain:
        return ["fetch_error"]
    last = chain[-1]
    hops = len(chain) - 1
    out: list[str] = []
    if last.get("loop") or (last["status"] in REDIRECT_CODES and not last.get("stopped")):
        return ["redirect_loop"]
    if hops >= 2:
        out.append("redirect_chain")
    elif hops == 1:
        out.append("redirected")
    st = last["status"]
    if st in (404, 410):
        out.append("not_found")
    elif st >= 500:
        out.append("server_error")
    elif st != 200:
        out.append("fetch_error")
    return out


def fetch_chain(client: httpx.Client, url: str, sleep: Callable[[], None] = lambda: None,
                max_hops: int = MAX_HOPS) -> tuple[list[dict[str, Any]], Optional[httpx.Response]]:
    """Yönlendirmeleri elle izler (istemci `follow_redirects=False`). Son cevap 200 dışıysa da döner."""
    chain: list[dict[str, Any]] = []
    seen: set[str] = set()
    cur = url
    if _is_rest(cur):
        return [{"url": cur, "status": 0, "location": None, "error": "API yolu taranmaz"}], None
    for _ in range(max_hops + 1):
        try:
            r = client.get(cur)
        except httpx.HTTPError as e:
            chain.append({"url": cur, "status": 0, "location": None, "error": str(e)[:200]})
            return chain, None
        loc = r.headers.get("location")
        nxt = urljoin(cur, loc) if loc else None
        chain.append({"url": cur, "status": r.status_code, "location": nxt})
        if r.status_code in REDIRECT_CODES and nxt:
            seen.add(_norm_url(cur))
            if _norm_url(nxt) in seen:
                chain[-1]["loop"] = True
                return chain, None
            if _is_rest(nxt):  # API yoluna giden yönlendirme izlenmez
                chain[-1]["stopped"] = True
                return chain, None
            cur = nxt
            sleep()
            continue
        return chain, r
    chain[-1]["loop"] = True
    return chain, None


def _is_rest(url: str) -> bool:
    return urlsplit(url).path.lower().startswith("/rest")


def page_issues(page: dict[str, Any], final_url: str, headers: dict[str, str], kind: str, name: str,
                lim: dict[str, int]) -> tuple[list[str], dict[str, Any]]:
    """Ayrıştırılmış sayfa → (sorunlar, kaydedilecek ayrıntı). Canonical hedefinin açılıp açılmadığı ayrıca bakılır."""
    found: list[str] = []
    robots = " ".join(page["robots"]).lower()
    xrobots = next((v for k, v in headers.items() if k.lower() == "x-robots-tag"), "") or ""
    if "noindex" in robots or "none" in robots.split(","):
        found.append("noindex")
    if "noindex" in xrobots.lower() or "none" in [x.strip() for x in xrobots.lower().split(",")]:
        found.append("header_noindex")
    if "nofollow" in robots:
        found.append("nofollow")

    cans = [c for c in page["canonicals"] if c]
    canonical = cans[0] if cans else None
    ck = canonical_kind(canonical, final_url)
    if ck == "missing":
        found.append("no_canonical")
    if len(set(cans)) > 1:
        found.append("canonical_multiple")
    if ck == "relative" or (canonical and not canonical.lower().startswith(("http://", "https://"))):
        found.append("canonical_relative")
    if ck == "other":
        found.append("canonical_other")
    if canonical and tracking_params(canonical):
        found.append("canonical_tracking")

    host = urlsplit(final_url).netloc.lower()
    tracked = sorted({urljoin(final_url, h) for h in page["links"]
                      if not h.lower().startswith(("mailto:", "tel:", "javascript:", "#"))
                      and urlsplit(urljoin(final_url, h)).netloc.lower() == host and tracking_params(h)})
    if tracked:
        found.append("tracking_links")

    title = page["title"] or ""
    if not title:
        found.append("title_missing")
    elif not lim["title_min"] <= len(title) <= lim["title_max"]:
        found.append("title_length")
    if page["h1"] == 0:
        found.append("h1_missing")
    elif page["h1"] > 1:
        found.append("h1_multiple")

    imgs = [i for i in page["images"] if i["src"] and not i["src"].startswith("data:")
            and not (i["width"] == "1" and i["height"] == "1")]
    no_alt = [i["src"] for i in imgs if i["alt"] is None]
    empty_alt = [i["src"] for i in imgs if i["alt"] is not None and not i["alt"].strip()]
    bad_name = [i["src"] for i in imgs if bad_image_name(i["src"])]
    no_size = [i["src"] for i in imgs if not (i["width"] and i["height"])]
    for key, lst in (("img_no_alt", no_alt), ("img_empty_alt", empty_alt), ("img_bad_name", bad_name), ("img_no_size", no_size)):
        if lst:
            found.append(key)

    main = None
    if kind == "product" and page["ogImage"]:
        og = urlsplit(page["ogImage"]).path.rsplit("/", 1)[-1].lower()
        main = next((i for i in imgs if og and urlsplit(i["src"]).path.rsplit("/", 1)[-1].lower() == og), None)
        if main is not None and name and not alt_matches_name(main["alt"], name):
            found.append("main_img_alt")

    data = {
        "finalUrl": final_url, "title": title or None, "titleLength": len(title), "h1": page["h1"],
        "canonical": {"href": canonical, "kind": ck, "count": len(cans)},
        "robots": " ".join(page["robots"]) or None, "xRobotsTag": xrobots or None,
        "hreflang": page["hreflang"], "trackingLinks": tracked,
        "images": {"count": len(imgs), "noAlt": no_alt, "emptyAlt": empty_alt, "badName": bad_name, "noSize": no_size},
        "mainImage": ({"src": main["src"], "alt": main["alt"]} if main else None),
    }
    return found, data


# ------------------------------------------------------------------ sitemap (saf kısım)
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_sitemap(body: bytes) -> dict[str, Any]:
    """sitemapindex | urlset → {"kind", "entries": [{"loc", "lastmod"}]}; bozuksa kind="invalid"."""
    if body[:2] == b"\x1f\x8b":
        try:
            body = gzip.decompress(body)
        except OSError:
            return {"kind": "invalid", "entries": [], "error": "gzip açılamadı"}
    try:
        root = ET.fromstring(body)
    except ET.ParseError as e:
        return {"kind": "invalid", "entries": [], "error": f"XML okunamadı: {e}"[:200]}
    kind = {"sitemapindex": "index", "urlset": "urlset"}.get(_local(root.tag), "invalid")
    entries = []
    for node in root:
        if _local(node.tag) not in ("sitemap", "url"):
            continue
        loc = lastmod = None
        for ch in node:
            t = _local(ch.tag)
            if t == "loc":
                loc = (ch.text or "").strip()
            elif t == "lastmod":
                lastmod = (ch.text or "").strip() or None
        if loc:
            entries.append({"loc": loc, "lastmod": lastmod})
    return {"kind": kind, "entries": entries}


def parse_lastmod(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    s = v.strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        try:
            d = datetime.fromisoformat(s[:10])
        except ValueError:
            return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _key(url: str) -> str:
    """Sitemap ↔ ürün karşılaştırması: şema ve www farkı yok sayılır."""
    s = urlsplit(url.strip())
    host = s.netloc.lower().removeprefix("www.")
    return f"{host}{s.path.rstrip('/').lower() or '/'}"


# ------------------------------------------------------------------ robots.txt (RFC 9309)
#: (bot, sahibi, amaç, açıklama). Amaç: search | ai_search | user | training.
BOTS: list[tuple[str, str, str, str]] = [
    ("Googlebot", "Google", "search", "Google araması ve Google'ın yapay zekâ özetleri bu botun taradığı dizinden gelir."),
    ("Bingbot", "Microsoft", "search", "Bing araması; ChatGPT'nin web araması ve Copilot büyük ölçüde Bing dizinini kullanır."),
    ("YandexBot", "Yandex", "search", "Yandex araması."),
    ("OAI-SearchBot", "OpenAI", "ai_search", "ChatGPT arama sonuçlarında sitenin gösterilip kaynak verilmesi bu bota bağlı."),
    ("ChatGPT-User", "OpenAI", "user", "Bir kullanıcı ChatGPT'de bağlantı verdiğinde ya da sorduğunda sayfayı o an açar."),
    ("PerplexityBot", "Perplexity", "ai_search", "Perplexity cevaplarında sitenin kaynak gösterilmesi bu bota bağlı."),
    ("Claude-SearchBot", "Anthropic", "ai_search", "Claude'un web aramasında sitenin kaynak gösterilmesi bu bota bağlı."),
    ("GPTBot", "OpenAI", "training", "OpenAI modellerinin eğitimi için veri toplar; ChatGPT aramasındaki görünürlüğü etkilemez."),
    ("ClaudeBot", "Anthropic", "training", "Anthropic modellerinin eğitimi için veri toplar; arama görünürlüğünü etkilemez."),
    ("Google-Extended", "Google", "training", "Tarayıcı değil, izin işaretidir: Gemini modellerinin eğitimi ve dayanak olarak "
                                              "kullanımı. Google aramasını ve sıralamayı etkilemez."),
    ("Applebot-Extended", "Apple", "training", "İzin işaretidir: Apple'ın yapay zekâ modellerinin eğitimi. Apple aramasını etkilemez."),
    ("CCBot", "Common Crawl", "training", "Açık web arşivi; birçok yapay zekâ modelinin eğitim verisi buradan gelir."),
    ("Bytespider", "ByteDance", "training", "ByteDance (TikTok) modellerinin eğitimi için veri toplar."),
]
PURPOSE = {"search": "Arama motoru", "ai_search": "Yapay zekâ araması", "user": "Kullanıcı isteği", "training": "Model eğitimi"}


def parse_robots(text: str) -> dict[str, Any]:
    groups: list[dict[str, Any]] = []
    sitemaps: list[str] = []
    cur: Optional[dict[str, Any]] = None
    last_was_agent = False
    for raw in (text or "").splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, val = (x.strip() for x in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if cur is None or not last_was_agent:
                cur = {"agents": [], "rules": []}
                groups.append(cur)
            cur["agents"].append(val.lower())
            last_was_agent = True
        elif key in ("allow", "disallow"):
            last_was_agent = False
            if cur is not None:
                cur["rules"].append((key == "allow", val))
        elif key == "sitemap":
            if val:
                sitemaps.append(val)
        else:
            last_was_agent = False
    return {"groups": groups, "sitemaps": sitemaps}


def _pattern(path: str) -> re.Pattern[str]:
    end = path.endswith("$")
    body = re.escape(path[:-1] if end else path).replace(r"\*", ".*")
    return re.compile(body + ("$" if end else ""))


def robots_decision(parsed: dict[str, Any], agent: str, url: str) -> dict[str, Any]:
    """{allowed, rule, group}: en uzun eşleşen kural kazanır, eşitlikte Allow; bot için grup yoksa `*` grubu."""
    token = agent.lower()
    groups = [g for g in parsed["groups"] if token in g["agents"]]
    which = "özel"
    if not groups:
        groups = [g for g in parsed["groups"] if "*" in g["agents"]]
        which = "genel (*)" if groups else "yok"
    s = urlsplit(url)
    path = (s.path or "/") + (f"?{s.query}" if s.query else "")
    if path == "/robots.txt":
        return {"allowed": True, "rule": None, "group": which}
    best: Optional[tuple[int, bool, str]] = None
    for g in groups:
        for allow, pat in g["rules"]:
            if not pat:
                continue  # boş Disallow: her şeye izin
            if _pattern(pat).match(path):
                cand = (len(pat), allow, pat)
                if best is None or cand[0] > best[0] or (cand[0] == best[0] and allow and not best[1]):
                    best = cand
    if best is None:
        return {"allowed": True, "rule": None, "group": which}
    return {"allowed": best[1], "rule": ("Allow: " if best[1] else "Disallow: ") + best[2], "group": which}


def advice(purpose: str, blocked_key: bool, blocked_any: bool) -> str:
    if purpose in ("search", "ai_search", "user"):
        if blocked_key:
            return ("Kapalı: bu motorun sonuçlarında ve cevaplarında sitenin sayfaları gösterilemez ya da kaynak verilemez. "
                    "Görünürlük isteniyorsa açılması önerilir.")
        if blocked_any:
            return "Ana sayfalar açık; yalnız bazı yollar kapalı (arama sonuç sayfası gibi kapalı olması olağan yollar)."
        return "Açık: görünürlük için doğru ayar."
    if blocked_any:
        return ("Kapalı: yalnız model eğitimini etkiler, arama ve yapay zekâ aramasındaki görünürlüğü etkilemez. "
                "Karar işletmenindir.")
    return ("Açık: içerik model eğitiminde kullanılabilir. Kapatmak görünürlüğü etkilemez; kapatıp kapatmamak işletmenin "
            "kararıdır.")


def evaluate_bots(text: str, paths: list[dict[str, str]]) -> dict[str, Any]:
    parsed = parse_robots(text)
    key_labels = {"Anasayfa", "Ürün", "Kategori", "Yazar"}
    bots = []
    for agent, owner, purpose, why in BOTS:
        results = [{**p, **robots_decision(parsed, agent, p["url"])} for p in paths]
        blocked_key = any(not r["allowed"] for r in results if r["label"] in key_labels)
        blocked_any = any(not r["allowed"] for r in results)
        bots.append({"agent": agent, "owner": owner, "purpose": purpose, "purposeLabel": PURPOSE[purpose], "why": why,
                     "group": results[0]["group"] if results else "yok", "results": results,
                     "advice": advice(purpose, blocked_key, blocked_any),
                     "visibility": purpose != "training", "blocked": blocked_key})
    return {"bots": bots, "paths": paths, "sitemaps": parsed["sitemaps"], "groups": len(parsed["groups"])}


# ------------------------------------------------------------------ çalışan kısım
def _ts(v: Optional[datetime]) -> float:
    if v is None:
        return 0.0
    return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).timestamp()


def _product_url(p: dict[str, Any], site: str) -> Optional[str]:
    link = p.get("SeoLink") or p.get("Url") or p.get("ProductUrl") or ""
    if not link:
        return None
    return str(link) if str(link).startswith("http") else f"{site}/{str(link).strip('/')}"


def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


class Tech:
    def __init__(self, seo: Any) -> None:
        self.seo = seo
        self._lock = threading.Lock()
        self.state: dict[str, Any] = {"running": False, "done": 0, "queue": None, "startedAt": None, "finishedAt": None,
                                      "error": None, "budget": None}
        self._snap_lock = threading.Lock()
        self.snap_state: dict[str, Any] = {"running": False, "startedAt": None, "finishedAt": None, "error": None}
        self._ready: set[int] = set()

    def engine(self) -> sa.engine.Engine:
        eng = self.seo.engine()
        if id(eng) not in self._ready:
            TECH.create(eng, checkfirst=True)
            SNAP.create(eng, checkfirst=True)
            self._ready.add(id(eng))
        return eng

    def site(self) -> str:
        site = (self.seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")
        if "/rest" in site.lower():
            raise RuntimeError(f"Mağaza adresi yanlış görünüyor ({site}); Yönetim → SEO & GEO → Mağaza adresi.")
        return site

    @staticmethod
    def client() -> httpx.Client:
        return httpx.Client(headers={"User-Agent": schema.USER_AGENT}, timeout=30, follow_redirects=False)

    # -------------------------------------------------------------- kuyruk
    def targets(self, site: str) -> list[dict[str, Any]]:
        """Anasayfa, ürünler (çok satandan) ve sayfalar karışık (3 ürün + 1 sayfa)."""
        from . import SALES, VIEWS

        tenant = self.seo.tenant()
        with self.engine().connect() as c:
            prods = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.name, PRODUCTS.c.data_json)
                              .where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True))
                              .order_by(SALES.desc(), VIEWS.desc(), PRODUCTS.c.product_id)).all()
            links = c.execute(sa.select(LINKS.c.link, LINKS.c.type, LINKS.c.table_id)
                              .where(LINKS.c.tenant_id == tenant, LINKS.c.type.in_(list(LINK_KIND)))
                              .order_by(LINKS.c.type, LINKS.c.link)).all()
        prod_t = []
        for pid, name, data in prods:
            url = _product_url(loads(data, {}), site)
            if url:
                prod_t.append({"url": url, "kind": "product", "productId": pid, "name": name or ""})
        page_t = [{"url": f"{site}/{str(l).strip('/')}", "kind": LINK_KIND[t], "productId": None, "name": ""}
                  for l, t, _ in links if l]
        out = [{"url": f"{site}/", "kind": "home", "productId": None, "name": ""}]
        while prod_t or page_t:
            out += prod_t[:3]
            del prod_t[:3]
            out += page_t[:1]
            del page_t[:1]
        seen: set[str] = set()
        uniq = []
        for t in out:
            if t["url"] not in seen and not _is_rest(t["url"]):
                seen.add(t["url"])
                uniq.append(t)
        return uniq

    def ordered(self, site: str) -> list[dict[str, Any]]:
        with self.engine().connect() as c:
            checked = dict(c.execute(sa.select(TECH.c.url, TECH.c.checked_at).where(TECH.c.tenant_id == self.seo.tenant())).all())
        items = self.targets(site)
        # Hiç bakılmamış önce (kendi sırasıyla), sonra en eski bakılan.
        return sorted(items, key=lambda t: (t["url"] in checked, _ts(checked.get(t["url"]))))

    # -------------------------------------------------------------- tarama
    def start_crawl(self, budget: int, delay: float = 1.0) -> bool:
        if not self._lock.acquire(blocking=False):
            return False
        self.state.update(running=True, done=0, queue=None, startedAt=iso(now()), finishedAt=None, error=None,
                          budget=max(60, budget))
        threading.Thread(target=self._crawl, args=(max(60, budget), max(1.0, delay)), name="seo-tech", daemon=True).start()
        return True

    def _crawl(self, budget: int, delay: float) -> None:
        deadline = time.monotonic() + budget
        fetcher = client = None
        try:
            site = self.site()
            queue = self.ordered(site)
            self.state["queue"] = len(queue)
            fetcher = schema.Fetcher(site)   # robots.txt'e uyum
            client = self.client()
            lim = rules.thresholds(self.seo.conf)
            pause = lambda: time.sleep(delay)  # noqa: E731
            for t in queue:
                if time.monotonic() > deadline:
                    break
                if not fetcher.allowed(t["url"]):
                    continue
                self.check(client, fetcher, t, lim, pause)
                self.state["done"] += 1
                pause()
            self.mark_duplicates()
            self.mark_images()
        except Exception as e:  # noqa: BLE001 — tur durur, bakılanlar kalır
            self.state["error"] = str(e)[:500]
            log.exception("seo tech crawl failed")
        finally:
            for x in (fetcher, client):
                try:
                    if x:
                        x.close()
                except Exception:  # noqa: BLE001
                    pass
            self.state.update(running=False, finishedAt=iso(now()))
            self._lock.release()

    def check(self, client: httpx.Client, fetcher: Any, t: dict[str, Any], lim: dict[str, int],
              pause: Callable[[], None]) -> dict[str, Any]:
        chain, resp = fetch_chain(client, t["url"], pause)
        issues = chain_issues(chain)
        data: dict[str, Any] = {}
        title = None
        if resp is not None and resp.status_code == 200:
            if "html" not in resp.headers.get("content-type", "").lower():
                issues.append("not_html")
            else:
                final = chain[-1]["url"]
                page = parse_page(resp.text)
                found, data = page_issues(page, final, dict(resp.headers), t["kind"], t["name"], lim)
                issues += found
                title = data.get("title")
                can = data["canonical"]
                if can["kind"] == "other" and can["href"]:
                    target = urljoin(final, can["href"])
                    if fetcher.allowed(target) and not _is_rest(target):
                        pause()
                        cchain, _ = fetch_chain(client, target, pause)
                        can["target"] = {"status": cchain[-1]["status"], "hops": len(cchain) - 1,
                                         "final": cchain[-1]["url"]}
                        if cchain[-1]["status"] != 200 or len(cchain) > 1:
                            issues.append("canonical_broken")
        issues = list(dict.fromkeys(issues))
        row = dict(kind=t["kind"], product_id=t["productId"], status=chain[-1]["status"] if chain else 0,
                   chain_json=dumps(chain), issues="," + ",".join(issues) + ",", title=(title or None) and title[:500],
                   data_json=dumps(data), checked_at=now())
        tenant = self.seo.tenant()
        with self.engine().begin() as c:
            # Yinelenen başlık işareti tur sonunda yeniden kurulur; burada korunmaz.
            n = c.execute(TECH.update().where(TECH.c.tenant_id == tenant, TECH.c.url == t["url"][:800]).values(**row)).rowcount
            if not n:
                c.execute(TECH.insert().values(tenant_id=tenant, url=t["url"][:800], **row))
        return row

    def mark_images(self) -> int:
        """Şablon görsellerini sayfa uyarılarından çıkarır; tarama sonunda bütün kayıt üzerinden yeniden hesaplanır."""
        tenant = self.seo.tenant()
        with self.engine().connect() as c:
            rows = c.execute(sa.select(TECH.c.url, TECH.c.issues, TECH.c.data_json, TECH.c.status)
                             .where(TECH.c.tenant_id == tenant)).all()
        pages = [(url, issues, loads(dj, {})) for url, issues, dj, st in rows if st == 200]
        chrome = chrome_images([d.get("images") or {} for _, _, d in pages])
        changed = 0
        with self.engine().begin() as c:
            for url, issues, d in pages:
                imgs, flags = without_chrome(d.get("images") or {}, chrome)
                old = [i for i in (issues or "").split(",") if i]
                parts = [i for i in old if i not in dict(_IMG_KEYS)] + [k for k, _ in _IMG_KEYS if k in flags]
                if parts == old and imgs == d.get("images"):
                    continue
                d["images"] = imgs
                c.execute(TECH.update().where(TECH.c.tenant_id == tenant, TECH.c.url == url)
                          .values(issues="," + ",".join(parts) + "," if parts else "", data_json=dumps(d)))
                changed += 1
        return changed

    def mark_duplicates(self) -> int:
        tenant = self.seo.tenant()
        with self.engine().connect() as c:
            rows = c.execute(sa.select(TECH.c.url, TECH.c.title, TECH.c.issues, TECH.c.status)
                             .where(TECH.c.tenant_id == tenant)).all()
        count = collections.Counter(_fold(t).strip() for _, t, _, st in rows if t and st == 200)
        changed = 0
        with self.engine().begin() as c:
            for url, title, issues, st in rows:
                dup = bool(title) and st == 200 and count[_fold(title).strip()] > 1
                has = ",duplicate_title," in (issues or "")
                if dup == has:
                    continue
                parts = [i for i in (issues or "").split(",") if i and i != "duplicate_title"] + (["duplicate_title"] if dup else [])
                c.execute(TECH.update().where(TECH.c.tenant_id == tenant, TECH.c.url == url)
                          .values(issues="," + ",".join(parts) + ","))
                changed += 1
        return changed

    # -------------------------------------------------------------- sitemap + robots
    def start_snapshots(self, sample: int, budget: int) -> bool:
        if not self._snap_lock.acquire(blocking=False):
            return False
        self.snap_state.update(running=True, startedAt=iso(now()), finishedAt=None, error=None)
        threading.Thread(target=self._snapshots, args=(max(0, sample), max(60, budget)), name="seo-tech-sitemap",
                         daemon=True).start()
        return True

    def _snapshots(self, sample: int, budget: int) -> None:
        try:
            self.refresh_robots()
            self.refresh_sitemaps(sample, budget)
        except Exception as e:  # noqa: BLE001
            self.snap_state["error"] = str(e)[:500]
            log.exception("seo tech sitemaps failed")
        finally:
            self.snap_state.update(running=False, finishedAt=iso(now()))
            self._snap_lock.release()

    def _save_snap(self, kind: str, data: dict[str, Any]) -> None:
        tenant = self.seo.tenant()
        with self.engine().begin() as c:
            n = c.execute(SNAP.update().where(SNAP.c.tenant_id == tenant, SNAP.c.kind == kind)
                          .values(data_json=dumps(data), saved_at=now())).rowcount
            if not n:
                c.execute(SNAP.insert().values(tenant_id=tenant, kind=kind, data_json=dumps(data), saved_at=now()))

    def snap(self, kind: str) -> Optional[dict[str, Any]]:
        with self.engine().connect() as c:
            r = c.execute(sa.select(SNAP.c.data_json, SNAP.c.saved_at).where(
                SNAP.c.tenant_id == self.seo.tenant(), SNAP.c.kind == kind)).first()
        return {**loads(r[0], {}), "savedAt": iso(r[1])} if r else None

    def _robots_text(self, site: str) -> tuple[Optional[int], str]:
        try:
            r = httpx.get(f"{site}/robots.txt", headers={"User-Agent": schema.USER_AGENT}, timeout=20, follow_redirects=True)
            return r.status_code, (r.text if r.status_code == 200 else "")
        except httpx.HTTPError:
            return None, ""

    def sample_paths(self, site: str) -> list[dict[str, str]]:
        """Temsilî yollar: anasayfa, en çok satan ürün, onun kategorisi ve yazarı, arama sonucu."""
        from . import SALES

        tenant = self.seo.tenant()
        out = [{"label": "Anasayfa", "url": f"{site}/"}]
        with self.engine().connect() as c:
            row = c.execute(sa.select(PRODUCTS.c.data_json).where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True))
                            .order_by(SALES.desc()).limit(1)).first()
            p = loads(row[0], {}) if row else {}
            url = _product_url(p, site) if p else None
            if url:
                out.append({"label": "Ürün", "url": url})
            for label, typ, tid in (("Kategori", "category", p.get("DefaultCategoryId")), ("Yazar", "model", p.get("ModelId"))):
                cond = [LINKS.c.tenant_id == tenant, LINKS.c.type == typ]
                link = None
                if tid:
                    link = c.execute(sa.select(LINKS.c.link).where(*cond, LINKS.c.table_id == str(tid))).scalar()
                link = link or c.execute(sa.select(LINKS.c.link).where(*cond).order_by(LINKS.c.link).limit(1)).scalar()
                if link:
                    out.append({"label": label, "url": f"{site}/{str(link).strip('/')}"})
        out.append({"label": "Arama sonucu", "url": f"{site}/arama?q=kitap"})
        return out

    def refresh_robots(self) -> dict[str, Any]:
        site = self.site()
        status, text = self._robots_text(site)
        paths = self.sample_paths(site)
        data = {"site": site, "status": status, "text": text, **evaluate_bots(text, paths), "checkedAt": iso(now())}
        self._save_snap("robots", data)
        return data

    def refresh_sitemaps(self, sample: int, budget: int, delay: float = 1.0) -> dict[str, Any]:
        from . import SALES

        deadline = time.monotonic() + budget
        site = self.site()
        status, robots_text = self._robots_text(site)
        declared = parse_robots(robots_text)["sitemaps"]
        queue: list[tuple[str, Optional[str], int]] = [(u, None, 0) for u in declared] or [(f"{site}/sitemap.xml", None, 0)]
        seen: set[str] = set()
        maps: list[dict[str, Any]] = []
        urls: dict[str, str] = {}
        cutoff = now() - timedelta(days=STALE_DAYS)
        fetcher = schema.Fetcher(site)
        client = httpx.Client(headers={"User-Agent": schema.USER_AGENT}, timeout=60, follow_redirects=True)
        try:
            while queue and time.monotonic() < deadline:
                url, parent, depth = queue.pop(0)
                if url in seen or depth > 5 or _is_rest(url):
                    continue
                seen.add(url)
                m: dict[str, Any] = {"url": url, "parent": parent, "status": None, "kind": None, "count": 0,
                                     "newest": None, "oldest": None, "withLastmod": 0, "stale": False, "error": None}
                try:
                    r = client.get(url)
                    m["status"] = r.status_code
                    if r.history:
                        m["redirectedTo"] = str(r.url)
                    if r.status_code == 200:
                        parsed = parse_sitemap(r.content)
                        m["kind"], m["error"] = parsed["kind"], parsed.get("error")
                        m["count"] = len(parsed["entries"])
                        dates = [d for d in (parse_lastmod(e["lastmod"]) for e in parsed["entries"]) if d]
                        m["withLastmod"] = len(dates)
                        if dates:
                            m["newest"], m["oldest"] = iso(max(dates)), iso(min(dates))
                            m["stale"] = max(dates) < cutoff
                        if parsed["kind"] == "index":
                            queue += [(e["loc"], url, depth + 1) for e in parsed["entries"]]
                        elif parsed["kind"] == "urlset":
                            for e in parsed["entries"]:
                                urls.setdefault(_key(e["loc"]), e["loc"])
                    else:
                        m["error"] = f"{r.status_code} döndü"
                except httpx.HTTPError as e:
                    m["error"] = str(e)[:200]
                maps.append(m)
                time.sleep(delay)
            partial = bool(queue)

            with self.engine().connect() as c:
                prods = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.name, PRODUCTS.c.data_json)
                                  .where(PRODUCTS.c.tenant_id == self.seo.tenant(), PRODUCTS.c.active.is_(True))
                                  .order_by(SALES.desc(), PRODUCTS.c.product_id)).all()
            active = []
            for pid, name, data in prods:
                u = _product_url(loads(data, {}), site)
                if u:
                    active.append({"id": pid, "name": name, "url": u})
            missing = [a for a in active if _key(a["url"]) not in urls] if urls else []

            locs = list(urls.values())
            picks = random.sample(locs, min(sample, len(locs))) if sample else []
            checks = []
            with self.client() as nc:
                for u in picks:
                    if time.monotonic() > deadline:
                        break
                    if not fetcher.allowed(u) or _is_rest(u):
                        continue
                    chain, _ = fetch_chain(nc, u, lambda: time.sleep(delay))
                    checks.append({"url": u, "status": chain[-1]["status"], "hops": len(chain) - 1,
                                   "final": chain[-1]["url"], "issues": chain_issues(chain)})
                    time.sleep(delay)
        finally:
            client.close()
            fetcher.close()
        bad = [x for x in checks if x["issues"]]
        data = {
            "site": site, "robotsStatus": status, "declared": declared, "fallback": not declared,
            "sitemaps": maps, "partial": partial, "totalUrls": len(urls), "staleDays": STALE_DAYS,
            "activeProducts": len(active), "missingCount": len(missing), "missing": missing,
            "sample": {"requested": sample, "checked": len(checks), "of": len(urls),
                       "ok": sum(1 for x in checks if not x["issues"]),
                       "redirect": sum(1 for x in checks if {"redirected", "redirect_chain", "redirect_loop"} & set(x["issues"])),
                       "error": sum(1 for x in checks if {"not_found", "server_error", "fetch_error"} & set(x["issues"])),
                       "items": bad},
            "checkedAt": iso(now()),
        }
        self._save_snap("sitemaps", data)
        return data

    # -------------------------------------------------------------- özet
    def summary(self) -> dict[str, Any]:
        tenant = self.seo.tenant()
        with self.engine().connect() as c:
            rows = c.execute(sa.select(TECH.c.kind, TECH.c.issues).where(TECH.c.tenant_id == tenant)).all()
            last = c.execute(sa.select(sa.func.max(TECH.c.checked_at)).where(TECH.c.tenant_id == tenant)).scalar()
        counts: dict[str, int] = {k: 0 for k in CHECKS}
        kinds: dict[str, int] = collections.Counter()
        with_issue = 0
        for kind, issues in rows:
            kinds[kind] += 1
            found = [k for k in (issues or "").split(",") if k]
            with_issue += bool(found)
            for k in found:
                counts[k] = counts.get(k, 0) + 1
        return {"checked": len(rows), "withIssues": with_issue, "byKind": dict(kinds), "lastChecked": iso(last),
                "crawl": self.state, "snapshots": self.snap_state,
                "checks": [{"id": k, "severity": v[0], "title": v[1], "why": v[2], "count": counts.get(k, 0),
                            "group": "image" if k in IMAGE_CHECKS else "page"} for k, v in CHECKS.items()]}


def register(app, ctx) -> None:
    from . import SALES

    tech = Tech(ctx.seo)
    ctx.seo.tech = tech  # başka özellikler (hız) sayfa listesine buradan ulaşabilir

    def _item(r: Any) -> dict[str, Any]:
        d = loads(r["data_json"], {})
        return {"url": r["url"], "kind": r["kind"], "productId": r["product_id"], "name": r["name"], "status": r["status"],
                "chain": loads(r["chain_json"], []), "issues": [i for i in (r["issues"] or "").split(",") if i],
                "checkedAt": iso(r["checked_at"]), "sales": int(r["sales"] or 0),
                "title": d.get("title"), "canonical": d.get("canonical"), "robots": d.get("robots"),
                "xRobotsTag": d.get("xRobotsTag"), "hreflang": len(d.get("hreflang") or []),
                "trackingLinks": d.get("trackingLinks") or [], "images": d.get("images"), "mainImage": d.get("mainImage"),
                "h1": d.get("h1"), "finalUrl": d.get("finalUrl")}

    @app.get("/api/v1/seo-geo/tech")
    def seo_tech(request: Request, issue: str = "", kind: str = "", group: str = "", start: int = 0,
                 limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        out = tech.summary()
        cond = [TECH.c.tenant_id == ctx.seo.tenant(), TECH.c.issues != ",,"]
        if issue:
            if issue not in CHECKS:
                raise _err(422, "Bilinmeyen denetim.")
            cond.append(TECH.c.issues.like(f"%,{issue},%"))
        elif group == "image":
            cond.append(sa.or_(*[TECH.c.issues.like(f"%,{k},%") for k in IMAGE_CHECKS]))
        if kind:
            if kind not in KINDS:
                raise _err(422, "Bilinmeyen sayfa türü.")
            cond.append(TECH.c.kind == kind)
        j = TECH.outerjoin(PRODUCTS, sa.and_(PRODUCTS.c.tenant_id == TECH.c.tenant_id, PRODUCTS.c.product_id == TECH.c.product_id))
        with tech.engine().connect() as c:
            total = c.execute(sa.select(sa.func.count()).select_from(TECH).where(*cond)).scalar() or 0
            rows = c.execute(sa.select(TECH, PRODUCTS.c.name.label("name"), SALES.label("sales")).select_from(j).where(*cond)
                             .order_by(sa.case({"home": 0}, value=TECH.c.kind, else_=1), SALES.desc(), TECH.c.url)
                             .offset(max(0, start)).limit(max(1, limit))).mappings().all()
        out.update(total=total, start=start, items=[_item(r) for r in rows], kinds=KINDS)
        return out

    @app.post("/api/v1/seo-geo/tech/crawl")
    def seo_tech_crawl(request: Request, budget: int = 3600) -> dict[str, Any]:
        user = ctx.gate(request)
        started = tech.start_crawl(budget)
        ctx.seo.audit(user, "run", "tech", "Teknik tarama", {"started": started, "budget": budget})
        return {"started": started, "crawl": tech.state}

    @app.get("/api/v1/seo-geo/tech/sitemaps")
    def seo_tech_sitemaps(request: Request, start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        s = tech.snap("sitemaps")
        if not s:
            return {"snapshot": None, "state": tech.snap_state}
        missing = s.pop("missing", [])
        s["missing"] = missing[max(0, start):max(0, start) + max(1, limit)]
        s["missingStart"] = start
        return {"snapshot": s, "state": tech.snap_state}

    @app.post("/api/v1/seo-geo/tech/sitemaps/refresh")
    def seo_tech_sitemaps_refresh(request: Request, sample: int = 50, budget: int = 1800) -> dict[str, Any]:
        user = ctx.gate(request)
        started = tech.start_snapshots(sample, budget)
        ctx.seo.audit(user, "run", "tech-sitemaps", "Sitemap ve robots.txt okuması", {"started": started, "sample": sample})
        return {"started": started, "state": tech.snap_state}

    @app.get("/api/v1/seo-geo/tech/robots")
    def seo_tech_robots(request: Request) -> dict[str, Any]:
        ctx.gate(request)
        s = tech.snap("robots")
        if s is None:
            try:
                s = {**tech.refresh_robots(), "savedAt": iso(now())}
            except Exception as e:  # noqa: BLE001 — site erişilemezse ekrana yazılır
                raise _err(502, f"robots.txt okunamadı: {e}") from None
        return {"snapshot": s, "state": tech.snap_state}

    def nightly() -> None:
        """Sitemap + robots, sonra şema taramasıyla aynı anda siteye iki kat istek gitmesin diye onun bitmesini bekleyip
        bütçeli teknik tarama. Arka planda koşar; gece işini bekletmez."""
        def run() -> None:
            if tech.start_snapshots(50, 1800):
                while tech.snap_state.get("running"):
                    time.sleep(10)
            time.sleep(60)
            waited = time.monotonic()
            while ctx.seo.crawl.get("running") and time.monotonic() - waited < 4 * 3600:
                time.sleep(30)
            tech.start_crawl(3600)

        threading.Thread(target=run, name="seo-tech-nightly", daemon=True).start()

    ctx.seo.nightly.append(("tech", nightly))
