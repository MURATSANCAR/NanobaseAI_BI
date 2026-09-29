"""Kimlik ve bilgi paneli hazırlığı: Google'ın bilgi grafiği ve yapay zekâ motorları Timaş'ı, yazarlarını ve
kitaplarını hangi kayıtlardan tanır, eksik ne.

(a) Kurum: Wikidata'da "Timaş Yayınları" kaydı (resmî site P856, sosyal hesap kimlikleri, Wikipedia maddesi) ve
    anasayfadaki Organization şeması (ad, logo, sameAs). Çıktı: geçti/kaldı listesi ve Wikidata'dan kurulmuş
    önerilen JSON-LD (tema isteğine konur; siteye bir şey yazılmaz).
(b) Yazarlar: çok satan kitapların yazarları (T-soft `Model`) Wikidata'da aranır; basın-web modülünün doğrulayan
    araması kullanılır (insan + yazıyla ilgili meslek; aynı adda birden çok kişi varsa bilinen eseriyle ayrıştırılır).
    Sonuç: Wikidata + Wikipedia / yalnız Wikidata / yok / belirsiz; eksik olan için ne gerektiği.
(c) Kitaplar: aktif kitapların ISBN'i Wikidata'da (P212) var mı — 200'lük toplu sorgularla.
(d) Google Kitaplar hazırlığı: CRM hakkı, yayın durumu, ISBN, kapak, tadımlık PDF. Yükleme Play Kitaplar İş Ortağı
    Merkezi'nden elle yapılır; burada yalnız liste çıkar.

Sonuçlar `semantic_seo_entity`'de saklanır, `REFRESH_DAYS` gün sonra yeniden bakılır. Yalnız okunur: Wikidata'ya,
Wikipedia'ya, siteye, CRM'e hiçbir şey yazılmaz.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import unicodedata
from datetime import timedelta
from typing import Any, Optional
from urllib.parse import quote

import sqlalchemy as sa
from fastapi import Request

from . import rules, schema
from .competitors import domain_of, matches
from .store import CRM_BOOKS, PRODUCTS, _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo")

USER_AGENT = "TimasZekiBot/1.0 (+https://timas.com.tr)"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
SPARQL = "https://query.wikidata.org/sparql"
REFRESH_DAYS = 30
ORG_NAME = "Timaş Yayınları"
BATCH = 200

ENTITY = sa.Table(
    "semantic_seo_entity", _md,  # kimlik denetimi önbelleği: kurum, yazar, kitap ISBN özeti
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kind", sa.String(16), primary_key=True),        # org | author | books
    sa.Column("name", sa.String(300), primary_key=True),       # org: "_org", books: "_isbn", author: katlanmış ad
    sa.Column("data_json", sa.Text, nullable=False),
    sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
)
_ready: set[int] = set()
_ready_lock = threading.Lock()

#: Wikidata sosyal hesap özellikleri → profil adresi.
SOCIAL = {
    "P2003": ("Instagram", "https://www.instagram.com/{}/"),
    "P2002": ("X (Twitter)", "https://x.com/{}"),
    "P2013": ("Facebook", "https://www.facebook.com/{}"),
    "P2397": ("YouTube", "https://www.youtube.com/channel/{}"),
    "P4264": ("LinkedIn", "https://www.linkedin.com/company/{}"),
    "P7085": ("TikTok", "https://www.tiktok.com/@{}"),
}
AUTHOR_STATUS = ("wikipedia", "wikidata", "yok", "belirsiz", "bekliyor")
AUTHOR_LABEL = {"wikipedia": "Wikidata + Wikipedia", "wikidata": "Yalnız Wikidata", "yok": "Kaydı yok",
                "belirsiz": "Belirsiz", "bekliyor": "Henüz bakılmadı"}
ORG_TYPES = {"Organization", "Corporation", "OnlineStore", "Store", "BookStore", "LocalBusiness", "NewsMediaOrganization"}
GB_CHECKS = {
    "isbn": "ISBN (978/979 ile başlayan 13 hane)",
    "rights": "CRM'de internette gösterim hakkı",
    "status": "CRM yayın durumu uygun (çekilmemiş, bizim)",
    "cover": "Kapak görseli",
    "pdf": "Tadımlık PDF (CRM)",
}


# ------------------------------------------------------------------------------ saf yardımcılar (testli)

def fold(text: Any) -> str:
    t = str(text or "").replace("İ", "i").replace("I", "ı").lower()
    t = unicodedata.normalize("NFKD", t.replace("ı", "i"))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", "".join(ch for ch in t if not unicodedata.combining(ch)))).strip()


def claims(ent: dict[str, Any], prop: str) -> list[Any]:
    out = []
    for c in (ent.get("claims") or {}).get(prop, []):
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
        if v is not None:
            out.append(v)
    return out


def label(ent: dict[str, Any]) -> Optional[str]:
    for lang in ("tr", "en"):
        v = (ent.get("labels") or {}).get(lang, {}).get("value")
        if v:
            return v
    return None


def pick_org(ids: list[str], entities: dict[str, Any], site: str, name: str = ORG_NAME) -> tuple[Optional[str], str]:
    """(QID, gerekçe). Resmî sitesi (P856) bizim alan adımız olan aday önce; yoksa adı birebir tutan ve insan
    olmayan tek aday. Adı tutan birden çok aday varsa karar verilmez (belirsiz)."""
    ours = domain_of(site)
    for q in ids:
        if any(matches(domain_of(w), ours) for w in claims(entities.get(q) or {}, "P856") if isinstance(w, str)):
            return q, "site"
    named = []
    for q in ids:
        e = entities.get(q) or {}
        human = any(isinstance(v, dict) and v.get("id") == "Q5" for v in claims(e, "P31"))
        if not human and fold(label(e)) == fold(name):
            named.append(q)
    if len(named) == 1:
        return named[0], "ad"
    return None, "belirsiz" if named else "yok"


def org_facts(ent: dict[str, Any]) -> dict[str, Any]:
    """Wikidata kurum kaydından okunacaklar."""
    qid = ent.get("id")
    sites = ent.get("sitelinks") or {}
    wiki = {lang: f"https://{lang[:-4]}.wikipedia.org/wiki/{quote(sites[lang]['title'].replace(' ', '_'))}"
            for lang in ("trwiki", "enwiki") if sites.get(lang, {}).get("title")}
    socials = []
    for prop, (name, pattern) in SOCIAL.items():
        for v in claims(ent, prop):
            if isinstance(v, str) and v.strip():
                socials.append({"property": prop, "network": name, "id": v, "url": pattern.format(v.strip())})
    inception = next((m.group(1) for v in claims(ent, "P571") if isinstance(v, dict)
                      for m in [re.match(r"^\+(\d{4})", v.get("time", ""))] if m), None)
    return {"id": qid, "url": f"https://www.wikidata.org/wiki/{qid}" if qid else None, "label": label(ent),
            "description": (ent.get("descriptions") or {}).get("tr", {}).get("value"),
            "website": [w for w in claims(ent, "P856") if isinstance(w, str)], "socials": socials,
            "wikipedia": wiki, "inception": inception}


def find_org(items: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Anasayfa JSON-LD'sinde kurum düğümü (Organization ya da alt tipleri)."""
    org = next((it for it in items if schema._types(it) & ORG_TYPES), None)
    if not org:
        return None
    return {k: org.get(k) for k in ("@type", "name", "description", "url", "logo", "sameAs", "foundingDate")}


