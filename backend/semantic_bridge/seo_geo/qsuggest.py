"""İzlenen soru önerileri: yapay zekâ görünürlüğü (GEO) ölçümüne eklenecek okur soruları, elle yazılmış bir soru
listesi olmadan, üç kaynaktan kodla üretilir. Model kullanılmaz; aynı veri aynı soruyu verir.

Kaynaklar:
- **Aramalar** — Search Console'daki son 28 günlük sorgulardan (``seo.gsc('queries')``) soru biçiminde ya da liste
  niyetli olanlar ("hangi", "nasıl", "önerileri", "en iyi", "… kitapları", "okunmalı", "… için kitap", yaş/sınıf).
  Sorgu kalıba göre doğal bir soruya çevrilir; kaynak sorgu ve gösterim sayısı yanında durur. Marka sorguları
  (timaş) atlanır: yapay zekâ ölçümünde anlamı yok.
- **Tema/yaş** — CRM kitap kartının tema (`new_new_kitap_new_temaBase` → `new_temaBase`) ve yaş
  (`new_new_kitap_new_yasBase` → `new_yasBase`) bağları gece okunup `semantic_seo_qsuggest_crm`'e yazılır; tür, web
  kategorisi ve hedef kitle `semantic_seo_crm_books.data_json`'dan gelir. Kalıp ("{yaş} yaş çocuklar için {tema}
  temalı kitap önerir misin?") yalnız satıştaki en az ``MIN_BOOKS`` kitabımız o birleşime uyuyorsa önerilir;
  cevabında kitabımız geçemeyecek soru ölçmeye değmez.
- **Sezon** — sezon takviminin özel günleri (`semantic_seo_seasons_days`, varsa) → "{gün} için hangi kitap hediye
  edilir?". Güne bağlı satıştaki kitabı olmayan gün önerilmez.

Tekilleştirme: metin Türkçe harf farkı, noktalama ve dolgu kelimeleri ("bana", "lütfen") atılarak karşılaştırılır;
izlenen sorularda (`semantic_seo_questions`) zaten olan öneri gösterilmez, öneriler arasında aynı olanın en yüksek
puanlısı kalır. Puan: gösterim, uyan kitap sayısı ve özel güne yakınlık (logaritmik; sıralama içindir, liste kesilmez).

Durum: öneri → eklendi (izlenen sorulara yazıldı) | reddedildi. Karar yenilemede korunur. CRM'e yazılmaz.
"""
from __future__ import annotations

import hashlib
import logging
import math
import os
import re
import threading
import uuid
from datetime import date
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Request

from . import crm
from .store import CRM_BOOKS, PRODUCTS, QUESTIONS, _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo")

SUGGEST = sa.Table(
    "semantic_seo_qsuggest", _md,  # soru önerisi: kaynağı, dayanağı, puanı, kararı
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("id", sa.String(32), primary_key=True),          # normalleştirilmiş metnin özeti (yenilemede aynı kalır)
    sa.Column("text", sa.String(500), nullable=False),
    sa.Column("norm", sa.String(500), nullable=False),
    sa.Column("source", sa.String(12), nullable=False),        # arama | tema | sezon
    sa.Column("basis_json", sa.Text, nullable=False),
    sa.Column("score", sa.Float, nullable=False, default=0.0),
    sa.Column("impressions", sa.Integer),
    sa.Column("books", sa.Integer),
    sa.Column("status", sa.String(16), nullable=False),        # öneri | eklendi | reddedildi
    sa.Column("question_id", sa.String(32)),
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False),
)
CRM_LINKS = sa.Table(
    "semantic_seo_qsuggest_crm", _md,  # CRM kitap ↔ tema / yaş bağı (gece okunur; yalnız okuma)
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("ean", sa.String(20), primary_key=True),
    sa.Column("kind", sa.String(8), primary_key=True),         # tema | yas
    sa.Column("value", sa.String(200), primary_key=True),
    sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
)

#: Tema/yaş/tür kalıbı ancak satıştaki bu kadar kitabımız o birleşime uyuyorsa önerilir.
MIN_BOOKS = 5
#: Özel güne yakınlık puanı bu kadar gün içinde azalarak sıfıra iner.
SEASON_HORIZON_DAYS = 180
SOURCES = {"arama": "Aramalar", "tema": "Tema/yaş", "sezon": "Sezon"}
#: Kabul edilen soru izlenen sorulara bu kategoriyle yazılır.
CATEGORY = {"arama": "Arama sorgusu", "tema": "Tema/yaş", "sezon": "Sezon"}
STATUSES = ("öneri", "eklendi", "reddedildi")
LIMIT = 500_000

