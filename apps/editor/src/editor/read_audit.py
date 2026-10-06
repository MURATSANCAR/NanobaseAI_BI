"""Okuma kalite denetimi: her okuma bitince kitabın çıktıları denetlenir, bulunan sorun sınıfına göre düzeltilir,
kalan sorun «gözden geçir» kaydına düşer (kullanıcı isteği 2026-10-06: «sen nasıl kontrol ediyorsan bizim model de
gerekli kontrolleri ve düzeltmeleri yapsın»). Bugüne kadar elle koşan okuma denetiminin (adım düşmesi, karakter,
künye, özet, bölüm, olay, öneri, dizin) kitaptan bağımsız kural hâli.

Akış:
- **İş akışında** (`quality-audit-v1`, tam ve arşiv): çıktılar ve kategori/yaş önerisi kurulduktan sonra
  `quality_audit` etkinliği → `run(gid, job_id, profile, failures, fix=True, origin='WORKFLOW')`. Okumanın kendi
  nesli: batch_guard'a sorulmaz. Kitabı yeniden okutmak gerekiyorsa iş SUCCEEDED kapandıktan sonra
  `quality_reread` etkinliği yeni işi sıraya koyar.
- **Komutla** (okunmuş eski kitaplar): `python -m editor.quality audit --all-read [--fix] [--ask]`. Varsayılan KURU
  koşudur (yalnız okur, hiçbir şey yazmaz); `--fix` düzeltir ve kaydı yazar; süren okumanın nesline dokunmaz
  (batch_guard, yazmadan hemen önce yeniden sorar).

Tur: denetim → düzeltme → yeniden denetim → (yeni eylem varsa) düzeltme → son denetim; en çok `ROUNDS` düzeltme
turu. Bir eylem aynı nesilde bir kez denenir (bu koşuda da, önceki kayıtlarda da: aynı sorun aynı eylemle tekrar
düzeltilmeye çalışılmaz); kitabı yeniden okutma bir kitap sürümünde en çok bir kez. «Zeki'ye sor» duman testi yalnız
son denetimde (iki soru, arka plan önceliğiyle, soru başına tek model çağrısı).

Kayıt: `ed.read_quality_audit` (037), her koşu bir satır: kontroller, ilk bulgular, kalan bulgular, düzeltmeler,
durum (CLEAN «Temiz» | FIXED «Düzeltildi» | REVIEW «Gözden geçir» | REREAD «yeniden okunacak»), yapan «ZEKİ AI».
İşin `progress.result.quality_audit` alanına özet yazılır. Kitap Eczanesi satırdaki rozeti ve ayrıntıdaki bulgu
listesini bu kayıttan gösterir (`listing`, `detail`).

Hiçbir kural kitap adı, sayfa numarası ya da ad içermez; eşikler `tests/test_read_quality_audit.py` sınır
testleriyle sabitlenmiştir."""

from __future__ import annotations

import argparse
import asyncio
import collections
import json
import logging
import re
import sys
import time
import unicodedata
from typing import Any

log = logging.getLogger(__name__)

VERSION = "read-audit-v1"
ACTOR = "ZEKİ AI"
#: Düzeltme turu sayısı (her turdan sonra yeniden denetim).
ROUNDS = 2

# ------------------------------------------------------------------ eşikler (sınır testleri: test_read_quality_audit)
#: Okunamayan sayfa (metin katmanı güvenilmez ve OCR yok / OCR gerekli ama koşmamış) payı ve en az sayısı.
UNREAD_SHARE = 0.10
UNREAD_MIN = 3
#: Bozuk karakter (‹ › ﬀ–ﬆ �) 10.000 karakterde; ünlüsüz ≥4 harfli kelime payı (yüzde), en az kelime sayısıyla.
GARBLE_PER_10K = 5.0
VOWELLESS_PCT = 3.0
GARBLE_MIN_WORDS = 2000
#: Tek «Kitap» bölümü bu sayfadan uzun kitapta şüphelidir.
LONG_BOOK_PAGES = 80
#: Aynı bölüm adı bu kadar kez.
REPEATED_TITLE_MIN = 3
#: Bölüm adı bu uzunluğu aşarsa cümle sayılır (romanın uzun bölüm adı «1. Bölüm: … – … – …» 92 karakter).
TITLE_MAX_CHARS = 120
#: Küçük harfle başlayan bölüm adı yalnız azınlıktaysa sorun (bütün başlıkları küçük harfle dizilmiş kitap tasarımdır).
LOWER_START_MAX_SHARE = 0.25
#: Künye kişisi: künye sayfası dışında hiç anılmayan kayıt (künyedeki editörle aynı adı taşıyan gerçek yan karakter
#: gövdede anılır ve sayılmaz).
IMPRINT_PERSON_BODY_PAGES = 0

STATUS_TR = {"CLEAN": "Temiz", "FIXED": "Düzeltildi", "REVIEW": "Gözden geçir", "REREAD": "Yeniden okunacak"}

_TR = str.maketrans("çğıöşüâîûÇĞİIÖŞÜÂÎÛ", "cgiosuaiuCGIIOSUAIU")


def fold(text: str | None) -> str:
    """Karşılaştırma anahtarı: Türkçe harf ve aksan farkı, büyük/küçük harf ve noktalama gözetilmez."""
    t = unicodedata.normalize("NFKD", (text or "").translate(_TR).casefold())
    return re.sub(r"[^a-z0-9]+", "", t.encode("ascii", "ignore").decode())


# ------------------------------------------------------------------ saf kurallar
_BAD_CHARS = re.compile(r"[‹›ﬀ-ﬆ�]")
_WORD = re.compile(r"[^\W\d_]+")
_VOWEL = re.compile(r"[aeıioöuüâîûAEIİOÖUÜÂÎÛ]")


def text_stats(texts: list[str]) -> dict:
    """Bozuk karakter sayısı (10.000 karakterde) ve ünlüsüz ≥ 4 harfli kelime payı (bozuk kodlamalı yazı tipi
    metni «ýaý.$%+ý» ya da harf harf dağılmış metin). Salt hesap."""
    chars = bad = words = vowelless = 0
    for t in texts:
        chars += len(t)
        bad += len(_BAD_CHARS.findall(t))
        ws = _WORD.findall(t)
        words += len(ws)
        vowelless += sum(1 for w in ws if len(w) >= 4 and not _VOWEL.search(w))
    return {"chars": chars, "bad_per_10k": round(bad * 1e4 / max(chars, 1), 2), "words": words,
            "vowelless_pct": round(vowelless * 100 / max(words, 1), 2)}


#: Okunamayan sayfa: metin katmanı güvenilmez ve OCR okuması yok, ya da OCR gerekli ama hiç koşmamış.
UNREAD_ISSUES = frozenset({"TEXT_LAYER_UNRELIABLE_NO_OCR", "OCR_REQUIRED_MISSING"})

KUNYE = re.compile(r"ISBN|Sertifika|Yay[ıi]n(ev|lar)|Bask[ıi]|©|Copyright|Matbaa|T[üu]m haklar[ıi]|"
                   r"Genel Yay[ıi]n Y[öo]netmeni|Edit[öo]r|[ÇC]eviren|Kapak Tasar|Redaksiyon|Sayfa Tasar|Düzelti",
                   re.I)
ROLE_WORD = re.compile(r"(Edit[öo]r|[ÇC]eviren|[ÇC]evirmen|Kapak|Tasar[ıi]m|Redakt|Redaksiyon|Düzelti|Resimleyen|"
                       r"[ÇC]izer|[ÇC]izen|Görsel Yönetmen|Yay[ıi]n Y[öo]netmeni)", re.I)
#: Künye sayfası: bu kadar künye sözcüğü (ISBN, baskı, yayınevi, ©…) taşıyan sayfa.
KUNYE_PAGE_HITS = 3
#: Bölüm adında künye: yalnız künyeye özgü sözcükler («Editörün Notu», «Yayınevinden» bölüm adı olabilir).
CHAPTER_IMPRINT = re.compile(r"ISBN|©|Copyright|Matbaa|Sertifika|T[üu]m haklar[ıi]|Genel Yay[ıi]n Y[öo]netmeni|"
                             r"Kapak Tasar|Sayfa Tasar|\b\d+\.\s*[Bb]ask[ıi]\b", re.I)
_SPACED = re.compile(r"(?:\b[^\W\d_]\s){3,}[^\W\d_]\b")
_MID_START = re.compile(r"^[a-zçğıöşüâîû]")
#: Satır sonunda bölünmüş kelime («sahne- nin»): yalnız akan metinde olur, başlıkta olmaz.
_HYPHENATED = re.compile(r"[a-zçğıöşüâîû]-\s+[a-zçğıöşüâîû]")
_MID_END = re.compile(r"(,|;|\s(ve|ile|ama|fakat|ki|de|da|ya|veya))$", re.I)


def chapter_title_problems(title: str, imprint_names: list[str] = (), *, lower_ok: bool = False) -> list[str]:
    """Bir bölüm adının sorunları: 'imprint' (künyeye özgü sözcük ya da adın kendisi künyedeki kişinin adı: imza
    satırı), 'spaced' (harf aralıklı dizilmiş: «K İ T A P»), 'midsentence' (virgül/bağlaçla bitiyor, satır sonunda
    bölünmüş kelime taşıyor, cümle kadar uzun ya da — `lower_ok` değilse — küçük harfle başlıyor). Salt hesap."""
    t = (title or "").strip()
    out = []
    if not t:
        return out
    if CHAPTER_IMPRINT.search(t) or any(n and len(fold(n)) >= 5 and fold(n) == fold(t) for n in imprint_names):
        out.append("imprint")
    if _SPACED.search(t):
        out.append("spaced")
    if (_MID_START.match(t) and not lower_ok) or _MID_END.search(t) or _HYPHENATED.search(t) \
            or len(t) > TITLE_MAX_CHARS:
        out.append("midsentence")
    return out


