"""Rehber içerikler: okurun sorusuna cevap veren liste/rehber sayfası taslakları ("9–11 yaş için değerler eğitimi
kitapları", "yeni başlayanlar için tasavvuf kitapları").

Neden: yapay zekâ cevap motorları ve Google, "hangi kitap?" sorusuna cevap veren liste sayfalarını kaynak gösterir;
ürün sayfası tek kitabı anlatır, bu soruyu cevaplamaz.

Akış:
1. Konu bulma (sabit konu listesi yok): Search Console sorgularından liste/öneri niyetli olanlar seçilir (kalıp
   sezgisi), yakın olanlar kelime örtüşmesiyle kümelenir, gösterimle sıralanır. İzlenen GEO soruları da konudur.
   Yazar/yayınevi adından ibaret sorgu ("X kitapları") yazar sayfasının işidir; konu sayılmaz.
2. Kitap seçimi yalnız bizim verimizden: T-soft'ta aktif ürün + barkodla CRM kitap kartı (tür, web kategorisi,
   anahtar kelime, hedef kitle, yaş). CRM'de "bizim değil / çekildi / geri istendi" işaretli kitap alınmaz.
   Konu kelimeleri bu alanlarla eşleştirilir; eşitlikte çok satan önde. Neden eşleştiği yazılır.
3. Taslak ZEKİ AI ile (LLM kapısı, `llm_for("seo", …)`): SEO başlığı, meta açıklama, giriş, kitap başına bir
   paragraf (yalnız o kitabın kendi bilgisinden), 3–5 soru–cevap. ItemList + FAQPage JSON-LD'yi model değil kod
   kurar. Gerçeklik denetimi (`propose.unsupported`) kaynakta geçmeyen sayı ve özel adları işaretler.
4. Karar: onay verebilen kişi düzenleyip onaylar ya da reddeder. Onay yalnız kayıttır; hiçbir yere gönderilmez
   (T-soft'a ve CRM'e yazma yok). Sitedeki yayını site yöneticisi dışa aktarılan HTML ile elle yapar.

Gece: taslağı olmayan en çok gösterilen konular için, süre bütçesi içinde, BATCH önceliğiyle taslak hazırlanır.
"""
from __future__ import annotations

import hashlib
import html as html_mod
import json
import logging
import re
import threading
import time
import uuid
from typing import Any, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from . import crm, propose, rules
from .store import _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo.guides")

