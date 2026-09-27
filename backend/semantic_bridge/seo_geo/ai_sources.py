"""Yapay zekânın kaynakları: yapay zekâ motorlarının izlenen sorulara verdiği cevaplarda gösterdiği kaynak adresleri
alan adına toplanır; hangi sitelerin bizim konularımızda sık kaynak gösterildiği ve bu cevaplarda Timaş'ın anılıp
anılmadığı çıkar. Timaş'ın anılmadığı sık kaynaklar tanıtım/iletişim için "hedef listesi"dir.

Kaynak: `semantic_seo_geo_results` (bütün motorlar, bütün sorular, başarılı ölçümler). Okuma anında hesaplanır; son
ölçüm zamanı + ayarlar değişmedikçe önbellekten verilir. Hiçbir siteye istek atılmaz, hiçbir yere yazılmaz.

Alan adı: adresin kayıtlı alan adı ("m.dr.com.tr" → "dr.com.tr"; ".com.tr" gibi iki düzeyli ülke uzantıları tanınır;
blogspot/wordpress gibi barındırma platformlarında alt alan adı ayrı site sayılır). Gemini kaynakları
`vertexaisearch.cloud.google.com` yönlendirme adresiyle verir; gerçek alan adı başlıktadır, oradan okunur.

Tür (sırayla ilk tutan kural; her alan adının yanında gerekçesi döner):
bizim site → Yönetim'deki rakip listesi (`SEO_COMPETITORS`) → bilinen kitapçı → pazar yeri → ansiklopedi → sosyal/video
→ bilinen haber sitesi / adında "haber, gazete, news" → yayınevi (adında "yayin", "kitap" + yayınevi listesi) →
blog/liste (platform, adında "blog", adreslerinin yarısı /blog/ ya da başlığı liste) → diğer.
"""
from __future__ import annotations

import logging
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Optional
from urllib.parse import parse_qs, urlsplit

import sqlalchemy as sa
from fastapi import HTTPException, Request

from .competitors import domain_of, matches, parse_domains
from .geo import ENGINES
from .store import GEO_RESULTS, QUESTIONS, iso, loads

log = logging.getLogger("semantic.seo_geo")

TZ = timezone(timedelta(hours=3))   # Türkiye saati (2016’dan beri yaz saati yok; sunucuda tz verisi şartı olmasın)
UNKNOWN = "bilinmeyen"

#: Hedef listesi eşikleri (ekranda da gösterilir).
TARGET_MIN_QUESTIONS = 2          # en az bu kadar farklı soruda kaynak gösterilmiş
TARGET_MAX_MENTION_SHARE = 0.25   # onu kaynak gösteren cevapların en fazla bu kadarında Timaş anılıyor
TARGET_TYPES = ("haber", "blog", "ansiklopedi", "sosyal", "yayinevi", "diger")
#: Liste satırında gösterilen örnek adres sayısı; bütün adresler ayrıntıda ve `urlCount` ile sayı hep görünür.
EXAMPLES_IN_LIST = 3
#: Blog/liste sayılmak için adreslerin en az bu oranı blog yolunda ya da liste başlıklı olmalı.
BLOG_URL_SHARE = 0.5

TYPES: dict[str, str] = {
    "bizim": "Bizim site",
    "rakip": "Rakip kitapçı",
    "pazaryeri": "Pazar yeri",
    "haber": "Haber / medya",
    "blog": "Blog / liste",
    "ansiklopedi": "Ansiklopedi / viki",
    "sosyal": "Sosyal / video",
    "yayinevi": "Yayınevi",
    "diger": "Diğer",
}
ACTIONS: dict[str, str] = {
    "haber": "Basın bülteni, yazar röportajı ya da yeni çıkan kitap haberi için iletişime geçin.",
    "blog": "Liste/öneri yazısına kitap önerisi ya da inceleme nüshası için yazarına ulaşın.",
    "ansiklopedi": "Maddede kaynaklı ve tarafsız bilgi eksikse sitenin kurallarına uyarak kaynak önerin; tanıtım yazılmaz.",
    "sosyal": "Kanal ya da hesapla iş birliği, kitap tanıtımı ya da okur topluluğunda görünürlük.",
    "yayinevi": "Ortak yayın, yazar söyleşisi ya da kaynakça iş birliği değerlendirilebilir.",
    "diger": "Sitenin konusu ve iletişim yolu incelenip uygun tanıtım biçimi seçilir.",
}