_ready: set[int] = set()
_ready_lock = threading.Lock()
_run_lock = threading.Lock()
state: dict[str, Any] = {"running": False, "startedAt": None, "finishedAt": None, "counts": None, "error": None,
                         "crmError": None}


def ensure_tables(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) not in _ready:
            for t in (SUGGEST, CRM_LINKS):
                t.create(engine, checkfirst=True)
            _ready.add(id(engine))


# ================================================================================================ metin

def fold(text: Any) -> str:
    """Türkçe harf farkını siler: "Öğretmenler GÜNÜ" → "ogretmenler gunu"."""
    t = str(text or "").replace("İ", "i").replace("I", "ı").lower().replace("̇", "")
    return t.translate(str.maketrans("ışğüöçâîû’", "isguocaiu'"))


def words(text: Any) -> list[str]:
    return re.findall(r"[a-z0-9]+", fold(text).replace("'", " "))


#: Karşılaştırmada anlam taşımayan dolgu kelimeleri.
FILLER = {"bana", "lutfen", "acaba", "bir", "birkac", "sen", "siz", "bi"}


def norm(text: Any) -> str:
    """Tekilleştirme anahtarı: harf farkı, noktalama ve dolgu kelimesi atılır."""
    return " ".join(w for w in words(text) if w not in FILLER)


def qid(n: str) -> str:
    return hashlib.sha1(n.encode("utf-8")).hexdigest()[:32]


def upper_first(s: str) -> str:
    s = s.strip()
    if not s:
        return s
    head = {"i": "İ", "ı": "I"}.get(s[0], s[0].upper())
    return head + s[1:]


def lower_tr(s: str) -> str:
    return str(s or "").replace("İ", "i").replace("I", "ı").lower().strip()