GUIDES = sa.Table(
    "semantic_seo_guides", _md,  # rehber sayfası taslağı → insan kararı. Hiçbir yere gönderilmez.
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("topic_key", sa.String(40), nullable=False, index=True),
    sa.Column("title", sa.String(300)),
    sa.Column("status", sa.String(16), nullable=False),        # hazir | onaylandi | reddedildi
    sa.Column("topic_json", sa.Text, nullable=False),          # taslak anındaki konu (sorgular, gösterim)
    sa.Column("fields_json", sa.Text, nullable=False),         # SeoTitle, SeoDescription, Intro, Books{id:metin}, Faq[{q,a}]
    sa.Column("books_json", sa.Text, nullable=False),          # seçilen kitapların taslak anındaki bilgisi (sıralı)
    sa.Column("jsonld_json", sa.Text, nullable=False),         # kodla kurulan ItemList + FAQPage
    sa.Column("unsupported_json", sa.Text, nullable=False),    # {"general": [...], "books": {id: [...]}}
    sa.Column("model", sa.String(120)),
    sa.Column("created_by", sa.String(120)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("note", sa.String(1000)),
)
STATUSES = ("hazir", "onaylandi", "reddedildi")
_ready: set[int] = set()
_ready_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    """store.ensure bu modül yüklenmeden koşmuş olabilir; tablo burada ayrıca kurulur."""
    with _ready_lock:
        if id(engine) in _ready:
            return
        GUIDES.create(engine, checkfirst=True)
        _ready.add(id(engine))


# ------------------------------------------------------------------ dil: Türkçe küçük harf + katlama
_FOLD = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def norm(s: Any) -> str:
    """Türkçe küçük harf, aksansız: "Değerler Eğitimi" → "degerler egitimi". Arama kutusuna Türkçe harfsiz
    yazılan sorgu ile CRM'deki doğru yazım aynı görünür."""
    return re.sub(r"\s+", " ", propose._lower(rules.text_of(s)).translate(_FOLD)).strip()


def stem(word: str) -> str:
    """Ek yüzünden ayrışmasın: uzun kelimede ilk 5 harf (propose._stem ile aynı ölçü, katlanmış)."""
    w = norm(re.split(r"['’]", word)[0])
    return w[:5] if len(w) > 6 else w


_STOP_WORDS = (
    "ve ile icin en bir bu su o de da mi mu ne neler hangi hangisi nasil nedir gibi olan olarak veya ya "
    "kitap kitaplar kitaplari kitabi kitaplarim kitaplarini kitaplik oneri oneriler onerileri onerisi tavsiye tavsiyeler "
    "tavsiyeleri tavsiye edilen iyi guzel okunmasi okunmali okumali okunacak okunabilecek gereken gerekenler liste listesi "
    "okul oncesi ilkokul ortaokul lise "
    "okuma yas yasi yasinda yasindaki yaslar yasindakiler sinif sinifi sinifa siniflar sinifinda yeni baslayan "
    "baslayanlar baslangic icin pdf oku indir ucretsiz satin al fiyat fiyati timas yayinlari yayinevi"
)
STOP = {stem(w) for w in _STOP_WORDS.split()}

#: Liste/öneri niyeti: sorgu bir kitabı değil "hangi kitaplar?" sorusunu soruyor. Sezgidir; katlanmış metne bakar.
INTENT = [re.compile(p) for p in (
    r"\bkitap (onerileri|onerisi|oneri|tavsiye)", r"\bkitaplari\b", r"\bkitaplar\b", r"\ben iyi\b", r"\bhangi kita[pb]",
    r"\bokunmasi gereken", r"\bokunmali\b", r"\bne okun", r"\bne okumali", r"\bokunacak\b", r"\bokuma listesi",
    r"\bkitap listesi", r"\d{1,2}\s*(?:(?:-|–|/)\s*\d{1,2}\s*)?yas", r"\byas grubu", r"\bsinif\b", r"\bsinifi\b",
    r"\bicin kitap", r"\broman (onerileri|onerisi|tavsiye)", r"\btavsiye edilen", r"\bbaslayanlar icin",
    r"\b(cocuklar|gencler|ogrenciler|yetiskinler|kadinlar|anneler|babalar) icin",
)]
_NAV = re.compile(r"\btimas\b|\bwww\b|\.com\b")


def is_list_intent(query: str) -> bool:
    q = norm(query)
    return bool(q) and not _NAV.search(q) and any(p.search(q) for p in INTENT)


def core_terms(text: str) -> list[tuple[str, str]]:
    """(kök, özgün kelime): niyet ve dolgu kelimeleri atılır; sayılar (yaş/sınıf) kalır."""
    out: dict[str, str] = {}
    for w in re.findall(r"\w+", rules.text_of(text)):
        s = stem(w)
        if s and s not in STOP and (len(s) > 1 or s.isdigit()):
            out.setdefault(s, w)
    return list(out.items())


def ages(text: str) -> Optional[tuple[int, int]]:
    """Konudaki yaş aralığı: "9-11 yaş", "10 yaş", "3. sınıf", "ilkokul"… Yoksa None."""
    q = norm(text)
    m = re.search(r"\b(\d{1,2})\s*(?:-|–|/|ile)\s*(\d{1,2})\s*yas", q)
    if m:
        a, b = sorted((int(m.group(1)), int(m.group(2))))
        return a, b
    m = re.search(r"\b(\d{1,2})\s*(?:\+\s*)?yas", q)
    if m:
        return int(m.group(1)), int(m.group(1))
    m = re.search(r"\b(\d{1,2})\s*\.?\s*sinif", q)
    if m and 1 <= int(m.group(1)) <= 12:
        n = int(m.group(1))
        return n + 5, n + 6
    for word, rng in (("okul oncesi", (3, 6)), ("ilkokul", (6, 10)), ("ortaokul", (10, 14)), ("lise", (14, 18))):
        if re.search(rf"\b{word}", q):
            return rng
    return None


def topic_key(core: set[str]) -> str:
    return hashlib.sha1(" ".join(sorted(core)).encode()).hexdigest()[:16]


def _similar(a: set[str], b: set[str]) -> bool:
    if not a or not b:
        return False
    if len(a & b) / len(a | b) >= 0.6:
        return True
    small, big = (a, b) if len(a) <= len(b) else (b, a)
    return len(small) >= 2 and small <= big and len(big) - len(small) <= 1


def cluster(items: list[dict[str, Any]], exclude: Optional[list[set[str]]] = None) -> list[dict[str, Any]]:
    """Sorgu/soru → konu. `items`: {text, impressions, clicks, position, source}. Gösterimi yüksek olan kümenin
    başı olur; aynı sayılar (yaş) ve ≥%60 kelime örtüşmesi aynı konu sayılır. `exclude`: yazar adlarının kök
    kümeleri; konu kelimeleri bir yazarın adıysa ("sabahattin ali kitapları") konu değil, yazar sayfasının işidir.
    Yayınevi adı dışarıda bırakılmaz: "Timaş Çocuk" yüzünden "çocuk kitapları" düşerdi."""
    exclude = exclude or []
    clusters: list[dict[str, Any]] = []
    for it in sorted(items, key=lambda x: (-(x.get("impressions") or 0), x["text"])):
        terms = core_terms(it["text"])
        core = {s for s, _ in terms}
        words = {s for s in core if not s.isdigit()}
        rng = ages(it["text"])
        # Yalnız okul/yaş taşıyan sorgu ("lise kitapları") da konudur: kitap yaşla seçilir.
        if not words and not rng:
            continue
        if words and any(words == name or (len(words) >= 2 and words <= name) for name in exclude if name):
            continue
        nums = {s for s in core if s.isdigit()}
        for c in clusters:
            if c["_nums"] == nums and c["_ages"] == rng and (_similar(words, c["_words"]) or not words and not c["_words"]):
                c["queries"].append(it)
                break
        else:
            clusters.append({"_words": words, "_nums": nums, "_ages": rng, "_terms": terms, "queries": [it]})
    out = []
    for c in clusters:
        head = c["queries"][0]
        pos = [q["position"] for q in c["queries"] if q.get("position")]
        text = head["text"].strip()
        age_tag = {f"yas:{c['_ages'][0]}-{c['_ages'][1]}"} if c["_ages"] else set()
        out.append({
            "key": topic_key(c["_words"] | c["_nums"] | age_tag), "title": text[:1].upper() + text[1:],
            "terms": [w for s, w in c["_terms"] if not s.isdigit()],
            "ages": list(c["_ages"]) if c["_ages"] else None,
            "impressions": sum(int(q.get("impressions") or 0) for q in c["queries"]),
            "clicks": sum(int(q.get("clicks") or 0) for q in c["queries"]),
            "position": round(min(pos), 1) if pos else None,
            "sources": sorted({q.get("source") or "arama" for q in c["queries"]}),
            "queries": [{"text": q["text"], "impressions": int(q.get("impressions") or 0), "clicks": int(q.get("clicks") or 0),
                         "position": q.get("position"), "source": q.get("source") or "arama"} for q in c["queries"]],
        })
    out.sort(key=lambda t: (-t["impressions"], -len(t["queries"]), t["title"]))
    return out


def topics(gsc_rows: list[dict[str, Any]], questions: list[str], exclude: Optional[list[set[str]]] = None) -> list[dict[str, Any]]:
    items = []
    for r in gsc_rows:
        q = (r.get("keys") or [""])[0]
        if q and is_list_intent(q):
            items.append({"text": q, "impressions": r.get("impressions") or 0, "clicks": r.get("clicks") or 0,
                          "position": r.get("position"), "source": "arama"})
    # İzlenen GEO soruları zaten okur sorusudur: niyet süzgecinden geçmez.
    items += [{"text": q, "impressions": 0, "clicks": 0, "position": None, "source": "soru"} for q in questions if q]
    return cluster(items, exclude)


# ------------------------------------------------------------------ kitap seçimi
#: (ağırlık, ekranda ad, kitap kaydındaki alan)
BOOK_FIELDS: tuple[tuple[float, str, str], ...] = (
    (3.0, "Tür", "genres"), (3.0, "Web kategorisi", "webCategories"), (2.0, "Anahtar kelime", "keywords"),
    (2.0, "Hedef kitle", "audience"), (2.0, "Kategori", "category"), (1.5, "Kitap adı", "name"),
    (1.0, "Etiket", "hashtags"), (1.0, "Yayınevi", "brand"), (1.0, "Tanıtım", "spot"),
)


def _parts(text: Any) -> list[str]:
    return [p.strip() for p in re.split(r"[,;|>/#\n]+", rules.text_of(text)) if p.strip()]


def field_index(book: dict[str, Any]) -> dict[str, list[tuple[str, set[str]]]]:
    """Alan → [(parça, kökler)]. Katalogda bir kez kurulur; her konu için binlerce kitap yeniden köklenmesin."""
    return {key: [(p, {stem(w) for w in re.findall(r"\w+", p)}) for p in _parts(book.get(key))] for _, _, key in BOOK_FIELDS}


def _public(b: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in b.items() if k != "_idx"}


def _num(v: Any) -> Optional[int]:
    try:
        n = int(float(str(v)))
        return n if n > 0 else None
    except (TypeError, ValueError):
        return None


def score_book(topic: dict[str, Any], book: dict[str, Any]) -> tuple[float, list[str]]:
    """Konu kelimelerinin kitap alanlarıyla eşleşmesi. (puan, neden). Puan 0 → aday değil.
    Kelimelerin en az yarısı eşleşmeli; konu yaş taşıyorsa ve kitabın yaş aralığı çakışmıyorsa aday değil."""
    terms = {stem(w) for w in topic.get("terms") or []}
    rng = topic.get("ages")
    idx = book.get("_idx") or field_index(book)
    why: list[str] = []
    total, matched = 0.0, 0
    for t in sorted(terms):
        for weight, label, key in BOOK_FIELDS:
            hit = next((p for p, stems in idx.get(key, ()) if t in stems), None)
            if hit:
                total += weight
                matched += 1
                reason = f"{label}: {hit[:80]}"
                if reason not in why:
                    why.append(reason)
                break
    if terms and matched * 2 < len(terms):
        return 0.0, []
    score = total * (matched / len(terms)) if terms else 0.0
    if rng:
        lo, hi = _num(book.get("ageFrom")), _num(book.get("ageTo"))
        if lo or hi:
            lo, hi = lo or hi, hi or lo
            if lo > rng[1] or hi < rng[0]:
                return 0.0, []
            score += 3.0
            why.append(f"Yaş: {lo}–{hi}" if lo != hi else f"Yaş: {lo}")
        elif not terms:
            return 0.0, []
    return round(score, 2), why


def candidates(topic: dict[str, Any], catalog: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aday kitaplar, puan sonra satışla. CRM durum işareti olan kitap aday değildir."""
    out = []
    for b in catalog:
        if b.get("statusFlag"):
            continue
        s, why = score_book(topic, b)
        if s > 0:
            out.append({**_public(b), "score": s, "why": why})
    out.sort(key=lambda b: (-b["score"], -(b.get("sales") or 0), b.get("name") or ""))
    return out


def book_record(p: dict[str, Any], c: Optional[dict[str, Any]], site: str, image: Optional[str]) -> dict[str, Any]:
    """T-soft ürünü + CRM kartı → rehberde kullanılan kitap bilgisi (taslakla birlikte saklanır)."""
    c = c or {}
    link = p.get("SeoLink") or p.get("Url") or p.get("ProductUrl") or ""
    url = link if str(link).startswith("http") else (f"{site.rstrip('/')}/{str(link).lstrip('/')}" if link and site else None)
    cat = " > ".join(x.strip() for x in f"{p.get('DefaultCategoryPath') or ''}>{p.get('DefaultCategoryName') or ''}".split(">") if x.strip())
    try:
        sales = int(float(str(p.get("CountTotalSales") or 0).replace(",", ".")))
    except ValueError:
        sales = 0
    tsoft_text = crm.clean(rules.text_of(p.get("ShortDescription")) or rules.text_of(p.get("Details")), 900)
    return {
        "id": str(p.get("ProductId") or ""), "name": rules.text_of(p.get("ProductName")) or c.get("name"),
        "author": rules.text_of(p.get("Model")) or c.get("authors"), "brand": rules.text_of(p.get("Brand")) or None,
        "category": cat or None, "url": url, "image": image, "isbn": crm.ean_key(p.get("Barcode")) or None, "sales": sales,
        "statusFlag": c.get("statusFlag"), "genres": c.get("genres"), "webCategories": c.get("webCategories"),
        "keywords": c.get("keywords") or rules.text_of(p.get("SearchKeywords")) or None, "hashtags": c.get("hashtags"),
        "audience": c.get("audience"), "ageFrom": c.get("ageFrom"), "ageTo": c.get("ageTo"), "pages": c.get("pages"),
        "translators": c.get("translators"), "illustrators": c.get("illustrators"), "originalTitle": c.get("originalTitle"),
        "spot": crm.clean(c.get("spot"), 1200), "summary": crm.clean(c.get("summary"), 1500), "tsoftText": tsoft_text,
    }


# ------------------------------------------------------------------ taslak
FACT_KEYS = (("name", "Ad"), ("author", "Yazar"), ("brand", "Yayınevi"), ("category", "Kategori"), ("genres", "Tür"),
             ("audience", "Hedef kitle"), ("pages", "Sayfa sayısı"), ("translators", "Çevirmen"),
             ("illustrators", "Çizer"), ("originalTitle", "Özgün adı"), ("spot", "Spot"), ("summary", "Özet"),
             ("tsoftText", "Sitedeki açıklama"))


def _age_text(b: dict[str, Any]) -> Optional[str]:
    lo, hi = _num(b.get("ageFrom")), _num(b.get("ageTo"))
    if not lo and not hi:
        return None
    return f"{lo or hi}–{hi or lo} yaş" if (lo or hi) != (hi or lo) else f"{lo or hi} yaş"


def book_facts(b: dict[str, Any]) -> str:
    lines = [f"id: {b['id']}"]
    for key, label in FACT_KEYS:
        v = b.get(key)
        if v not in (None, "", 0):
            lines.append(f"{label}: {v}")
    if _age_text(b):
        lines.append(f"Yaş: {_age_text(b)}")
    return "\n".join(lines)


PROMPT = """Sen Timaş Yayınları'nın sitesi (timas.com.tr) için Türkçe rehber sayfası yazan editörsün.
Okurun sorusu / konu: "{topic}"
Bu konuda yapılan aramalar: {queries}
Aşağıdaki kitaplarla bu soruya cevap veren bir liste sayfası yaz. Kurallar:
- YALNIZ aşağıdaki kitap bilgilerini kullan. Verilmeyen ödül, baskı sayısı, yaş, sayfa sayısı, tarih, yazar
  biyografisi UYDURMA. Emin olmadığın bilgiyi yazma.
- Satış adedi şirket içi bilgidir: satış rakamı ya da "çok satan" yazma.
- Her kitap paragrafı YALNIZ o kitabın kendi bilgisinden yazılır; bir kitabın bilgisini başkasına taşıma.
- SeoTitle: {title_min}–{title_max} karakter; okurun sorusunu karşılayan başlık, sonunda sığarsa " | Timaş".
- SeoDescription: {meta_min}–{meta_max} karakter, tek paragraf; başlığı tekrar etme, tırnak ve emoji yok.
- Intro: 120–200 kelimelik giriş (düz metin): bu liste kimin için, hangi ihtiyaca cevap veriyor; kitap
  bilgilerine dayanarak.
- Books: listedeki HER kitap için 40–90 kelimelik tek paragraf (düz metin); kitabın adını ve varsa yazarını
  geçir. "id" alanını aşağıdakiyle aynen yaz.
- Faq: 3–5 soru–cevap; yalnız verilen bilgiyle cevaplanabilen sorular. Cevabı bilgide olmayan soruyu yazma.
Sadece şu JSON'u döndür, başka hiçbir şey yazma:
{{"SeoTitle": "...", "SeoDescription": "...", "Intro": "...", "Books": [{{"id": "...", "text": "..."}}], "Faq": [{{"q": "...", "a": "..."}}]}}

KİTAPLAR
{books}
"""


def build_prompt(topic: dict[str, Any], books: list[dict[str, Any]], lim: dict[str, int]) -> str:
    queries = "; ".join(q["text"] for q in topic.get("queries", [])) or "-"
    return PROMPT.format(topic=topic["title"], queries=queries,
                         books="\n\n".join(f"[{i}]\n{book_facts(b)}" for i, b in enumerate(books, 1)), **lim)


def parse(raw: Optional[str], ids: list[str]) -> dict[str, Any]:
    if not raw:
        raise ValueError("Model cevap vermedi.")
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("Model cevabında JSON bulunamadı.")
    data = json.loads(m.group(0))
    books = {}
    for item in data.get("Books") or []:
        if isinstance(item, dict) and str(item.get("id")) in ids and rules.text_of(item.get("text")):
            books[str(item["id"])] = rules.text_of(item["text"])
    faq = [{"q": rules.text_of(f.get("q")), "a": rules.text_of(f.get("a"))} for f in data.get("Faq") or []
           if isinstance(f, dict) and rules.text_of(f.get("q")) and rules.text_of(f.get("a"))]
    out = {"SeoTitle": rules.text_of(data.get("SeoTitle")), "SeoDescription": rules.text_of(data.get("SeoDescription")),
           "Intro": rules.text_of(data.get("Intro")), "Books": books, "Faq": faq}
    if not out["SeoTitle"] and not out["Intro"] and not books:
        raise ValueError("Model boş taslak döndürdü.")
    return out


def violations(fields: dict[str, Any], ids: list[str], lim: dict[str, int]) -> list[str]:
    out = propose.violations(fields, lim)
    missing = [i for i in ids if not fields["Books"].get(i)]
    if missing:
        out.append("Books şu id'ler için paragraf eksik: " + ", ".join(missing))
    if not 3 <= len(fields["Faq"]) <= 5:
        out.append(f"Faq {len(fields['Faq'])} soru; 3–5 olmalı (yalnız bilgiyle cevaplanabilen)")
    return out


def suggest(llm: Any, topic: dict[str, Any], books: list[dict[str, Any]], lim: dict[str, int]) -> dict[str, Any]:
    """Taslak; kural dışı çıkarsa model bir kez, neyin yanlış olduğu söylenerek düzeltmeye çağrılır. İkinci cevap
    daha iyi değilse ilki kalır; ekran sayaçları kırmızı gösterir, editör düzenler."""
    ids = [b["id"] for b in books]
    messages = [{"role": "user", "content": build_prompt(topic, books, lim)}]
    raw = llm.chat(messages, max_tokens=6000, temperature=0.2)
    fields = parse(raw, ids)
    wrong = violations(fields, ids, lim)
    if wrong:
        messages += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": "Düzelt: " + "; ".join(wrong) + ". Aynı JSON biçiminde yalnız düzeltilmiş hâli döndür."}]
        try:
            fixed = parse(llm.chat(messages, max_tokens=6000, temperature=0.2), ids)
            if len(violations(fixed, ids, lim)) < len(wrong):
                fields = fixed
        except ValueError:
            pass
    fields.update(propose.enforce({"SeoTitle": fields["SeoTitle"], "SeoDescription": fields["SeoDescription"]}, lim))
    return fields


# ------------------------------------------------------------------ JSON-LD (kodla; model yazmaz)
def jsonld(fields: dict[str, Any], books: list[dict[str, Any]], page_url: Optional[str] = None) -> list[dict[str, Any]]:
    """ItemList (kitap sırası, adresleriyle) + FAQPage (soru–cevap varsa). Adresi olmayan kitap Book öğesiyle girer."""
    items = []
    for i, b in enumerate(books, 1):
        if b.get("url"):
            items.append({"@type": "ListItem", "position": i, "url": b["url"], "name": b.get("name")})
        else:
            book: dict[str, Any] = {"@type": "Book", "name": b.get("name")}
            if b.get("author"):
                book["author"] = {"@type": "Person", "name": b["author"]}
            if b.get("isbn"):
                book["isbn"] = b["isbn"]
            items.append({"@type": "ListItem", "position": i, "item": book})
    lst: dict[str, Any] = {"@context": "https://schema.org", "@type": "ItemList", "name": fields.get("SeoTitle") or None,
                           "numberOfItems": len(items), "itemListElement": items}
    if fields.get("SeoDescription"):
        lst["description"] = fields["SeoDescription"]
    if page_url:
        lst["url"] = page_url
    out = [{k: v for k, v in lst.items() if v is not None}]
    faq = [f for f in fields.get("Faq") or [] if f.get("q") and f.get("a")]
    if faq:
        out.append({"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": f["q"], "acceptedAnswer": {"@type": "Answer", "text": f["a"]}} for f in faq]})
    return out


# ------------------------------------------------------------------ gerçeklik denetimi
def _book_source(b: dict[str, Any]) -> str:
    vals = [str(b.get(k)) for k, _ in FACT_KEYS if b.get(k) not in (None, "")]
    vals += [str(b.get(k) or "") for k in ("keywords", "webCategories", "hashtags", "isbn")]
    return " ".join(vals + [_age_text(b) or "", "Timaş Yayınları Timaş"])


def _html(*parts: Any) -> str:
    return "".join(f"<p>{html_mod.escape(str(p))}</p>" for p in parts if p)


def reality(topic: dict[str, Any], books: list[dict[str, Any]], fields: dict[str, Any]) -> dict[str, Any]:
    """Genel metin (başlık, açıklama, giriş, SSS) konu + bütün kitaplara karşı; her kitap paragrafı yalnız o kitabın
    kendi kaydına karşı taranır. Kaynakta geçmeyen sayı ve cümle ortası özel adlar listelenir."""
    src_all = " ".join([topic.get("title") or "", " ".join(q["text"] for q in topic.get("queries", []))]
                       + [_book_source(b) for b in books])
    general = propose.unsupported(
        {"ProductName": topic.get("title"), "Details": src_all},
        {"SeoTitle": fields.get("SeoTitle", ""), "SeoDescription": fields.get("SeoDescription", ""),
         "Details": _html(fields.get("Intro"), *[x for f in fields.get("Faq") or [] for x in (f.get("q"), f.get("a"))])})
    per: dict[str, list[str]] = {}
    for b in books:
        text = (fields.get("Books") or {}).get(b["id"])
        if text:
            miss = propose.unsupported({"ProductName": b.get("name"), "Details": _book_source(b)}, {"Details": _html(text)})
            if miss:
                per[b["id"]] = miss
    return {"general": general, "books": per}


# ------------------------------------------------------------------ dışa aktarım
def export_html(fields: dict[str, Any], books: list[dict[str, Any]], ld: list[dict[str, Any]], status: str) -> str:
    e = html_mod.escape
    items = []
    for b in books:
        name = e(b.get("name") or "")
        head = f'<a href="{e(b["url"])}">{name}</a>' if b.get("url") else name
        by = f"<p class=\"yazar\">{e(b['author'])}</p>" if b.get("author") else ""
        items.append(f"  <li>\n    <h2>{head}</h2>\n    {by}\n    <p>{e((fields.get('Books') or {}).get(b['id'], ''))}</p>\n  </li>")
    faq = "".join(f"\n  <h3>{e(f['q'])}</h3>\n  <p>{e(f['a'])}</p>" for f in fields.get("Faq") or [] if f.get("q"))
    scripts = "\n".join('<script type="application/ld+json">\n' + json.dumps(x, ensure_ascii=False, indent=2).replace("</", "<\\/")
                        + "\n</script>" for x in ld)
    note = "" if status == "onaylandi" else "<!-- DİKKAT: bu taslak henüz onaylanmadı. -->\n"
    return (f"<!doctype html>\n{note}<html lang=\"tr\">\n<head>\n<meta charset=\"utf-8\">\n<title>{e(fields.get('SeoTitle') or '')}</title>\n"
            f"<meta name=\"description\" content=\"{e(fields.get('SeoDescription') or '')}\">\n{scripts}\n</head>\n<body>\n<article>\n"
            f"<h1>{e(fields.get('SeoTitle') or '')}</h1>\n<p>{e(fields.get('Intro') or '')}</p>\n<ol>\n" + "\n".join(items) + "\n</ol>\n"
            + (f"<section>\n  <h2>Sıkça Sorulan Sorular</h2>{faq}\n</section>\n" if faq else "")
            + "</article>\n</body>\n</html>\n")


def clean_fields(raw: dict[str, Any]) -> dict[str, Any]:
    """Ekrandan gelen düzenleme: bilinen alanlar, düz metin."""
    out: dict[str, Any] = {}
    for k in ("SeoTitle", "SeoDescription", "Intro"):
        if k in raw:
            out[k] = rules.text_of(raw.get(k))
    if isinstance(raw.get("Books"), dict):
        out["Books"] = {str(k): rules.text_of(v) for k, v in raw["Books"].items()}
    if isinstance(raw.get("Faq"), list):
        out["Faq"] = [{"q": rules.text_of(f.get("q")), "a": rules.text_of(f.get("a"))} for f in raw["Faq"]
                      if isinstance(f, dict) and (rules.text_of(f.get("q")) or rules.text_of(f.get("a")))]
    return out


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", norm(text)).strip("-")[:80] or "rehber"


# ------------------------------------------------------------------ uçlar
# Modül düzeyinde: `from __future__ import annotations` ile FastAPI tipleri modülün globallerinde arar; içeride
# tanımlı model/Request sorgu parametresi sanılır (422 «query.request missing»).
class GuideCreate(BaseModel):
    topicKey: str = Field(min_length=1, max_length=40)
    bookIds: Optional[list[str]] = None


class GuideDecision(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    fields: dict[str, Any] = Field(default_factory=dict)
    bookIds: Optional[list[str]] = None
    note: str = Field(default="", max_length=1000)


def register(app, ctx) -> None:  # noqa: C901 — uçlar tek yerde, modülün düzeni böyle
    from fastapi.responses import HTMLResponse

    from . import EAN, _image
    from .store import CRM_BOOKS, PRODUCTS, QUESTIONS

    seo = ctx.seo
    run: dict[str, Any] = {"running": False, "done": 0, "failed": 0, "skipped": 0, "startedAt": None,
                           "finishedAt": None, "error": None}
    cache: dict[str, Any] = {}
    cache_lock = threading.Lock()

    def err(status: int, message: str) -> HTTPException:
        return HTTPException(status, {"code": "SEO", "message": message})

    def eng():
        e = seo.engine()
        ensure(e)
        return e

    def catalog() -> tuple[list[dict[str, Any]], list[set[str]]]:
        """Aktif T-soft ürünleri + CRM kartı; eşitleme damgası değişene kadar bellekte (her istekte binlerce JSON
        açılmasın). İkinci dönüş: yazar adlarının kök kümeleri (konu dışı bırakma için)."""
        tenant = seo.tenant()
        with eng().connect() as c:
            stamp = (c.execute(sa.select(sa.func.max(PRODUCTS.c.synced_at)).where(PRODUCTS.c.tenant_id == tenant)).scalar(),
                     c.execute(sa.select(sa.func.max(CRM_BOOKS.c.synced_at)).where(CRM_BOOKS.c.tenant_id == tenant)).scalar())
        with cache_lock:
            hit = cache.get(tenant)
            if hit and hit[0] == stamp:
                return hit[1], hit[2]
        site = seo.conf("SEO_SITE_URL")
        j = PRODUCTS.outerjoin(CRM_BOOKS, sa.and_(CRM_BOOKS.c.tenant_id == PRODUCTS.c.tenant_id, CRM_BOOKS.c.ean == EAN))
        with eng().connect() as c:
            rows = c.execute(sa.select(PRODUCTS.c.data_json, CRM_BOOKS.c.data_json.label("crm_json")).select_from(j)
                             .where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True))).all()
        books, names = [], set()
        for data, crm_json in rows:
            p = loads(data, {})
            b = book_record(p, loads(crm_json, None) if crm_json else None, site, _image(p, site))
            if b["id"]:
                b["_idx"] = field_index(b)
                books.append(b)
            # Çok yazarlı kayıtta ("A, B") her yazar ayrı ad.
            for n in re.split(r"[,;&]| ve ", b.get("author") or ""):
                if n.strip():
                    names.add(frozenset(s for s, _ in core_terms(n) if not s.isdigit()))
        excl = [set(n) for n in names if n]
        with cache_lock:
            cache[tenant] = (stamp, books, excl)
        return books, excl

    def all_topics() -> list[dict[str, Any]]:
        g = seo.gsc("queries") or {}
        with eng().connect() as c:
            qs = [r[0] for r in c.execute(sa.select(QUESTIONS.c.text).where(QUESTIONS.c.tenant_id == seo.tenant()))]
        _, excl = catalog()
        return topics(g.get("rows") or [], qs, excl)

    def topic_by_key(key: str) -> dict[str, Any]:
        t = next((t for t in all_topics() if t["key"] == key), None)
        if t is None:
            raise err(404, "Konu bulunamadı; Search Console verisi yenilenmiş olabilir.")
        return t

    def drafts_by_topic() -> dict[str, dict[str, Any]]:
        with eng().connect() as c:
            rows = c.execute(sa.select(GUIDES.c.topic_key, GUIDES.c.id, GUIDES.c.status).where(
                GUIDES.c.tenant_id == seo.tenant()).order_by(GUIDES.c.created_at)).all()
        return {k: {"id": i, "status": s} for k, i, s in rows}   # konu başına en yenisi

    def default_count() -> int:
        try:
            return max(1, int(seo.conf("SEO_GUIDE_BOOKS") or 10))
        except ValueError:
            return 10

    def min_books() -> int:
        try:
            return max(1, int(seo.conf("SEO_GUIDE_MIN_BOOKS") or 3))
        except ValueError:
            return 3

    def cand_view(b: dict[str, Any]) -> dict[str, Any]:
        return {k: b.get(k) for k in ("id", "name", "author", "brand", "url", "image", "sales", "score", "why",
                                      "genres", "audience", "category")} | {"ages": _age_text(b)}

    def row(gid: str) -> dict[str, Any]:
        with eng().connect() as c:
            r = c.execute(sa.select(GUIDES).where(GUIDES.c.tenant_id == seo.tenant(), GUIDES.c.id == gid)).mappings().first()
        if not r:
            raise err(404, "Rehber taslağı bulunamadı.")
        return dict(r)

    def view(r: dict[str, Any], full: bool = True) -> dict[str, Any]:
        fields, books = loads(r["fields_json"], {}), loads(r["books_json"], [])
        out = {"id": r["id"], "topicKey": r["topic_key"], "title": r["title"], "status": r["status"],
               "topic": loads(r["topic_json"], {}), "books": len(books), "model": r["model"],
               "createdBy": r["created_by"], "createdAt": iso(r["created_at"]), "decidedBy": r["decided_by"],
               "decidedAt": iso(r["decided_at"]), "note": r["note"]}
        if full:
            out.update(fields=fields, books=[{k: b.get(k) for k in ("id", "name", "author", "brand", "url", "image", "isbn",
                                                                    "category", "genres", "audience", "why")}
                                             | {"ages": _age_text(b)} for b in books],
                       jsonld=loads(r["jsonld_json"], []), unsupported=loads(r["unsupported_json"], {"general": [], "books": {}}),
                       limits=rules.thresholds(seo.conf))
        return out

    def pick(ids: list[str], topic: dict[str, Any]) -> list[dict[str, Any]]:
        books, _ = catalog()
        by_id = {b["id"]: b for b in books}
        scored = {b["id"]: b for b in candidates(topic, books)}
        out = []
        for i in dict.fromkeys(str(x) for x in ids):
            b = scored.get(i) or by_id.get(i)
            if b is None:
                raise err(422, f"Kitap bulunamadı ya da aktif değil: {i}")
            if b.get("statusFlag"):
                raise err(422, f"CRM'de işaretli kitap rehbere alınmaz: {b.get('name')}")
            out.append(_public(b))
        return out

    def make(topic: dict[str, Any], book_ids: Optional[list[str]], user: str, priority: Optional[int] = None) -> dict[str, Any]:
        gen_key = f"guide:{topic['key']}"
        with seo._gen_lock:
            if gen_key in seo._generating:
                raise err(409, "Bu konu için taslak şu an yazılıyor.")
            seo._generating.add(gen_key)
        try:
            books = pick(book_ids, topic) if book_ids else candidates(topic, catalog()[0])[:default_count()]
            if not books:
                raise err(422, "Bu konu için kitap verimizde eşleşen kitap yok.")
            llm = seo.runtime().llm_for("seo", priority)
            if llm is None:
                raise err(503, "Yapay zekâ modeli bu kurulumda tanımlı değil.")
            lim = rules.thresholds(seo.conf)
            try:
                fields = suggest(llm, topic, books, lim)
            except ValueError as e:
                raise err(502, f"Taslak üretilemedi: {e}") from None
            gid, tenant = uuid.uuid4().hex, seo.tenant()
            with eng().begin() as c:
                # Aynı konunun bekleyen eski taslağı yenisiyle değişir; karar verilmişler kalır.
                c.execute(GUIDES.delete().where(GUIDES.c.tenant_id == tenant, GUIDES.c.topic_key == topic["key"],
                                                GUIDES.c.status == "hazir"))
                c.execute(GUIDES.insert().values(
                    id=gid, tenant_id=tenant, topic_key=topic["key"], title=(fields["SeoTitle"] or topic["title"])[:300],
                    status="hazir", topic_json=dumps(topic), fields_json=dumps(fields), books_json=dumps(books),
                    jsonld_json=dumps(jsonld(fields, books)), unsupported_json=dumps(reality(topic, books, fields)),
                    model=(getattr(llm, "model", None) or seo.conf("LLM_MODEL_NAME") or "")[:120] or None,
                    created_by=user, created_at=now()))
            seo.audit(user, "create", f"guide:{gid}", topic["title"][:200], {"guide": gid, "books": len(books)})
            return view(row(gid))
        finally:
            with seo._gen_lock:
                seo._generating.discard(gen_key)

    @app.get("/api/v1/seo-geo/guides/topics")
    def guide_topics(request: Request, start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        ts, drafts = all_topics(), drafts_by_topic()
        g = seo.gsc("queries") or {}
        page = ts[max(0, start):max(0, start) + max(1, limit)]
        return {"total": len(ts), "start": start, "search": {"start": g.get("start"), "end": g.get("end"), "savedAt": g.get("savedAt")},
                "items": [{**t, "draft": drafts.get(t["key"])} for t in page], "run": run}

    @app.get("/api/v1/seo-geo/guides/topics/{key}/books")
    def guide_topic_books(key: str, request: Request, start: int = 0, limit: int = 100) -> dict[str, Any]:
        ctx.gate(request)
        t = topic_by_key(key)
        cands = candidates(t, catalog()[0])
        return {"topic": t, "total": len(cands), "start": start, "preselect": default_count(),
                "items": [cand_view(b) for b in cands[max(0, start):max(0, start) + max(1, limit)]]}

    @app.post("/api/v1/seo-geo/guides")
    def guide_create(body: GuideCreate, request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        return make(topic_by_key(body.topicKey), body.bookIds, user)

    @app.get("/api/v1/seo-geo/guides")
    def guide_list(request: Request, status: str = "", start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        if status and status not in STATUSES:
            raise err(422, "Bilinmeyen durum.")
        cond = [GUIDES.c.tenant_id == seo.tenant()] + ([GUIDES.c.status == status] if status else [])
        with eng().connect() as c:
            total = c.execute(sa.select(sa.func.count()).select_from(GUIDES).where(*cond)).scalar() or 0
            rows = c.execute(sa.select(GUIDES).where(*cond).order_by(GUIDES.c.created_at.desc())
                             .offset(max(0, start)).limit(max(1, limit))).mappings().all()
            counts = dict(c.execute(sa.select(GUIDES.c.status, sa.func.count()).where(GUIDES.c.tenant_id == seo.tenant())
                                    .group_by(GUIDES.c.status)).all())
        return {"total": total, "start": start, "counts": counts, "items": [view(dict(r), full=False) for r in rows]}

    @app.get("/api/v1/seo-geo/guides/{gid}")
    def guide_get(gid: str, request: Request) -> dict[str, Any]:
        ctx.gate(request)
        return view(row(gid))

    @app.post("/api/v1/seo-geo/guides/{gid}/decide")
    def guide_decide(gid: str, body: GuideDecision, request: Request) -> dict[str, Any]:
        """Karar yalnız kaydedilir; siteye/T-soft'a/CRM'e hiçbir şey gönderilmez."""
        user = ctx.approver(request)
        r = row(gid)
        if r["status"] != "hazir":
            raise err(409, "Bu taslak için karar zaten verilmiş.")
        topic, books, fields = loads(r["topic_json"], {}), loads(r["books_json"], []), loads(r["fields_json"], {})
        approve = body.action == "approve"
        if approve:
            edit = clean_fields(body.fields or {})
            fields = {**fields, **{k: v for k, v in edit.items() if k != "Books"},
                      "Books": {**(fields.get("Books") or {}), **edit.get("Books", {})}}
            if body.bookIds is not None:
                have = {b["id"]: b for b in books}
                new = [i for i in dict.fromkeys(str(x) for x in body.bookIds) if i not in have]
                extra = {b["id"]: b for b in pick(new, topic)} if new else {}
                books = [have.get(i) or extra[i] for i in dict.fromkeys(str(x) for x in body.bookIds)]
            fields["Books"] = {b["id"]: fields["Books"].get(b["id"], "") for b in books}
            if not books:
                raise err(422, "Rehberde en az bir kitap olmalı.")
            empty = [b.get("name") or b["id"] for b in books if not fields["Books"].get(b["id"])]
            if empty:
                raise err(422, "Şu kitapların paragrafı boş: " + ", ".join(empty))
            if not fields.get("SeoTitle"):
                raise err(422, "SEO başlığı boş olamaz.")
        with eng().begin() as c:
            vals: dict[str, Any] = dict(status="onaylandi" if approve else "reddedildi", decided_by=user,
                                        decided_at=now(), note=body.note or None)
            if approve:
                vals.update(title=fields["SeoTitle"][:300], fields_json=dumps(fields), books_json=dumps(books),
                            jsonld_json=dumps(jsonld(fields, books)), unsupported_json=dumps(reality(topic, books, fields)))
            c.execute(GUIDES.update().where(GUIDES.c.id == gid).values(**vals))
        seo.audit(user, body.action, f"guide:{gid}", (r["title"] or "")[:200], {"guide": gid, "kind": "guide"})
        return view(row(gid))

    @app.get("/api/v1/seo-geo/guides/{gid}/export.html")
    def guide_export(gid: str, request: Request):
        ctx.gate(request)
        r = row(gid)
        body = export_html(loads(r["fields_json"], {}), loads(r["books_json"], []), loads(r["jsonld_json"], []), r["status"])
        return HTMLResponse(body, headers={"Content-Disposition": f'attachment; filename="rehber-{slug(r["title"] or "")}.html"'})

    def nightly() -> None:
        """Taslağı olmayan konular, en çok gösterilenden; süre bütçesi (`SEO_GUIDES_BUDGET`, sn) dolunca durur,
        kalan sonraki gece. Yeterli kitabı (`SEO_GUIDE_MIN_BOOKS`) olmayan konu atlanır."""
        from semantic_layer.runtime.llm_queue import BATCH

        try:
            budget = int(seo.conf("SEO_GUIDES_BUDGET") or 1800)
        except ValueError:
            budget = 1800
        deadline = time.monotonic() + max(60, budget)
        run.update(running=True, done=0, failed=0, skipped=0, startedAt=iso(now()), finishedAt=None, error=None)
        try:
            has = drafts_by_topic()
            books = catalog()[0]
            for t in all_topics():
                if time.monotonic() > deadline:
                    break
                if t["key"] in has:
                    continue
                if len(candidates(t, books)) < min_books():
                    run["skipped"] += 1
                    continue
                try:
                    make(t, None, "zamanlayıcı", BATCH)
                    run["done"] += 1
                except HTTPException as e:
                    if e.status_code == 503:
                        raise
                    run["failed"] += 1
        except Exception as e:  # noqa: BLE001 — tur durur, üretilenler kalır
            run["error"] = str(getattr(e, "detail", e))[:500]
            log.exception("seo guides nightly failed")
        finally:
            run.update(running=False, finishedAt=iso(now()))

    seo.nightly.append(("guides", nightly))