# Kayıtlı alan adı: ülke uzantısının altındaki genel ikinci düzey adlar (".com.tr", ".org.tr", ".co.uk" …).
SECOND_LEVEL = frozenset({"com", "org", "net", "gov", "edu", "ac", "co", "gen", "web", "bel", "k12", "av", "biz", "info",
                          "tv", "name", "tel", "pol", "dr", "bbs", "tsk", "mil", "nc", "ltd", "plc", "sch", "me", "or",
                          "ne", "go", "gob", "nic"})
# Bu platformlarda her alt alan adı ayrı bir sitedir.
PLATFORMS = frozenset({"blogspot.com", "wordpress.com", "medium.com", "substack.com", "tumblr.com", "wixsite.com",
                       "github.io", "weebly.com", "blogger.com"})
REDIRECT_HOSTS = ("vertexaisearch.cloud.google.com",)

BOOKSTORES = frozenset({"dr.com.tr", "idefix.com", "kitapyurdu.com", "bkmkitap.com", "kitapsepeti.com", "pandora.com.tr",
                        "babil.com", "kidega.com", "halkkitabevi.com", "eganba.com", "kitapkalbi.com", "ilknokta.com",
                        "kitapdunyasi.com", "tozlu.com", "remzi.com.tr", "insanvekitap.com"})
MARKETPLACES = frozenset({"trendyol.com", "hepsiburada.com", "n11.com", "amazon.com.tr", "amazon.com", "amazon.de",
                          "ciceksepeti.com", "pazarama.com", "akakce.com", "cimri.com", "epey.com", "ebay.com", "etsy.com",
                          "nadirkitap.com", "letgo.com", "sahibinden.com", "migros.com.tr", "a101.com.tr"})
ENCYCLOPEDIAS = frozenset({"wikipedia.org", "wikiwand.com", "wikidata.org", "wikiquote.org", "wikisource.org",
                           "britannica.com", "islamansiklopedisi.org.tr", "tdk.gov.tr", "sozluk.gov.tr", "vikipedi.org"})
SOCIAL = frozenset({"youtube.com", "youtu.be", "instagram.com", "facebook.com", "x.com", "twitter.com", "tiktok.com",
                    "reddit.com", "eksisozluk.com", "quora.com", "pinterest.com", "linkedin.com", "goodreads.com",
                    "1000kitap.com", "spotify.com", "threads.net", "dailymotion.com", "vimeo.com", "uludagsozluk.com",
                    "incisozluk.com.tr", "kitapdiyari.com"})
NEWS = frozenset({"hurriyet.com.tr", "milliyet.com.tr", "sabah.com.tr", "sozcu.com.tr", "haberturk.com", "ntv.com.tr",
                  "cnnturk.com", "trthaber.com", "trt.net.tr", "aa.com.tr", "bbc.com", "bbc.co.uk", "cumhuriyet.com.tr",
                  "yenisafak.com", "star.com.tr", "karar.com", "dunya.com", "ensonhaber.com", "t24.com.tr",
                  "indyturk.com", "gazeteduvar.com.tr", "dw.com", "euronews.com", "aksam.com.tr", "posta.com.tr",
                  "takvim.com.tr", "turkiyegazetesi.com.tr", "yeniakit.com.tr", "milligazete.com.tr", "haber7.com",
                  "internethaber.com", "mynet.com", "ahaber.com.tr", "tgrthaber.com", "fikriyat.com", "kitapeki.com",
                  "birgun.net", "evrensel.net", "diken.com.tr", "medyascope.tv", "independent.co.uk", "nytimes.com",
                  "theguardian.com", "reuters.com"})
