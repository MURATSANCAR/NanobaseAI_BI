"""Kitap SEO karnesi: bir kitabın bütün SEO/GEO modüllerindeki durumu tek sayfada.

Her bölüm başka bir modülün tablosundan ya da hesabından okunur (ürün denetimi, CRM, şema, teknik tarama, Google
taraması, Search Console, yarışan sayfalar, site içi bağlantılar, yorumlar, video, rakipler, yapay zekâ ölçümü, sezon
takvimi, satıştan kalkan, yazar güven sinyalleri, rehberler, hız, gelen bağlantılar). Bölüm biçimi:

    {id, title, status: iyi|dikkat|sorun|bilinmiyor, summary, facts: [{label, value}], actions: [{text, link}],
     link, reason}

Bir modül henüz hiç çalışmadıysa (tablosu yok ya da boş) ya da okunamadıysa bölüm "bilinmiyor" döner ve nedeni
yazılır; karne asla bu yüzden hata vermez.

Genel not: bilinen bölümlerin ağırlıklı ortalaması (iyi 100, dikkat 60, sorun 20; ağırlıklar `SECTIONS`'ta ve yanıtta
açıkça durur). "Önce yapılacak 3 iş": önce sorunlu, sonra dikkat isteyen bölümlerin ilk işleri, ağırlığa göre.

Yalnız okunur: T-soft'a, CRM'e ya da başka bir yere hiçbir şey yazılmaz; ağ isteği yapılmaz.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timezone
from typing import Any, Callable, Optional
from urllib.parse import quote

import sqlalchemy as sa
from fastapi import Request

from . import rules
from .store import CRM_BOOKS, GEO_RESULTS, PRODUCTS, PROPOSALS, QUESTIONS, SCHEMA, iso, loads

log = logging.getLogger("semantic.seo_geo.scorecard")

STATUSES = ("iyi", "dikkat", "sorun", "bilinmiyor")
#: Durum → puan. "bilinmiyor" hesaba girmez (paydadan da çıkar).
POINTS = {"iyi": 100, "dikkat": 60, "sorun": 20}
#: Harf notu alt sınırları (puan ≥ sınır).
LETTERS = (("A", 85), ("B", 70), ("C", 55), ("D", 0))
#: Bilinen bölümlerin ağırlık payı bundan azsa not "az veriyle" işaretlenir.
MIN_COVERAGE = 0.5
TOP_N = 3

#: Bölüm → (başlık, ağırlık, ayrıntı ekranı). `{pid}` ürün kimliğiyle doldurulur. Sıra ekrandaki sıradır.
SECTIONS: dict[str, tuple[str, int, str]] = {
    "urun": ("Ürün kaydı ve öneri", 20, "/seo-geo/urun-denetimi?urun={pid}"),
    "crm": ("Haklar ve CRM", 8, "/seo-geo/crm-haklar?urun={pid}"),
    "google": ("Google taraması", 12, "/seo-geo/google-taramasi"),
    "arama": ("Arama performansı", 10, "/seo-geo/firsatlar"),
    "teknik": ("Teknik", 10, "/seo-geo/teknik"),
    "sema": ("Şema", 8, "/seo-geo/sema"),
    "ic_baglanti": ("Site içi bağlantılar", 6, "/seo-geo/ic-baglantilar"),
    "rakipler": ("Rakipler", 5, "/seo-geo/rakipler"),
    "yapay_zeka": ("Yapay zekâ", 5, "/seo-geo/ai-gorunurluk"),
    "satistan_kalkan": ("Satıştan kalkan", 5, "/seo-geo/satistan-kalkan"),
    "yarisan": ("Yarışan sayfalar", 4, "/seo-geo/yarisan"),
    "yorumlar": ("Okur yorumları", 4, "/seo-geo/yorumlar"),
    "yazar": ("Yazar", 4, "/seo-geo/yazar-sayfalari"),
    "hiz": ("Hız", 4, "/seo-geo/teknik?sekme=hiz"),
    "sezon": ("Sezon", 3, "/seo-geo/takvim"),
    "geri_baglanti": ("Gelen bağlantılar", 3, "/seo-geo/geri-baglantilar"),
    "video": ("Video", 2, "/seo-geo/video"),
    "rehber": ("Rehber", 2, "/seo-geo/rehberler"),
}
WEIGHTS = {k: v[1] for k, v in SECTIONS.items()}
NOT_RUN = "Bu ölçüm henüz hiç çalışmadı; gece işi ya da ilgili ekrandaki düğme ilk okumayı yapar."


# ================================================================================================ saf işlevler

def link_of(sid: str, pid: str) -> str:
    return SECTIONS[sid][2].replace("{pid}", pid)


def section(sid: str, pid: str, status: str, summary: str, facts: Optional[list[tuple[str, Any]]] = None,
            actions: Optional[list[tuple[str, Optional[str]]]] = None, reason: Optional[str] = None,
            extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Bölüm sözlüğü. `facts`: (etiket, değer); boş değerli olgu atlanır. `actions`: (metin, bağlantı|None → bölüm
    ekranı)."""
    if status not in STATUSES:
        raise ValueError(status)
    link = link_of(sid, pid)
    return {"id": sid, "title": SECTIONS[sid][0], "weight": SECTIONS[sid][1], "status": status, "summary": summary,
            "facts": [{"label": k, "value": v} for k, v in (facts or []) if v not in (None, "")],
            "actions": [{"text": t, "link": l or link} for t, l in (actions or []) if t],
            "link": link, "reason": reason, **(extra or {})}


def unknown(sid: str, pid: str, reason: str) -> dict[str, Any]:
    return section(sid, pid, "bilinmiyor", reason, reason=reason)


def letter(score: Optional[float]) -> Optional[str]:
    if score is None:
        return None
    return next(l for l, lo in LETTERS if score >= lo)


def grade(sections: list[dict[str, Any]], weights: Optional[dict[str, int]] = None) -> dict[str, Any]:
    """Bilinen bölümlerin ağırlıklı ortalaması. Bilinmeyen bölüm hesaba girmez; kapsama ayrıca verilir."""
    weights = weights or WEIGHTS
    known = [s for s in sections if s["status"] in POINTS]
    total_w = sum(weights.get(s["id"], 0) for s in sections)
    known_w = sum(weights.get(s["id"], 0) for s in known)
    score = round(sum(weights.get(s["id"], 0) * POINTS[s["status"]] for s in known) / known_w) if known_w else None
    coverage = (known_w / total_w) if total_w else 0.0
    counts = {k: sum(1 for s in sections if s["status"] == k) for k in STATUSES}
    return {"score": score, "letter": letter(score), "coverage": round(coverage, 3),
            "lowData": coverage < MIN_COVERAGE, "counts": counts, "points": POINTS,
            "letters": [{"letter": l, "min": lo} for l, lo in LETTERS]}