def _as_list(v: Any) -> list[str]:
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return [x for x in v if isinstance(x, str)]
    return []


def _logo(v: Any) -> Optional[str]:
    if isinstance(v, dict):
        return v.get("url") or v.get("contentUrl")
    return v if isinstance(v, str) and v else None


def recommend_sameas(wd: Optional[dict[str, Any]], current: Any) -> list[str]:
    """Önerilen sameAs: Wikidata, Wikipedia (tr, en), Wikidata'daki sosyal hesaplar, sonra sayfada zaten olanlar.
    Tekrar eden (sondaki "/" ve "www." farkı dahil) atılır; sıra korunur."""
    urls: list[str] = []
    if wd:
        urls += [wd["url"]] if wd.get("url") else []
        urls += [wd["wikipedia"][k] for k in ("trwiki", "enwiki") if (wd.get("wikipedia") or {}).get(k)]
        urls += [s["url"] for s in wd.get("socials") or []]
    urls += _as_list(current)
    out, seen = [], set()
    for u in urls:
        key = re.sub(r"^https?://(www\.)?", "", u.strip().lower()).rstrip("/")
        if key and key not in seen:
            seen.add(key)
            out.append(u.strip())
    return out


def org_jsonld(site: str, wd: Optional[dict[str, Any]], current: Optional[dict[str, Any]]) -> dict[str, Any]:
    cur = current or {}
    out: dict[str, Any] = {"@context": "https://schema.org", "@type": "Organization", "name": ORG_NAME,
                           "url": site.rstrip("/") + "/",
                           "logo": _logo(cur.get("logo")) or f"{site.rstrip('/')}/…/logo.png"}
    founding = cur.get("foundingDate") or (wd or {}).get("inception")
    if founding:
        out["foundingDate"] = str(founding)
    out["sameAs"] = recommend_sameas(wd, cur.get("sameAs"))
    return out