def finish(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip().rstrip(".!? ")
    return upper_first(s) + "?"


# ================================================================================================ sorgu → soru

_AGE = re.compile(r"(?<![\w])(\d{1,2})\s*(?:(?:-|–|ile)\s*(\d{1,2})\s*)?(yaş|yas)(?:ında\w*|inda\w*|lar\w*|lı\w*|li\w*|a|ı|i)?(?!\w)",
                  re.I)
_GRADE = re.compile(r"(?<![\w])(\d{1,2})\s*\.?\s*(sınıf|sinif)\w*", re.I)
_LIST_SUFFIX = re.compile(r"\s*(önerileri|önerisi|onerileri|onerisi|tavsiyeleri|tavsiyesi|tavsiye|öneri|oneri)\s*$", re.I)
_BEST = re.compile(r"^\s*en\s+(iyi|güzel|guzel|çok\s+okunan|cok\s+okunan|popüler|populer)\s+", re.I)
_BOOKS_END = re.compile(r"\b(kitapları|kitaplari|kitaplar|romanları|romanlari|romanlar|hikayeleri|hikâyeleri|"
                        r"masalları|masallari)\s*$", re.I)
_MUST_READ = re.compile(r"\b(okunmalı|okunmali|okunması\s+gereken|okunmasi\s+gereken|okunacak)\b", re.I)
_FOR_BOOK = re.compile(r"^(.+?)\s+(için|icin)\s+(kitap|kitaplar|kitapları|kitaplari|roman|romanlar|hikaye|hikâye)\s*$", re.I)
#: Soru kelimesi (tek başına "ne" kitap adlarında çok geçer; yalnız fiille birlikte sayılır).
_QWORD = re.compile(r"(^|\s)(hangi|hangisi|hangileri|nasıl|nasil|nedir|neler|kimdir|nerede|niçin|nicin|neden)(\s|$)"
                    r"|(^|\s)ne\s+(okumal|okuyal|okunur|hediye|alınır|alinir|almal)"
                    r"|\s(mi|mı|mu|mü|misin|mısın|musun|müsün)(\s|$)", re.I)
BRAND = re.compile(r"tima[şs]", re.I)
#: Sorguda konu sayılmayan kelimeler (uyan kitap aranırken atılır).
GENERIC = {"kitap", "kitaplar", "kitaplari", "kitabi", "kitaplarini", "en", "iyi", "guzel", "oneri", "onerisi", "onerileri",
           "tavsiye", "tavsiyeleri", "hangi", "hangisi", "hangileri", "nasil", "ne", "neler", "nedir", "icin", "okunmali",
           "okunmasi", "gereken", "okunacak", "mutlaka", "cok", "okunan", "populer", "yas", "yasinda", "yasindaki",
           "sinif", "sinifi", "cocuk", "cocuklar", "cocuklara", "cocuklari", "ogrenci", "ogrencileri", "icin", "mi",
           "mu", "misin", "musun", "oku", "okumali", "okumaliyim", "hediye", "ve", "ile", "de", "da", "bir", "yeni"}


def age_phrase(q: str) -> Optional[tuple[str, str]]:
    """Sorgudaki yaş ya da sınıf: (kalıp metni, sorgudan atılacak parça). "9-12 yaş" → "9-12 yaş çocuklar"."""
    m = _AGE.search(q)
    if m:
        a, b = m.group(1), m.group(2)
        return age_group(f"{a}-{b}" if b else a), m.group(0)
    m = _GRADE.search(q)
    if m:
        return f"{m.group(1)}. sınıf öğrencileri", m.group(0)
    return None


def _topic(rest: str, default: str) -> str:
    rest = re.sub(r"\s+", " ", rest).strip(" -,.")
    return rest or default


def detect(query: str) -> Optional[str]:
    """Sorgunun niyeti: soru | liste | yas | okunmali | icin | None (soru önerisine uygun değil)."""
    q = re.sub(r"\s+", " ", str(query or "")).strip()
    if len(words(q)) < 2 or BRAND.search(q):
        return None
    if _QWORD.search(" " + q + " ") or q.endswith("?"):
        return "soru"
    if _MUST_READ.search(q):
        return "okunmali"
    if age_phrase(q):
        return "yas"
    if _LIST_SUFFIX.search(q) or _BEST.search(q):
        return "liste"
    if _FOR_BOOK.match(q):
        return "icin"
    if _BOOKS_END.search(q):
        return "liste"
    return None


def rewrite(query: str) -> Optional[str]:
    """Sorguyu kalıpla doğal bir okur sorusuna çevirir; uygun değilse None. Model kullanılmaz."""
    q = re.sub(r"\s+", " ", str(query or "")).strip()
    kind = detect(q)
    if kind is None:
        return None
    low = lower_tr(q)
    if kind == "soru":
        return finish(low)
    if kind == "okunmali":
        s = re.sub(r"\s+", " ", _MUST_READ.sub("okunması gereken", low)).strip()
        if s.endswith("okunması gereken"):
            s += " kitaplar"
        return finish(f"{s} hangileri")
    if kind == "yas":
        phrase, part = age_phrase(low)  # type: ignore[misc]
        rest = _LIST_SUFFIX.sub("", low.replace(part.lower(), " "))
        rest = _BEST.sub("", rest)
        rest = re.sub(r"(^|\s)(çocuk|cocuk|öğrenci|ogrenci)\w*", " ", rest)
        rest = re.sub(r"(^|\s)(için|icin)(?=\s|$)", " ", rest)
        toks = _topic(rest, "kitap").split()
        if toks[-1].startswith("kitap"):  # "okuma kitapları" → "okuma kitabı", "kitapları" → "kitap"
            toks[-1] = "kitabı" if len(toks) > 1 else "kitap"
        return finish(f"{phrase} için {' '.join(toks)} önerir misin")
    if kind == "icin":
        m = _FOR_BOOK.match(low)
        return finish(f"{m.group(1)} için hangi kitabı önerirsin")  # type: ignore[union-attr]
    # liste
    if _LIST_SUFFIX.search(low):
        rest = _BEST.sub("", _LIST_SUFFIX.sub("", low) + " ")
        return finish(f"{_topic(rest, 'kitap')} önerir misin")
    rest = _BEST.sub("", low + " ")
    return finish(f"en iyi {_topic(rest, 'kitaplar')} hangileri")


def topic_words(query: str) -> list[str]:
    """Uyan kitap aramak için sorgunun konu kelimeleri (genel ve soru kelimeleri, sayılar atılır)."""
    return [w for w in words(query) if w not in GENERIC and not w.isdigit() and len(w) >= 3]


def stem(w: str) -> str:
    """Türkçe ek için kaba kök: 5 harften uzunsa ilk 5 harf."""
    return w[:5] if len(w) > 5 else w


def book_index(books: Iterable[dict[str, Any]]) -> dict[str, set[str]]:
    """kök → kitap (EAN). Kitabın adı, türü, web kategorisi, teması ve anahtar kelimeleri."""
    idx: dict[str, set[str]] = {}
    for b in books:
        text = " ".join(str(b.get(k) or "") for k in ("name", "genres", "webCategories", "keywords"))
        text += " " + " ".join(b.get("themes") or [])
        for w in set(words(text)):
            if len(w) >= 3:
                idx.setdefault(stem(w), set()).add(b["ean"])
    return idx


def matching_books(query: str, idx: dict[str, set[str]]) -> Optional[int]:
    """Sorgunun bütün konu kelimelerini taşıyan kitap sayısı; konu kelimesi yoksa None (genel soru)."""
    tw = topic_words(query)
    if not tw:
        return None
    sets = [idx.get(stem(w), set()) for w in tw]
    return len(set.intersection(*sets)) if sets else 0


def from_queries(rows: Iterable[dict[str, Any]], idx: dict[str, set[str]]) -> list[dict[str, Any]]:
    out = []
    for r in rows:
        q = (r.get("keys") or [""])[0]
        text = rewrite(q)
        if not text:
            continue
        impr = int(r.get("impressions") or 0)
        books = matching_books(q, idx)
        out.append({"text": text, "source": "arama", "impressions": impr, "books": books,
                    "basis": {"query": q, "impressions": impr, "clicks": int(r.get("clicks") or 0),
                              "position": round(float(r.get("position") or 0), 1), "kind": detect(q), "books": books}})
    return out


# ================================================================================================ tema / yaş

def split_values(v: Any) -> list[str]:
    """CRM çok değerli metin alanı ("Roman, Hikâye" / "Çocuk > Masal") → son kademe adları."""
    out = []
    for part in re.split(r"[,;|\n]", str(v or "")):
        part = re.split(r"\s*[>/]\s*", part.strip())[-1].strip()
        if part and part not in out:
            out.append(part)
    return out


def age_label(v: str) -> Optional[str]:
    """CRM yaş adı → kalıptaki yaş: "9 Yaş" → "9", "9-12 Yaş" → "9-12". Sayı yoksa None."""
    m = re.search(r"(\d{1,2})\s*(?:[-–+]\s*(\d{1,2}))?", str(v or ""))
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}" if m.group(2) else m.group(1)