def imprint_people(characters: list[dict], texts: dict[int, str], kunye_pages: set[int],
                   people: list[str]) -> list[str]:
    """Künye kişisi karakter sayılmış mı: adı künye sayfasında bir görev sözcüğünün («Editör», «Çeviren», «Kapak
    Tasarımı») yanında ya da künyenin yazar/çizer/çevirmen iddiasıyla aynı, ve künye sayfaları dışında en çok
    `IMPRINT_PERSON_BODY_PAGES` sayfada anılıyor. `characters`: {'name', 'pages'}. Salt hesap."""
    keys = {fold(p) for p in people if p and len(fold(p)) >= 5}
    out = []
    for ch in characters:
        name = ch.get("name") or ""
        k = fold(name)
        if len(k) < 5:
            continue
        body = {p for p in ch.get("pages") or () if p not in kunye_pages}
        if len(body) > IMPRINT_PERSON_BODY_PAGES:
            continue
        hit = k in keys
        if not hit:
            for p in kunye_pages:
                t = texts.get(p) or ""
                for m in re.finditer(re.escape(name), t):
                    if ROLE_WORD.search(t[max(0, m.start() - 40):m.end() + 5]):
                        hit = True
                        break
                if hit:
                    break
        if hit:
            out.append(name)
    return out


def kunye_hits(text: str) -> int:
    """Sayfadaki FARKLI künye sözcüğü sayısı (önsözde üç kez «… Yayınları» geçmesi künye yapmaz)."""
    return len({fold(m.group(0))[:6] for m in KUNYE.finditer(text or "")})


def kunye_pages_of(texts: dict[int, str], out_of_scope: set[int], last_page: int) -> set[int]:
    """Künye sayfaları: kapsam dışı sayfalar + kitabın ön/arka penceresinde en az `KUNYE_PAGE_HITS` farklı künye
    sözcüğü taşıyan sayfalar (gövdedeki kaynakça notu «… Yayınları, 2. baskı» künye değildir)."""
    from . import page_scope
    front_end, back_start = page_scope.edge_windows(last_page or max(texts, default=0))
    return set(out_of_scope) | {p for p, t in texts.items() if (p <= front_end or p >= back_start)
                                and kunye_hits(t) >= KUNYE_PAGE_HITS}


# ------------------------------------------------------------------ K20–K23 tespitleri
# Düzeltmeleri chapters / page_scope / archive'de ayrı bir işte yazılıyor; o modüller saf tespit fonksiyonunu
# verdiğinde (`HOOKS`: modül, ad) denetim onu kullanır, yoksa buradaki basit kural koşar. Bağlama tek yer burası.
HOOKS = {"production_note": ("chapters", "production_note"),
         "body_sentence_chapters": ("chapters", "body_sentence_chapters"),
         "bio_sentence": ("page_scope", "bio_sentence")}


def _hook(name: str):
    mod, attr = HOOKS[name]
    try:
        import importlib
        return getattr(importlib.import_module(f"editor.{mod}"), attr, None)
    except Exception:  # noqa: BLE001
        return None


#: K20: baskı/üretim notu (kesim, ebat, pencere/kapak içi talimatı) bölüm adına girmiş.
_PRODUCTION = re.compile(r"\bB[IıI]ÇAK\b|\bEBAT\s*:|\b\d+\s*[xX×]\s*\d+\s*(cm|mm)?\b|Pencere aç[ıi]ld[ıi][ğg][ıi]nda|"
                         r"i[çc]ine bask[ıi]|kapak i[çc]i|kesim [çc]izgisi|bindirme|\bCMYK\b|\bPANTONE\b|\bDPI\b", re.I)
#: K20: kitabın dilinde olmayan satır (yabancı dilin işlev sözcükleri; Türkçe kitapta ≥ 4 kelimelik başlıkta pay).
_FOREIGN = frozenset({"der", "die", "das", "und", "ist", "sich", "ein", "eine", "wo", "was", "wie", "nicht", "mit",
                      "the", "and", "of", "is", "are", "where", "what", "with", "le", "la", "les", "et", "est", "du"})
FOREIGN_SHARE = 0.3


def production_note(title: str) -> bool:
    """K20 (saf): bölüm adı baskı/üretim notu ya da yabancı dilde uzun satır."""
    fn = _hook("production_note")
    if fn is not None:
        return bool(fn(title))
    t = (title or "").strip()
    if not t:
        return False
    if _PRODUCTION.search(t):
        return True
    words = re.findall(r"[^\W\d_]+", t.casefold())
    return len(words) >= 4 and sum(1 for w in words if w in _FOREIGN) >= FOREIGN_SHARE * len(words)


#: K21: resimli (kısa) kitap ve bölüm sayısı; cümle biçimli başlık payı.
PICTURE_BOOK_PAGES = 48
BODY_SENTENCE_MIN_CHAPTERS = 4
BODY_SENTENCE_SHARE = 0.5
_VERB_END = re.compile(r"(d[ıiuü]|t[ıiuü]|m[ıiuü]ş|yor|ecek|acak|d[ıiuü]l[ae]r|di[kn]|du[kn])[.!?…,]*$", re.I)


def _sentence_title(t: str) -> bool:
    words = t.split()
    return len(words) >= 4 and ("," in t or bool(_VERB_END.search(t)) or t.rstrip()[-1:] in ".!?…")


def body_sentence_chapters(chapters: list[dict], pages_n: int) -> bool:
    """K21 (saf): kısa resimli kitapta çok sayıda bölüm ve başlıkların en az yarısı virgüllü/fiilli cümle parçası."""
    fn = _hook("body_sentence_chapters")
    if fn is not None:
        return bool(fn(chapters, pages_n))
    if not pages_n or pages_n > PICTURE_BOOK_PAGES or len(chapters) < BODY_SENTENCE_MIN_CHAPTERS:
        return False
    n = sum(1 for c in chapters if _sentence_title((c.get("title") or "").strip()))
    return n >= BODY_SENTENCE_SHARE * len(chapters)


_BIO = re.compile(r"\b(do[ğg](du|mu[şs])|d[üu]nyaya gel(di|mi[şs])|mezun ol(du|mu[şs])|[öo][ğg]renimini|"
                  r"e[ğg]itimini .{0,60}tamamla(d[ıi]|m[ıi][şs])|y[ıi]l[ıi]nda .{0,40}(do[ğg]|vefat))", re.I)


def bio_sentence(text: str) -> bool:
    """K22 (saf): cümle yazar özgeçmişi gibi («… doğmuş, … mezun olmuş»)."""
    fn = _hook("bio_sentence")
    if fn is not None:
        return bool(fn(text))
    return bool(_BIO.search(text or ""))


def duplicate_books(c, book_id: str, title: str | None, pages: int | None) -> list[dict]:
    """K23: aynı adla (Türkçe harf/büyük-küçük farkı gözetmeden) ve ±2 sayfa içinde başka bir kitap kaydı okunmuş mu
    (kopya dosya). Ad taşımayan ad («Kitap») sayılmaz. Salt okuma."""
    key = fold(title)
    if len(key) < 4 or key in ("kitap", "adsiz") or not pages:
        return []
    rows = c.execute("SELECT DISTINCT b.id::text AS id, b.title, bv.page_count FROM ed.book b JOIN ed.book_version bv"
                     " ON bv.book_id=b.id JOIN ed.generation g ON g.book_version_id=bv.id WHERE b.id::text<>%s AND"
                     " lower(b.title)=lower(%s) AND abs(coalesce(bv.page_count,0)-%s)<=2", (book_id, title, pages)
                     ).fetchall()
    return [{"book_id": r["id"], "pages": r["page_count"]} for r in rows if fold(r["title"]) == key]