def org_checks(wd: Optional[dict[str, Any]], wd_reason: str, site_org: Optional[dict[str, Any]], site_ok: bool,
               site: str) -> list[dict[str, Any]]:
    """Kurum kimliği denetimi: her madde {id, title, ok (True/False/None=bakılamadı), detail}."""
    ours = domain_of(site)
    out = []

    def add(cid: str, title: str, ok: Optional[bool], detail: str) -> None:
        out.append({"id": cid, "title": title, "ok": ok, "detail": detail})

    if wd:
        add("wikidata", "Wikidata'da kurum kaydı var", True, f"{wd['id']} · {wd.get('label') or ''}".strip(" ·"))
        webs = wd.get("website") or []
        add("wikidata_site", "Wikidata'da resmî site timas.com.tr", any(matches(domain_of(w), ours) for w in webs),
            ", ".join(webs) or "Resmî site (P856) girilmemiş.")
        add("wikidata_social", "Wikidata'da sosyal medya hesapları", bool(wd.get("socials")),
            ", ".join(s["network"] for s in wd["socials"]) or "Instagram/X/YouTube kimlikleri girilmemiş.")
        add("wikipedia", "Türkçe Wikipedia maddesi", bool((wd.get("wikipedia") or {}).get("trwiki")),
            (wd.get("wikipedia") or {}).get("trwiki") or "Wikidata kaydına bağlı Türkçe madde yok.")
    else:
        add("wikidata", "Wikidata'da kurum kaydı var", False,
            "Adı tutan birden çok kayıt var; doğru olanın resmî sitesi (P856) girilmeli." if wd_reason == "belirsiz"
            else "Wikidata'da Timaş Yayınları kaydı bulunamadı.")
    if not site_ok:
        add("site_org", "Anasayfada kurum şeması", None, "Anasayfa okunamadı.")
        return out
    add("site_org", "Anasayfada kurum şeması", bool(site_org),
        f"Tip: {site_org.get('@type')}" if site_org else "Anasayfada Organization tipinde yapılandırılmış veri yok.")
    if not site_org:
        return out
    name = rules.text_of(site_org.get("name"))
    add("site_name", "Şemadaki ad «Timaş Yayınları»", fold(name) == fold(ORG_NAME), name or "Ad yok.")
    add("site_logo", "Şemada logo", bool(_logo(site_org.get("logo"))), _logo(site_org.get("logo")) or "Logo yok.")
    same = [s.lower() for s in _as_list(site_org.get("sameAs"))]
    add("sameas_wikidata", "sameAs içinde Wikidata", any("wikidata.org" in s for s in same),
        "Var." if any("wikidata.org" in s for s in same) else "Wikidata bağlantısı yok.")
    add("sameas_wikipedia", "sameAs içinde Wikipedia", any("wikipedia.org" in s for s in same),
        "Var." if any("wikipedia.org" in s for s in same) else "Wikipedia bağlantısı yok.")
    want = [s["url"] for s in (wd or {}).get("socials") or []]
    missing = [u for u in want if not any(domain_of(u) == domain_of(s) and u.rstrip("/").lower().split("/")[-1] in s
                                          for s in same)]
    add("sameas_social", "sameAs içinde sosyal hesaplar",
        (not missing) if want else bool([s for s in same if "wiki" not in s]),
        ("Eksik: " + ", ".join(missing)) if missing else (f"{len(same)} bağlantı." if same else "sameAs boş."))
    return out