#: Bu yaştan başlayan okur kalıpta "gençler" diye anılır.
TEEN_FROM = 13


def age_group(age: str) -> str:
    """"9" → "9 yaş çocuklar", "14-16" → "14-16 yaş gençler"."""
    first = int(re.match(r"\d+", age).group(0)) if re.match(r"\d+", age) else 0
    return f"{age} yaş {'gençler' if first >= TEEN_FROM else 'çocuklar'}"


def genre_phrase(g: str) -> str:
    """"Roman" → "roman", "Çocuk Kitapları" → "çocuk"; kalıpta "… kitapları" iki kez yazılmasın."""
    g = lower_tr(g)
    g = re.sub(r"\s*(kitapları|kitaplari|kitaplar|kitabı|kitabi|kitap)\s*$", "", g).strip()
    return g


def book_facets(b: dict[str, Any]) -> dict[str, list[str]]:
    """Kitabın kalıp boyutları: yaş, tema, tür (tür + web kategorisi), hedef kitle."""
    ages = [a for a in (age_label(x) for x in b.get("ages") or []) if a]
    if not ages and b.get("ageFrom") not in (None, ""):
        try:
            lo, hi = int(b["ageFrom"]), int(b.get("ageTo") or b["ageFrom"])
            ages = [str(lo) if lo == hi else f"{lo}-{hi}"]
        except (TypeError, ValueError):
            ages = []
    genres = []
    for g in split_values(b.get("genres")) + split_values(b.get("webCategories")):
        p = genre_phrase(g)
        if p and len(p) >= 3 and p not in genres:
            genres.append(p)
    audience = [lower_tr(b["audience"])] if b.get("audience") and not age_label(b["audience"]) else []
    return {"ages": list(dict.fromkeys(ages)), "themes": list(dict.fromkeys(b.get("themes") or [])),
            "genres": genres, "audience": audience}