def top_actions(sections: list[dict[str, Any]], n: int = TOP_N) -> list[dict[str, Any]]:
    """Önce sorunlu, sonra dikkat isteyen bölümler; her bölümün önce ilk işi (çeşitlilik), sonra ağırlık."""
    rank = {"sorun": 0, "dikkat": 1}
    cands = []
    for s in sections:
        if s["status"] not in rank:
            continue
        for i, a in enumerate(s["actions"]):
            cands.append(((rank[s["status"]], i, -s.get("weight", 0), s["id"]), s, a))
    cands.sort(key=lambda c: c[0])
    out, seen = [], set()
    for _, s, a in cands:
        if a["text"] in seen:
            continue
        seen.add(a["text"])
        out.append({"text": a["text"], "link": a["link"], "sectionId": s["id"], "section": s["title"], "status": s["status"]})
        if len(out) >= n:
            break
    return out


_SEV_RANK = {"kritik": 0, "yüksek": 1, "orta": 2, "düşük": 3}


def severity_status(severities: list[str]) -> str:
    """Açık sorunların önemine göre: kritik → sorun; yüksek/orta → dikkat; yalnız düşük ya da hiç → iyi."""
    if any(s == "kritik" for s in severities):
        return "sorun"
    if any(s in ("yüksek", "orta") for s in severities):
        return "dikkat"
    return "iyi"


def split_flags(raw: Optional[str]) -> list[str]:
    return [x for x in (raw or "").split(",") if x]


def product_status(score: Optional[int], issues: list[dict[str, Any]]) -> str:
    sev = [i.get("severity") for i in issues]
    if score is None:
        return "bilinmiyor"
    if score < 50 or "kritik" in sev:
        return "sorun"
    if score < 80 or "yüksek" in sev:
        return "dikkat"
    return "iyi"


def rights_status(book: Optional[dict[str, Any]]) -> str:
    if not book:
        return "dikkat"
    if book.get("statusFlag"):
        return "sorun"
    r = book.get("rights")
    if r == "eksik":
        return "sorun"
    if r in ("incele", "yok"):
        return "dikkat"
    return "iyi"


def search_status(clicks: int, impressions: int, position: Optional[float], low_ctr: int) -> str:
    if impressions <= 0:
        return "sorun"
    if (position is not None and position > 10) or low_ctr:
        return "dikkat"
    return "iyi"


def links_status(followed: int, depth: Optional[int], deep: int, weak: int, author_linked: Optional[bool]) -> str:
    if followed <= 0:
        return "sorun"
    if followed < weak or (depth is not None and depth > deep) or author_linked is False:
        return "dikkat"
    return "iyi"


def reviews_status(count: int, average: Optional[float], schema_missing: bool) -> str:
    if count <= 0 or (average is not None and average <= 3) or schema_missing:
        return "dikkat"
    return "iyi"


def speed_status(score: Optional[float], categories: list[Optional[str]]) -> str:
    if "poor" in categories or (score is not None and score < 50):
        return "sorun"
    if "ni" in categories or (score is not None and score < 90):
        return "dikkat"
    return "iyi"


def book_key(name: Any) -> str:
    """GEO ölçümündeki kitap adıyla karşılaştırma anahtarı (geo.book_index ile aynı temizlik)."""
    return re.sub(r"\s*\(.*?\)\s*$", "", rules.text_of(name)).strip().casefold()


def books_mention(books: Any, key: str) -> bool:
    return bool(key) and any(str(b).strip().casefold() == key for b in (books or []))


def pct(v: Optional[float], digits: int = 1) -> Optional[str]:
    return None if v is None else f"%{v * 100:.{digits}f}".replace(".", ",")


def num(v: Any, digits: int = 0) -> Optional[str]:
    if v is None:
        return None
    s = f"{float(v):,.{digits}f}"
    return s.replace(",", "_").replace(".", ",").replace("_", ".")


def yesno(v: Optional[bool]) -> Optional[str]:
    return None if v is None else ("Var" if v else "Yok")


# ================================================================================================ bağlam