def split_authors(model: Any) -> list[str]:
    """T-soft `Model` bir ya da birden çok yazar taşır ("A, B", "A & B", "A; B")."""
    text = rules.text_of(model) if model else ""
    return [p.strip() for p in re.split(r"\s*(?:,|;|&|/)\s*", text) if len(p.strip()) > 2]


def author_status(result: dict[str, Any]) -> str:
    """Basın-web modülünün Wikidata sonucu → ekran durumu."""
    st = result.get("status")
    if st == "bulundu":
        return "wikipedia" if (result.get("facts") or {}).get("wikipedia") else "wikidata"
    return "belirsiz" if st == "belirsiz" else "yok"


def author_needs(status: str) -> list[str]:
    return {
        "yok": ["Wikidata'da kişi kaydı açılmalı: insan (P31=Q5), meslek yazar (P106), yayımlanmış eserleri (P800), "
                "resmî site ya da sosyal hesap.",
                "Kayda kaynak olarak yayınevinin yazar sayfası ve künyesi gösterilmeli.",
                "Kayıt açılınca kitap sayfalarında yazar şemasına sameAs olarak eklenmeli."],
        "wikidata": ["Türkçe Wikipedia maddesi — yalnız bağımsız kaynaklarda (basın, ödül, akademik) yeterince yer "
                     "alıyorsa; yayınevinin kendisi yazmamalı (çıkar çatışması).",
                     "Kitap sayfalarında yazar şemasına sameAs: Wikidata bağlantısı."],
        "belirsiz": ["Aynı adda birden çok kayıt var: doğru kişinin Wikidata kaydına eserleri (P800) ve yayınevi "
                     "eklenmeli ki ayrışsın."],
        "wikipedia": ["Kitap sayfalarında yazar şemasına sameAs: Wikidata ve Wikipedia bağlantıları."],
    }.get(status, [])


def isbn13(v: Any) -> Optional[str]:
    d = re.sub(r"[^0-9]", "", str(v or ""))
    return d if len(d) == 13 and d.startswith(("978", "979")) else None


def isbn_variants(isbn: str) -> list[str]:
    """Wikidata P212 tireli yazılır (978-605-4816-12-3); tire yeri yayıncı kodu uzunluğuna bağlıdır. Türkiye
    grupları (605, 625, 975) için bütün olası yayıncı kodu uzunlukları, ayrıca tiresiz hâl üretilir."""
    out = [isbn]
    if isbn[3:6] in ("605", "625", "975"):
        head, rest, check = f"{isbn[:3]}-{isbn[3:6]}", isbn[6:12], isbn[12]
        for n in range(2, 6):
            out.append(f"{head}-{rest[:n]}-{rest[n:]}-{check}")
    return out


def gb_checks(isbn: Optional[str], crm_book: Optional[dict[str, Any]], image: Optional[str]) -> dict[str, bool]:
    b = crm_book or {}
    return {"isbn": bool(isbn), "rights": b.get("rights") in ("var", "koruma_disi"),
            "status": bool(crm_book) and not b.get("statusFlag"), "cover": bool(image), "pdf": bool(b.get("previewPdf"))}