# ------------------------------------------------------------------ bulgular
#: Bulgu sınıfı → (önem, ekrandaki ad, düzeltme eylemi ya da None). Önem: critical | warn | info. info hiçbir zaman
#: «Gözden geçir»e düşürmez (bilgi; künyenin dizi adı gibi okurken zaten düzeltilen işaretler).
CLASSES: dict[str, tuple[str, str, str | None]] = {
    "outputs_missing": ("critical", "Kitabın özeti, kartı ve raporu kurulmamış", "outputs"),
    "step_failed": ("critical", "Okumanın bir adımı yarıda kaldı", None),        # eylem adıma göre (STEP_FIX)
    "characters_zero": ("critical", "Anlatı kitabında hiç karakter kaydı yok", "identity"),
    "proofing_incomplete": ("critical", "Son okuma denetimleri eksik", "proofreading"),
    "pages_unread": ("critical", "Okunamayan sayfalar var", "reread"),
    "text_garbled": ("warn", "Metinde bozuk karakter oranı yüksek", "reread"),
    "metadata_missing": ("warn", "Künyede yazar yok", "metadata"),
    "metadata_author_elsewhere": ("info", "Künyede yazar yok (çizer/çevirmen ya da kitap kaydında kişi var)", None),
    "metadata_publisher_missing": ("info", "Künyede yayınevi yok", None),
    "metadata_isbn_missing": ("info", "Künyede ISBN yok", None),
    "metadata_flagged": ("info", "Künyedeki bir ad dizi adı ya da kişi adı (okurken düzeltildi)", None),
    "summary_missing": ("warn", "Kitabın özeti yok", "outputs"),
    "summary_fallback": ("warn", "Özet yazılamadı; doğrulanmış kayıtlardan derlendi", "outputs"),
    "summary_front_matter": ("warn", "Özet kitap dışı bir sayfayla (ithaf, önsöz, tanıtım) başlıyor", "scope"),
    "scope_stale": ("warn", "Kitap dışı sayfaların işareti güncel değil", "scope"),
    "chapters_single": ("warn", "Uzun kitapta tek bölüm bulundu", "outputs"),
    "chapters_repeated": ("warn", "Aynı bölüm adı birçok kez", "outputs"),
    "chapters_imprint": ("warn", "Bölüm adına künye ya da imza karışmış", "outputs"),
    "chapters_spaced": ("warn", "Bölüm adı harf aralıklı yazılmış", "outputs"),
    "chapters_midsentence": ("warn", "Bölüm adı cümle ortasından alınmış", "outputs"),
    # K20–K23 (2026-10-06, 44 arşiv kitabı): düzeltmesi chapters/page_scope/archive'de ayrı işte; burada tespit
    "chapters_production_note": ("warn", "Bölüm adında baskı/üretim notu ya da kitabın dilinde olmayan satır", "outputs"),
    "chapters_body_sentence": ("warn", "Resimli kitapta gövde cümleleri bölüm adı olmuş", "outputs"),
    "summary_author_bio": ("warn", "Özet yazar özgeçmişiyle başlıyor", "scope"),
    "duplicate_book_record": ("warn", "Aynı kitap iki ayrı kayıtla okunmuş (kopya dosya)", None),
    "summary_no_facts": ("warn", "Özet ve olay yok, ama dosya «kitap değil» diye de işaretlenmemiş", None),
    "characters_duplicate": ("warn", "Aynı adla birden çok karakter kaydı", "fold"),
    "characters_out_of_scope": ("warn", "Yalnız kitap dışı sayfalarda geçen karakter", "scope"),
    "characters_imprint_person": ("warn", "Künyedeki bir kişi karakter sayılmış", "scope"),
    "events_out_of_scope": ("warn", "Kitap dışı sayfadan olay", "scope"),
    "events_on_imprint_page": ("warn", "Künye sayfasından olay", "scope"),
    "recommendation_missing": ("warn", "Kategori ve yaş önerisi yok", "recommend"),
    "recommendation_not_a_book": ("warn", "Kitap olmayan dosyaya kategori/yaş önerisi yapılmış", None),
    "recommendation_conflict": ("warn", "Öneri kitabın kayıtlı okur kitlesiyle çelişiyor", None),
    "index_empty": ("critical", "Arama dizini boş", "reindex"),
    "ask_failed": ("warn", "«Zeki'ye sor» denemesi kitabın kendi kaydını bulamadı", None),
}

#: Düşen adım → düzeltme eylemi. Adı geçmeyen adım insana kalır.
STEP_FIX = {"identity": "identity", "proofreading": "proofreading", "proofreading_checks": "proofreading",
            "identity_fold": "fold", "deep_scan": "rescan", "key_event_scan": "rescan", "fast_scan": "rescan",
            "book_metadata": "metadata", "recommend": "recommend", "ocr": "reread", "extract": "reread",
            "chapter_summary": "outputs", "catalog_card": "outputs"}
STEP_TR = {"identity": "karakter kimlikleri", "proofreading": "son okuma denetimleri",
           "proofreading_checks": "son okuma denetimlerinin bir kısmı", "identity_fold": "kişi kayıtlarının birleştirilmesi",
           "deep_scan": "derin görsel inceleme", "key_event_scan": "önemli olay sayfalarının görsel incelemesi",
           "fast_scan": "hızlı görsel tarama", "book_metadata": "künye", "recommend": "kategori ve yaş önerisi",
           "ocr": "sayfa metni okuma", "extract": "karakter ve olay adayları", "chapter_summary": "bölüm özetleri",
           "catalog_card": "katalog kartı", "outputs": "özet ve kart", "visual_identity": "görsel kimlik"}
#: Kitap sayfaları taranarak düzeltilen adımlar (failures listesindeki sayfa numaraları).
RESCAN_DEPTH = {"deep_scan": ("deep", None), "key_event_scan": ("deep", ["IMPORTANT_EVENT"]), "fast_scan": ("fast", None)}
#: Okumayı yeniden yapmayı gerektiren eylem; kitap sürümü başına en çok bir kez.
REREAD = "reread"
#: Çıktıları yeniden kuran eylemler (bir turda tek kurulum, sonda).
KNOWLEDGE_ACTIONS = frozenset({"identity", "fold", "proofreading", "rescan", "metadata", "scope"})


def finding(code: str, detail: dict | None = None, *, title: str | None = None, fix: str | None = None,
            key: str | None = None) -> dict:
    sev, name, default_fix = CLASSES[code]
    return {"code": code, "key": key or code, "severity": sev, "title": title or name,
            "fix": fix if fix is not None else default_fix, "detail": detail or {}}


def _failed_pages(items) -> list[int]:
    out = []
    for x in items or []:
        if isinstance(x, dict) and isinstance(x.get("failed"), int):
            out.append(x["failed"])
    return sorted(set(out))


def evaluate(f: dict) -> list[dict]:
    """Bulgular (salt hesap). `f`: `gather`'ın topladığı olgular. Sıra: ekranda gösterim sırası."""
    out: list[dict] = []
    book = not f.get("not_a_book")
    # anlatı: türü kurgu ya da anlatı kurgu dışı diye belirlenmiş kitap (türü bilinmeyen kavram/etkinlik kitabında
    # karakter olmaması kusur değildir)
    story = book and f.get("form") in NARRATIVE_FORMS
    # 1. adım düşmesi
    for step, items in sorted((f.get("failures") or {}).items()):
        if not items or step == "quality_audit":
            continue
        pages = _failed_pages(items) if step in RESCAN_DEPTH or step == "ocr" else []
        name = STEP_TR.get(step, step.replace("_", " "))
        detail = {"step": step, "pages": pages[:50]} if pages else {"step": step}
        sev = "critical" if step in ("identity", "proofreading", "extract", "identity_fold") else "warn"
        x = finding("step_failed", detail, title=f"Okumanın bir adımı yarıda kaldı: {name}"
                    + (f" ({len(pages)} sayfa)" if pages else ""), fix=STEP_FIX.get(step, ""), key=f"step:{step}")
        x["severity"] = sev
        out.append(x)
    if not f.get("snapshot"):
        out.append(finding("outputs_missing"))
        return out
    # 2. karakter 0
    if story and f.get("characters_n", 0) == 0:
        unresolved = f.get("unresolved_mentions", 0)
        out.append(finding("characters_zero", {"unresolved_mentions": unresolved},
                           fix="identity" if unresolved else ""))
    # 3. son okuma denetimleri
    proof = f.get("proof")
    if proof and proof.get("expected") and proof["recorded"] < proof["total"]:
        out.append(finding("proofing_incomplete", {"recorded": proof["recorded"], "total": proof["total"],
                                                   "missing": proof.get("missing", [])[:20]},
                           title=f"Son okuma denetimleri eksik ({proof['recorded']}/{proof['total']})"))
    # 4. metin
    pages_n = f.get("pages_n") or 0
    unread = f.get("unread_pages") or []
    if pages_n and len(unread) >= UNREAD_MIN and len(unread) >= UNREAD_SHARE * pages_n:
        out.append(finding("pages_unread", {"pages": unread[:50], "of": pages_n},
                           title=f"Okunamayan sayfalar var ({len(unread)}/{pages_n})"))
    ts = f.get("text") or {}
    if ts.get("words", 0) >= GARBLE_MIN_WORDS and (ts.get("bad_per_10k", 0) >= GARBLE_PER_10K
                                                    or ts.get("vowelless_pct", 0) >= VOWELLESS_PCT):
        # aynı kodla yeniden okumak aynı metni verir: yeniden okuma yalnız okuma eski kodla yapıldıysa
        out.append(finding("text_garbled", {k: ts.get(k) for k in ("bad_per_10k", "vowelless_pct", "words")},
                           fix="reread" if f.get("read_code") and f.get("read_code") != f.get("code_now") else ""))
    # 5. künye
    if book:
        meta = f.get("metadata") or {}
        missing = [k for k in ("AUTHOR", "PUBLISHER") if not meta.get(k)]
        if "AUTHOR" in missing:
            if f.get("people_elsewhere"):
                out.append(finding("metadata_author_elsewhere"))
            else:
                out.append(finding("metadata_missing", {"fields": ["AUTHOR"]},
                                   fix="metadata" if f.get("metadata_refill_possible") else ""))
        if "PUBLISHER" in missing:
            out.append(finding("metadata_publisher_missing"))
        if not meta.get("ISBN"):
            out.append(finding("metadata_isbn_missing"))
        if f.get("metadata_flags"):
            out.append(finding("metadata_flagged", {"flags": f["metadata_flags"][:10]}))
    # 6. özet
    summ = f.get("summary") or {}
    if book and f.get("events_n", 0) and not summ.get("n"):
        out.append(finding("summary_missing", {"status": summ.get("status")}))
    if summ.get("status") == "EXTRACTIVE_FALLBACK":
        out.append(finding("summary_fallback"))
    if book and summ.get("status") == "NO_VERIFIED_FACTS" and not f.get("events_n"):
        out.append(finding("summary_no_facts"))
    if summ.get("first_text") and bio_sentence(summ["first_text"]) and not summ.get("first_front_kind"):
        out.append(finding("summary_author_bio", {"pages": summ.get("first_pages")}))
    if summ.get("first_front_kind"):
        out.append(finding("summary_front_matter", {"pages": summ.get("first_pages"), "kind": summ["first_front_kind"]},
                           title=f"Özet kitap dışı bir sayfayla ({summ['first_front_kind']}) başlıyor"))
    if f.get("scope_writes"):
        out.append(finding("scope_stale", {"pages": f["scope_writes"][:50]}))
    # 7. bölümler
    chs = f.get("chapters") or []
    if book and len(chs) == 1 and fold(chs[0].get("title")) == "kitap" and pages_n >= LONG_BOOK_PAGES:
        out.append(finding("chapters_single", {"pages": pages_n}))
    counts = collections.Counter(fold(c.get("title")) for c in chs if fold(c.get("title")))
    rep = {k: n for k, n in counts.items() if n >= REPEATED_TITLE_MIN}
    if rep:
        first = {fold(c.get("title")): c.get("title") for c in chs}
        out.append(finding("chapters_repeated", {"titles": [{"title": first[k], "times": n} for k, n in rep.items()][:5]},
                           title="Aynı bölüm adı birçok kez: " + ", ".join(f"«{first[k]}» ×{n}" for k, n in
                                                                           list(rep.items())[:3])))
    probs: dict[str, list] = collections.defaultdict(list)
    lower = sum(1 for c in chs if _MID_START.match((c.get("title") or "").strip()))
    lower_ok = bool(chs) and lower > LOWER_START_MAX_SHARE * len(chs)
    for c in chs:
        for p in chapter_title_problems(c.get("title") or "", f.get("imprint_names") or [], lower_ok=lower_ok):
            probs[p].append({"title": (c.get("title") or "")[:80], "page": c.get("page_from")})
    for c in chs:
        if production_note(c.get("title") or ""):
            probs["production"].append({"title": (c.get("title") or "")[:80], "page": c.get("page_from")})
    for p, code in (("imprint", "chapters_imprint"), ("spaced", "chapters_spaced"),
                    ("midsentence", "chapters_midsentence"), ("production", "chapters_production_note")):
        if probs.get(p):
            out.append(finding(code, {"chapters": probs[p][:5], "count": len(probs[p])}))
    if book and body_sentence_chapters(chs, pages_n):
        out.append(finding("chapters_body_sentence", {"count": len(chs), "pages_n": pages_n},
                           title=f"Resimli kitapta gövde cümleleri bölüm adı olmuş ({len(chs)} bölüm, {pages_n} sayfa)"))
    if f.get("duplicate_books"):
        out.append(finding("duplicate_book_record", {"books": f["duplicate_books"][:5]}))
    # 8. karakterler
    if f.get("duplicate_names"):
        out.append(finding("characters_duplicate", {"names": f["duplicate_names"][:10]},
                           title="Aynı adla birden çok karakter kaydı: " + ", ".join(f["duplicate_names"][:3])))
    if f.get("characters_out_of_scope"):
        out.append(finding("characters_out_of_scope", {"names": f["characters_out_of_scope"][:10]}))
    if f.get("imprint_people"):
        out.append(finding("characters_imprint_person", {"names": f["imprint_people"][:10]},
                           title="Künyedeki kişi karakter sayılmış: " + ", ".join(f["imprint_people"][:3])))
    # 9. olaylar
    if f.get("events_out_of_scope"):
        out.append(finding("events_out_of_scope", {"pages": f["events_out_of_scope"][:20]}))
    if f.get("events_on_imprint"):
        out.append(finding("events_on_imprint_page", {"pages": f["events_on_imprint"][:20]}))
    # 10. öneri
    rec = f.get("recommendation")
    if not book and rec and rec.get("status") == "OK":
        out.append(finding("recommendation_not_a_book"))
    elif book and f.get("recommend_expected") and (not rec or rec.get("status") != "OK"):
        out.append(finding("recommendation_missing", {"status": (rec or {}).get("status")}))
    elif book and rec and rec.get("status") == "OK" and f.get("audience_trusted"):
        a, b = f["audience_trusted"], rec.get("audience")
        if a and b and {a, b} == {"CHILD", "ADULT"}:
            out.append(finding("recommendation_conflict", {"book": a, "suggested": b}))
    # 11. dizin
    idx = f.get("index") or {}
    if idx.get("expected") and idx.get("count") == 0:
        out.append(finding("index_empty", {"build_key": (idx.get("build_key") or "")[:12]}))
    # 12. Zeki'ye sor
    for q in (f.get("ask") or {}).get("questions") or []:
        if q.get("ok") is False:
            out.append(finding("ask_failed", {"question": q.get("kind"), "why": q.get("why")},
                               key=f"ask:{q.get('kind')}",
                               title="«Zeki'ye sor» denemesi: " + {"main": "ana karakter/konu",
                                                                  "event": "kayıtlı olayın sayfası"}.get(
                                   q.get("kind"), q.get("kind") or "") + " bulunamadı"))
    return out