def facet_templates(books: list[dict[str, Any]], min_books: int = MIN_BOOKS) -> list[dict[str, Any]]:
    """Tema/yaş/tür kalıpları; yalnız en az `min_books` satıştaki kitabımızın uyduğu birleşimler."""
    groups: dict[tuple[str, ...], set[str]] = {}

    def add(key: tuple[str, ...], ean: str) -> None:
        groups.setdefault(key, set()).add(ean)

    for b in books:
        f = book_facets(b)
        for t in f["themes"]:
            add(("tema", t), b["ean"])
            for a in f["ages"]:
                add(("yas_tema", a, t), b["ean"])
        for g in f["genres"]:
            add(("tur", g), b["ean"])
            for a in f["ages"]:
                add(("yas_tur", a, g), b["ean"])
            for au in f["audience"]:
                add(("kitle_tur", au, g), b["ean"])
    out = []
    for key, eans in groups.items():
        if len(eans) < min_books:
            continue
        kind = key[0]
        if kind == "tema":
            text, basis = f"«{key[1]}» temalı en iyi kitaplar hangileri", {"theme": key[1]}
        elif kind == "yas_tema":
            text, basis = f"{age_group(key[1])} için «{key[2]}» temalı kitap önerir misin", {"age": key[1], "theme": key[2]}
        elif kind == "tur":
            text, basis = f"en iyi {key[1]} kitapları hangileri", {"genre": key[1]}
        elif kind == "yas_tur":
            text, basis = f"{age_group(key[1])} için {key[2]} kitabı önerir misin", {"age": key[1], "genre": key[2]}
        else:
            text, basis = f"{key[1]} okurlar için {key[2]} kitabı önerir misin", {"audience": key[1], "genre": key[2]}
        out.append({"text": finish(text), "source": "tema", "impressions": None, "books": len(eans),
                    "basis": {**basis, "kind": kind, "books": len(eans)}})
    return out


# ================================================================================================ sezon

def season_templates(days: list[dict[str, Any]], today: date,
                     next_date: Callable[[dict[str, Any], date], Optional[date]]) -> list[dict[str, Any]]:
    """Özel gün → hediye sorusu. `days`: {name, books} (books = güne bağlı satıştaki kitap sayısı)."""
    out = []
    for d in days:
        if not d.get("books"):
            continue
        nd = next_date(d, today)
        until = (nd - today).days if nd else None
        out.append({"text": finish(f"{d['name']} için hangi kitap hediye edilir"), "source": "sezon",
                    "impressions": None, "books": d["books"], "daysUntil": until,
                    "basis": {"day": d["name"], "date": nd.isoformat() if nd else None, "daysUntil": until,
                              "books": d["books"]}})
    return out


# ================================================================================================ puan, tekilleştirme

def score(c: dict[str, Any]) -> float:
    s = 0.0
    if c.get("impressions"):
        s += 10 * math.log10(1 + c["impressions"])
    if c.get("books"):
        s += 10 * math.log10(1 + c["books"])
    until = c.get("daysUntil")
    if until is not None and 0 <= until <= SEASON_HORIZON_DAYS:
        s += 30 * (1 - until / SEASON_HORIZON_DAYS)
    return round(s, 2)


def dedupe(cands: Iterable[dict[str, Any]], existing: set[str]) -> list[dict[str, Any]]:
    """İzlenen sorularda olanı atar; aynı soru birden çok kaynaktan gelirse en yüksek puanlısı kalır."""
    best: dict[str, dict[str, Any]] = {}
    for c in cands:
        n = norm(c["text"])
        if not n or n in existing:
            continue
        c = {**c, "norm": n, "score": score(c)}
        prev = best.get(n)
        if prev is None or c["score"] > prev["score"]:
            best[n] = c
    return sorted(best.values(), key=lambda c: (-c["score"], c["norm"]))


# ================================================================================================ okuma

def links_sql(p: str, link: str, col: str, vocab: str, key: str) -> str:
    return (f"SELECT k.new_ean13 AS ean, v.new_name AS name FROM {p}{link} x"
            f" JOIN {p}new_kitapBase k ON k.new_kitapId = x.new_kitapid"
            f" JOIN {p}{vocab} v ON v.{key} = x.{col}"
            " WHERE k.statecode = 0 AND v.statecode = 0 AND k.new_ean13 IS NOT NULL")


CRM_SOURCES = {"tema": ("new_new_kitap_new_temaBase", "new_temaid", "new_temaBase", "new_temaId"),
               "yas": ("new_new_kitap_new_yasBase", "new_yasid", "new_yasBase", "new_yasId")}


def read_crm_links(schema: str, execute: Callable[[str, int], Any]) -> list[tuple[str, str, str]]:
    """(ean, tür, ad) üçlüleri. `execute(sql, limit)` → (kolonlar, satırlar, kesik)."""
    p = crm._prefix(schema)
    out: set[tuple[str, str, str]] = set()
    for kind, (link, col, vocab, key) in CRM_SOURCES.items():
        _, rows, truncated = execute(links_sql(p, link, col, vocab, key), LIMIT)
        if truncated:
            raise RuntimeError("CRM sonucu kesildi; eksik veriyle öneri üretilmez.")
        for r in rows:
            ean, name = crm.ean_key(r.get("ean")), crm.clean(r.get("name"))
            if len(ean) >= 8 and name:
                out.add((ean[:20], kind, name[:200]))
    return sorted(out)