def stale(at: Any, days: int = REFRESH_DAYS) -> bool:
    if at is None:
        return True
    if at.tzinfo is None:
        from datetime import timezone
        at = at.replace(tzinfo=timezone.utc)
    return now() - at >= timedelta(days=days)


# ------------------------------------------------------------------------------ ağ (yalnız okuma)

def _http():
    import httpx

    return httpx.Client(headers={"User-Agent": USER_AGENT}, timeout=40, follow_redirects=True)


def _wd(client, params: dict[str, str]) -> dict[str, Any]:
    r = client.get(WIKIDATA_API, params={**params, "format": "json", "maxlag": "5"})
    r.raise_for_status()
    time.sleep(0.5)
    return r.json()


def lookup_org(client, site: str) -> tuple[Optional[dict[str, Any]], str]:
    hits = _wd(client, {"action": "wbsearchentities", "search": ORG_NAME, "language": "tr", "uselang": "tr",
                        "type": "item", "limit": "10"})
    ids = [h["id"] for h in hits.get("search", [])]
    if not ids:
        hits = _wd(client, {"action": "wbsearchentities", "search": "Timaş", "language": "tr", "type": "item", "limit": "10"})
        ids = [h["id"] for h in hits.get("search", [])]
    if not ids:
        return None, "yok"
    ents = _wd(client, {"action": "wbgetentities", "ids": "|".join(ids), "props": "labels|descriptions|claims|sitelinks",
                        "languages": "tr|en"}).get("entities", {})
    qid, why = pick_org(ids, ents, site)
    return (org_facts(ents[qid]) if qid else None), why


def sparql(client, query: str) -> list[dict[str, Any]]:
    r = client.post(SPARQL, data={"query": query}, headers={"Accept": "application/sparql-results+json"})
    r.raise_for_status()
    time.sleep(1.0)
    return r.json().get("results", {}).get("bindings", [])


# ------------------------------------------------------------------------------ çalışma