PUBLISHERS = frozenset({"iskultur.com.tr", "ykykultur.com.tr", "can.com.tr", "dogankitap.com.tr", "everestyayinlari.com",
                        "iletisim.com.tr", "kronikkitap.com", "yapikrediyayinlari.com", "alfakitap.com", "epsilonyayinevi.com",
                        "pegasusyayinlari.com", "ithakiyayinlari.com", "sulemaniye.com", "ketebe.com", "hayykitap.com",
                        "destekyayinlari.com", "kapiyayinlari.com", "profilkitap.com", "yediveren.com.tr",
                        "nesilyayinlari.com", "erdemyayinlari.com", "beyan.com.tr", "insanyayinlari.com.tr",
                        "dergah.com.tr", "otuken.com.tr", "kaynakyayinlari.com", "penguin.co.uk",
                        "penguinrandomhouse.com", "harpercollins.com"})
NEWS_WORDS = re.compile(r"haber|gazete|news|times|post\b|medya|dergi", re.I)
PUBLISHER_WORDS = re.compile(r"yayin|yayinevi|yayinlari|kitabevi|publishing|publisher|press\b", re.I)
BLOG_WORDS = re.compile(r"blog", re.I)
LIST_TITLE = re.compile(r"en iyi|öneri|oneri|listes|okunması gereken|okunmasi gereken|kitap önerileri|\b\d{1,3} kitap|"
                        r"best\b|top \d+|must[- ]read", re.I)
BLOG_PATH = re.compile(r"/(blog|yazi|yazilar|makale|makaleler|liste|list|oneri|oneriler)/", re.I)
_DOMAIN_IN = re.compile(r"(?<![\w.-])((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24})(?![\w-])", re.I)
_IP = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


# ------------------------------------------------------------------------------------------------ saf işlevler

def registrable(host: Any) -> str:
    """Kayıtlı alan adı: "m.dr.com.tr" → "dr.com.tr", "tr.wikipedia.org" → "wikipedia.org",
    "ali.blogspot.com" → "ali.blogspot.com" (platform alt alanı ayrı site)."""
    h = domain_of(host)
    if not h or _IP.match(h):
        return h
    labels = h.split(".")
    if len(labels) <= 2:
        return h
    n = 3 if len(labels[-1]) == 2 and labels[-2] in SECOND_LEVEL else 2
    base = ".".join(labels[-n:])
    if base in PLATFORMS and len(labels) > n:
        return ".".join(labels[-(n + 1):])
    return base


def _is_redirect(host: str) -> bool:
    return any(host == r or host.endswith("." + r) for r in REDIRECT_HOSTS)


def source_domain(cite: dict[str, Any]) -> tuple[str, bool]:
    """(alan adı, yönlendirme mi). Yönlendirme adresinde (Gemini) alan adı başlıktan okunur; okunamazsa `UNKNOWN`.
    Google'ın `/url?q=` adresinde gerçek adres parametrededir."""
    url = str(cite.get("url") or "").strip()
    title = str(cite.get("title") or "").strip()
    host = domain_of(url)
    if host and _is_redirect(host):
        m = _DOMAIN_IN.search(title.lower())
        return (registrable(m.group(1)) if m else UNKNOWN), True
    if host in ("google.com", "google.com.tr") and "/url" in url:
        q = parse_qs(urlsplit(url).query)
        real = (q.get("q") or q.get("url") or [""])[0]
        if real:
            return registrable(real) or UNKNOWN, True
    if not host:
        m = _DOMAIN_IN.search(title.lower())
        return (registrable(m.group(1)) if m else UNKNOWN), False
    return registrable(host), False


def _in(domain: str, names: Iterable[str]) -> Optional[str]:
    return next((n for n in names if matches(domain, n)), None)