def blocking(findings: list[dict]) -> list[dict]:
    """«Gözden geçir»e düşüren bulgular (critical/warn)."""
    return [x for x in findings if x["severity"] in ("critical", "warn")]


def plan_fixes(findings: list[dict], tried: set[str], *, rebuild_effective: bool = True,
               reread_allowed: bool = True) -> list[str]:
    """Bu turda uygulanacak eylemler, sırayla. Daha önce denenmiş eylem (bu koşuda ya da önceki kayıtta) yeniden
    seçilmez; `outputs` yalnız etkiliyse (kurulum kuralı değiştiyse ya da bilgi değiştiyse) seçilir. Yeniden okuma
    gerekiyorsa başka eylem yapılmaz (yeni okuma her şeyi yeniden kurar)."""
    acts = []
    for x in blocking(findings):
        a = x.get("fix")
        if a and a not in acts and a not in tried:
            acts.append(a)
    if REREAD in acts:
        return [REREAD] if reread_allowed else [a for a in acts if a != REREAD]
    if "outputs" in acts and not rebuild_effective:
        acts.remove("outputs")
    order = ("identity", "fold", "rescan", "proofreading", "metadata", "scope", "recommend", "outputs", "reindex")
    return sorted(acts, key=lambda a: order.index(a) if a in order else len(order))


def status_of(first: list[dict], last: list[dict], fixes: list[dict], reread: bool) -> str:
    if reread:
        return "REREAD"
    if blocking(last):
        return "REVIEW"
    if blocking(first) and any(x.get("ok") for x in fixes):
        return "FIXED"
    return "CLEAN" if not blocking(first) else "FIXED"


# ------------------------------------------------------------------ olgular (salt okuma)
STORY_FORMS = ("FICTION", "NARRATIVE_NONFICTION", "UNKNOWN")
NARRATIVE_FORMS = ("FICTION", "NARRATIVE_NONFICTION")


def _artifact(c, gid: str, kind: str) -> dict | None:
    row = c.execute("SELECT v.content, v.build_key FROM ed.current_artifact a JOIN ed.artifact_version v ON"
                    " v.generation_id=a.generation_id AND v.kind=a.kind AND v.input_digest=a.input_digest"
                    " WHERE a.generation_id=%s AND a.kind=%s ORDER BY v.created_at DESC LIMIT 1", (gid, kind)).fetchone()
    if not row:
        return None
    return {**(row["content"] or {}), "_build_key": row["build_key"]}


JOB_SQL = ("SELECT j.id, j.profile, j.status, j.progress, g.sealed_at, g.code_version, s.origin, bv.book_id,"
           " bv.id AS book_version_id,"
           " bv.page_count, b.title FROM ed.generation g JOIN ed.analysis_job j ON j.id=g.job_id"
           " JOIN ed.book_version bv ON bv.id=g.book_version_id JOIN ed.book b ON b.id=bv.book_id"
           " LEFT JOIN ed.generation_state s ON s.generation_id=g.id WHERE g.id=%s")