class Entity:
    def __init__(self, seo) -> None:
        self.seo = seo
        self._lock = threading.Lock()
        self.state: dict[str, Any] = {"running": False, "phase": None, "done": 0, "queue": None, "startedAt": None,
                                      "finishedAt": None, "error": None}

    def engine(self) -> sa.engine.Engine:
        eng = self.seo.engine()
        with _ready_lock:
            if id(eng) not in _ready:
                from semantic_layer.store import schema_stamp
                schema_stamp.create_all(_md, eng, tables=[ENTITY])
                _ready.add(id(eng))
        return eng

    def site(self) -> str:
        return (self.seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")

    def cached(self, kind: str) -> dict[str, tuple[dict[str, Any], Any]]:
        with self.engine().connect() as c:
            rows = c.execute(sa.select(ENTITY.c.name, ENTITY.c.data_json, ENTITY.c.checked_at).where(
                ENTITY.c.tenant_id == self.seo.tenant(), ENTITY.c.kind == kind)).all()
        return {n: (loads(d, {}), at) for n, d, at in rows}

    def save(self, kind: str, name: str, data: dict[str, Any]) -> None:
        tenant = self.seo.tenant()
        with self.engine().begin() as c:
            n = c.execute(ENTITY.update().where(ENTITY.c.tenant_id == tenant, ENTITY.c.kind == kind, ENTITY.c.name == name)
                          .values(data_json=dumps(data), checked_at=now())).rowcount
            if not n:
                c.execute(ENTITY.insert().values(tenant_id=tenant, kind=kind, name=name, data_json=dumps(data), checked_at=now()))

    def products(self) -> list[tuple[str, dict[str, Any], Optional[str]]]:
        """Aktif ürünler çok satandan aza: (ürün no, T-soft kaydı, CRM kartı JSON)."""
        from . import EAN, SALES, VIEWS

        tenant = self.seo.tenant()
        j = PRODUCTS.outerjoin(CRM_BOOKS, sa.and_(CRM_BOOKS.c.tenant_id == PRODUCTS.c.tenant_id, CRM_BOOKS.c.ean == EAN))
        with self.engine().connect() as c:
            rows = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.data_json, CRM_BOOKS.c.data_json).select_from(j)
                             .where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True))
                             .order_by(SALES.desc(), VIEWS.desc(), PRODUCTS.c.product_id)).all()
        return [(pid, loads(d, {}), crm_json) for pid, d, crm_json in rows]

    def authors(self, prods: Optional[list] = None) -> list[dict[str, Any]]:
        """Yazarlar satış toplamıyla (çok satandan aza), önbellekteki Wikidata durumuyla."""
        from . import _num

        agg: dict[str, dict[str, Any]] = {}
        for pid, p, _ in prods if prods is not None else self.products():
            for name in split_authors(p.get("Model")):
                a = agg.setdefault(fold(name), {"name": name, "sales": 0, "books": {}})
                a["sales"] += _num(p.get("CountTotalSales"))
                a["books"][pid] = rules.text_of(p.get("ProductName"))
        cache = self.cached("author")
        out = []
        for key, a in agg.items():
            data, at = cache.get(key[:300], ({}, None))
            status = data.get("status") or "bekliyor"
            out.append({"key": key, "name": a["name"], "sales": a["sales"], "books": len(a["books"]),
                        "titles": list(a["books"].values())[:5], "bookMap": a["books"], "status": status,
                        "label": AUTHOR_LABEL[status], "wikidata": data.get("wikidata"),
                        "wikipedia": data.get("wikipedia"), "description": data.get("description"),
                        "needs": author_needs(status), "checkedAt": iso(at), "stale": stale(at)})
        out.sort(key=lambda x: (-x["sales"], x["name"]))
        return out

    # -------------------------------------------------------------- tazeleme
    def start(self, budget: int, force: bool = False) -> bool:
        if not self._lock.acquire(blocking=False):
            return False
        self.state.update(running=True, phase=None, done=0, queue=None, startedAt=iso(now()), finishedAt=None, error=None)
        threading.Thread(target=self._run, args=(budget, force), name="seo-entity", daemon=True).start()
        return True

    def _run(self, budget: int, force: bool) -> None:
        deadline = time.monotonic() + max(60, budget)
        try:
            with _http() as client:
                org_cache = self.cached("org").get("_org")
                if force or not org_cache or stale(org_cache[1]):
                    self.state["phase"] = "kurum"
                    self.refresh_org(client)
                prods = self.products()
                books_cache = self.cached("books").get("_isbn")
                if force or not books_cache or stale(books_cache[1]):
                    self.state["phase"] = "kitaplar"
                    self.refresh_isbn(client, prods, deadline)
            self.state["phase"] = "yazarlar"
            self.refresh_authors(prods, deadline, force)
        except Exception as e:  # noqa: BLE001 — tur durur, bakılanlar kalır
            self.state["error"] = str(e)[:500]
            log.exception("seo entity refresh failed")
        finally:
            self.state.update(running=False, phase=None, finishedAt=iso(now()))
            self._lock.release()

    def refresh_org(self, client) -> dict[str, Any]:
        site = self.site()
        wd, why = lookup_org(client, site)
        site_org, site_ok = None, False
        fetcher = schema.Fetcher(site)
        try:
            code, html = fetcher.get(site + "/")
            if code == 200:
                site_ok = True
                site_org = find_org(schema.parse(html)["items"])
        except Exception:  # noqa: BLE001 — anasayfa açılmazsa madde "bakılamadı" olur
            pass
        finally:
            fetcher.close()
        data = {"wikidata": wd, "wikidataReason": why, "site": site_org, "siteOk": site_ok}
        self.save("org", "_org", data)
        return data

    def refresh_isbn(self, client, prods: list, deadline: float) -> None:
        isbns = list(dict.fromkeys(i for _, p, _ in prods if (i := isbn13(p.get("Barcode")))))
        found: dict[str, str] = {}
        org = (self.cached("org").get("_org") or ({}, None))[0].get("wikidata") or {}
        by_publisher = 0
        if org.get("id"):
            rows = sparql(client, f"SELECT ?item ?isbn WHERE {{ ?item wdt:P123 wd:{org['id']} . "
                                  "OPTIONAL { ?item wdt:P212 ?isbn } }")
            by_publisher = len({r["item"]["value"] for r in rows})
            for r in rows:
                d = isbn13((r.get("isbn") or {}).get("value"))
                if d:
                    found[d] = r["item"]["value"].rsplit("/", 1)[-1]
        self.state["queue"] = len(isbns)
        checked = 0
        for i in range(0, len(isbns), BATCH):
            if time.monotonic() > deadline:
                break
            chunk = isbns[i:i + BATCH]
            values = " ".join(json.dumps(v) for x in chunk for v in isbn_variants(x))
            for r in sparql(client, f"SELECT ?item ?isbn WHERE {{ VALUES ?isbn {{ {values} }} ?item wdt:P212 ?isbn . }}"):
                d = isbn13(r["isbn"]["value"])
                if d:
                    found[d] = r["item"]["value"].rsplit("/", 1)[-1]
            checked += len(chunk)
            self.state["done"] = checked
        active = set(isbns)
        self.save("books", "_isbn", {"active": len(isbns), "checked": checked, "complete": checked >= len(isbns),
                                     "found": {k: v for k, v in found.items() if k in active},
                                     "byPublisher": by_publisher})

    def refresh_authors(self, prods: list, deadline: float, force: bool) -> None:
        from semantic_bridge import web_watch

        todo = [a for a in self.authors(prods) if force or a["stale"]]
        self.state.update(queue=len(todo), done=0)
        for a in todo:
            if time.monotonic() > deadline:
                break
            try:
                got = web_watch.wikidata_author(a["name"], a["bookMap"])
            except Exception as e:  # noqa: BLE001 — bir yazar düşerse sıradaki; ağ sorunu için kısa bekleme
                log.warning("wikidata author %s: %s", a["name"], e)
                time.sleep(5)
                continue
            st = author_status(got)
            f = got.get("facts") or {}
            self.save("author", a["key"][:300], {"name": a["name"], "status": st, "wikidata": f.get("wikidata"),
                                                 "wikipedia": f.get("wikipedia"), "description": f.get("description")})
            self.state["done"] += 1

    # -------------------------------------------------------------- okuma
    def organization(self) -> Optional[dict[str, Any]]:
        got = self.cached("org").get("_org")
        if not got:
            return None
        data, at = got
        site, wd = self.site(), data.get("wikidata")
        rec = org_jsonld(site, wd, data.get("site"))
        return {"checkedAt": iso(at), "wikidata": wd, "wikidataReason": data.get("wikidataReason"),
                "site": data.get("site"), "siteOk": data.get("siteOk"),
                "checks": org_checks(wd, data.get("wikidataReason") or "yok", data.get("site"), bool(data.get("siteOk")), site),
                "sameAs": rec["sameAs"], "jsonld": json.dumps(rec, ensure_ascii=False, indent=2)}

    def google_books(self, prods: Optional[list] = None) -> list[dict[str, Any]]:
        from . import _image, _num

        site = self.site()
        out = []
        for pid, p, crm_json in prods if prods is not None else self.products():
            b = loads(crm_json, None) if crm_json else None
            isbn, image = isbn13(p.get("Barcode")), _image(p, site)
            checks = gb_checks(isbn, b, image)
            ebook = any(c.get("inForce") and c.get("ebook") for c in (b or {}).get("contracts") or [])
            link = p.get("SeoLink")
            out.append({"id": pid, "name": rules.text_of(p.get("ProductName")), "author": rules.text_of(p.get("Model")),
                        "image": image, "url": f"{site}/{str(link).strip('/')}" if link else None,
                        "sales": _num(p.get("CountTotalSales")), "isbn": isbn,
                        "rights": (b or {}).get("rights"), "statusFlag": (b or {}).get("statusFlag"),
                        "previewPdf": (b or {}).get("previewPdf"), "ebookRight": ebook, "inCrm": bool(b),
                        "checks": checks, "missing": [GB_CHECKS[k] for k, ok in checks.items() if not ok],
                        "ready": all(checks.values())})
        return out

    def overview(self) -> dict[str, Any]:
        prods = self.products()
        authors = self.authors(prods)
        gb = self.google_books(prods)
        isbn = self.cached("books").get("_isbn")
        counts = {k: sum(1 for a in authors if a["status"] == k) for k in AUTHOR_STATUS}
        checked = [a["checkedAt"] for a in authors if a["checkedAt"]]
        return {
            "organization": self.organization(),
            "authors": {"total": len(authors), "counts": counts, "labels": AUTHOR_LABEL,
                        "lastChecked": max(checked, default=None),
                        "top": [{k: a[k] for k in ("name", "sales", "status", "label")} for a in authors[:10]]},
            "books": {
                "isbn": ({**{k: v for k, v in isbn[0].items() if k != "found"}, "found": len(isbn[0].get("found") or {}),
                          "checkedAt": iso(isbn[1])} if isbn else None),
                "googleBooks": {"total": len(gb), "ready": sum(1 for x in gb if x["ready"]),
                                "missing": {k: sum(1 for x in gb if not x["checks"][k]) for k in GB_CHECKS},
                                "checks": GB_CHECKS},
            },
            "state": self.state, "refreshDays": REFRESH_DAYS,
        }