def classify_domain(domain: str, our: str, rivals: list[str],
                    samples: Iterable[tuple[str, str]] = ()) -> tuple[str, str]:
    """(tür, gerekçe). `samples`: bu alan adından kaynak gösterilen (adres, başlık) çiftleri."""
    if domain == UNKNOWN:
        return "diger", "Yönlendirme adresinden alan adı okunamadı."
    if our and matches(domain, our):
        return "bizim", f"Sitemizin alan adı ({our})."
    hit = _in(domain, rivals)
    if hit:
        return "rakip", f"Yönetim ayarındaki rakip listesinde ({hit})."
    hit = _in(domain, BOOKSTORES)
    if hit:
        return "rakip", "Bilinen kitapçılar listesinde; rakip listesine eklenmemiş."
    if _in(domain, MARKETPLACES):
        return "pazaryeri", "Bilinen pazar yerleri listesinde."
    if _in(domain, ENCYCLOPEDIAS):
        return "ansiklopedi", "Bilinen ansiklopedi/sözlük listesinde."
    if _in(domain, SOCIAL):
        return "sosyal", "Bilinen sosyal ağ / video / okur topluluğu listesinde."
    if _in(domain, NEWS):
        return "haber", "Bilinen haber siteleri listesinde."
    if _in(domain, PUBLISHERS):
        return "yayinevi", "Bilinen yayınevleri listesinde."
    base = registrable(domain)
    if base in PLATFORMS or any(domain.endswith("." + p) for p in PLATFORMS):
        return "blog", "Blog barındırma platformunda."
    name = domain.split(".")[0] if base == domain else domain
    if NEWS_WORDS.search(name):
        return "haber", "Alan adında haber/gazete/dergi sözcüğü var."
    if PUBLISHER_WORDS.search(name):
        return "yayinevi", "Alan adında yayın/yayınevi sözcüğü var."
    if BLOG_WORDS.search(name):
        return "blog", "Alan adında \"blog\" geçiyor."
    samples = list(samples)
    if samples:
        listy = sum(1 for u, t in samples if BLOG_PATH.search(urlsplit(u or "").path + "/") or LIST_TITLE.search(t or ""))
        if listy / len(samples) >= BLOG_URL_SHARE:
            return "blog", f"Kaynak gösterilen adreslerinin {listy}/{len(samples)} kadarı blog yazısı ya da liste."
    return "diger", "Hiçbir kurala uymadı."


def local_day(t: datetime) -> str:
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return t.astimezone(TZ).date().isoformat()