def _crm_configured() -> bool:
    from semantic_bridge import admin as admin_mod

    return bool(admin_mod.conf("CRM_SCHEMA")) and bool(crm.CONNECTION_FILE) and os.path.exists(crm.CONNECTION_FILE)


def _sync_crm(seo) -> Optional[str]:
    """Tema/yaş bağlarını CRM'den okuyup yazar. CRM yoksa ya da okunamazsa eski kayıt kalır; hata metni döner."""
    from semantic_bridge import admin as admin_mod

    if not _crm_configured():
        return None
    eng, tenant = seo.engine(), seo.tenant()
    try:
        con = crm.connector()
        try:
            links = read_crm_links(admin_mod.conf("CRM_SCHEMA"), con.execute)
        finally:
            try:
                con.close()
            except Exception:  # noqa: BLE001
                pass
    except Exception as e:  # noqa: BLE001
        log.warning("soru önerisi CRM okuması başarısız: %s", e)
        return str(e)[:500]
    stamp = now()
    with eng.begin() as c:
        c.execute(CRM_LINKS.delete().where(CRM_LINKS.c.tenant_id == tenant))
        vals = [dict(tenant_id=tenant, ean=e, kind=k, value=v, synced_at=stamp) for e, k, v in links]
        for i in range(0, len(vals), 1000):
            c.execute(CRM_LINKS.insert(), vals[i:i + 1000])
    return None


def _books(seo) -> list[dict[str, Any]]:
    """Satıştaki (T-soft'ta aktif, CRM'de durum işareti olmayan) kitaplar, tema/yaş bağlarıyla."""
    from . import EAN

    eng, tenant = seo.engine(), seo.tenant()
    j = PRODUCTS.join(CRM_BOOKS, sa.and_(CRM_BOOKS.c.tenant_id == PRODUCTS.c.tenant_id, CRM_BOOKS.c.ean == EAN))
    with eng.connect() as c:
        rows = c.execute(sa.select(CRM_BOOKS.c.ean, PRODUCTS.c.name, CRM_BOOKS.c.data_json).select_from(j).where(
            PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True), CRM_BOOKS.c.status_flag.is_(None))).all()
        links = c.execute(sa.select(CRM_LINKS.c.ean, CRM_LINKS.c.kind, CRM_LINKS.c.value)
                          .where(CRM_LINKS.c.tenant_id == tenant)).all()
    extra: dict[str, dict[str, list[str]]] = {}
    for ean, kind, value in links:
        extra.setdefault(ean, {"tema": [], "yas": []})[kind].append(value)
    out: dict[str, dict[str, Any]] = {}
    for ean, name, raw in rows:
        b = loads(raw, {})
        e = extra.get(ean, {})
        out[ean] = {"ean": ean, "name": name or b.get("name"), "genres": b.get("genres"),
                    "webCategories": b.get("webCategories"), "keywords": b.get("keywords"), "audience": b.get("audience"),
                    "ageFrom": b.get("ageFrom"), "ageTo": b.get("ageTo"), "themes": e.get("tema", []),
                    "ages": e.get("yas", [])}
    return list(out.values())


def _season_days(seo, on_sale: set[str]) -> tuple[list[dict[str, Any]], Callable[[dict[str, Any], date], Optional[date]]]:
    """Sezon takviminin günleri (tablo yoksa boş) ve satıştaki bağlı kitap sayısı."""
    try:
        from . import seasons
    except ImportError:
        return [], lambda d, t: None
    eng, tenant = seo.engine(), seo.tenant()
    insp = sa.inspect(eng)
    if not insp.has_table(seasons.DAYS.name):
        return [], lambda d, t: None
    with eng.connect() as c:
        days = c.execute(sa.select(seasons.DAYS).where(seasons.DAYS.c.tenant_id == tenant)).mappings().all()
        links = c.execute(sa.select(seasons.BOOKS.c.day_key, seasons.BOOKS.c.ean)
                          .where(seasons.BOOKS.c.tenant_id == tenant)).all() if insp.has_table(seasons.BOOKS.name) else []
    per: dict[str, set[str]] = {}
    for key, ean in links:
        if ean in on_sale:
            per.setdefault(key, set()).add(ean)
    out = [{"key": d["day_key"], "name": d["name"], "weekFrom": d["week_from"], "weekTo": d["week_to"],
            "fixedDate": d["fixed_date"], "books": len(per.get(d["day_key"], ()))} for d in days]

    def next_date(d: dict[str, Any], today: date) -> Optional[date]:
        occ = seasons.next_occurrence(seasons.resolve(d), today)
        return occ[0] if occ else None

    return out, next_date