class Book:
    """Tek istek boyunca kitabın ortak bilgisi."""

    def __init__(self, seo: Any, pid: str) -> None:
        from . import _product_view

        self.seo, self.pid = seo, pid
        self.eng = seo.engine()
        self.tenant = seo.tenant()
        self.site = (seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")
        self.row = seo.product_row(pid)
        self.p = loads(self.row["data_json"], {})
        self.view = _product_view(self.row, self.site)
        self.url: Optional[str] = self.view.get("url")
        self.today = date.today()
        self._insp = sa.inspect(self.eng)
        self._crm: Any = ...

    def has(self, table: sa.Table) -> bool:
        return self._insp.has_table(table.name)

    def path(self) -> Optional[str]:
        from .opportunities import path_key

        return path_key(self.p.get("SeoLink") or self.url)

    def crm(self) -> Optional[dict[str, Any]]:
        if self._crm is ...:
            self._crm = self.seo.crm_book(self.p)
        return self._crm

    def crm_read(self) -> bool:
        with self.eng.connect() as c:
            return bool(c.execute(sa.select(sa.func.count()).select_from(CRM_BOOKS)
                                  .where(CRM_BOOKS.c.tenant_id == self.tenant)).scalar())


# ================================================================================================ bölümler

def s_urun(b: Book) -> dict[str, Any]:
    from . import propose

    issues = sorted(loads(b.row["issues_json"], []), key=lambda i: (-(i.get("weight") or 0), i.get("rule") or ""))
    with b.eng.connect() as c:
        prop = c.execute(sa.select(PROPOSALS.c.status, PROPOSALS.c.created_at, PROPOSALS.c.score_after,
                                   PROPOSALS.c.decided_at).where(PROPOSALS.c.tenant_id == b.tenant,
                                                                 PROPOSALS.c.product_id == b.pid)
                         .order_by(PROPOSALS.c.created_at.desc()).limit(1)).mappings().first()
    status = product_status(b.row["score"], issues)
    labels = {"hazir": "Onay bekliyor", "onaylandi": "Onaylandı", "reddedildi": "Reddedildi"}
    actions: list[tuple[str, Optional[str]]] = []
    if prop and prop["status"] == "hazir":
        actions.append((f"ZEKİ AI önerisi onay bekliyor (puanı {prop['score_after']} yapar): inceleyip karar verin", None))
    fixable = [i for i in issues if propose.RULE_FIELD.get(i.get("rule"))]
    if fixable and not (prop and prop["status"] == "hazir"):
        actions.append(("ZEKİ AI’dan SEO alanları için öneri isteyin", None))
    actions += [(f"{i.get('title')}", None) for i in issues if not propose.RULE_FIELD.get(i.get("rule"))]
    if not actions and issues:
        actions.append((issues[0].get("title"), None))
    summary = (f"Puan {b.row['score']}/100, {len(issues)} açık sorun" if issues else f"Puan {b.row['score']}/100, açık sorun yok")
    facts = [("SEO puanı", f"{b.row['score']}/100"), ("Açık sorun", str(len(issues))),
             ("Sorunlar", ", ".join(i.get("title") or i.get("rule") for i in issues) or None),
             ("Son öneri", f"{labels.get(prop['status'], prop['status'])} · {iso(prop['created_at'])[:10]}" if prop else "Hiç istenmedi"),
             ("Son eşitleme", (iso(b.row["synced_at"]) or "")[:10])]
    return section("urun", b.pid, status, summary, facts, actions)


def s_crm(b: Book) -> dict[str, Any]:
    from .crm import RIGHTS

    book = b.crm()
    if not book:
        if not b.crm_read():
            return unknown("crm", b.pid, "CRM henüz okunmadı.")
        return section("crm", b.pid, "dikkat", "Barkod CRM’deki hiçbir kitap kartıyla eşleşmedi; hak ve yayın durumu bilinmiyor.",
                       [("Barkod", b.view.get("barcode"))], [("Ürünün barkodunu CRM kartındaki EAN-13 ile eşleştirin", None)])
    rights_label = {"var": "Hak var", "incele": "İncelenmeli", "eksik": "Hak eksik", "yok": "Sözleşme kaydı yok",
                    "koruma_disi": "Koruma dışı eser", "set": "Set (içindeki kitaplar)", "kitap_degil": "Kitap değil"}
    r = book.get("rights")
    actions: list[tuple[str, Optional[str]]] = []
    if book.get("statusFlag"):
        actions.append((f"CRM’de «{book.get('statusLabel')}» ama sitede satışta: yayın birimi sayfanın kalıp kalmayacağına karar vermeli", None))
    if r == "eksik":
        actions.append(("İnternette gösterim hakkı eksik: telif birimiyle netleştirin, o zamana kadar alıntı kullanmayın", None))
    elif r in ("incele", "yok"):
        actions.append(("Telif sözleşmesindeki internet hakkını telif birimine doğrulatın", None))
    if r == "var" and not book.get("previewPdf"):
        actions.append(("Hak var ama tadımlık PDF yok: CRM kartına tadımlık PDF eklenebilir", None))
    status = rights_status(book)
    facts = [("İnternette gösterim", rights_label.get(r, r) if r in RIGHTS else r), ("Yayın durumu", book.get("statusLabel")),
             ("Tür", book.get("kind")), ("Tadımlık PDF", yesno(bool(book.get("previewPdf")))),
             ("Video", yesno(bool(book.get("video")))), ("Yürürlükteki sözleşme", str(book.get("inForce", 0)))]
    return section("crm", b.pid, status, book.get("rightsWhy") or rights_label.get(r, ""), facts, actions)


def s_sema(b: Book) -> dict[str, Any]:
    from . import schema

    with b.eng.connect() as c:
        r = c.execute(sa.select(SCHEMA).where(SCHEMA.c.tenant_id == b.tenant, SCHEMA.c.product_id == b.pid)).mappings().first()
    if not r:
        return unknown("sema", b.pid, "Sayfa henüz şema taramasından geçmedi.")
    flags = sorted(split_flags(r["issues"]), key=lambda f: _SEV_RANK.get(schema.CHECKS.get(f, ("düşük",))[0], 9))
    sev = [schema.CHECKS[f][0] for f in flags if f in schema.CHECKS]
    status = severity_status(sev)
    titles = [schema.CHECKS[f][1] if f in schema.CHECKS else f for f in flags]
    types = loads(r["types_json"], [])
    facts = [("Sayfa durumu", str(r["status"]) if r["status"] else None), ("Bulunan şemalar", ", ".join(map(str, types)) or "Yok"),
             ("Eksikler", ", ".join(titles) or "Yok"), ("Son tarama", (iso(r["checked_at"]) or "")[:10])]
    summary = f"{len(flags)} eksik: {', '.join(titles[:3])}" + ("…" if len(titles) > 3 else "") if flags else "Kitap şeması tam"
    return section("sema", b.pid, status, summary, facts,
                   [(f"{t} — tema isteğine ekleyin", None) for t in titles])


def s_teknik(b: Book) -> dict[str, Any]:
    from .tech import CHECKS, TECH

    if not b.has(TECH):
        return unknown("teknik", b.pid, NOT_RUN)
    with b.eng.connect() as c:
        r = c.execute(sa.select(TECH).where(TECH.c.tenant_id == b.tenant, TECH.c.product_id == b.pid)
                      .order_by(TECH.c.checked_at.desc()).limit(1)).mappings().first()
    if not r:
        return unknown("teknik", b.pid, "Bu kitabın sayfası henüz teknik taramaya girmedi (tarama çok satandan başlar).")
    flags = sorted(split_flags(r["issues"]), key=lambda f: _SEV_RANK.get(CHECKS.get(f, ("düşük",))[0], 9))
    status = severity_status([CHECKS[f][0] for f in flags if f in CHECKS])
    titles = [CHECKS[f][1] if f in CHECKS else f for f in flags]
    chain = loads(r["chain_json"], [])
    facts = [("Durum kodu", str(r["status"]) if r["status"] else "Açılamadı"),
             ("Yönlendirme", f"{len(chain) - 1} adım" if len(chain) > 1 else "Yok"),
             ("Sorunlar", ", ".join(titles) or "Yok"), ("Son tarama", (iso(r["checked_at"]) or "")[:10])]
    summary = f"{len(flags)} teknik sorun: {', '.join(titles[:2])}" + ("…" if len(titles) > 2 else "") if flags else "Teknik sorun yok"
    return section("teknik", b.pid, status, summary, facts, [(t, None) for t in titles])


def s_google(b: Book) -> dict[str, Any]:
    from .crawlbot import INSPECT, STALE_CRAWL_DAYS, STATUS_LABEL, days_since, row_status

    if not b.has(INSPECT):
        return unknown("google", b.pid, NOT_RUN)
    with b.eng.connect() as c:
        r = c.execute(sa.select(INSPECT).where(INSPECT.c.tenant_id == b.tenant, INSPECT.c.product_id == b.pid)
                      .order_by(INSPECT.c.inspected_at.desc()).limit(1)).mappings().first()
    if not r:
        return unknown("google", b.pid, "Bu sayfa henüz Google’a sorulmadı (günlük kotayla çok satandan başlanır).")
    st = row_status(dict(r))
    label, tone = STATUS_LABEL.get(st, (st, "mid"))
    status = {"good": "iyi", "bad": "sorun"}.get(tone, "dikkat")
    age = days_since(r["last_crawl"])
    actions: list[tuple[str, Optional[str]]] = []
    if status != "iyi":
        actions.append((f"Google: «{label}» — nedenini Google taraması ekranında inceleyin", None))
    if r["canonical_mismatch"]:
        if status == "iyi":
            status = "dikkat"
        actions.append(("Google sayfanın canonical’ını başka adres seçmiş: canonical ve iç bağlantıları düzeltin", None))
    if st != "error" and (age is None or age > STALE_CRAWL_DAYS):
        if status == "iyi":
            status = "dikkat"
        actions.append(("Google sayfayı uzun süredir taramadı: site içi bağlantı ve site haritasını güçlendirin", None))
    facts = [("Durum", label), ("Son Google taraması", f"{age} gün önce" if age is not None else "Hiç"),
             ("Taranan cihaz", {"MOBILE": "Mobil", "DESKTOP": "Masaüstü"}.get(str(r["crawled_as"] or "").upper(), r["crawled_as"])),
             ("Canonical uyuşmazlığı", "Var" if r["canonical_mismatch"] else "Yok"),
             ("Denetlendi", (iso(r["inspected_at"]) or "")[:10])]
    return section("google", b.pid, status, label, facts, actions)


def ga4_facts(b: Book) -> list[tuple[str, Any]]:
    """Google Analytics (aramadan satışa): ürüne eşlenen giriş sayfalarının son 28 gün organik oturum/sepet/satış/ciro."""
    try:
        from . import ga4

        t = ga4.product_totals(b.eng, b.tenant, b.pid)
    except Exception as e:  # noqa: BLE001 — okuma yoksa satır yok
        log.info("seo scorecard ga4 %s: %s", b.pid, e)
        return []
    if not t:
        return []
    c, p = t["cur"], t["prev"]
    ch = ga4.pct(c["revenue"], p["revenue"])
    out = [("Google’dan gelen ziyaret (Google Analytics, 28 gün)",
            f"{num(c['sessions'])} oturum · {num(c['carts'])} sepete ekleme · {num(c['purchases'])} satış"),
           ("Google’dan gelen ciro (28 gün)", f"{num(c['revenue'])} ₺" + (f" ({ch:+.0f}% önceki 28 güne göre)" if ch is not None else ""))]
    if t["flags"]:
        out.append(("Aramadan satış uyarısı", ", ".join(ga4.FLAGS.get(f, f) for f in t["flags"])))
    return out


def s_arama(b: Book) -> dict[str, Any]:
    from . import impact, opportunities as opps

    key = b.path()
    pages = b.seo.gsc("pages")
    src = opps.source(b.seo)
    if not pages and src["from"] is None:
        return unknown("arama", b.pid, "Search Console henüz okunmadı ya da bağlı değil.")
    row = next((r for r in (pages or {}).get("rows") or [] if key and opps.path_key((r.get("keys") or [""])[0]) == key), None)
    clicks = int(float((row or {}).get("clicks") or 0))
    impr = int(float((row or {}).get("impressions") or 0))
    pos = float(row["position"]) if row and row.get("position") else None
    queries = []
    if src["from"] == "query_page" and key:
        for r in src["rows"]:
            k = r.get("keys") or []
            if len(k) > 1 and opps.path_key(k[1]) == key:
                queries.append({"query": k[0], "clicks": int(float(r.get("clicks") or 0)),
                                "impressions": int(float(r.get("impressions") or 0)), "position": r.get("position")})
        queries.sort(key=lambda q: (-q["clicks"], -q["impressions"], q["query"]))
    my_opps = [i for i in opps.computed(b.seo)["items"] if key and i.get("page") and opps.path_key(i["page"]) == key]
    low = [i for i in my_opps if "dusuk_tiklama" in i["kinds"]]
    near = [i for i in my_opps if "yakin" in i["kinds"]]
    last_impact = None
    if b.has(impact.IMPACT):
        with b.eng.connect() as c:
            last_impact = c.execute(sa.select(impact.IMPACT).where(impact.IMPACT.c.tenant_id == b.tenant,
                                                                   impact.IMPACT.c.product_id == b.pid)
                                    .order_by(impact.IMPACT.c.applied_at.desc().nullslast()).limit(1)).mappings().first()
    status = search_status(clicks, impr, pos, len(low))
    actions: list[tuple[str, Optional[str]]] = []
    if impr <= 0:
        actions.append(("Sayfa son 28 günde Google’da hiç gösterilmedi: başlık, açıklama ve iç bağlantıları güçlendirin",
                        link_of("urun", b.pid)))
    for i in low:
        actions.append((f"«{i['query']}» aramasında çok gösterilip az tıklanıyor: başlık ve meta açıklamayı yenileyin",
                        link_of("urun", b.pid)))
    for i in near:
        actions.append((f"«{i['query']}» aramasında {i['position']:.1f}. sırada: ilk üçe yakın, sayfayı bu arama için güçlendirin", None))
    facts = [("Dönem", f"{pages['start']} – {pages['end']}" if pages else None), ("Tıklama", num(clicks)),
             ("Gösterim", num(impr)), ("Tıklama oranı", pct(clicks / impr) if impr else None),
             ("Ortalama sıra", num(pos, 1) if pos else None),
             ("Öne çıkan aramalar", ", ".join(q["query"] for q in queries[:5]) or None),
             ("Fırsat", f"{len(near)} yakın sıra · {len(low)} düşük tıklama" if my_opps else None)]
    if last_impact:
        d = impact.delta(loads(last_impact["before_json"], None), loads(last_impact["after_json"], None))
        facts.append(("Son onaylı değişikliğin etkisi",
                      (f"Tıklama {d['clicksPct']:+.0f}%" if d and d.get("clicksPct") is not None else
                       {"olculuyor": "Ölçülüyor", "veri_yok": "Veri yok", "bekliyor": "Sitede bekleniyor"}.get(
                           last_impact["status"], last_impact["status"]))))
    facts += ga4_facts(b)
    summary = (f"{num(clicks)} tıklama, {num(impr)} gösterim" + (f", ortalama {num(pos, 1)}. sıra" if pos else "")
               if impr else "Son 28 günde Google’da gösterim yok")
    return section("arama", b.pid, status, summary, facts, actions, extra={"queries": queries})


def s_yarisan(b: Book) -> dict[str, Any]:
    from . import cannibal

    data = cannibal.computed(b.seo)
    if data["source"]["from"] != "query_page":
        return unknown("yarisan", b.pid, "Hangi aramada hangi sayfanın göründüğü henüz okunmadı.")
    mine = [i for i in data["items"] if any((p.get("product") or {}).get("id") == b.pid for p in i["pages"])]
    order = {"zararli": 0, "izle": 1, "baskin": 2}
    mine.sort(key=lambda i: (order[i["severity"]], -i["impressions"]))
    harm = [i for i in mine if i["severity"] == "zararli"]
    watch = [i for i in mine if i["severity"] == "izle"]
    status = "sorun" if harm else "dikkat" if watch else "iyi"
    actions = []
    for i in harm + watch:
        pair = next((p for p in i["pairs"]), None)
        if pair:
            actions.append((f"«{i['query']}»: {pair['action']}", None))
    facts = [("Yarışan arama", str(len(mine))), ("Zararlı", str(len(harm))), ("İzlenecek", str(len(watch))),
             ("Aramalar", ", ".join(i["query"] for i in mine) or None)]
    summary = (f"{len(mine)} aramada sitemizin başka bir sayfasıyla yarışıyor" if mine else "Başka sayfamızla yarıştığı arama yok")
    return section("yarisan", b.pid, status, summary, facts, actions)


def s_ic_baglanti(b: Book) -> dict[str, Any]:
    from .links import DEEP_CLICKS, WEAK_INLINKS, url_detail

    links = getattr(b.seo, "links", None)
    if links is None:
        return unknown("ic_baglanti", b.pid, "Site içi bağlantı hesabı bu kurulumda yüklü değil.")
    if not b.url:
        return unknown("ic_baglanti", b.pid, "Ürünün sitedeki adresi bilinmiyor.")
    g = links.result()["graph"]
    if not g.get("crawled"):
        return unknown("ic_baglanti", b.pid, "Teknik tarama henüz sayfaların bağlantılarını okumadı.")
    d = url_detail(g, b.url)
    followed = sum(1 for i in d["inlinks"] if not i["nofollow"])
    has_author = bool(str(b.p.get("ModelId") or "").strip() not in ("", "0"))
    author_linked = (any(o.get("kind") == "author" for o in d["outlinks"]) if d["outlinksKnown"] and has_author else None)
    status = links_status(followed, d["depth"], DEEP_CLICKS, WEAK_INLINKS, author_linked)
    actions: list[tuple[str, Optional[str]]] = []
    if followed == 0:
        actions.append(("Taranan hiçbir sayfa bu kitaba bağlantı vermiyor: yazar, kategori ve ilgili kitap sayfalarından bağlantı verin", None))
    elif followed < WEAK_INLINKS:
        actions.append((f"Yalnız {followed} sayfadan bağlantı alıyor: ilgili sayfalardan bağlantı ekleyin", None))
    if d["depth"] is not None and d["depth"] > DEEP_CLICKS:
        actions.append((f"Anasayfadan {d['depth']} tıklama uzakta: liste ve kategori sayfalarında öne alın", None))
    if author_linked is False:
        actions.append(("Kitap sayfası yazar sayfasına bağlantı vermiyor", None))
    facts = [("Bağlantı veren sayfa", str(followed)),
             ("Yalnız nofollow", str(len(d["inlinks"]) - followed) if len(d["inlinks"]) > followed else None),
             ("Anasayfadan uzaklık", f"{d['depth']} tıklama" if d["depth"] is not None else "Ulaşılamadı"),
             ("Yazar sayfasına bağlantı", yesno(author_linked)),
             ("Sayfa tarandı mı", "Evet" if d["crawled"] else "Hayır")]
    return section("ic_baglanti", b.pid, status, f"{followed} sayfadan bağlantı alıyor", facts, actions)


def s_yorumlar(b: Book) -> dict[str, Any]:
    from . import reviews

    agg = None
    if b.has(reviews.REVIEWS):
        with b.eng.connect() as c:
            r = c.execute(sa.select(reviews.REVIEWS).where(reviews.REVIEWS.c.tenant_id == b.tenant,
                                                           reviews.REVIEWS.c.product_id == b.pid)).mappings().first()
        if r:
            agg = {"comments": r["comments"], "approved": r["approved"], "rated": r["rated"], "rateSum": r["rate_sum"],
                   "stars": loads(r["stars_json"], {})}
    m = reviews.merge(b.p, agg)
    with b.eng.connect() as c:
        issues = c.execute(sa.select(SCHEMA.c.issues).where(SCHEMA.c.tenant_id == b.tenant, SCHEMA.c.product_id == b.pid)).scalar()
    schema_missing = bool(m["count"]) and issues is not None and ",no_rating," in issues
    status = reviews_status(m["count"], m["average"], schema_missing)
    actions: list[tuple[str, Optional[str]]] = []
    if not m["count"]:
        actions.append(("Hiç okur yorumu yok: satın alma sonrası yorum isteği bu kitaptan başlasın", None))
    if m["average"] is not None and m["average"] <= 3:
        actions.append(("Ortalama puan düşük: yorumlara yayınevi adına kısa cevap verin", None))
    if schema_missing:
        actions.append(("Yorumu var ama sayfada puan şeması yok: tema isteğine ekleyin", link_of("sema", b.pid)))
    facts = [("Yorum", str(m["count"])), ("Ortalama", f"{num(m['average'], 1)} / 5" if m["average"] else None),
             ("Şemada puan", ("Yok" if schema_missing else "Var") if m["count"] and issues is not None else None),
             ("Kaynak", m["source"])]
    summary = f"{m['count']} yorum" + (f", ortalama {num(m['average'], 1)}" if m["average"] else "") if m["count"] else "Hiç yorum yok"
    return section("yorumlar", b.pid, status, summary, facts, actions)


def s_video(b: Book) -> dict[str, Any]:
    from . import video

    book = b.crm()
    if not book:
        return unknown("video", b.pid, "Video bilgisi CRM kitap kartından gelir; kart eşleşmedi ya da CRM okunmadı.")
    if not book.get("video"):
        return section("video", b.pid, "dikkat", "CRM’de tanıtım videosu yok",
                       [("Video", "Yok")], [("CRM kartına tanıtım videosu eklenirse sayfada video şeması kullanılabilir", None)])
    vid = video.youtube_id(book.get("video"))
    with b.eng.connect() as c:
        r = c.execute(sa.select(SCHEMA.c.types_json, SCHEMA.c.checked_at).where(
            SCHEMA.c.tenant_id == b.tenant, SCHEMA.c.product_id == b.pid)).first()
    st = video.schema_state(loads(r[0], []) if r else [], r is not None)
    if not vid:
        return section("video", b.pid, "sorun", "CRM’deki video bağlantısı geçerli bir YouTube videosu değil",
                       [("Bağlantı", book.get("video"))], [("CRM kartındaki video bağlantısını düzeltin", None)])
    status = "iyi" if st == "var" else "dikkat"
    actions = [] if st == "var" else [("Sayfaya video şeması (VideoObject) ekletin; tema isteği Video ekranında", None)]
    return section("video", b.pid, status, video.STATE_LABEL[st],
                   [("Video", book.get("video")), ("Şema", video.STATE_LABEL[st])], actions,
                   extra={"thumbnail": video.thumbnail(vid)})


def s_rakipler(b: Book) -> dict[str, Any]:
    from . import competitors as comp

    if not b.has(comp.SERP):
        return unknown("rakipler", b.pid, NOT_RUN)
    with b.eng.connect() as c:
        r = c.execute(sa.select(comp.SERP).where(comp.SERP.c.tenant_id == b.tenant, comp.SERP.c.product_id == b.pid)
                      .order_by(comp.SERP.c.searched_at.desc()).limit(1)).mappings().first()
    if not r:
        return unknown("rakipler", b.pid, "Bu kitap için henüz Google araması yapılmadı (aylık kotayla çok satandan başlanır).")
    cm = getattr(b.seo, "competitors", None) or comp.Competitors(b.seo)
    our, rivals = cm.our(), cm.rivals()
    res = loads(r["positions_json"], {}).get("organic") or []
    p = comp.positions(res, [our, *rivals])
    verdict, best = comp.verdict(p.get(our), {d: p[d] for d in rivals})
    f = loads(r["features_json"], {})
    status = {"onde": "iyi", "geride": "dikkat", "yok": "sorun"}[verdict]
    actions: list[tuple[str, Optional[str]]] = []
    if verdict == "yok":
        actions.append((f"«{r['query']}» aramasında ilk 20’de yokuz: başlık ve açıklamada kitap adı + yazar geçsin",
                        link_of("urun", b.pid)))
    elif verdict == "geride" and best:
        actions.append((f"{best['domain']} bizden önde ({best['position']}. sıra): sayfa içeriğini ve bağlantıları güçlendirin", None))
    if f.get("aiOverview") and f.get("aiOverviewUs") is False:
        actions.append(("Google’ın yapay zekâ özetinde kaynak gösterilmiyoruz", link_of("yapay_zeka", b.pid)))
    facts = [("Arama", r["query"]), ("Bizim sıramız", f"{p.get(our)}." if p.get(our) else "İlk 20’de yok"),
             ("En iyi rakip", f"{best['domain']} · {best['position']}." if best else None),
             ("Yapay zekâ özeti", ("Var, biz kaynağız" if f.get("aiOverviewUs") else "Var, biz yokuz") if f.get("aiOverview") else "Yok"),
             ("Alışveriş sonuçları", ("Var, biz varız" if f.get("shoppingUs") else "Var, biz yokuz") if f.get("shopping") else "Yok"),
             ("Arandı", (iso(r["searched_at"]) or "")[:10])]
    summary = {"onde": "Hiçbir rakip bizden önde değil", "geride": "Bir rakip bizden önde",
               "yok": "Google’ın ilk 20 sonucunda yokuz"}[verdict]
    return section("rakipler", b.pid, status, summary, facts, actions)


def s_yapay_zeka(b: Book) -> dict[str, Any]:
    key = book_key(b.p.get("ProductName") or b.row["name"])
    with b.eng.connect() as c:
        rows = c.execute(sa.select(GEO_RESULTS.c.question_id, GEO_RESULTS.c.engine, GEO_RESULTS.c.books_json,
                                   GEO_RESULTS.c.cited, GEO_RESULTS.c.asked_at)
                         .where(GEO_RESULTS.c.tenant_id == b.tenant, GEO_RESULTS.c.ok.is_(True))).all()
        qtext = dict(c.execute(sa.select(QUESTIONS.c.id, QUESTIONS.c.text).where(QUESTIONS.c.tenant_id == b.tenant)).all())
    if not rows:
        return unknown("yapay_zeka", b.pid, "Yapay zekâ görünürlüğü henüz ölçülmedi.")
    hits = [r for r in rows if books_mention(loads(r[2], []), key)]
    qs_all = {r[0] for r in rows}
    qs_hit = sorted({r[0] for r in hits})
    engines = sorted({r[1] for r in hits})
    status = "iyi" if hits else "dikkat"
    actions = [] if hits else [
        ("Hiçbir yapay zekâ cevabında geçmiyor: kitabı arayan bir okur sorusunu izlemeye ekleyin", None),
        ("Kitabı konusuna uyan bir rehber sayfasına ekletin; yapay zekâ liste sayfalarını kaynak gösterir", link_of("rehber", b.pid))]
    facts = [("Ölçülen soru", str(len(qs_all))), ("Geçtiği soru", str(len(qs_hit))),
             ("Motor", ", ".join(engines) or None),
             ("Sorular", " · ".join(qtext.get(q, q) for q in qs_hit) or None)]
    summary = f"{len(qs_hit)} izlenen soruda yapay zekâ cevabında geçiyor" if hits else "İzlenen hiçbir soruda cevapta geçmiyor"
    return section("yapay_zeka", b.pid, status, summary, facts, actions)


def s_sezon(b: Book) -> dict[str, Any]:
    from . import crm as crm_mod, seasons

    if not b.has(seasons.BOOKS):
        return unknown("sezon", b.pid, NOT_RUN)
    ean = crm_mod.ean_key(b.p.get("Barcode"))
    if not ean:
        return unknown("sezon", b.pid, "Ürünün barkodu yok; özel gün bağı CRM kartından barkodla kurulur.")
    with b.eng.connect() as c:
        keys = {k for (k,) in c.execute(sa.select(seasons.BOOKS.c.day_key).where(
            seasons.BOOKS.c.tenant_id == b.tenant, seasons.BOOKS.c.ean == ean))}
        any_rows = c.execute(sa.select(sa.func.count()).select_from(seasons.BOOKS)
                             .where(seasons.BOOKS.c.tenant_id == b.tenant)).scalar()
        prop = c.execute(sa.select(PROPOSALS.c.status).where(PROPOSALS.c.tenant_id == b.tenant, PROPOSALS.c.product_id == b.pid)
                         .order_by(PROPOSALS.c.created_at.desc()).limit(1)).scalar()
    if not any_rows:
        return unknown("sezon", b.pid, "Sezon takvimi henüz CRM’den okunmadı.")
    if not keys:
        return section("sezon", b.pid, "iyi", "Hiçbir özel güne bağlı değil", [("Özel gün", "Yok")])
    views = [seasons._day_view(d, b.today) for d in seasons._load_days(b.seo) if d["key"] in keys]
    views.sort(key=lambda v: (v.get("start") or "9999", v["name"]))
    issues = loads(b.row["issues_json"], [])
    ready = seasons.readiness(b.row["score"], [i.get("severity") for i in issues], prop, (b.crm() or {}).get("rights"))
    soon = [v for v in views if v.get("phase") in ("hazirlik", "suruyor")]
    status = "iyi"
    actions: list[tuple[str, Optional[str]]] = []
    if ready["level"] != "hazir":
        status = "sorun" if soon else "dikkat" if views and any(v.get("start") for v in views) else "iyi"
        if soon:
            actions.append((f"{soon[0]['name']} yaklaşıyor ({soon[0]['start']}): sayfa hazır değil — {', '.join(ready['reasons']) or ready['label']}",
                            link_of("urun", b.pid)))
    facts = [("Özel günler", ", ".join(f"{v['name']}" + (f" ({v['start']})" if v.get("start") else "") for v in views)),
             ("Hazırlık", ready["label"]), ("Yaklaşan", ", ".join(v["name"] for v in soon) or None)]
    summary = f"{len(views)} özel güne bağlı" + (f"; {soon[0]['name']} için hazırlık zamanı" if soon else "")
    return section("sezon", b.pid, status, summary, facts, actions)


def s_satistan_kalkan(b: Book) -> dict[str, Any]:
    from .sunset import ACTIONS, REASON_LABEL, SUNSET

    if not b.has(SUNSET):
        return unknown("satistan_kalkan", b.pid, NOT_RUN)
    with b.eng.connect() as c:
        r = c.execute(sa.select(SUNSET).where(SUNSET.c.tenant_id == b.tenant, SUNSET.c.product_id == b.pid)).mappings().first()
    if not r:
        return section("satistan_kalkan", b.pid, "iyi", "Satıştan kalkma durumu yok")
    act = ACTIONS.get(r["chosen_action"] or r["action"], r["action"])
    if r["status"] == "bekliyor":
        status, actions = "sorun", [(f"Satıştan kalkan sayfa için karar verin (öneri: {act})", None)]
    elif r["status"] == "onaylandi":
        status, actions = "dikkat", [(f"Onaylanan karar ({act}) T-soft panelinden uygulanmalı", None)]
    else:
        status, actions = "iyi", []
    facts = [("Neden", REASON_LABEL.get(r["reason"], r["reason"])), ("Öneri", act), ("Gerekçe", r["why"]),
             ("Karar", {"bekliyor": "Bekliyor", "onaylandi": "Onaylandı", "reddedildi": "Reddedildi"}.get(r["status"], r["status"])),
             ("Son 28 gün gösterim", num(r["impressions"]))]
    return section("satistan_kalkan", b.pid, status, f"{REASON_LABEL.get(r['reason'], r['reason'])} · {act}", facts, actions)


def s_yazar(b: Book) -> dict[str, Any]:
    from . import authors, entity

    names = entity.split_authors(b.p.get("Model"))
    if not names:
        return unknown("yazar", b.pid, "Ürün kaydında yazar yok.")
    rows, _ = authors.Authors(b.seo).rows()
    by_key = {r["key"]: r for r in rows}
    a = next((by_key[entity.fold(n)] for n in names if entity.fold(n) in by_key), None)
    if not a:
        return unknown("yazar", b.pid, "Yazar güven sinyalleri bu yazar için hesaplanamadı.")
    sc = a["score"]
    status = "bilinmiyor" if sc is None else "iyi" if sc >= 80 else "dikkat" if sc >= 50 else "sorun"
    link = link_of("yazar", b.pid) + "?q=" + quote(a["name"])
    facts = [("Yazar", a["name"]), ("Güven puanı", f"{sc}/100" if sc is not None else None),
             ("Yazar sayfası", a["page"]["url"] if a.get("page") else "Yok"),
             ("Wikidata", a.get("wikidata") or "Yok"), ("Kitap sayısı", str(a["books"]))]
    summary = f"{a['name']}: güven puanı {sc}/100" if sc is not None else a["name"]
    if status == "bilinmiyor":
        return section("yazar", b.pid, status, summary, facts, reason="Yazarın güven maddeleri henüz bilinmiyor.")
    return section("yazar", b.pid, status, summary, facts, [(t, link) for t in a["actions"]])


def s_rehber(b: Book) -> dict[str, Any]:
    from .guides import GUIDES

    if not b.has(GUIDES):
        return unknown("rehber", b.pid, NOT_RUN)
    with b.eng.connect() as c:
        rows = c.execute(sa.select(GUIDES.c.title, GUIDES.c.status, GUIDES.c.books_json).where(
            GUIDES.c.tenant_id == b.tenant, GUIDES.c.status != "reddedildi")).all()
    mine = [(t, st) for t, st, bj in rows if any(str(x.get("id")) == b.pid for x in loads(bj, []) if isinstance(x, dict))]
    approved = [t for t, st in mine if st == "onaylandi"]
    status = "iyi" if approved else "dikkat"
    actions = [] if approved else [
        ("Taslakta olduğu rehberi onaylayın" if mine else "Kitabın konusuna uyan bir rehber taslağı hazırlatın", None)]
    facts = [("Rehberler", " · ".join(f"{t} ({'onaylı' if st == 'onaylandi' else 'taslak'})" for t, st in mine) or "Yok")]
    summary = f"{len(mine)} rehberde geçiyor ({len(approved)} onaylı)" if mine else "Hiçbir rehberde yok"
    return section("rehber", b.pid, status, summary, facts, actions)


def s_hiz(b: Book) -> dict[str, Any]:
    from .speed import SPEED

    if not b.has(SPEED):
        return unknown("hiz", b.pid, NOT_RUN)
    if not b.url:
        return unknown("hiz", b.pid, "Ürünün sitedeki adresi bilinmiyor.")
    with b.eng.connect() as c:
        rows = c.execute(sa.select(SPEED).where(SPEED.c.tenant_id == b.tenant, SPEED.c.url == b.url)
                         .order_by(SPEED.c.measured_at.asc())).mappings().all()
    if not rows:
        return unknown("hiz", b.pid, "Bu sayfa hız örnekleminde yok (her gece en çok satanlar ölçülür).")
    latest = {(r["source"], r["strategy"]): loads(r["metrics_json"], {}) | {"at": r["measured_at"]} for r in rows}
    mob = latest.get(("psi", "mobile")) or {}
    desk = latest.get(("psi", "desktop")) or {}
    field = mob.get("field") or {}
    cats = [v.get("category") for v in field.values()] or list((mob.get("labCategory") or {}).values())
    status = speed_status(mob.get("score"), cats)
    lcp = (field.get("lcp") or {}).get("p75") or (mob.get("lab") or {}).get("lcp")
    cls = (field.get("cls") or {}).get("p75") if field.get("cls") else (mob.get("lab") or {}).get("cls")
    inp = (field.get("inp") or {}).get("p75")
    actions = [] if status == "iyi" else [("Mobil hız zayıf: kapak görseli boyutu ve sayfa kodları tema tarafında iyileştirilmeli", None)]
    facts = [("Mobil puan", num(mob.get("score"))), ("Masaüstü puan", num(desk.get("score"))),
             ("LCP", f"{num(lcp / 1000, 1)} sn" if lcp else None), ("CLS", num(cls, 2) if cls is not None else None),
             ("INP", f"{num(inp)} ms" if inp else None),
             ("Gerçek kullanıcı verisi", "Var" if field and not mob.get("fieldOrigin") else "Yok (laboratuvar ölçümü)"),
             ("Ölçüldü", (iso(mob.get("at")) or "")[:10] if mob else None)]
    return section("hiz", b.pid, status, f"Mobil hız puanı {num(mob.get('score'))}" if mob.get("score") is not None else "Ölçüldü",
                   facts, actions)


def s_geri_baglanti(b: Book) -> dict[str, Any]:
    from . import backlinks as bl

    if not b.has(bl.SNAPS):
        return unknown("geri_baglanti", b.pid, NOT_RUN)
    if not b.url:
        return unknown("geri_baglanti", b.pid, "Ürünün sitedeki adresi bilinmiyor.")
    with b.eng.connect() as c:
        snap = c.execute(sa.select(bl.SNAPS).where(bl.SNAPS.c.tenant_id == b.tenant)
                         .order_by(bl.SNAPS.c.taken_at.desc()).limit(1)).mappings().first()
        if not snap:
            return unknown("geri_baglanti", b.pid, "Gelen bağlantılar henüz okunmadı.")
        me = bl.norm_url(b.url)
        counts = [r for r in c.execute(sa.select(bl.COUNTS).where(bl.COUNTS.c.snap_id == snap["id"])).mappings()
                  if bl.norm_url(r["target"]) == me]
        sources = [s for t, s in c.execute(sa.select(bl.LINKS_T.c.target, bl.LINKS_T.c.source)
                                           .where(bl.LINKS_T.c.snap_id == snap["id"])).all() if bl.norm_url(t) == me]
    n = sum(r["count"] for r in counts)
    domains = sorted({bl.domain_of(s) for s in sources})
    status = "iyi" if n else "dikkat"
    actions = [] if n else [("Dışarıdan hiç bağlantı görünmüyor: tanıtım yazıları ve kitapçı sayfalarından bağlantı hedefleyin", None)]
    facts = [("Gelen bağlantı", num(n)), ("Bağlantı veren site", ", ".join(domains) or None),
             ("Okuma", (iso(snap["taken_at"]) or "")[:10])]
    return section("geri_baglanti", b.pid, status, f"{num(n)} dış bağlantı" if n else "Görünen dış bağlantı yok", facts, actions)


BUILDERS: dict[str, Callable[[Book], dict[str, Any]]] = {
    "urun": s_urun, "crm": s_crm, "google": s_google, "arama": s_arama, "teknik": s_teknik, "sema": s_sema,
    "ic_baglanti": s_ic_baglanti, "rakipler": s_rakipler, "yapay_zeka": s_yapay_zeka,
    "satistan_kalkan": s_satistan_kalkan, "yarisan": s_yarisan, "yorumlar": s_yorumlar, "yazar": s_yazar,
    "hiz": s_hiz, "sezon": s_sezon, "geri_baglanti": s_geri_baglanti, "video": s_video, "rehber": s_rehber,
}


def guarded(sid: str, pid: str, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """Bölüm hesabı hata verirse (tablo yok, modül yüklü değil, veri bozuk) karne düşmez: bölüm "bilinmiyor"."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        log.warning("seo scorecard %s/%s: %s", pid, sid, e)
        return unknown(sid, pid, "Bu bölümün verisi okunamadı; ilgili ekran açılarak denetlenebilir.")


def build(seo: Any, pid: str) -> dict[str, Any]:
    b = Book(seo, pid)  # ürün yoksa 404 buradan
    sections = [guarded(sid, pid, lambda f=f: f(b)) for sid, f in BUILDERS.items()]
    order = list(SECTIONS)
    sections.sort(key=lambda s: order.index(s["id"]))
    crm_book = None
    try:
        crm_book = b.crm()
    except Exception:  # noqa: BLE001
        pass
    from . import _num

    v = b.view
    return {"product": {"id": pid, "name": v["name"], "code": v["code"], "brand": v["brand"], "active": v["active"],
                        "author": rules.text_of(b.p.get("Model")) or None, "image": v["image"], "url": v["url"],
                        "barcode": v["barcode"], "sales": v["sales"], "views": v["views"], "score": v["score"],
                        "comments": _num(b.p.get("CommentCount"))},
            "grade": grade(sections), "top": top_actions(sections), "sections": sections, "crm": crm_book,
            "weights": [{"id": k, "title": t, "weight": w} for k, (t, w, _) in SECTIONS.items()],
            "generatedAt": datetime.now(timezone.utc).isoformat()}


def search(seo: Any, q: str, start: int, limit: int) -> dict[str, Any]:
    from . import EAN, SALES, VIEWS, _product_view

    tenant, site = seo.tenant(), (seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")
    cond = [PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True)]
    if q.strip():
        like = f"%{q.strip()}%"
        cond.append(sa.or_(PRODUCTS.c.name.ilike(like), PRODUCTS.c.code.ilike(like), PRODUCTS.c.brand.ilike(like),
                           sa.cast(PRODUCTS.c.data_json, sa.JSON)["Model"].as_string().ilike(like), EAN == q.strip()))
    j = PRODUCTS.outerjoin(CRM_BOOKS, sa.and_(CRM_BOOKS.c.tenant_id == PRODUCTS.c.tenant_id, CRM_BOOKS.c.ean == EAN))
    with seo.engine().connect() as c:
        total = c.execute(sa.select(sa.func.count()).select_from(PRODUCTS).where(*cond)).scalar() or 0
        rows = c.execute(sa.select(PRODUCTS, CRM_BOOKS.c.rights, CRM_BOOKS.c.status_flag).select_from(j).where(*cond)
                         .order_by(SALES.desc(), VIEWS.desc(), PRODUCTS.c.product_id)
                         .offset(max(0, start)).limit(max(1, limit))).mappings().all()
    items = []
    for r in rows:
        v = _product_view(dict(r), site)
        items.append({"id": v["id"], "name": v["name"], "code": v["code"], "brand": v["brand"],
                      "author": rules.text_of(loads(r["data_json"], {}).get("Model")) or None, "image": v["image"],
                      "sales": v["sales"], "score": v["score"], "rights": r["rights"], "statusFlag": r["status_flag"]})
    return {"total": total, "start": max(0, start), "items": items}


def register(app, ctx) -> None:
    @app.get("/api/v1/seo-geo/scorecard")
    def seo_scorecard_search(request: Request, q: str = "", start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        return search(ctx.seo, q, start, limit)

    @app.get("/api/v1/seo-geo/scorecard/{pid}")
    def seo_scorecard(pid: str, request: Request) -> dict[str, Any]:
        ctx.gate(request)
        return build(ctx.seo, pid)