def aggregate(results: list[dict[str, Any]], questions: dict[str, dict[str, Any]], our: str, rivals: list[str],
              engine: Optional[str] = None) -> dict[str, Any]:
    """`results`: başarılı ölçümler — {id, question_id, engine, asked_at, mentioned, cited, sources:[{url,title}]}.
    Dönüş: {"domains": {alan: kayıt}, "summary": {...}, "trend": [...]} (sıralama/süzme okuma anında)."""
    chosen = [r for r in results if not engine or r["engine"] == engine]
    domains: dict[str, dict[str, Any]] = {}
    day_stats: dict[str, dict[str, Any]] = {}
    with_sources = cited_ours = mentioned = citations = 0
    engines_seen: set[str] = set()
    first = last = None
    for r in chosen:
        engines_seen.add(r["engine"])
        t = r["asked_at"]
        first = t if first is None or t < first else first
        last = t if last is None or t > last else last
        day = local_day(t)
        ds = day_stats.setdefault(day, {"date": day, "answers": 0, "withSources": 0, "ours": 0, "mentioned": 0,
                                        "domains": set()})
        ds["answers"] += 1
        if r.get("mentioned"):
            mentioned += 1
            ds["mentioned"] += 1
        per_answer: dict[str, list[dict[str, Any]]] = {}
        for c in r.get("sources") or []:
            if not isinstance(c, dict) or not (c.get("url") or c.get("title")):
                continue
            dom, via = source_domain(c)
            per_answer.setdefault(dom, []).append({"url": c.get("url") or "", "title": c.get("title") or "", "redirect": via})
        if per_answer:
            with_sources += 1
            ds["withSources"] += 1
        ours_here = False
        for dom, cites in per_answer.items():
            citations += len(cites)
            d = domains.setdefault(dom, {"domain": dom, "citations": 0, "answers": 0, "mentionedAnswers": 0,
                                         "questions": {}, "engines": {}, "urls": {}, "days": {},
                                         "firstSeen": t, "lastSeen": t})
            d["citations"] += len(cites)
            d["answers"] += 1
            if r.get("mentioned"):
                d["mentionedAnswers"] += 1
            q = d["questions"].setdefault(r["question_id"], {"id": r["question_id"], "answers": 0, "mentioned": 0,
                                                              "engines": set()})
            q["answers"] += 1
            q["mentioned"] += 1 if r.get("mentioned") else 0
            q["engines"].add(r["engine"])
            d["engines"][r["engine"]] = d["engines"].get(r["engine"], 0) + 1
            d["days"][day] = d["days"].get(day, 0) + 1
            d["firstSeen"], d["lastSeen"] = min(d["firstSeen"], t), max(d["lastSeen"], t)
            for c in cites:
                key = c["title"].lower() if c["redirect"] else c["url"]
                u = d["urls"].setdefault(key, {**c, "count": 0})
                u["count"] += 1
            ds["domains"].add(dom)
            if our and dom != UNKNOWN and matches(dom, our):
                ours_here = True
        if ours_here:
            cited_ours += 1
            ds["ours"] += 1
    total = len(chosen)
    for d in domains.values():
        samples = [(u["url"] if not u["redirect"] else "", u["title"]) for u in d["urls"].values()]
        d["type"], d["why"] = classify_domain(d["domain"], our, rivals, samples)
        d["share"] = d["answers"] / total if total else 0.0
        d["mentionShare"] = d["mentionedAnswers"] / d["answers"] if d["answers"] else 0.0
        d["questionCount"] = len(d["questions"])
        d["target"] = is_target(d)
    by_type: dict[str, dict[str, int]] = {k: {"domains": 0, "answers": 0, "citations": 0} for k in TYPES}
    for d in domains.values():
        b = by_type[d["type"]]
        b["domains"] += 1
        b["answers"] += d["answers"]
        b["citations"] += d["citations"]
    trend = [{**v, "domains": len(v["domains"])} for _, v in sorted(day_stats.items())]
    summary = {"answers": total, "answersWithSources": with_sources, "citations": citations, "domains": len(domains),
               "oursCited": cited_ours, "oursShare": cited_ours / total if total else None,
               "mentioned": mentioned, "mentionShare": mentioned / total if total else None,
               "questions": len({r["question_id"] for r in chosen}), "engines": sorted(engines_seen),
               "firstAt": iso(first), "lastAt": iso(last), "byType": by_type,
               "targets": sum(1 for d in domains.values() if d["target"]),
               "unknown": domains.get(UNKNOWN, {}).get("answers", 0)}
    return {"domains": domains, "summary": summary, "trend": trend, "questions": questions}


def is_target(d: dict[str, Any]) -> bool:
    """Hedef: bizim konularımızda en az `TARGET_MIN_QUESTIONS` soruda kaynak, Timaş'ın anılmadığı (oran eşik altı) ve
    tanıtımla ulaşılabilecek türde (bizim site, rakip, pazar yeri değil)."""
    return (d["type"] in TARGET_TYPES and d["domain"] != UNKNOWN and d["questionCount"] >= TARGET_MIN_QUESTIONS
            and d["mentionShare"] <= TARGET_MAX_MENTION_SHARE)


def rank(domains: Iterable[dict[str, Any]], type_: str = "") -> list[dict[str, Any]]:
    rows = list(domains)
    if type_ == "hedef":
        rows = [d for d in rows if d["target"]]
    elif type_:
        rows = [d for d in rows if d["type"] == type_]
    return sorted(rows, key=lambda d: (-d["answers"], -d["questionCount"], -d["citations"], d["domain"]))


def _urls(d: dict[str, Any]) -> list[dict[str, Any]]:
    return sorted(d["urls"].values(), key=lambda u: (-u["count"], u["title"] or u["url"]))