def min_books(seo) -> int:
    try:
        return max(1, int(seo.conf("SEO_QSUGGEST_MIN_BOOKS") or MIN_BOOKS))
    except (TypeError, ValueError):
        return MIN_BOOKS


def refresh(seo, today: Optional[date] = None) -> dict[str, Any]:
    today = today or date.today()
    eng, tenant = seo.engine(), seo.tenant()
    ensure_tables(eng)
    state["crmError"] = _sync_crm(seo)
    books = _books(seo)
    idx = book_index(books)
    cands: list[dict[str, Any]] = []
    gsc = seo.gsc("queries")
    if gsc:
        cands += from_queries(gsc.get("rows") or [], idx)
    cands += facet_templates(books, min_books(seo))
    days, next_date = _season_days(seo, {b["ean"] for b in books})
    cands += season_templates(days, today, next_date)
    with eng.connect() as c:
        existing = {norm(t) for (t,) in c.execute(sa.select(QUESTIONS.c.text).where(QUESTIONS.c.tenant_id == tenant)).all()}
        old = {r["id"]: dict(r) for r in c.execute(sa.select(SUGGEST).where(SUGGEST.c.tenant_id == tenant)).mappings().all()}
    fresh = dedupe(cands, existing)
    stamp = now()
    keep = {k for k, r in old.items() if r["status"] != "öneri"}  # kararlı kayıt yenilemede korunur
    with eng.begin() as c:
        c.execute(SUGGEST.delete().where(SUGGEST.c.tenant_id == tenant, SUGGEST.c.status == "öneri"))
        vals = []
        for cand in fresh:
            i = qid(cand["norm"])
            row = dict(text=cand["text"][:500], norm=cand["norm"][:500], source=cand["source"],
                       basis_json=dumps(cand["basis"]), score=cand["score"], impressions=cand.get("impressions"),
                       books=cand.get("books"), refreshed_at=stamp)
            if i in keep:
                c.execute(SUGGEST.update().where(SUGGEST.c.tenant_id == tenant, SUGGEST.c.id == i).values(**row))
                continue
            vals.append(dict(tenant_id=tenant, id=i, status="öneri", created_at=old.get(i, {}).get("created_at") or stamp, **row))
        for k in range(0, len(vals), 1000):
            c.execute(SUGGEST.insert(), vals[k:k + 1000])
    counts: dict[str, int] = {}
    for cand in fresh:
        counts[cand["source"]] = counts.get(cand["source"], 0) + 1
    return {"candidates": len(fresh), "bySource": counts, "books": len(books), "days": len(days)}


def start_refresh(seo, user: str) -> bool:
    if not _run_lock.acquire(blocking=False):
        return False
    state.update(running=True, startedAt=iso(now()), finishedAt=None, error=None)

    def job() -> None:
        try:
            state["counts"] = refresh(seo)
            log.info("seo qsuggest refresh (%s): %s", user, state["counts"])
        except Exception as e:  # noqa: BLE001
            state["error"] = str(e)[:1000]
            log.exception("seo qsuggest refresh failed")
        finally:
            state.update(running=False, finishedAt=iso(now()))
            _run_lock.release()

    threading.Thread(target=job, name="seo-qsuggest", daemon=True).start()
    return True


# ================================================================================================ uçlar

def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


def _view(r: Any) -> dict[str, Any]:
    return {"id": r["id"], "text": r["text"], "source": r["source"], "sourceLabel": SOURCES.get(r["source"], r["source"]),
            "basis": loads(r["basis_json"], {}), "score": r["score"], "impressions": r["impressions"], "books": r["books"],
            "status": r["status"], "questionId": r["question_id"], "decidedBy": r["decided_by"],
            "decidedAt": iso(r["decided_at"]), "createdAt": iso(r["created_at"]), "refreshedAt": iso(r["refreshed_at"])}