def gather(c, gid: str, *, failures: dict | None = None, profile: str | None = None) -> dict:
    """Denetimin olguları, tek salt okunur bağlantıdan. `failures`: iş akışının bellekteki düşen adımları (okuma
    sürerken iş kaydında henüz yok); verilmezse nesli kuran işin ve üstünde koşmuş redaksiyonun kaydından."""
    from . import page_scope
    job = c.execute(JOB_SQL, (gid,)).fetchone()
    if job is None:
        raise KeyError(gid)
    f: dict[str, Any] = {"generation_id": gid, "book_id": str(job["book_id"]), "title": job["title"],
                         "job_id": str(job["id"]), "book_version_id": str(job["book_version_id"]),
                         "profile": profile or job["profile"] or "full", "sealed": job["sealed_at"] is not None,
                         "tracked": job["origin"] == "TRACKED", "read_code": job["code_version"],
                         "code_now": _code_version()}
    red = c.execute("SELECT id, status, progress FROM ed.analysis_job WHERE profile='redaction' AND"
                    " progress->>'generation_id'=%s ORDER BY created_at DESC LIMIT 1", (gid,)).fetchone()
    if failures is None:
        failures = dict(((job["progress"] or {}).get("result") or {}).get("failures") or {})
        if red and red["status"] == "SUCCEEDED":
            for k, v in (((red["progress"] or {}).get("result") or {}).get("failures") or {}).items():
                failures.setdefault(k, v)
    f["failures"] = {k: v for k, v in (failures or {}).items() if v}
    prof = c.execute("SELECT form, audience, audience_source FROM ed.book_profile WHERE generation_id=%s",
                     (gid,)).fetchone() or {}
    f["form"] = prof.get("form")
    f["not_a_book"] = prof.get("form") == "NOT_A_BOOK"
    f["audience_trusted"] = prof.get("audience") if prof.get("audience_source") in ("CRM", "EDITOR") else None
    # çıktıların donmuş girdisi: güncel raporun bilgi görüntüsü
    rep = c.execute("SELECT a.input_revision, a.input_digest FROM ed.current_artifact a WHERE a.generation_id=%s"
                    " AND a.kind='report'", (gid,)).fetchone()
    snap = None
    if rep:
        row = c.execute("SELECT content FROM ed.knowledge_snapshot WHERE generation_id=%s AND revision=%s AND"
                        " input_digest=%s", (gid, rep["input_revision"], rep["input_digest"])).fetchone()
        snap = (row or {}).get("content")
    f["snapshot"] = snap is not None
    f["pages_n"] = job["page_count"] or 0
    unresolved = c.execute("SELECT count(*) AS n FROM ed.character_mention WHERE generation_id=%s AND character_id"
                           " IS NULL AND via IN ('TEXT','BOTH')", (gid,)).fetchone()["n"]
    f["unresolved_mentions"] = unresolved
    # son okuma denetimleri: tam okumada ve redaksiyonu koşmuş arşivde beklenir
    expected = f["profile"] in ("full", "redaction") or (red is not None and red["status"] == "SUCCEEDED")
    if expected:
        from . import proofing
        versions = {n: str(m.VERSION) for n, m in proofing.checks().items()}
        runs = c.execute("SELECT DISTINCT check_name, check_version FROM ed.proof_run WHERE generation_id=%s"
                         " AND status='SUCCEEDED'", (gid,)).fetchall()
        have = {r["check_name"] for r in runs if versions.get(r["check_name"]) == r["check_version"]}
        f["proof"] = {"expected": True, "recorded": len(have), "total": len(versions),
                      "missing": sorted(set(versions) - have)}
    rec = c.execute("SELECT status, audience, age_from, age_to FROM ed.book_recommendation WHERE generation_id=%s",
                    (gid,)).fetchone()
    f["recommendation"] = dict(rec) if rec else None
    f["duplicate_books"] = duplicate_books(c, f["book_id"], job["title"], job["page_count"])
    f["recommend_expected"] = True
    if snap is None:
        return f
    f["snap_code"] = snap.get("code_version")
    f["revision"] = snap.get("revision")
    pages = snap.get("sources") or []
    f["pages_n"] = max(f["pages_n"], len(pages))
    lines = {p["page_no"]: [s["text"] for s in p.get("spans") or [] if s.get("role") != "RUNNING_HEAD"]
             for p in pages}
    texts = {p: "\n".join(ls) for p, ls in lines.items()}
    f["unread_pages"] = sorted(p["page_no"] for p in pages if UNREAD_ISSUES & set(p.get("issues") or ()))
    for x in _failed_pages((f["failures"] or {}).get("ocr")):
        if x not in f["unread_pages"]:
            f["unread_pages"].append(x)
    f["unread_pages"].sort()
    f["text"] = text_stats(list(texts.values()))
    oos = set((snap.get("scope") or {}).get("out_of_scope_pages") or [])
    kunye = kunye_pages_of(texts, oos, f["pages_n"])
    # künye (doğrulanmış iddialar, kartın okuduğu gibi gözden geçirilmiş)
    from . import read_model
    meta_rows = [cl for cl in snap.get("claims") or [] if cl.get("kind") == "METADATA"]
    reviewed = read_model.reviewed_metadata(c, f["book_id"], job["title"] or "", meta_rows)
    meta: dict[str, list[str]] = {}
    for m in reviewed:
        meta.setdefault(m.get("subject"), []).append(m.get("claim") or "")
    f["metadata"] = {k: v[0][:80] for k, v in meta.items() if v and v[0]}
    f["metadata_flags"] = [m.get("flag") for m in reviewed if m.get("flag")]
    crm = c.execute("SELECT authors FROM ed.book_crm_record WHERE book_id=%s", (f["book_id"],)).fetchone() or {}
    f["people_elsewhere"] = bool(meta.get("ILLUSTRATOR") or meta.get("TRANSLATOR") or crm.get("authors"))
    # eksik alan okuması: künye hiç yoksa ya da kimlik alanı eksik ve ek okuma henüz yapılmamışsa (catalog)
    from . import catalog
    refill = c.execute("SELECT 1 AS x FROM ed.model_call WHERE generation_id=%s AND prompt_name=%s LIMIT 1",
                       (gid, catalog.REFILL_PROMPT)).fetchone()
    f["metadata_refill_possible"] = bool(meta_rows) and refill is None or "book_metadata" in f["failures"]
    imprint_names = [v for k in ("AUTHOR", "ILLUSTRATOR", "TRANSLATOR") for v in meta.get(k, [])]
    f["imprint_names"] = [n for n in imprint_names if n][:10]
    # özet
    bs = _artifact(c, gid, "book_summary") or {}
    sents = bs.get("sentences") or []
    f["summary"] = {"status": bs.get("status"), "n": len(sents)}
    if sents:
        first = sorted(set(sents[0].get("pages") or []))
        f["summary"]["first_pages"] = first[:5]
        f["summary"]["first_front_kind"] = front_kind(first, texts, oos, f["pages_n"], imprint_names)
        f["summary"]["first_text"] = (sents[0].get("text") or "")[:400]
    # bölümler
    f["chapters"] = [{"title": ch.get("title"), "page_from": ch.get("page_from"), "page_to": ch.get("page_to")}
                     for ch in snap.get("chapters") or []]
    # karakterler
    chars = snap.get("characters") or []
    f["characters_n"] = len(chars)
    ids = [str(ch["id"]) for ch in chars]
    ment: dict[str, set] = collections.defaultdict(set)
    if ids:
        for r in c.execute("SELECT character_id::text AS cid, page_no FROM ed.character_mention WHERE generation_id=%s"
                           " AND character_id::text = ANY(%s)", (gid, ids)).fetchall():
            ment[r["cid"]].add(r["page_no"])
    from .identity_links import is_unnamed
    by = collections.defaultdict(list)
    for ch in chars:
        # adsız kayıt («Postacı», «Annesi», «Hizmetçi») aynı etiketle birden çok kişidir; yalnız adlar sayılır
        if not is_unnamed(ch["canonical_name"], ch.get("traits")):
            by[fold(ch["canonical_name"])].append(ch["canonical_name"])
    f["duplicate_names"] = sorted(v[0] for k, v in by.items() if k and len(v) > 1)
    f["characters_out_of_scope"] = sorted(ch["canonical_name"] for ch in chars
                                          if ment.get(str(ch["id"])) and oos and ment[str(ch["id"])] <= oos)
    people = imprint_names + [p for k in ("EDITOR",) for p in meta.get(k, [])]
    f["imprint_people"] = imprint_people([{"name": ch["canonical_name"], "pages": ment.get(str(ch["id"]), set())}
                                          for ch in chars], texts, kunye, people) if kunye else []
    # olaylar
    evs = snap.get("events") or []
    f["events_n"] = len(evs)
    f["events_out_of_scope"] = sorted({e["page_from"] for e in evs if e.get("page_from") in oos})
    f["events_on_imprint"] = sorted({e["page_from"] for e in evs if e.get("page_from") in kunye - oos})
    # sayfa kapsamı kuralı güncel mi (bölümler görüntüden: PDF açılmaz)
    if f["tracked"] and not f["sealed"]:
        try:
            plan_ = page_scope.plan(c, gid, sections=snap.get("chapters") or [])
            f["scope_writes"] = sorted(plan_["writes"])
        except Exception as e:  # noqa: BLE001 — kural okunamazsa bu kontrol atlanır
            f["scope_error"] = f"{type(e).__name__}: {e}"[:200]
    # arama dizini (sayım `index_count` ile, zaman uyumsuz)
    si = _artifact(c, gid, "search_index")
    f["index"] = {"expected": bool(si), "build_key": (si or {}).get("build_key") or (si or {}).get("_build_key"),
                  "indexed": (si or {}).get("indexed")}
    return f


def front_kind(pages: list[int], texts: dict[int, str], oos: set[int], last_page: int,
               names: list[str] = ()) -> str | None:
    """Özetin ilk cümlesinin dayandığı sayfalar kitap dışı mı: hepsi kapsam dışı işaretli ya da (ön/arka pencerede)
    metni ithaf, epigraf, yazar özgeçmişi, yayınevi/yazar notu ya da teşekkür kuralına uyuyor. Salt hesap."""
    if not pages:
        return None
    if oos and set(pages) <= oos:
        return "kitap dışı sayfa"
    from . import page_scope
    front_end, back_start = page_scope.edge_windows(last_page or max(pages))
    kinds = []
    for p in pages:
        if not (p <= front_end or p >= back_start):
            return None
        lines = [x for x in (texts.get(p) or "").split("\n") if x.strip()]
        if not lines:
            return None
        k = page_scope.front_page_kind(lines, before_body=p <= front_end)
        if not k and page_scope.is_author_bio(lines, list(names)):
            k = "yazar tanıtımı"
        if not k and (page_scope.is_publisher_note(lines) or page_scope.is_author_note(lines)):
            k = "yayınevi/yazar notu"
        if not k and page_scope.is_acknowledgement(lines):
            k = "teşekkür"
        if not k:
            return None
        kinds.append(k)
    return kinds[0]


async def index_count(f: dict) -> None:
    """Güncel dizin anahtarının nokta sayısı `f['index']['count']`'a (dizin okunamazsa sayılmaz)."""
    idx = f.get("index") or {}
    if not idx.get("expected") or not idx.get("build_key"):
        return
    try:
        from qdrant_client import models

        from . import retrieval
        res = await retrieval.qdrant().count(retrieval.PASSAGES, exact=True, count_filter=models.Filter(must=[
            models.FieldCondition(key="generation_id", match=models.MatchValue(value=f["generation_id"])),
            models.FieldCondition(key="build_key", match=models.MatchValue(value=idx["build_key"]))]))
        idx["count"] = res.count
    except Exception as e:  # noqa: BLE001
        idx["error"] = f"{type(e).__name__}: {e}"[:200]


# ------------------------------------------------------------------ «Zeki'ye sor» duman testi
_CITE = re.compile(r"\[s\.?\s*(\d[\d\s,;–-]*)\]")
_RANGE = re.compile(r"(\d{1,4})(?:\s*[-–]\s*(\d{1,4}))?")


def cited_pages(text: str) -> set[int]:
    """Cevabın [s.N], [s.N–M] ve [s.N, M, K] atıflarındaki sayfalar."""
    out: set[int] = set()
    for body in _CITE.findall(text or ""):
        for a, b in _RANGE.findall(body):
            lo = int(a)
            hi = int(b) if b else lo
            if 0 < hi - lo <= 40:
                out.update(range(lo, hi + 1))
            else:
                out.add(lo)
    return out