def view(d: dict[str, Any], questions: dict[str, dict[str, Any]], full: bool = False,
         trend: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    urls = _urls(d)
    out = {"domain": d["domain"], "type": d["type"], "typeLabel": TYPES[d["type"]], "why": d["why"],
           "citations": d["citations"], "answers": d["answers"], "share": d["share"],
           "questions": d["questionCount"], "mentionedAnswers": d["mentionedAnswers"], "mentionShare": d["mentionShare"],
           "engines": dict(sorted(d["engines"].items())), "firstSeen": iso(d["firstSeen"]), "lastSeen": iso(d["lastSeen"]),
           "target": d["target"], "action": ACTIONS.get(d["type"]) if d["target"] else None,
           "urlCount": len(urls), "examples": urls if full else urls[:EXAMPLES_IN_LIST]}
    if full:
        out["questionList"] = sorted(
            ({"id": q["id"], "text": (questions.get(q["id"]) or {}).get("text") or "(silinmiş soru)",
              "category": (questions.get(q["id"]) or {}).get("category"), "answers": q["answers"],
              "mentioned": q["mentioned"], "engines": sorted(q["engines"])} for q in d["questions"].values()),
            key=lambda q: (-q["answers"], q["text"]))
        totals = {t["date"]: t["answers"] for t in trend or []}
        # Ölçüm günü başına: o gün bu alan adını kaynak gösteren cevap / o günkü bütün cevaplar.
        out["trend"] = [{"date": k, "answers": d["days"].get(k, 0), "total": n,
                         "share": d["days"].get(k, 0) / n if n else None} for k, n in sorted(totals.items())] \
            or [{"date": k, "answers": v, "total": None, "share": None} for k, v in sorted(d["days"].items())]
    return out


def by_question(results: list[dict[str, Any]], questions: dict[str, dict[str, Any]], our: str, rivals: list[str],
                engine: Optional[str] = None) -> list[dict[str, Any]]:
    """Her sorunun her motordaki SON başarılı ölçümünde kullanılan kaynaklar (alan adı + tür)."""
    latest: dict[tuple[str, str], dict[str, Any]] = {}
    for r in results:
        if engine and r["engine"] != engine:
            continue
        k = (r["question_id"], r["engine"])
        if k not in latest or r["asked_at"] > latest[k]["asked_at"]:
            latest[k] = r
    out: dict[str, dict[str, Any]] = {}
    for (qid, eng), r in latest.items():
        q = out.setdefault(qid, {"id": qid, "text": (questions.get(qid) or {}).get("text") or "(silinmiş soru)",
                                 "category": (questions.get(qid) or {}).get("category"), "engines": {}})
        srcs = []
        for c in r.get("sources") or []:
            if not isinstance(c, dict) or not (c.get("url") or c.get("title")):
                continue
            dom, via = source_domain(c)
            typ, _ = classify_domain(dom, our, rivals, [("" if via else c.get("url") or "", c.get("title") or "")])
            srcs.append({"domain": dom, "type": typ, "url": c.get("url") or "", "title": c.get("title") or "", "redirect": via})
        q["engines"][eng] = {"askedAt": iso(r["asked_at"]), "mentioned": r.get("mentioned"), "cited": r.get("cited"),
                             "sources": srcs}
    return sorted(out.values(), key=lambda q: q["text"])


# ------------------------------------------------------------------------------------------------ veri

_cache: dict[Any, Any] = {}
_cache_lock = threading.Lock()


def _settings(seo) -> tuple[str, list[str]]:
    our = domain_of(seo.conf("SEO_SITE_URL") or "https://timas.com.tr") or "timas.com.tr"
    our = registrable(our)
    return our, [d for d in parse_domains(seo.conf("SEO_COMPETITORS")) if not matches(d, our)]


def load(seo) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], Any]:
    tenant = seo.tenant()
    with seo.engine().connect() as c:
        stamp = c.execute(sa.select(sa.func.max(GEO_RESULTS.c.asked_at), sa.func.count()).where(
            GEO_RESULTS.c.tenant_id == tenant, GEO_RESULTS.c.ok.is_(True))).one()
        key = (tenant, stamp[0], stamp[1])
        with _cache_lock:
            if _cache.get("raw_key") == key:
                return _cache["raw"][0], _cache["raw"][1], key
        rows = c.execute(sa.select(GEO_RESULTS.c.id, GEO_RESULTS.c.question_id, GEO_RESULTS.c.engine,
                                   GEO_RESULTS.c.asked_at, GEO_RESULTS.c.mentioned, GEO_RESULTS.c.cited,
                                   GEO_RESULTS.c.sources_json).where(
            GEO_RESULTS.c.tenant_id == tenant, GEO_RESULTS.c.ok.is_(True)).order_by(GEO_RESULTS.c.asked_at)).mappings().all()
        qs = c.execute(sa.select(QUESTIONS.c.id, QUESTIONS.c.text, QUESTIONS.c.category).where(
            QUESTIONS.c.tenant_id == tenant)).mappings().all()
    results = [{"id": r["id"], "question_id": r["question_id"], "engine": r["engine"], "asked_at": r["asked_at"],
                "mentioned": r["mentioned"], "cited": r["cited"], "sources": loads(r["sources_json"], [])} for r in rows]
    questions = {q["id"]: {"text": q["text"], "category": q["category"]} for q in qs}
    with _cache_lock:
        _cache.clear()
        _cache.update(raw_key=key, raw=(results, questions))
    return results, questions, key