def register(app, ctx) -> None:
    seo = ctx.seo

    def nightly() -> None:
        start_refresh(seo, "zamanlayıcı")

    seo.nightly.append(("qsuggest", nightly))

    def _row(sid: str) -> dict[str, Any]:
        with seo.engine().connect() as c:
            r = c.execute(sa.select(SUGGEST).where(SUGGEST.c.tenant_id == seo.tenant(), SUGGEST.c.id == sid)).mappings().first()
        if not r:
            raise _err(404, "Öneri bulunamadı.")
        return dict(r)

    @app.get("/api/v1/seo-geo/qsuggest")
    def seo_qsuggest(request: Request, source: str = "", status: str = "öneri", start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        if source and source not in SOURCES:
            raise _err(422, "Bilinmeyen kaynak.")
        if status and status not in STATUSES:
            raise _err(422, "Bilinmeyen durum.")
        eng, tenant = seo.engine(), seo.tenant()
        ensure_tables(eng)
        cond = [SUGGEST.c.tenant_id == tenant]
        if source:
            cond.append(SUGGEST.c.source == source)
        if status:
            cond.append(SUGGEST.c.status == status)
        start = max(0, start)
        with eng.connect() as c:
            total = c.execute(sa.select(sa.func.count()).select_from(SUGGEST).where(*cond)).scalar() or 0
            rows = c.execute(sa.select(SUGGEST).where(*cond)
                             .order_by(SUGGEST.c.score.desc(), SUGGEST.c.norm)
                             .offset(start).limit(max(1, min(limit, 200)))).mappings().all()
            grouped = c.execute(sa.select(SUGGEST.c.source, SUGGEST.c.status, sa.func.count())
                                .where(SUGGEST.c.tenant_id == tenant).group_by(SUGGEST.c.source, SUGGEST.c.status)).all()
            last = c.execute(sa.select(sa.func.max(SUGGEST.c.refreshed_at)).where(SUGGEST.c.tenant_id == tenant)).scalar()
        counts = {s: {st: 0 for st in STATUSES} for s in SOURCES}
        for src, st, n in grouped:
            if src in counts and st in counts[src]:
                counts[src][st] = n
        return {"total": total, "start": start, "items": [_view(r) for r in rows], "counts": counts, "sources": SOURCES,
                "minBooks": min_books(seo), "lastRefresh": iso(last), "state": state,
                "gsc": bool(seo.gsc("queries")), "crm": _crm_configured()}

    @app.post("/api/v1/seo-geo/qsuggest/refresh")
    def seo_qsuggest_refresh(request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        started = start_refresh(seo, user)
        seo.audit(user, "run", "qsuggest", "Soru önerileri üretimi", {"started": started})
        return {"started": started, "state": state}

    @app.post("/api/v1/seo-geo/qsuggest/{sid}/accept")
    def seo_qsuggest_accept(sid: str, request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        r = _row(sid)
        if r["status"] == "eklendi":
            return {"id": sid, "questionId": r["question_id"], "status": "eklendi"}
        tenant = seo.tenant()
        with seo.engine().begin() as c:
            same = next((q_id for q_id, t in c.execute(sa.select(QUESTIONS.c.id, QUESTIONS.c.text)
                                                        .where(QUESTIONS.c.tenant_id == tenant)).all()
                         if norm(t) == r["norm"]), None)
            q_id = same or uuid.uuid4().hex
            if not same:
                c.execute(QUESTIONS.insert().values(id=q_id, tenant_id=tenant, text=r["text"],
                                                    category=CATEGORY.get(r["source"], r["source"]),
                                                    created_by=user, created_at=now()))
            c.execute(SUGGEST.update().where(SUGGEST.c.tenant_id == tenant, SUGGEST.c.id == sid)
                      .values(status="eklendi", question_id=q_id, decided_by=user, decided_at=now()))
        seo.audit(user, "create", q_id, r["text"][:120],
                  {"kind": "geo_question", "from": "qsuggest", "source": r["source"], "basis": loads(r["basis_json"], {}),
                   "existing": bool(same)})
        return {"id": sid, "questionId": q_id, "status": "eklendi"}

    @app.post("/api/v1/seo-geo/qsuggest/{sid}/reject")
    def seo_qsuggest_reject(sid: str, request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        r = _row(sid)
        if r["status"] == "eklendi":
            raise _err(409, "Bu soru izlenen sorulara eklenmiş; kaldırmak için Yapay zekâ görünürlüğü ekranını kullanın.")
        with seo.engine().begin() as c:
            c.execute(SUGGEST.update().where(SUGGEST.c.tenant_id == seo.tenant(), SUGGEST.c.id == sid)
                      .values(status="reddedildi", decided_by=user, decided_at=now()))
        seo.audit(user, "reject", sid, r["text"][:120], {"kind": "geo_question_suggestion", "source": r["source"]})
        return {"id": sid, "status": "reddedildi"}