def _page(items: list, start: int, limit: int) -> tuple[int, list]:
    s = max(0, start)
    return s, items[s:s + max(1, limit)]


def register(app, ctx) -> None:
    ent = Entity(ctx.seo)
    ctx.seo.entity = ent

    @app.get("/api/v1/seo-geo/entity")
    def seo_entity(request: Request) -> dict[str, Any]:
        ctx.gate(request)
        return ent.overview()

    @app.get("/api/v1/seo-geo/entity/authors")
    def seo_entity_authors(request: Request, status: str = "", q: str = "", start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        if status and status not in AUTHOR_STATUS:
            from . import _err
            raise _err(422, "Bilinmeyen durum.")
        rows = ent.authors()
        counts = {k: sum(1 for a in rows if a["status"] == k) for k in AUTHOR_STATUS}
        if status:
            rows = [a for a in rows if a["status"] == status]
        if q.strip():
            rows = [a for a in rows if fold(q) in a["key"]]
        s, page = _page(rows, start, limit)
        return {"total": len(rows), "start": s, "counts": counts,
                "items": [{k: v for k, v in a.items() if k not in ("bookMap", "key")} for a in page]}

    @app.get("/api/v1/seo-geo/entity/google-books")
    def seo_entity_gb(request: Request, ready: str = "", missing: str = "", start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        rows = ent.google_books()
        summary = {"total": len(rows), "ready": sum(1 for x in rows if x["ready"]),
                   "missing": {k: sum(1 for x in rows if not x["checks"][k]) for k in GB_CHECKS}, "checks": GB_CHECKS}
        if ready in ("1", "0"):
            rows = [x for x in rows if x["ready"] == (ready == "1")]
        if missing in GB_CHECKS:
            rows = [x for x in rows if not x["checks"][missing]]
        s, page = _page(rows, start, limit)
        return {"total": len(rows), "start": s, "items": page, "summary": summary}

    @app.post("/api/v1/seo-geo/entity/refresh")
    def seo_entity_refresh(request: Request, budget: int = 1800, force: bool = False) -> dict[str, Any]:
        user = ctx.gate(request)
        started = ent.start(budget, force)
        ctx.seo.audit(user, "run", "entity", "Kimlik denetimi", {"started": started, "force": force, "budget": budget})
        return {"started": started, "state": ent.state}

    def nightly() -> None:
        ent.start(1800, False)   # yalnız eskimiş kayıtlar; 30 dk bütçe, kalan ertesi gece

    ctx.seo.nightly.append(("entity", nightly))