def computed(seo, engine: Optional[str]) -> dict[str, Any]:
    results, questions, key = load(seo)
    our, rivals = _settings(seo)
    ck = ("agg", key, our, tuple(rivals), engine or "")
    with _cache_lock:
        if ck in _cache:
            return _cache[ck]
    data = aggregate(results, questions, our, rivals, engine)
    data["our"], data["rivals"] = our, rivals
    with _cache_lock:
        _cache[ck] = data
    return data


# ------------------------------------------------------------------------------------------------ uçlar

def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


def _engine_param(engine: str) -> Optional[str]:
    if not engine:
        return None
    if engine not in ENGINES:
        raise _err(404, "Bilinmeyen motor.")
    return engine


def _meta() -> dict[str, Any]:
    return {"types": [{"id": k, "label": v} for k, v in TYPES.items()],
            "engineLabels": {k: v["label"] for k, v in ENGINES.items()},
            "thresholds": {"targetMinQuestions": TARGET_MIN_QUESTIONS, "targetMaxMentionShare": TARGET_MAX_MENTION_SHARE,
                           "targetTypes": list(TARGET_TYPES), "examplesInList": EXAMPLES_IN_LIST,
                           "blogUrlShare": BLOG_URL_SHARE}}


def register(app, ctx) -> None:
    seo = ctx.seo

    @app.get("/api/v1/seo-geo/ai-sources")
    def seo_ai_sources(request: Request, type: str = "", engine: str = "", start: int = 0,
                       limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        if type and type != "hedef" and type not in TYPES:
            raise _err(404, "Bilinmeyen kaynak türü.")
        data = computed(seo, _engine_param(engine))
        ranked = rank(data["domains"].values(), type)
        start = max(0, start)
        page = ranked[start:start + max(1, limit)]
        return {"type": type, "engine": engine, "start": start, "total": len(ranked),
                "items": [view(d, data["questions"]) for d in page], "summary": data["summary"],
                "trend": data["trend"], "our": data["our"], "rivals": data["rivals"], **_meta()}

    @app.get("/api/v1/seo-geo/ai-source-questions")
    def seo_ai_source_questions(request: Request, engine: str = "", start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        results, questions, _ = load(seo)
        our, rivals = _settings(seo)
        items = by_question(results, questions, our, rivals, _engine_param(engine))
        start = max(0, start)
        return {"engine": engine, "start": start, "total": len(items), "items": items[start:start + max(1, limit)],
                "our": our, **_meta()}

    @app.get("/api/v1/seo-geo/ai-sources/{domain}")
    def seo_ai_source(request: Request, domain: str, engine: str = "") -> dict[str, Any]:
        ctx.gate(request)
        data = computed(seo, _engine_param(engine))
        d = data["domains"].get(domain.strip().lower())
        if not d:
            raise _err(404, "Bu alan adı ölçülen cevaplarda kaynak gösterilmemiş.")
        return {"engine": engine, "item": view(d, data["questions"], full=True, trend=data["trend"]), "summary": data["summary"], **_meta()}