#: Anlatıcının kaydı («Ben», «Anlatıcı»): ad değil, cevapta aranmaz.
NARRATOR_LABELS = frozenset({"ben", "anlatici", "biz"})
_NARRATOR = re.compile(r"anlat[ıi]c[ıi]|birinci (tekil )?(şahıs|ağız)", re.I)


def ask_questions(card: dict, story: bool) -> list[dict]:
    """Kitabın kendi kayıtlarından iki soru: ana karakter (anlatı kitabında; yoksa konu) ve kayıtlı bir olayın
    sayfası (kitabın ortasına en yakın olay). Beklenen: ad cevapta geçer / cevabın sayfası olayın sayfasına ±1."""
    qs = []
    chars = [c for c in card.get("characters") or [] if c.get("canonical_name") and not c.get("minor")]
    chars.sort(key=lambda c: -(c.get("mentions") or 0))
    # en çok anılan üç adlı kayıt: hangisini ana karakter sayacağı modelin yorumu; biri cevapta geçmeli
    names = [c["canonical_name"] for c in chars if fold(c["canonical_name"]) not in NARRATOR_LABELS][:3]
    if story and chars:
        qs.append({"kind": "main", "q": "Bu kitabın ana karakteri kim? Kısaca yaz ve sayfasını ver.",
                   "expect_names": names,
                   "narrator": any(fold(c["canonical_name"]) in NARRATOR_LABELS for c in chars[:3])})
    else:
        # özeti olmayan kitapta (kavram kitabı) sayfalı cevap beklenmez; «bulunamadı» denmemesi yeter
        qs.append({"kind": "main", "q": "Bu kitap neyi anlatıyor? Kısaca yaz ve sayfasını ver.",
                   "need_pages": bool(card.get("summary"))})
    evs = [e for e in card.get("key_events") or [] if isinstance(e.get("page_from"), int) and e.get("summary")]
    if evs:
        mid = sorted(e["page_from"] for e in evs)[len(evs) // 2]
        ev = min(evs, key=lambda e: abs(e["page_from"] - mid))
        words = " ".join(str(ev["summary"]).split()[:12])
        qs.append({"kind": "event", "q": f"Kitapta «{words}» olayı hangi sayfada geçiyor?",
                   "expect_pages": [ev["page_from"], ev.get("page_to") or ev["page_from"]]})
    return qs


def judge_answer(q: dict, text: str | None) -> dict:
    """Cevap kaynak sayfa veriyor mu ve beklenenle örtüşüyor mu. Salt hesap."""
    from . import quick_answer
    if text is None:
        return {"ok": None, "why": "model cevap vermedi"}
    t = text.strip()
    pages = cited_pages(t)
    if not t or t.startswith(quick_answer.NOT_FOUND) or quick_answer.DEEPER in t:
        return {"ok": False, "why": "bulunamadı dedi", "pages": sorted(pages)[:10]}
    if not pages and q.get("need_pages", True):
        return {"ok": False, "why": "kaynak sayfa yok"}
    if q.get("expect_names"):
        said = fold(t)
        keys = {fold(w) for n in q["expect_names"] for w in n.split() if len(fold(w)) >= 3}
        told = q.get("narrator") and _NARRATOR.search(t)
        if keys and not told and not any(k in said for k in keys):
            return {"ok": False, "why": "ana karakter adı cevapta yok", "pages": sorted(pages)[:10]}
    if q.get("expect_pages"):
        lo, hi = q["expect_pages"]
        if not any(lo - 1 <= p <= hi + 1 for p in pages):
            return {"ok": False, "why": f"sayfa beklenenle örtüşmüyor (s.{lo})", "pages": sorted(pages)[:10]}
    return {"ok": True, "pages": sorted(pages)[:10]}


async def ask_smoke(gid: str, story: bool) -> dict:
    """İki soru, soru başına tek model çağrısı, arka plan önceliğiyle (etkileşimli başlık yok: okuyucunun sorusu
    önce gelir). Bağlam Zeki'ye sor'un kendi bağlamı (seçili kitap = bu nesil)."""
    from . import foundation, quick_answer, read_model
    with foundation.read_snapshot() as c:
        card = read_model.card(c, (c.execute("SELECT bv.book_id FROM ed.generation g JOIN ed.book_version bv ON"
                                             " bv.id=g.book_version_id WHERE g.id=%s", (gid,)).fetchone() or {})
                                    .get("book_id"))
    if not card or not card.get("available") or card.get("generation_id") != gid:
        return {"skipped": "kitabın güncel kartı bu nesil değil"}
    out = []
    for q in ask_questions(card, story):
        try:
            ctx, books, _ = await quick_answer.context(q["q"], None, generation_id=gid)
            got = await quick_answer._ask(quick_answer.SYSTEM, ctx, f"Seçili kitap: «{card['title']}». Soru: {q['q']}",
                                          None, quick_answer.ANSWER_TOKENS, headers={})
            text = got[0] if got else None
        except Exception as e:  # noqa: BLE001 — model/arama düşerse soru sayılmaz
            text, err = None, f"{type(e).__name__}: {e}"[:200]
        else:
            err = None
        res = {"kind": q["kind"], **judge_answer(q, text)}
        if res.get("ok") is False:
            # neden düştüğü görülsün: beklenen ve cevabın başı (en çok 20 kelime)
            res["expected"] = q.get("expect_names") or q.get("expect_pages")
            res["answer"] = " ".join((text or "").split()[:20])
        if err:
            res["error"] = err
        out.append(res)
    return {"questions": out}


# ------------------------------------------------------------------ düzeltmeler (yazar)
def _snapshot_ref(gid: str) -> tuple[dict, str] | None:
    from . import foundation
    with foundation.read_snapshot() as c:
        rep = c.execute("SELECT a.input_revision, a.input_digest FROM ed.current_artifact a WHERE"
                        " a.generation_id=%s AND a.kind='search_index'", (gid,)).fetchone()
        if not rep:
            return None
        snap = c.execute("SELECT content FROM ed.knowledge_snapshot WHERE generation_id=%s AND revision=%s AND"
                         " input_digest=%s", (gid, rep["input_revision"], rep["input_digest"])).fetchone()
        si = _artifact(c, gid, "search_index") or {}
    if not snap:
        return None
    return snap["content"], si.get("build_key") or si.get("_build_key")


def _scope_apply(gid: str) -> dict:
    """Sayfa kapsamı kuralının bekleyen yazımları (bölümler donmuş görüntüden: PDF açılmaz)."""
    from . import db, foundation, page_scope
    with foundation.read_snapshot() as c:
        rep = c.execute("SELECT a.input_revision, a.input_digest FROM ed.current_artifact a WHERE"
                        " a.generation_id=%s AND a.kind='report'", (gid,)).fetchone()
        chapters = []
        if rep:
            row = c.execute("SELECT content->'chapters' AS ch FROM ed.knowledge_snapshot WHERE generation_id=%s AND"
                            " revision=%s AND input_digest=%s", (gid, rep["input_revision"], rep["input_digest"])).fetchone()
            chapters = (row or {}).get("ch") or []
    with db.tx() as c:
        p = page_scope.plan(c, gid, sections=chapters)
        n = page_scope.apply(c, gid, p["writes"])
    return {"written": n, "pages": sorted(p["writes"])[:50]}


def _last_job_failures(job_id: str) -> dict:
    from . import db
    r = db.one("SELECT progress->'result'->'failures' AS f FROM ed.analysis_job WHERE id=%s", job_id)
    return dict((r or {}).get("f") or {})


async def apply_action(action: str, ctx: dict) -> dict:
    """Bir düzeltme eylemi. `ctx`: generation_id, job_id, profile, failures (bellekteki), cleared (temizlenen
    adımlar buraya eklenir). Dönüş {'action', 'ok', 'changed', …}; hata yükselmez, kayda yazılır."""
    from . import backfill
    gid, profile = ctx["generation_id"], ctx["profile"]
    t0 = time.time()
    out: dict[str, Any] = {"action": action}
    try:
        if action == "identity":
            item = {"generation_id": gid, "job_id": ctx["job_id"], "profile": profile, "steps": ["identity"]}
            res = await backfill.apply_one(item)
            ok = "error" not in (res.get("identity") or {})
            out.update(ok=ok, changed=ok, built=True, detail={"characters": (res.get("identity") or {}).get("characters"),
                                                              "outputs": (res.get("outputs") or {}).get("technical_status")})
            if ok:
                ctx["cleared"].update({"identity"})
        elif action == "proofreading":
            out_, lost, transient = await backfill.proofread(gid, resume=True)
            ok = not transient
            out.update(ok=ok, changed=True, detail={"checks": len(out_), "failed_checks": lost})
            if ok:
                ctx["cleared"].update({"proofreading"} | ({"proofreading_checks"} if not lost else set()))
        elif action == "fold":
            from . import identity_fold
            res = await asyncio.to_thread(identity_fold.run, gid)
            out.update(ok=True, changed=bool(res.get("records_folded")),
                       detail={k: res.get(k) for k in ("characters", "records_folded", "characters_after")})
            ctx["cleared"].add("identity_fold")
        elif action == "rescan":
            from . import vision
            done, failed = [], []
            for step, (depth, reasons) in RESCAN_DEPTH.items():
                for p in _failed_pages(ctx["failures"].get(step)):
                    try:
                        await vision.analyze_page_visual(gid, p, depth, reasons)
                        await asyncio.to_thread(vision.persist_page_visual, gid, p)
                        done.append(p)
                    except Exception as e:  # noqa: BLE001
                        failed.append({"page": p, "error": f"{type(e).__name__}: {e}"[:120]})
                if not failed and ctx["failures"].get(step):
                    ctx["cleared"].add(step)
            out.update(ok=not failed, changed=bool(done), detail={"pages": done[:50], "failed": failed[:10]})
        elif action == "metadata":
            from . import catalog
            meta = await catalog.extract_metadata(gid)
            out.update(ok=True, changed=True, detail={"fields": sorted(meta)})
            ctx["cleared"].add("book_metadata")
        elif action == "scope":
            res = await asyncio.to_thread(_scope_apply, gid)
            out.update(ok=True, changed=bool(res["written"]), detail=res)
        elif action == "recommend":
            from . import recommend
            res = await recommend.run(gid)
            out.update(ok=res.get("status") in ("OK", "NOT_A_BOOK"), changed=True, detail={"status": res.get("status")})
            if out["ok"]:
                ctx["cleared"].add("recommend")
        elif action == "outputs":
            res = await backfill.outputs(gid, profile)
            out.update(ok=res.get("technical_status") in ("SUCCEEDED", "ALREADY_CURRENT", "QUEUED"), changed=False,
                       built=True, detail=res)
            if out["ok"]:
                ctx["cleared"].update({"chapter_summary", "catalog_card"})
        elif action == "reindex":
            ref = await asyncio.to_thread(_snapshot_ref, gid)
            if ref is None or not ref[1]:
                out.update(ok=False, detail={"why": "güncel dizin kaydı yok"})
            else:
                from . import retrieval
                res = await retrieval.embed_snapshot(ref[0], ref[1])
                out.update(ok=True, changed=False, detail={"indexed": res.get("indexed")})
        elif action == REREAD:
            out.update(ok=True, changed=False, detail={"queued": "okuma bitince"})
            ctx["reread"] = True
        else:
            out.update(ok=False, detail={"why": "bilinmeyen eylem"})
    except Exception as e:  # noqa: BLE001 — bir eylemin hatası denetimi durdurmaz
        out.update(ok=False, error=f"{type(e).__name__}: {e}"[:300])
    out["seconds"] = round(time.time() - t0, 1)
    return out


def queue_reread(job_id: str) -> dict:
    """Kitabı aynı kipte yeniden okutur (kalite denetiminin kararı): kitap sürümünde başka QUEUED/RUNNING iş yoksa
    yeni iş; korunan alanlar (`portal_books.CARRIED`) aynen, isteyen aynı (toplu arşiv kuyruğundaki yeri korunur).
    Kitap sürümünde daha önce kalite denetimiyle yeniden okuma açılmışsa açılmaz (en çok bir kez)."""
    from . import db
    from . import portal_books as PB
    r = db.one("SELECT book_version_id, profile, requested_by, progress FROM ed.analysis_job WHERE id=%s", job_id)
    if not r:
        return {"queued": False, "why": "iş yok"}
    if reread_done(str(r["book_version_id"])):
        return {"queued": False, "why": "bu kitap sürümü kalite denetimiyle zaten yeniden okundu"}
    kept = {k: v for k, v in (r.get("progress") or {}).items() if k in PB.CARRIED and k != "generation_id"}
    progress = {**kept, "attempt": 1, "quality_reread_of": str(job_id)}
    job = db.one("INSERT INTO ed.analysis_job(book_version_id, profile, requested_by, progress) SELECT %s,%s,%s,%s"
                 " WHERE NOT EXISTS (SELECT 1 FROM ed.analysis_job WHERE book_version_id=%s AND status IN"
                 " ('QUEUED','RUNNING') AND id<>%s) RETURNING id", r["book_version_id"], r["profile"] or "full",
                 r["requested_by"], db.J(progress), r["book_version_id"], job_id)
    return {"queued": bool(job), "job_id": str(job["id"]) if job else None,
            **({} if job else {"why": "kitap zaten sırada ya da okunuyor"})}


def reread_done(book_version_id: str) -> bool:
    from . import db
    return db.one("SELECT 1 AS x FROM ed.analysis_job WHERE book_version_id=%s AND progress ? 'quality_reread_of'"
                  " LIMIT 1", book_version_id) is not None


def tried_before(gid: str) -> set[str]:
    """Bu nesilde önceki denetimlerin denediği eylemler (aynı eylem aynı nesilde tekrar denenmez)."""
    from . import db
    if not has_table():
        return set()
    rows = db.all_rows("SELECT fixes FROM ed.read_quality_audit WHERE generation_id=%s", gid)
    return {x.get("action") for r in rows for x in (r["fixes"] or []) if x.get("action")}


_HAS_TABLE: dict[str, bool] = {}


def has_table(c=None) -> bool:
    if "v" not in _HAS_TABLE:
        from . import db
        q = "SELECT to_regclass('ed.read_quality_audit') IS NOT NULL AS ok"
        r = c.execute(q).fetchone() if c is not None else db.one(q)
        if not r["ok"]:
            return False
        _HAS_TABLE["v"] = True
    return _HAS_TABLE["v"]


def store(rec: dict) -> int | None:
    from . import db
    if not has_table():
        return None
    row = db.one("INSERT INTO ed.read_quality_audit(generation_id, job_id, book_id, origin, status, rounds, checks,"
                 " findings, remaining, fixes, version, actor, code_version) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                 " RETURNING id", rec["generation_id"], rec.get("job_id"), rec.get("book_id"), rec["origin"],
                 rec["status"], rec["rounds"], db.J(rec["checks"]), db.J(rec["findings"]), db.J(rec["remaining"]),
                 db.J(rec["fixes"]), VERSION, ACTOR, rec.get("code_version"))
    return row["id"] if row else None


def note_job(job_id: str, summary: dict, cleared: list[str]) -> None:
    """İşin progress.result alanına denetim özeti; temizlenen adımlar failures'tan düşer (komut yolu: iş bitmiş)."""
    from . import db
    db.one("UPDATE ed.analysis_job SET progress = jsonb_set(progress, '{result}', (coalesce(progress->'result',"
           " '{}'::jsonb) || jsonb_build_object('quality_audit', %s::jsonb)) || jsonb_build_object('failures',"
           " coalesce(progress->'result'->'failures', '{}'::jsonb) - %s::text[])) WHERE id=%s AND progress ? 'result'"
           " RETURNING id", db.J(summary), list(cleared), job_id)


def checks_view(findings: list[dict]) -> dict:
    names = ("adım", "karakter", "son okuma", "metin", "künye", "özet", "bölüm", "kişi kaydı", "olay", "öneri",
             "dizin", "soru", "kayıt")
    by = {"adım": ("step_failed", "outputs_missing"), "karakter": ("characters_zero",),
          "son okuma": ("proofing_incomplete",), "metin": ("pages_unread", "text_garbled"),
          "künye": ("metadata_missing",), "özet": ("summary_missing", "summary_fallback", "summary_front_matter",
                                         "summary_author_bio", "summary_no_facts"),
          "bölüm": ("chapters_single", "chapters_repeated", "chapters_imprint", "chapters_spaced", "chapters_midsentence",
                    "chapters_production_note", "chapters_body_sentence"),
          "kayıt": ("duplicate_book_record",),
          "kişi kaydı": ("characters_duplicate", "characters_out_of_scope", "characters_imprint_person"),
          "olay": ("events_out_of_scope", "events_on_imprint_page", "scope_stale"),
          "öneri": ("recommendation_missing", "recommendation_not_a_book", "recommendation_conflict"),
          "dizin": ("index_empty",), "soru": ("ask_failed",)}
    bad = {x["code"] for x in blocking(findings)}
    return {n: ("sorun" if bad & set(by[n]) else "tamam") for n in names}


def _code_version() -> str:
    import os
    return os.environ.get("EDITOR_CODE_VERSION", "unknown")


async def _facts(gid: str, failures: dict | None, profile: str | None) -> dict:
    from . import foundation

    def read():
        with foundation.read_snapshot() as c:
            c.execute("SET LOCAL statement_timeout='120s'")
            return gather(c, gid, failures=failures, profile=profile)
    f = await asyncio.to_thread(read)
    await index_count(f)
    return f


def _rebuild_effective(f: dict) -> bool:
    """Çıktıları yeniden kurmak bir şey değiştirir mi: kurulum kuralı (kod sürümü) değişmiş ya da çıktı yok."""
    return not f.get("snapshot") or f.get("snap_code") != _code_version()


async def run(gid: str, *, job_id: str | None = None, profile: str | None = None, failures: dict | None = None,
              fix: bool = False, ask: bool = True, origin: str = "COMMAND", record: bool | None = None) -> dict:
    """Denetim (+ `fix` ise düzeltme turları). `failures` verilirse (iş akışı) iş kaydı yerine o kullanılır ve
    temizlenen adımlar dönüşün `cleared` alanındadır. `record` (varsayılan `fix`): kayıt tablosuna yazılır."""
    record = fix if record is None else record
    failures = dict(failures) if failures is not None else None
    f = await _facts(gid, failures, profile)
    profile = f["profile"]
    job_id = job_id or f["job_id"]
    first = evaluate(f)
    ctx = {"generation_id": gid, "job_id": job_id, "profile": profile, "failures": dict(f["failures"]),
           "cleared": set(), "reread": False}
    fixes: list[dict] = []
    tried = await asyncio.to_thread(tried_before, gid) if fix else set()
    reread_ok = fix and not await asyncio.to_thread(reread_done, f["book_version_id"])
    writable = f.get("tracked") and not f.get("sealed")
    last, rounds = first, 1
    for _ in range(ROUNDS if fix and writable else 0):
        acts = plan_fixes(last, tried, rebuild_effective=_rebuild_effective(f), reread_allowed=reread_ok)
        if not acts:
            break
        changed = False
        for a in acts:
            tried.add(a)
            res = await apply_action(a, ctx)
            fixes.append(res)
            changed = changed or bool(res.get("changed"))
        if ctx["reread"]:
            break
        built = any(x.get("built") for x in fixes[-len(acts):])
        if changed and not built and any(a in KNOWLEDGE_ACTIONS for a in acts):
            res = await apply_action("outputs", ctx)
            res["after"] = acts
            fixes.append(res)
        remaining = {k: v for k, v in ctx["failures"].items() if k not in ctx["cleared"]}
        f = await _facts(gid, remaining if failures is not None else None, profile)
        if failures is None:
            f["failures"] = {k: v for k, v in f["failures"].items() if k not in ctx["cleared"]}
        last = evaluate(f)
        rounds += 1
    if ask and f.get("snapshot") and not ctx["reread"]:
        story = not f.get("not_a_book") and f.get("form") in (None, *STORY_FORMS)
        f["ask"] = await ask_smoke(gid, story)
        last = evaluate(f)
    status = status_of(first, last, fixes, ctx["reread"])
    rec = {"generation_id": gid, "job_id": job_id, "book_id": f.get("book_id"), "origin": origin, "status": status,
           "rounds": rounds, "checks": {**checks_view(last), "_ask": f.get("ask")}, "findings": first,
           "remaining": last, "fixes": fixes, "code_version": _code_version()}
    if record:
        rec["id"] = await asyncio.to_thread(store, rec)
    summary = {"status": status, "findings": len(blocking(first)), "remaining": len(blocking(last)),
               "fixes": [{"action": x["action"], "ok": x.get("ok")} for x in fixes], "by": ACTOR,
               "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "audit_id": rec.get("id")}
    if not fix:
        rec["planned"] = plan_fixes(first, set(), rebuild_effective=_rebuild_effective(f), reread_allowed=True)
    rec["summary"] = summary
    rec["cleared"] = sorted(ctx["cleared"])
    rec["title"] = f.get("title")
    rec["profile"] = profile
    return rec


async def run_step(job_id: str, gid: str, profile: str, failures: dict) -> dict:
    """İş akışının `quality_audit` adımı: düzeltir, kaydeder; dönüş iş akışının özeti (durum, temizlenen adımlar,
    yeniden okuma gerekip gerekmediği). Okumanın kendi nesli: batch_guard'a sorulmaz."""
    rec = await run(gid, job_id=job_id, profile=profile, failures=failures, fix=True, ask=True, origin="WORKFLOW")
    return {**rec["summary"], "cleared": rec["cleared"], "reread": rec["status"] == "REREAD"}


# ------------------------------------------------------------------ Kitap Eczanesi (salt okuma)
def _view(x: dict) -> dict:
    return {"code": x["code"], "severity": x["severity"], "title": x["title"],
            "pages": (x.get("detail") or {}).get("pages") if isinstance((x.get("detail") or {}).get("pages"), list) else None}


FIX_TR = {"identity": "Karakter kimlikleri yeniden okundu", "fold": "Aynı kişinin kayıtları birleştirildi",
          "proofreading": "Eksik son okuma denetimleri koşturuldu", "rescan": "Yarıda kalan sayfalar yeniden incelendi",
          "metadata": "Künye yeniden okundu", "scope": "Kitap dışı sayfalar işaretlendi",
          "recommend": "Kategori ve yaş önerisi yeniden yapıldı", "outputs": "Özet, kart ve rapor yeniden kuruldu",
          "reindex": "Arama dizini yeniden kuruldu", "reread": "Kitap yeniden okumaya alındı"}


def listing(c, book_ids: list[str]) -> dict[str, dict]:
    """{kitap: {'status', 'label', 'open'}} — kitabın en yeni denetimi (en yeni nesil önce)."""
    if not book_ids or not has_table(c):
        return {}
    rows = c.execute("SELECT DISTINCT ON (a.book_id) a.book_id::text AS book_id, a.status, a.remaining, a.created_at"
                     " FROM ed.read_quality_audit a JOIN ed.generation g ON g.id=a.generation_id WHERE"
                     " a.book_id::text = ANY(%s) ORDER BY a.book_id, g.created_at DESC, a.created_at DESC",
                     (list(book_ids),)).fetchall()
    return {r["book_id"]: {"status": r["status"], "label": STATUS_TR.get(r["status"], r["status"]),
                           "open": len(blocking(r["remaining"] or []))} for r in rows}


def detail(c, book_id: str) -> dict | None:
    """Ayrıntı alanının bulgu listesi: kalan bulgular, ilk bulgular ve yapılan düzeltmeler (ekran dili)."""
    if not has_table(c):
        return None
    r = c.execute("SELECT a.status, a.findings, a.remaining, a.fixes, a.created_at, a.origin FROM ed.read_quality_audit a"
                  " JOIN ed.generation g ON g.id=a.generation_id WHERE a.book_id=%s ORDER BY g.created_at DESC,"
                  " a.created_at DESC LIMIT 1", (book_id,)).fetchone()
    if not r:
        return None
    open_ = [_view(x) for x in blocking(r["remaining"] or [])]
    keys = {x["code"] for x in blocking(r["remaining"] or [])}
    fixed = [_view(x) for x in blocking(r["findings"] or []) if x["code"] not in keys]
    notes = [_view(x) for x in (r["remaining"] or []) if x["severity"] == "info"]
    return {"status": r["status"], "label": STATUS_TR.get(r["status"], r["status"]), "at": r["created_at"].isoformat() if hasattr(r["created_at"], "isoformat") else str(r["created_at"]),
            "open": len(open_), "issues": open_, "fixed": fixed, "notes": notes,
            "fixes": [{"text": FIX_TR.get(x.get("action"), x.get("action")), "ok": bool(x.get("ok"))}
                      for x in r["fixes"] or [] if x.get("action")]}


# ------------------------------------------------------------------ komut
def targets(limit: int | None = None, generations: list[str] | None = None) -> list[dict]:
    """Okunmuş kitapların en yeni nesli (tam ya da arşiv okuması SUCCEEDED; en yeni bitiş önce)."""
    from . import foundation
    with foundation.read_snapshot() as c:
        rows = c.execute(
            "SELECT * FROM (SELECT DISTINCT ON (bv.book_id) g.id::text AS generation_id, b.title, j.profile,"
            " j.finished_at FROM ed.analysis_job j JOIN ed.generation g ON g.job_id=j.id JOIN ed.book_version bv ON"
            " bv.id=g.book_version_id JOIN ed.book b ON b.id=bv.book_id WHERE j.status='SUCCEEDED' AND j.profile IN"
            " ('full','archive') ORDER BY bv.book_id, j.finished_at DESC) t ORDER BY finished_at DESC").fetchall()
    out = [dict(r) for r in rows if not generations or r["generation_id"] in generations]
    return out[:limit] if limit else out


def row_text(r: dict) -> str:
    rem = blocking(r.get("remaining") or [])
    return (f"{(r.get('title') or '')[:36]:<36} {r['generation_id'][:8]} {r['status']:<6} "
            f"bulgu {len(blocking(r.get('findings') or []))} kalan {len(rem)}"
            + (": " + "; ".join(x["key"] for x in rem[:6]) if rem else "")
            + (" | düzeltme: " + ", ".join(f"{x['action']}{'' if x.get('ok') else '!'}" for x in r.get("fixes") or [])
               if r.get("fixes") else "")
            + (" | yapılacak: " + ", ".join(r["planned"]) if r.get("planned") else ""))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m editor.quality")
    sub = ap.add_subparsers(dest="cmd", required=True)
    au = sub.add_parser("audit", help="okunmuş kitapların kalite denetimi (varsayılan kuru: yazmaz)")
    who = au.add_mutually_exclusive_group(required=True)
    who.add_argument("--all-read", action="store_true", help="okunmuş her kitabın en yeni nesli")
    who.add_argument("--generation", action="append", help="yalnız bu nesil (tekrar verilebilir)")
    au.add_argument("--limit", type=int, help="en yeni bitenlerden bu kadar kitap")
    au.add_argument("--fix", action="store_true", help="düzelt ve kaydı yaz (yoksa yalnız denetler)")
    au.add_argument("--ask", action="store_true", help="«Zeki'ye sor» duman testi de (iki model çağrısı/kitap)")
    au.add_argument("--json", help="sonuçları bu dosyaya jsonl yaz")
    a = ap.parse_args(argv)
    rows = targets(a.limit, a.generation)
    print(f"{len(rows)} kitap; {'DÜZELTME (yazar)' if a.fix else 'kuru denetim (yazılmaz)'}", file=sys.stderr)
    out = open(a.json, "w", encoding="utf-8") if a.json else None
    from . import batch_guard
    skipped = batch_guard.Skipped("quality audit")
    totals: collections.Counter = collections.Counter()
    classes: collections.Counter = collections.Counter()

    async def all_():
        for r in rows:
            gid = r["generation_id"]
            fix = a.fix
            if fix and not await asyncio.to_thread(skipped.check, gid, r.get("title")):
                fix = False                       # süren okumanın nesli: yalnız denetlenir, yazılmaz
            try:
                rec = await run(gid, fix=fix, ask=a.ask, origin="COMMAND")
                if fix and rec["status"] == "REREAD":
                    rec["reread"] = await asyncio.to_thread(queue_reread, rec["job_id"])
                if fix:
                    await asyncio.to_thread(note_job, rec["job_id"], rec["summary"], rec["cleared"])
            except Exception as e:  # noqa: BLE001 — bir kitap ötekileri durdurmaz
                rec = {"generation_id": gid, "title": r.get("title"), "status": "ERROR",
                       "error": f"{type(e).__name__}: {e}"[:300], "findings": [], "remaining": []}
            totals[rec["status"]] += 1
            for x in blocking(rec.get("findings") or []):
                classes[x["code"]] += 1
            if out:
                out.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
                out.flush()
            print(row_text(rec) if rec["status"] != "ERROR" else f"{r.get('title')} {gid[:8]} HATA {rec['error']}",
                  flush=True)
    asyncio.run(all_())
    print("durum: " + json.dumps(dict(totals), ensure_ascii=False), file=sys.stderr)
    print("sınıf: " + json.dumps(dict(classes.most_common()), ensure_ascii=False), file=sys.stderr)
    if a.fix:
        skipped.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
