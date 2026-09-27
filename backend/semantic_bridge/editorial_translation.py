"""M4 Çeviri: kaynak metin → segmentler → çevirmen ekranı → inceleme → kalite raporu. CRM'de karşılığı yok.

Bir **çeviri işi** (job) bir kitabın bir dil çiftindeki çevirisidir. Kaynak dosya (DOCX / TXT / MD / PDF)
paragraflara, paragraflar cümle segmentlerine bölünür; bölüm başlıkları ayrı segmenttir ve bölümü açar.

- Çevirmen (işe atanan AD kullanıcısı) segmenti yazar: boş → taslak (kaydedildi) → çevrildi (onayladı).
- İnceleyen segmenti düzeltip onaylar (onaylandi) ve gerekirse hata işaretler (MQM: kategori + ağırlık).
  Çevirmenin onayladığı metin `submitted`'da saklanır; inceleyenin düzeltme oranı bundan hesaplanır.
- Terim bankası: dil çifti başına (genel) ya da işe özel; onaylı terim, adayı çevirmen önerir. Yasak
  karşılıklar tutulur. Segmentte geçen terim ve karşılığının hedefte olup olmadığı modelsiz denetlenir.
- Çeviri belleği: aynı dil çiftinde çevrilmiş/onaylı segmentlerden birebir ve benzer eşleşme.
- Otomatik denetim (modelsiz): sayı, terim, yasak karşılık, son noktalama, parantez/tırnak dengesi,
  bağlantı/e-posta, boşluk, kaynağın aynen kopyası, iş içi tutarsızlık, uzunluk uç değeri (Tukey).
- ZEKİ ham taslak (isteğe bağlı, işi yöneten başlatır): taslak ayrı sütuna yazılır, hedefe kendiliğinden
  geçmez; çevirmen kullanıp kullanmayacağına karar verir.
- Dışa/içe: hedef DOCX, iki dilli XLIFF 1.2 (Trados/memoQ/OmegaT), terim bankası CSV. Biten çeviri
  M3 Redaksiyon'a yeni metin sürümü olarak aktarılır.

Dosyalar diskte (`EDITORIAL_DIR/translation/<iş>`), kayıtlar `semantic_translation_*` tablolarında.
"""
from __future__ import annotations

import csv
import difflib
import hashlib
import io
import json
import logging
import os
import re
import shutil
import threading
import unicodedata
import uuid
import zipfile
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional
from xml.etree import ElementTree
from xml.sax.saxutils import escape as xml_escape

import sqlalchemy as sa

from semantic_bridge import editorial_desk as desk

log = logging.getLogger("semantic.editorial_translation")
_md = sa.MetaData()

JOBS = sa.Table(
    "semantic_translation_jobs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("author", sa.String(300)),
    sa.Column("source_lang", sa.String(8), nullable=False),
    sa.Column("target_lang", sa.String(8), nullable=False),
    sa.Column("translator", sa.String(120)),
    sa.Column("translator_name", sa.String(200)),
    sa.Column("reviewer", sa.String(120)),
    sa.Column("reviewer_name", sa.String(200)),
    sa.Column("due_date", sa.Date),
    sa.Column("note", sa.Text),
    sa.Column("source_version", sa.Integer, nullable=False, default=0),
    sa.Column("source_filename", sa.String(300)),
    sa.Column("source_sha256", sa.String(64)),
    sa.Column("source_bytes", sa.BigInteger),
    sa.Column("source_path", sa.String(500)),
    sa.Column("draft_state", sa.String(20), nullable=False, default="yok"),   # yok | calisiyor | bitti | hata
    sa.Column("draft_note", sa.String(500)),
    sa.Column("draft_done", sa.Integer, nullable=False, default=0),
    sa.Column("draft_total", sa.Integer, nullable=False, default=0),
    sa.Column("work_id", sa.String(32)),                  # M3'e aktarıldıysa eser dosyası
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("completed_at", sa.DateTime(timezone=True)),
)
SEGMENTS = sa.Table(
    "semantic_translation_segments", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("job_id", sa.String(32), nullable=False, index=True),
    sa.Column("no", sa.Integer, nullable=False),
    sa.Column("para", sa.Integer, nullable=False),
    sa.Column("chapter", sa.Integer, nullable=False),
    sa.Column("chapter_title", sa.String(300), nullable=False),
    sa.Column("heading", sa.Boolean, nullable=False, default=False),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("target", sa.Text, nullable=False, default=""),
    sa.Column("draft", sa.Text),
    sa.Column("status", sa.String(20), nullable=False, default="bos"),   # bos | taslak | cevrildi | onaylandi
    sa.Column("words", sa.Integer, nullable=False),
    sa.Column("submitted", sa.Text),
    sa.Column("note", sa.Text),
    sa.Column("translated_by", sa.String(120)),
    sa.Column("translated_at", sa.DateTime(timezone=True)),
    sa.Column("approved_by", sa.String(120)),
    sa.Column("approved_at", sa.DateTime(timezone=True)),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
ERRORS = sa.Table(
    "semantic_translation_errors", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("job_id", sa.String(32), nullable=False, index=True),
    sa.Column("segment_id", sa.String(32), nullable=False, index=True),
    sa.Column("category", sa.String(20), nullable=False),
    sa.Column("severity", sa.String(10), nullable=False),
    sa.Column("note", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
)
TERMS = sa.Table(
    "semantic_translation_terms", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("source_lang", sa.String(8), nullable=False),
    sa.Column("target_lang", sa.String(8), nullable=False),
    sa.Column("source_term", sa.String(300), nullable=False),
    sa.Column("target_term", sa.String(300), nullable=False, default=""),
    sa.Column("forbidden_json", sa.Text, nullable=False, default="[]"),
    sa.Column("note", sa.Text),
    sa.Column("job_id", sa.String(32), index=True),          # boşsa dil çiftinin genel terimi
    sa.Column("status", sa.String(10), nullable=False, default="onayli"),   # onayli | aday
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_by", sa.String(120)),
    sa.Column("updated_at", sa.DateTime(timezone=True)),
)
EVENTS = sa.Table(
    "semantic_translation_events", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("job_id", sa.String(32), nullable=False, index=True),
    sa.Column("segment_id", sa.String(32), nullable=False),
    sa.Column("username", sa.String(120), nullable=False),
    sa.Column("action", sa.String(20), nullable=False),     # cevrildi | onaylandi | geri
    sa.Column("words", sa.Integer, nullable=False),
    sa.Column("at", sa.DateTime(timezone=True), nullable=False, index=True),
)

LANGS: dict[str, str] = {
    "en": "İngilizce", "tr": "Türkçe", "ar": "Arapça", "fa": "Farsça", "fr": "Fransızca", "de": "Almanca",
    "es": "İspanyolca", "it": "İtalyanca", "ru": "Rusça", "pt": "Portekizce", "nl": "Felemenkçe",
    "ur": "Urduca", "az": "Azerbaycan Türkçesi", "bs": "Boşnakça", "sq": "Arnavutça", "ja": "Japonca",
    "zh": "Çince", "ko": "Korece", "el": "Yunanca", "bg": "Bulgarca",
}
CATEGORIES: dict[str, str] = {
    "anlam": "Anlam hatası", "eksik": "Eksik / fazla çeviri", "terim": "Terim", "dilbilgisi": "Dil bilgisi",
    "yazim": "Yazım ve noktalama", "uslup": "Üslup", "bicim": "Biçim",
}
#: MQM 2.0 ağırlıkları (küçük 1, büyük 5, kritik 25).
SEVERITIES: dict[str, tuple[str, int]] = {"kucuk": ("Küçük", 1), "buyuk": ("Büyük", 5), "kritik": ("Kritik", 25)}
DONE = ("cevrildi", "onaylandi")

MAX_BYTES = 120 * 1024 * 1024
_ready: set[int] = set()
_lock = threading.Lock()
_running: set[str] = set()


class TranslationError(ValueError):
    """Kişiye gösterilecek düz Türkçe hata."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


def reset_stale(engine: sa.engine.Engine) -> None:
    """Servis yeniden başladıysa yarıda kalan taslak işi 'çalışıyor' diye asılı kalmasın."""
    with engine.begin() as conn:
        conn.execute(sa.update(JOBS).where(JOBS.c.draft_state == "calisiyor").values(
            draft_state="hata", draft_note="Servis yeniden başladı; kalan segmentler için taslağı yeniden başlatın."))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Optional[str]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).isoformat()
    return v.isoformat()


def _new() -> str:
    return uuid.uuid4().hex


def _root() -> str:
    return os.path.join(desk._root(), "translation")


def _user(v: Any) -> Optional[str]:
    s = str(v or "").strip().lower()
    return s[:120] or None


# ============================================================================================ metin

_WORD = re.compile(r"[^\W_]+(?:['’][^\W\d_]+)?", re.UNICODE)


def word_count(text: str) -> int:
    return len(_WORD.findall(text or ""))


def fold(s: str) -> str:
    """Karşılaştırma için küçük harf: Türkçe İ/ı ve birleşik noktalar dahil."""
    return unicodedata.normalize("NFC", s or "").casefold().replace("i\u0307", "i")


_EN_HEAD = re.compile(r"^\s*(?:chapter|part|book|prologue|epilogue|introduction|preface|foreword|afterword|"
                      r"acknowledg(?:e)?ments|contents|appendix)\b.{0,80}$", re.I)
_TERMINAL = ".!?…。！？؟:;\"'”’»)]"


def _is_heading_line(text: str) -> bool:
    t = text.strip()
    if not t or len(t) > 90:
        return False
    if desk._HEADING.match(t) or _EN_HEAD.match(t):
        return True
    words = t.split()
    letters = [ch for ch in t if ch.isalpha()]
    # Tamamı büyük harfli kısa satır (ÖNSÖZ, THE BEGINNING) ve cümle sonu noktalaması yok.
    return (len(words) <= 8 and len(letters) >= 3 and all(ch == ch.upper() for ch in letters)
            and any(ch != ch.lower() for ch in letters) and t[-1] not in ".!?…,;:")


def _join_lines(lines: list[str]) -> list[tuple[str, bool]]:
    """PDF satırlarını paragrafa çevirir: satır cümle sonuyla bitiyorsa ve sonraki satır kısa değilse paragraf
    orada biter; satır sonu tirelemesi birleştirilir."""
    out: list[tuple[str, bool]] = []
    cur = ""
    for raw in lines:
        ln = raw.strip()
        if not ln:
            if cur:
                out.append((cur, False))
                cur = ""
            continue
        if _is_heading_line(ln) and not cur:
            out.append((ln, True))
            continue
        if cur.endswith("-") and ln[:1].islower():
            cur = cur[:-1] + ln
        else:
            cur = f"{cur} {ln}" if cur else ln
        if ln[-1] in ".!?…”\"»" and len(ln) < 60:
            out.append((cur, False))
            cur = ""
    if cur:
        out.append((cur, False))
    return out


def paragraphs(filename: str, data: bytes) -> list[tuple[str, bool]]:
    """(paragraf, başlık mı). DOCX stil başlığını, TXT boş satırı, PDF satır birleştirmeyi kullanır."""
    ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else ""
    if ext == "docx":
        try:
            paras = desk._docx_paragraphs(data)
        except desk.DeskError as e:
            raise TranslationError(str(e)) from e
        return [(t, h or _is_heading_line(t)) for t, h in paras]
    if ext == "pdf":
        try:
            reader = desk._pdf_reader(data)
        except desk.DeskError as e:
            raise TranslationError(str(e), e.status) from e
        lines: list[str] = []
        for page in reader.pages:
            lines.extend((page.extract_text() or "").splitlines())
            lines.append("")
        return _join_lines(lines)
    if ext in ("txt", "md"):
        text = data.decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        if ext == "md":
            # Markdown başlığı (# …) kendi paragrafıdır.
            text = re.sub(r"^(#{1,6}\s+.+)$", r"\n\1\n", text, flags=re.M)
        blocks = [b for b in re.split(r"\n\s*\n", text) if b.strip()]
        if len(blocks) <= 1 and text.count("\n") > 2:
            blocks = [ln for ln in text.split("\n") if ln.strip()]
        out = []
        for b in blocks:
            one = re.sub(r"\s*\n\s*", " ", b.strip())
            md_head = ext == "md" and one.startswith("#")
            if md_head:
                one = one.lstrip("#").strip()
            out.append((one, md_head or _is_heading_line(one)))
        return out
    raise TranslationError("Kaynak dosya DOCX, TXT, MD ya da PDF olmalı.")


_ABBR: set[str] = {
    # İngilizce
    "mr", "mrs", "ms", "dr", "prof", "st", "jr", "sr", "vs", "e.g", "i.e", "no", "vol", "fig", "p", "pp", "ch", "ed",
    "eds", "inc", "ltd", "co", "mt", "gen", "col", "lt", "capt", "sgt", "rev", "hon", "gov", "sen", "rep", "cf", "al",
    "jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec", "approx", "dept", "est",
    # Türkçe
    "doç", "yrd", "bkz", "vb", "örn", "s", "sf", "c", "sn", "av", "müh", "şti", "hz", "a.ş", "yy", "m.ö", "m.s",
    "age", "a.g.e", "çev", "haz", "yay", "ra", "as", "ks",
    # Fransızca / Almanca
    "mme", "mlle", "m", "hr", "fr", "bzw", "usw", "z.b", "ca",
}
_SPLIT = re.compile(r"([.!?…。！？؟]+[\"'”’»)\]]*)(\s+)")


def split_sentences(text: str) -> list[str]:
    """Paragrafı cümlelere böler. Kısaltma, baş harf (J. K.), ondalık sayı ve küçük harfle süren cümle bölünmez;
    büyük/küçük harfi olmayan yazılarda (Arapça, Çince…) noktalama yeter."""
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    out, start = [], 0
    for m in _SPLIT.finditer(text):
        end = m.end(1)
        before = text[start:m.start(1)]
        token = re.split(r"[\s(\"'“‘«\[]", before)[-1] if before else ""
        rest = text[m.end():]
        nxt = rest[:1]
        if not nxt:
            continue
        punct = m.group(1)
        if punct.startswith(".") and not punct.startswith("..."):
            low = token.lower().rstrip(".")
            if low in _ABBR or (len(token) == 1 and token.isalpha() and token.isupper()) or re.fullmatch(r"(?:[A-Za-z]\.)+[A-Za-z]", token):
                continue
            if token.isdigit() and len(token) <= 3 and nxt.isdigit():
                continue
        opener = nxt in "\"'“‘«([—–-¿¡" or nxt.isdigit()
        caseless = nxt.isalpha() and nxt.lower() == nxt.upper()
        if not (nxt.isupper() or opener or caseless):
            continue
        out.append(text[start:end].strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return [s for s in out if s]


def segment(paras: list[tuple[str, bool]]) -> list[dict[str, Any]]:
    """Paragraflardan segment listesi. Başlık tek segmenttir ve yeni bölümü açar; başlık yoksa tek bölüm."""
    segs: list[dict[str, Any]] = []
    chapter, title = 0, "Metin"
    for p_no, (text, heading) in enumerate(paras, 1):
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        if heading:
            chapter += 1
            title = text[:300]
            segs.append({"para": p_no, "chapter": chapter, "chapter_title": title, "heading": True, "source": text})
            continue
        if chapter == 0:
            chapter = 1
        for s in split_sentences(text):
            segs.append({"para": p_no, "chapter": chapter, "chapter_title": title, "heading": False, "source": s})
    for i, s in enumerate(segs, 1):
        s["no"] = i
        s["words"] = word_count(s["source"])
    return segs


# ============================================================================================ terimler

def _forbidden(row: Any) -> list[str]:
    try:
        return [str(x) for x in json.loads(row.forbidden_json or "[]") if str(x).strip()]
    except ValueError:
        return []


def _term_rx(term: str) -> str:
    parts = [re.escape(p) for p in fold(term).split()]
    return r"\s+".join(parts)


class TermIndex:
    """Bir dil çiftinin terimleri için tek düzenli ifade; segmentte geçen terimleri bulur."""

    def __init__(self, terms: list[Any]):
        self.by_key: dict[str, list[Any]] = defaultdict(list)
        for t in terms:
            key = " ".join(fold(t.source_term).split())
            if key:
                self.by_key[key].append(t)
        keys = sorted(self.by_key, key=len, reverse=True)
        self.rx = re.compile(r"(?<![^\W_])(" + "|".join(_term_rx(k) for k in keys) + r")(?:s|es|'s|’s)?(?![^\W_])",
                             re.UNICODE) if keys else None

    def find(self, source: str) -> list[tuple[Any, int, int]]:
        if self.rx is None:
            return []
        src = fold(source)
        out = []
        for m in self.rx.finditer(src):
            key = " ".join(m.group(1).split())
            for t in self.by_key.get(key, []):
                out.append((t, m.start(1), m.end(1)))
        return out


_SOFT = {"p": "b", "ç": "c", "t": "d", "k": "ğ"}


def _stems(word: str) -> set[str]:
    """Hedef dildeki çekimli biçimi yakalamak için kök adayları (Türkçe ünsüz yumuşaması dahil)."""
    w = fold(word)
    out = {w}
    if len(w) >= 5:
        out.add(w[:-1])
    if w and w[-1] in _SOFT and len(w) >= 3:
        out.add(w[:-1] + _SOFT[w[-1]])
        if w[-1] == "k":
            out.add(w[:-1] + "g")
    return out


def target_has(target: str, term: str) -> bool:
    """Terim (ya da | ile ayrılmış karşılıklarından biri) hedefte geçiyor mu: her kelimesi bir hedef kelimenin başı."""
    words = [fold(w) for w in _WORD.findall(target or "")]
    for alt in (a.strip() for a in (term or "").split("|")):
        parts = _WORD.findall(alt)
        if parts and all(any(w.startswith(st) for w in words for st in _stems(p)) for p in parts):
            return True
    return False


def _contains_phrase(target: str, phrase: str) -> bool:
    p = fold(phrase).strip()
    return bool(p) and re.search(r"(?<![^\W_])" + _term_rx(p), fold(target)) is not None


# ============================================================================================ denetim

_NUM = re.compile(r"\d+(?:[.,:/]\d+)*")
_LINK = re.compile(r"(?:https?://\S+|www\.\S+|[\w.+-]+@[\w-]+\.[\w.-]+)")
_PAIRS = (("(", ")"), ("[", "]"), ("«", "»"), ("“", "”"))
QA_LABELS: dict[str, str] = {
    "sayi": "Sayı uyuşmuyor", "terim": "Terim karşılığı yok", "yasak": "Yasak karşılık", "noktalama": "Son noktalama farklı",
    "denge": "Parantez/tırnak dengesi", "baglanti": "Bağlantı ya da e-posta eksik", "bosluk": "Fazla boşluk",
    "ayni": "Kaynak aynen kopyalanmış", "tutarsiz": "Aynı cümle farklı çevrilmiş", "uzunluk": "Uzunluk olağan dışı",
}


def _nums(s: str) -> Counter:
    return Counter(re.sub(r"\D", "", n) for n in _NUM.findall(s or ""))


def _end_class(s: str) -> Optional[str]:
    t = (s or "").rstrip().rstrip("\"'”’»)] ")
    if not t:
        return None
    ch = t[-1]
    if ch in "?؟？":
        return "?"
    if ch in "!！":
        return "!"
    if ch in ".…。:;":
        return "."
    return None


def check_segment(source: str, target: str, terms: list[tuple[Any, int, int]]) -> list[dict[str, str]]:
    """Tek segmentin modelsiz denetimi. İş düzeyindeki (tutarsızlık, uzunluk) denetim `job_checks`'te."""
    if not (target or "").strip():
        return []
    out: list[dict[str, str]] = []
    a, b = _nums(source), _nums(target)
    if a != b:
        miss, extra = sorted((a - b).elements()), sorted((b - a).elements())
        out.append({"code": "sayi", "text": "Kaynakta olup hedefte olmayan: " + (", ".join(miss) or "—")
                    + (" · hedefte fazladan: " + ", ".join(extra) if extra else "")})
    seen: set[str] = set()
    for t, _, _ in terms:
        if t.status != "onayli" or t.id in seen:
            continue
        seen.add(t.id)
        if t.target_term and not target_has(target, t.target_term):
            out.append({"code": "terim", "text": f"«{t.source_term}» → «{t.target_term}» bekleniyordu"})
        for bad in _forbidden(t):
            if _contains_phrase(target, bad):
                out.append({"code": "yasak", "text": f"«{t.source_term}» için «{bad}» kullanılmamalı"})
    ea, eb = _end_class(source), _end_class(target)
    if ea in ("?", "!") and eb != ea:
        out.append({"code": "noktalama", "text": f"Kaynak «{ea}» ile bitiyor"})
    elif ea == "." and eb is None and len(target.strip()) > 1:
        out.append({"code": "noktalama", "text": "Kaynak cümle sonu noktalamasıyla bitiyor, hedef bitmiyor"})
    for o, c in _PAIRS:
        if source.count(o) == source.count(c) and target.count(o) != target.count(c):
            out.append({"code": "denge", "text": f"«{o}» {target.count(o)} kez, «{c}» {target.count(c)} kez"})
    for q in ('"',):
        if source.count(q) % 2 == 0 and target.count(q) % 2 == 1:
            out.append({"code": "denge", "text": "Çift tırnak sayısı tek"})
    for link in _LINK.findall(source):
        if link.rstrip(".,;:)") not in target:
            out.append({"code": "baglanti", "text": link.rstrip(".,;:)")})
    if "  " in target or target != target.strip():
        out.append({"code": "bosluk", "text": "Çift boşluk ya da baş/son boşluk"})
    if word_count(source) >= 3 and fold(source.strip()) == fold(target.strip()):
        out.append({"code": "ayni", "text": "Hedef kaynakla aynı"})
    return out


def _norm_src(s: str) -> str:
    return " ".join(fold(s).split())


def job_checks(rows: list[Any]) -> dict[str, list[dict[str, str]]]:
    """İş düzeyindeki denetimler: aynı kaynak cümlesinin farklı çevirisi ve uzunluk oranı uç değeri.
    Uç değer Tukey'in 'çok uzak' sınırıdır (Q1 − 3·IQR, Q3 + 3·IQR); en az 20 çevrilmiş segment ister."""
    out: dict[str, list[dict[str, str]]] = defaultdict(list)
    done = [r for r in rows if r.status in DONE and (r.target or "").strip()]
    by_src: dict[str, set[str]] = defaultdict(set)
    for r in done:
        if word_count(r.source) >= 3:
            by_src[_norm_src(r.source)].add(" ".join(r.target.split()))
    for r in done:
        variants = by_src.get(_norm_src(r.source)) or set()
        if len(variants) > 1:
            out[r.id].append({"code": "tutarsiz", "text": f"Bu cümlenin işte {len(variants)} farklı çevirisi var"})
    ratios = sorted(len(r.target) / len(r.source) for r in done if len(r.source) >= 20)
    if len(ratios) >= 20:
        q1, q3 = ratios[len(ratios) // 4], ratios[(3 * len(ratios)) // 4]
        lo, hi = q1 - 3 * (q3 - q1), q3 + 3 * (q3 - q1)
        for r in done:
            if len(r.source) >= 20:
                x = len(r.target) / len(r.source)
                if x < lo or x > hi:
                    out[r.id].append({"code": "uzunluk", "text": f"Hedef/kaynak uzunluk oranı {x:.2f} (işte olağan {q1:.2f}–{q3:.2f})"})
    return out


# ============================================================================================ erişim

def _job(conn: sa.Connection, tenant: str, job_id: str, user: str, see_all: bool) -> Any:
    row = conn.execute(sa.select(JOBS).where(JOBS.c.id == job_id, JOBS.c.tenant_id == tenant)).first()
    if row is None:
        raise TranslationError("Çeviri işi bulunamadı.", 404)
    u = user.lower()
    if see_all or u in (row.created_by.lower(), (row.translator or ""), (row.reviewer or "")):
        return row
    raise TranslationError("Bu çeviri işine erişiminiz yok.", 403)


def _roles(job: Any, user: str, see_all: bool) -> dict[str, bool]:
    u = user.lower()
    owner = see_all or u == job.created_by.lower()
    return {
        "translate": owner or u == (job.translator or ""),
        "review": owner or u == (job.reviewer or ""),
        "manage": owner,
    }


def _segment(conn: sa.Connection, tenant: str, seg_id: str, user: str, see_all: bool, lock: bool = False) -> tuple[Any, Any]:
    q = sa.select(SEGMENTS).where(SEGMENTS.c.id == seg_id)
    s = conn.execute(q.with_for_update() if lock else q).first()
    if s is None:
        raise TranslationError("Segment bulunamadı.", 404)
    return s, _job(conn, tenant, s.job_id, user, see_all)


def _terms_for(conn: sa.Connection, tenant: str, job: Any) -> list[Any]:
    return conn.execute(sa.select(TERMS).where(
        TERMS.c.tenant_id == tenant, TERMS.c.source_lang == job.source_lang, TERMS.c.target_lang == job.target_lang,
        sa.or_(TERMS.c.job_id.is_(None), TERMS.c.job_id == job.id))).all()


# ============================================================================================ işler

def _date(v: Any) -> Optional[date]:
    s = str(v or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s[:10])
    except ValueError as e:
        raise TranslationError("Teslim tarihi YYYY-AA-GG biçiminde olmalı.") from e


def _lang(v: Any, what: str) -> str:
    s = str(v or "").strip().lower()
    if s not in LANGS:
        raise TranslationError(f"{what} dili tanınmıyor.")
    return s


def create_job(engine: sa.engine.Engine, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
    title = str(body.get("title") or "").strip()
    if not title:
        raise TranslationError("Eser adı gerekli.")
    src, tgt = _lang(body.get("sourceLang"), "Kaynak"), _lang(body.get("targetLang"), "Hedef")
    if src == tgt:
        raise TranslationError("Kaynak ve hedef dil aynı olamaz.")
    row = {
        "id": _new(), "tenant_id": tenant, "title": title[:300], "author": str(body.get("author") or "").strip()[:300] or None,
        "source_lang": src, "target_lang": tgt, "translator": _user(body.get("translator")),
        "translator_name": str(body.get("translatorName") or "").strip()[:200] or None,
        "reviewer": _user(body.get("reviewer")), "reviewer_name": str(body.get("reviewerName") or "").strip()[:200] or None,
        "due_date": _date(body.get("dueDate")), "note": str(body.get("note") or "").strip()[:4000] or None,
        "source_version": 0, "draft_state": "yok", "draft_done": 0, "draft_total": 0,
        "created_by": user.lower(), "created_at": _now(),
    }
    with engine.begin() as conn:
        conn.execute(sa.insert(JOBS).values(**row))
    return {"id": row["id"], "title": row["title"]}


def update_job(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str, body: dict[str, Any]) -> dict[str, Any]:
    with engine.begin() as conn:
        job = _job(conn, tenant, job_id, user, see_all)
        if not _roles(job, user, see_all)["manage"]:
            raise TranslationError("İşi yalnız açan kişi ya da yetkili yönetici değiştirir.", 403)
        v: dict[str, Any] = {}
        if "title" in body and str(body["title"]).strip():
            v["title"] = str(body["title"]).strip()[:300]
        if "author" in body:
            v["author"] = str(body.get("author") or "").strip()[:300] or None
        for key, col in (("translator", "translator"), ("reviewer", "reviewer")):
            if key in body:
                v[col] = _user(body.get(key))
                v[f"{col}_name"] = str(body.get(f"{key}Name") or "").strip()[:200] or None
        if "dueDate" in body:
            v["due_date"] = _date(body.get("dueDate"))
        if "note" in body:
            v["note"] = str(body.get("note") or "").strip()[:4000] or None
        has_segments = conn.execute(sa.select(SEGMENTS.c.id).where(SEGMENTS.c.job_id == job_id).limit(1)).first() is not None
        for key, col, what in (("sourceLang", "source_lang", "Kaynak"), ("targetLang", "target_lang", "Hedef")):
            if key in body and body[key] != getattr(job, col):
                if has_segments and key == "sourceLang":
                    raise TranslationError("Kaynak yüklendikten sonra kaynak dil değiştirilemez.", 409)
                v[col] = _lang(body[key], what)
        if (v.get("source_lang") or job.source_lang) == (v.get("target_lang") or job.target_lang):
            raise TranslationError("Kaynak ve hedef dil aynı olamaz.")
        if v:
            conn.execute(sa.update(JOBS).where(JOBS.c.id == job_id).values(**v))
        return {k: (_iso(x) if isinstance(x, (date, datetime)) else x) for k, x in v.items()}


def delete_job(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str) -> str:
    with engine.begin() as conn:
        job = _job(conn, tenant, job_id, user, see_all)
        if not _roles(job, user, see_all)["manage"]:
            raise TranslationError("İşi yalnız açan kişi ya da yetkili yönetici siler.", 403)
        if job_id in _running:
            raise TranslationError("ZEKİ taslağı sürerken iş silinemez.", 409)
        for t in (SEGMENTS, ERRORS, EVENTS):
            conn.execute(sa.delete(t).where(t.c.job_id == job_id))
        conn.execute(sa.delete(TERMS).where(TERMS.c.job_id == job_id))
        conn.execute(sa.delete(JOBS).where(JOBS.c.id == job_id))
        title = job.title
    shutil.rmtree(os.path.join(_root(), job_id), ignore_errors=True)
    return title


def _counts(conn: sa.Connection, job_ids: list[str]) -> dict[str, dict[str, dict[str, int]]]:
    out: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: {"segments": {}, "words": {}})
    if not job_ids:
        return out
    for jid, st, n, w in conn.execute(sa.select(SEGMENTS.c.job_id, SEGMENTS.c.status, sa.func.count(), sa.func.sum(SEGMENTS.c.words))
                                      .where(SEGMENTS.c.job_id.in_(job_ids)).group_by(SEGMENTS.c.job_id, SEGMENTS.c.status)).all():
        out[jid]["segments"][st] = int(n)
        out[jid]["words"][st] = int(w or 0)
    return out


def _stage(c: dict[str, dict[str, int]]) -> str:
    seg = c["segments"]
    total = sum(seg.values())
    if not total:
        return "kaynak"
    if seg.get("onaylandi", 0) == total:
        return "tamamlandi"
    if seg.get("bos", 0) + seg.get("taslak", 0) == 0:
        return "inceleme"
    return "ceviri"


def _pace(conn: sa.Connection, job: Any, remaining_words: int) -> dict[str, Any]:
    """Son 14 günün çeviri hızı (takvim günü başına kelime), bu hızla bitiş tarihi, teslime yetişmek için gereken hız."""
    today = _now().date()
    since = _now() - timedelta(days=14)
    rows = conn.execute(sa.select(EVENTS.c.words, EVENTS.c.at).where(
        EVENTS.c.job_id == job.id, EVENTS.c.action == "cevrildi", EVENTS.c.at >= since)).all()
    first = conn.execute(sa.select(sa.func.min(EVENTS.c.at)).where(EVENTS.c.job_id == job.id, EVENTS.c.action == "cevrildi")).scalar()
    words = sum(int(w) for w, _ in rows)
    days_active = len({(a if a.tzinfo else a.replace(tzinfo=timezone.utc)).date() for _, a in rows})
    window = 14
    if first is not None:
        f = first if first.tzinfo else first.replace(tzinfo=timezone.utc)
        window = max(1, min(14, (today - f.date()).days + 1))
    per_day = words / window if words else 0.0
    finish = (today + timedelta(days=int(-(-remaining_words // per_day)))) if per_day and remaining_words else (today if not remaining_words else None)
    days_left = (job.due_date - today).days if job.due_date else None
    need = (remaining_words / max(days_left, 1)) if (days_left is not None and remaining_words) else None
    late = bool(job.due_date and remaining_words and (finish is None or finish > job.due_date))
    return {"wordsLast14": words, "activeDays": days_active, "windowDays": window, "perDay": round(per_day, 1),
            "finish": _iso(finish), "daysLeft": days_left, "needPerDay": round(need, 1) if need is not None else None,
            "late": late, "overdue": bool(days_left is not None and days_left < 0 and remaining_words)}


def _summary(conn: sa.Connection, job: Any, c: dict[str, dict[str, int]], user: str, see_all: bool) -> dict[str, Any]:
    seg, words = c["segments"], c["words"]
    total_w = sum(words.values())
    done_w = words.get("cevrildi", 0) + words.get("onaylandi", 0)
    return {
        "id": job.id, "title": job.title, "author": job.author, "sourceLang": job.source_lang, "targetLang": job.target_lang,
        "translator": job.translator, "translatorName": job.translator_name, "reviewer": job.reviewer,
        "reviewerName": job.reviewer_name, "dueDate": _iso(job.due_date), "note": job.note, "createdBy": job.created_by,
        "createdAt": _iso(job.created_at), "completedAt": _iso(job.completed_at), "workId": job.work_id,
        "source": {"version": job.source_version, "filename": job.source_filename, "bytes": int(job.source_bytes or 0),
                   "sha256": job.source_sha256} if job.source_version else None,
        "draft": {"state": job.draft_state, "note": job.draft_note, "done": job.draft_done, "total": job.draft_total},
        "stage": _stage(c),
        "segments": {"total": sum(seg.values()), **{k: seg.get(k, 0) for k in ("bos", "taslak", "cevrildi", "onaylandi")}},
        "words": {"total": total_w, "done": done_w, "approved": words.get("onaylandi", 0)},
        "pace": _pace(conn, job, total_w - done_w),
        "roles": _roles(job, user, see_all),
    }


def list_jobs(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, mine: bool = False) -> list[dict[str, Any]]:
    u = user.lower()
    with engine.connect() as conn:
        q = sa.select(JOBS).where(JOBS.c.tenant_id == tenant)
        if mine or not see_all:
            cond = [JOBS.c.translator == u, JOBS.c.reviewer == u]
            if not mine:
                cond.append(sa.func.lower(JOBS.c.created_by) == u)
            q = q.where(sa.or_(*cond))
        rows = conn.execute(q.order_by(JOBS.c.created_at.desc())).all()
        counts = _counts(conn, [r.id for r in rows])
        return [_summary(conn, r, counts[r.id], user, see_all) for r in rows]


def job_detail(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str) -> dict[str, Any]:
    with engine.connect() as conn:
        job = _job(conn, tenant, job_id, user, see_all)
        out = _summary(conn, job, _counts(conn, [job_id])[job_id], user, see_all)
        chapters = conn.execute(sa.select(
            SEGMENTS.c.chapter, sa.func.min(SEGMENTS.c.chapter_title), SEGMENTS.c.status, sa.func.count(), sa.func.sum(SEGMENTS.c.words))
            .where(SEGMENTS.c.job_id == job_id).group_by(SEGMENTS.c.chapter, SEGMENTS.c.status)).all()
        by: dict[int, dict[str, Any]] = {}
        for ch, title, st, n, w in chapters:
            d = by.setdefault(int(ch), {"no": int(ch), "title": title, "segments": 0, "words": 0,
                                        **{k: 0 for k in ("bos", "taslak", "cevrildi", "onaylandi")}, "wordsDone": 0})
            d["segments"] += int(n)
            d["words"] += int(w or 0)
            d[st] = d.get(st, 0) + int(n)
            if st in DONE:
                d["wordsDone"] += int(w or 0)
        out["chapters"] = [by[k] for k in sorted(by)]
        out["languages"] = {"source": LANGS.get(job.source_lang), "target": LANGS.get(job.target_lang)}
        return out


# ============================================================================================ kaynak

def upload_source(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str,
                  filename: str, data: bytes) -> dict[str, Any]:
    if not data:
        raise TranslationError("Dosya boş.")
    if len(data) > MAX_BYTES:
        raise TranslationError("Dosya 120 MB sınırını aşıyor.", 413)
    segs = segment(paragraphs(filename, data))
    if not segs:
        raise TranslationError("Dosyada okunabilir metin bulunamadı.")
    sha = hashlib.sha256(data).hexdigest()
    with engine.begin() as conn:
        job = _job(conn, tenant, job_id, user, see_all)
        if not _roles(job, user, see_all)["manage"]:
            raise TranslationError("Kaynağı yalnız işi açan kişi ya da yetkili yönetici yükler.", 403)
        if job_id in _running:
            raise TranslationError("ZEKİ taslağı sürerken kaynak değiştirilemez.", 409)
        if job.source_sha256 == sha:
            raise TranslationError("Bu dosya son yüklenen kaynakla aynı; yeni sürüm açılmadı.", 409)
        # Önceki sürümdeki çeviriler aynı kaynak cümlesine taşınır (ilk eşleşen); onay çevrildi'ye iner.
        carry: dict[str, Any] = {}
        for r in conn.execute(sa.select(SEGMENTS).where(SEGMENTS.c.job_id == job_id).order_by(SEGMENTS.c.no)).all():
            if (r.target or "").strip() or r.draft:
                carry.setdefault(_norm_src(r.source), r)
        version = int(job.source_version or 0) + 1
        ext = re.sub(r"[^a-z0-9]", "", filename.lower().rsplit(".", 1)[-1])[:8] if "." in filename else "bin"
        folder = os.path.join(_root(), job_id)
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, f"source-v{version}.{ext}")
        with open(path, "wb") as f:
            f.write(data)
        conn.execute(sa.delete(ERRORS).where(ERRORS.c.job_id == job_id))
        conn.execute(sa.delete(SEGMENTS).where(SEGMENTS.c.job_id == job_id))
        kept = 0
        rows = []
        for s in segs:
            old = carry.get(_norm_src(s["source"]))
            row = {"id": _new(), "job_id": job_id, **s, "target": "", "status": "bos", "draft": None}
            if old is not None:
                kept += 1 if (old.target or "").strip() else 0
                row.update(target=old.target or "", draft=old.draft,
                           status=("cevrildi" if old.status in DONE else old.status) if (old.target or "").strip() else "bos",
                           submitted=old.submitted, translated_by=old.translated_by, translated_at=old.translated_at,
                           updated_by=old.updated_by, updated_at=old.updated_at)
            rows.append(row)
        conn.execute(sa.insert(SEGMENTS), rows)
        conn.execute(sa.update(JOBS).where(JOBS.c.id == job_id).values(
            source_version=version, source_filename=filename[:300], source_sha256=sha, source_bytes=len(data),
            source_path=path, completed_at=None))
    chapters = len({s["chapter"] for s in segs})
    return {"version": version, "segments": len(segs), "chapters": chapters, "words": sum(s["words"] for s in segs), "carried": kept}


def source_path(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str) -> tuple[str, str]:
    with engine.connect() as conn:
        job = _job(conn, tenant, job_id, user, see_all)
    if not job.source_path or not os.path.isfile(job.source_path):
        raise TranslationError("Kaynak dosya diskte bulunamadı.", 410)
    return job.source_path, job.source_filename or os.path.basename(job.source_path)


# ============================================================================================ segmentler

FILTERS = ("hepsi", "bos", "taslak", "cevrildi", "onaylandi", "sorunlu", "hatali", "taslakli")


def _seg_row(r: Any, issues: list[dict[str, str]], errors: int) -> dict[str, Any]:
    return {"id": r.id, "no": r.no, "para": r.para, "chapter": r.chapter, "heading": bool(r.heading), "source": r.source,
            "target": r.target or "", "status": r.status, "words": r.words, "hasDraft": bool(r.draft),
            "issues": issues, "errors": errors, "note": r.note,
            "edited": bool(r.submitted is not None and r.status == "onaylandi" and r.submitted != r.target),
            "updatedBy": r.updated_by, "updatedAt": _iso(r.updated_at)}


def _issues_all(conn: sa.Connection, tenant: str, job: Any, rows: list[Any]) -> dict[str, list[dict[str, str]]]:
    index = TermIndex(_terms_for(conn, tenant, job))
    job_level = job_checks(rows)
    return {r.id: check_segment(r.source, r.target or "", index.find(r.source)) + job_level.get(r.id, []) for r in rows}


def segments(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str,
             chapter: Optional[int], flt: str, q: str = "") -> dict[str, Any]:
    if flt not in FILTERS:
        raise TranslationError("Geçersiz süzgeç.")
    with engine.connect() as conn:
        job = _job(conn, tenant, job_id, user, see_all)
        rows = conn.execute(sa.select(SEGMENTS).where(SEGMENTS.c.job_id == job_id).order_by(SEGMENTS.c.no)).all()
        issues = _issues_all(conn, tenant, job, rows)
        errs = Counter(sid for (sid,) in conn.execute(sa.select(ERRORS.c.segment_id).where(ERRORS.c.job_id == job_id)).all())
    qf = fold(q.strip())
    out = []
    for r in rows:
        if chapter is not None and r.chapter != chapter:
            continue
        if flt in ("bos", "taslak", "cevrildi", "onaylandi") and r.status != flt:
            continue
        if flt == "sorunlu" and not issues[r.id]:
            continue
        if flt == "hatali" and not errs.get(r.id):
            continue
        if flt == "taslakli" and not (r.draft and r.status == "bos"):
            continue
        if qf and qf not in fold(r.source) and qf not in fold(r.target or ""):
            continue
        out.append(_seg_row(r, issues[r.id], errs.get(r.id, 0)))
    return {"items": out, "total": len(rows), "roles": _roles(job, user, see_all)}


def _tm(conn: sa.Connection, tenant: str, job: Any, seg: Any) -> list[dict[str, Any]]:
    """Çeviri belleği: aynı dil çiftinde çevrilmiş ya da onaylanmış segmentlerden birebir ve ≥%70 benzer olanlar.
    Aday kümesi kaynaktaki en uzun kelimeyle daraltılır, benzerlik difflib oranıyla ölçülür."""
    words = sorted(set(_WORD.findall(seg.source)), key=len, reverse=True)
    if not words or len(words[0]) < 4:
        return []
    key = words[0]
    n = len(seg.source)
    q = (sa.select(SEGMENTS.c.id, SEGMENTS.c.source, SEGMENTS.c.target, SEGMENTS.c.status, JOBS.c.title, JOBS.c.id.label("jid"))
         .join(JOBS, JOBS.c.id == SEGMENTS.c.job_id)
         .where(JOBS.c.tenant_id == tenant, JOBS.c.source_lang == job.source_lang, JOBS.c.target_lang == job.target_lang,
                SEGMENTS.c.status.in_(DONE), SEGMENTS.c.id != seg.id,
                sa.func.length(SEGMENTS.c.source).between(int(n * 0.6), int(n * 1.6) + 1),
                SEGMENTS.c.source.ilike(f"%{key}%")))
    seen: dict[str, dict[str, Any]] = {}
    src = _norm_src(seg.source)
    for r in conn.execute(q).all():
        ratio = difflib.SequenceMatcher(a=src, b=_norm_src(r.source), autojunk=False).ratio()
        if ratio < 0.7:
            continue
        k = " ".join(r.target.split())
        best = seen.get(k)
        if best is None or ratio > best["score"]:
            seen[k] = {"source": r.source, "target": r.target, "score": round(ratio * 100),
                       "status": r.status, "job": r.title, "sameJob": r.jid == job.id}
    return sorted(seen.values(), key=lambda x: (-x["score"], not x["sameJob"]))


def segment_detail(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, seg_id: str) -> dict[str, Any]:
    with engine.connect() as conn:
        s, job = _segment(conn, tenant, seg_id, user, see_all)
        terms = _terms_for(conn, tenant, job)
        hits = TermIndex(terms).find(s.source)
        rows = conn.execute(sa.select(SEGMENTS).where(SEGMENTS.c.job_id == job.id)).all()
        issues = check_segment(s.source, s.target or "", hits) + job_checks(rows).get(s.id, [])
        errs = conn.execute(sa.select(ERRORS).where(ERRORS.c.segment_id == seg_id).order_by(ERRORS.c.created_at)).all()
        tm = _tm(conn, tenant, job, s)
        ctx = conn.execute(sa.select(SEGMENTS.c.no, SEGMENTS.c.source, SEGMENTS.c.target).where(
            SEGMENTS.c.job_id == job.id, SEGMENTS.c.no.between(s.no - 2, s.no + 2), SEGMENTS.c.id != s.id).order_by(SEGMENTS.c.no)).all()
    seen: set[str] = set()
    term_out = []
    for t, a, b in hits:
        if t.id in seen:
            continue
        seen.add(t.id)
        term_out.append({"id": t.id, "source": t.source_term, "target": t.target_term, "forbidden": _forbidden(t), "note": t.note,
                         "status": t.status, "jobOnly": t.job_id is not None, "at": [a, b],
                         "ok": (not t.target_term) or target_has(s.target or "", t.target_term)})
    return {
        **_seg_row(s, issues, len(errs)), "chapterTitle": s.chapter_title, "draft": s.draft, "submitted": s.submitted,
        "translatedBy": s.translated_by, "translatedAt": _iso(s.translated_at), "approvedBy": s.approved_by,
        "approvedAt": _iso(s.approved_at),
        "diff": desk.diff_ops(s.submitted, s.target) if s.submitted is not None and s.submitted != s.target else [],
        "terms": term_out, "memory": tm,
        "context": [{"no": c.no, "source": c.source, "target": c.target or ""} for c in ctx],
        "errorList": [{"id": e.id, "category": e.category, "severity": e.severity, "note": e.note, "by": e.created_by,
                       "at": _iso(e.created_at)} for e in errs],
        "roles": _roles(job, user, see_all), "jobId": job.id,
    }


def _event(conn: sa.Connection, job_id: str, seg: Any, user: str, action: str) -> None:
    conn.execute(sa.insert(EVENTS).values(id=_new(), job_id=job_id, segment_id=seg.id, username=user.lower(),
                                          action=action, words=int(seg.words), at=_now()))


def save_segment(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, seg_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Çevirmenin kaydı: taslak (kaydet) ya da çevrildi (onayla). Onaylı segmenti yalnız inceleyen değiştirir."""
    target = str(body.get("target") if body.get("target") is not None else "")
    status = str(body.get("status") or "taslak")
    if status not in ("taslak", "cevrildi"):
        raise TranslationError("Durum «taslak» ya da «cevrildi» olmalı.")
    if len(target) > 20000:
        raise TranslationError("Segment çok uzun.")
    with engine.begin() as conn:
        s, job = _segment(conn, tenant, seg_id, user, see_all, lock=True)
        roles = _roles(job, user, see_all)
        if not roles["translate"]:
            raise TranslationError("Bu işte çevirmen değilsiniz.", 403)
        if s.status == "onaylandi":
            raise TranslationError("Segment onaylı; değiştirmek için inceleyen onayı geri almalı.", 409)
        if expected := body.get("updatedAt"):
            if _iso(s.updated_at) and expected != _iso(s.updated_at):
                raise TranslationError(f"Segment bu arada {s.updated_by or 'başka biri'} tarafından değiştirildi; yeniden açın.", 409)
        clean = target.strip()
        if status == "cevrildi" and not clean:
            raise TranslationError("Boş segment çevrildi olarak işaretlenemez.")
        new_status = status if clean else "bos"
        now = _now()
        v: dict[str, Any] = {"target": target if clean else "", "status": new_status, "updated_by": user.lower(), "updated_at": now}
        if new_status == "cevrildi":
            v.update(submitted=target, translated_by=user.lower(), translated_at=now)
            if s.status != "cevrildi":
                _event(conn, job.id, s, user, "cevrildi")
        elif s.status == "cevrildi":
            _event(conn, job.id, s, user, "geri")
        if "note" in body:
            v["note"] = str(body.get("note") or "").strip()[:2000] or None
        conn.execute(sa.update(SEGMENTS).where(SEGMENTS.c.id == seg_id).values(**v))
        # Aynı kaynak cümlesi işte başka yerde boşsa taslak olarak doldurulur (tekrar eden cümle).
        filled = 0
        if new_status == "cevrildi" and word_count(s.source) >= 1:
            for r in conn.execute(sa.select(SEGMENTS.c.id, SEGMENTS.c.source).where(
                    SEGMENTS.c.job_id == job.id, SEGMENTS.c.status == "bos", SEGMENTS.c.id != seg_id,
                    SEGMENTS.c.source == s.source)).all():
                conn.execute(sa.update(SEGMENTS).where(SEGMENTS.c.id == r.id).values(
                    target=target, status="taslak", updated_by=user.lower(), updated_at=now))
                filled += 1
        return {"status": new_status, "updatedAt": _iso(now), "repeatsFilled": filled}


def review_segment(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, seg_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """İnceleyen: onayla (gerekirse düzelterek) ya da onayı geri al / çevirmene geri gönder."""
    action = str(body.get("action") or "")
    if action not in ("onayla", "geri"):
        raise TranslationError("İşlem «onayla» ya da «geri» olmalı.")
    with engine.begin() as conn:
        s, job = _segment(conn, tenant, seg_id, user, see_all, lock=True)
        if not _roles(job, user, see_all)["review"]:
            raise TranslationError("Bu işte inceleyen değilsiniz.", 403)
        now = _now()
        if action == "onayla":
            target = str(body.get("target") if body.get("target") is not None else s.target or "")
            if not target.strip():
                raise TranslationError("Boş segment onaylanamaz.")
            if s.status == "bos":
                raise TranslationError("Çevrilmemiş segment onaylanamaz.", 409)
            v = {"target": target, "status": "onaylandi", "approved_by": user.lower(), "approved_at": now,
                 "updated_by": user.lower(), "updated_at": now}
            if s.submitted is None:
                v["submitted"] = s.target
            conn.execute(sa.update(SEGMENTS).where(SEGMENTS.c.id == seg_id).values(**v))
            if s.status != "onaylandi":
                _event(conn, job.id, s, user, "onaylandi")
        else:
            back = "taslak" if body.get("toTranslator") else "cevrildi"
            if s.status == "bos":
                raise TranslationError("Segment zaten boş.", 409)
            conn.execute(sa.update(SEGMENTS).where(SEGMENTS.c.id == seg_id).values(
                status=back, approved_by=None, approved_at=None, updated_by=user.lower(), updated_at=now,
                note=(str(body.get("note")).strip()[:2000] or None) if body.get("note") is not None else s.note))
            _event(conn, job.id, s, user, "geri")
        _sync_completed(conn, job.id)
        return {"updatedAt": _iso(now)}


def _sync_completed(conn: sa.Connection, job_id: str) -> None:
    left = conn.execute(sa.select(sa.func.count()).where(SEGMENTS.c.job_id == job_id, SEGMENTS.c.status != "onaylandi")).scalar_one()
    total = conn.execute(sa.select(sa.func.count()).where(SEGMENTS.c.job_id == job_id)).scalar_one()
    job = conn.execute(sa.select(JOBS.c.completed_at).where(JOBS.c.id == job_id)).first()
    if total and not left and job.completed_at is None:
        conn.execute(sa.update(JOBS).where(JOBS.c.id == job_id).values(completed_at=_now()))
    elif left and job.completed_at is not None:
        conn.execute(sa.update(JOBS).where(JOBS.c.id == job_id).values(completed_at=None))


def approve_many(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """İnceleyen, bir bölümün (ya da işin) çevrildi durumundaki segmentlerini düzeltmeden onaylar."""
    chapter = body.get("chapter")
    with engine.begin() as conn:
        job = _job(conn, tenant, job_id, user, see_all)
        if not _roles(job, user, see_all)["review"]:
            raise TranslationError("Bu işte inceleyen değilsiniz.", 403)
        q = sa.select(SEGMENTS).where(SEGMENTS.c.job_id == job_id, SEGMENTS.c.status == "cevrildi")
        if chapter is not None:
            q = q.where(SEGMENTS.c.chapter == int(chapter))
        rows = conn.execute(q.with_for_update()).all()
        now = _now()
        for s in rows:
            conn.execute(sa.update(SEGMENTS).where(SEGMENTS.c.id == s.id).values(
                status="onaylandi", approved_by=user.lower(), approved_at=now, updated_by=user.lower(), updated_at=now,
                submitted=s.submitted if s.submitted is not None else s.target))
            _event(conn, job_id, s, user, "onaylandi")
        _sync_completed(conn, job_id)
        return {"approved": len(rows)}


def add_error(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, seg_id: str, body: dict[str, Any]) -> dict[str, Any]:
    cat, sev = str(body.get("category") or ""), str(body.get("severity") or "")
    if cat not in CATEGORIES or sev not in SEVERITIES:
        raise TranslationError("Hata kategorisi ya da ağırlığı geçersiz.")
    with engine.begin() as conn:
        s, job = _segment(conn, tenant, seg_id, user, see_all)
        if not _roles(job, user, see_all)["review"]:
            raise TranslationError("Hata yalnız inceleyen tarafından işaretlenir.", 403)
        if s.status == "bos":
            raise TranslationError("Çevrilmemiş segmente hata işaretlenmez.", 409)
        eid = _new()
        conn.execute(sa.insert(ERRORS).values(id=eid, job_id=job.id, segment_id=seg_id, category=cat, severity=sev,
                                              note=str(body.get("note") or "").strip()[:2000] or None,
                                              created_by=user.lower(), created_at=_now()))
        return {"id": eid}


def delete_error(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, error_id: str) -> None:
    with engine.begin() as conn:
        e = conn.execute(sa.select(ERRORS).where(ERRORS.c.id == error_id)).first()
        if e is None:
            raise TranslationError("Hata kaydı bulunamadı.", 404)
        job = _job(conn, tenant, e.job_id, user, see_all)
        if not _roles(job, user, see_all)["review"]:
            raise TranslationError("Hata kaydını yalnız inceleyen kaldırır.", 403)
        conn.execute(sa.delete(ERRORS).where(ERRORS.c.id == error_id))


def use_draft(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """Boş segmentlere ZEKİ taslağını taslak olarak yerleştirir (bölüm ya da bütün iş). Çevrildi sayılmaz."""
    chapter = body.get("chapter")
    with engine.begin() as conn:
        job = _job(conn, tenant, job_id, user, see_all)
        if not _roles(job, user, see_all)["translate"]:
            raise TranslationError("Bu işte çevirmen değilsiniz.", 403)
        q = sa.update(SEGMENTS).where(SEGMENTS.c.job_id == job_id, SEGMENTS.c.status == "bos", SEGMENTS.c.draft.isnot(None),
                                      SEGMENTS.c.draft != "")
        if chapter is not None:
            q = q.where(SEGMENTS.c.chapter == int(chapter))
        n = conn.execute(q.values(target=SEGMENTS.c.draft, status="taslak", updated_by=user.lower(), updated_at=_now())).rowcount
        return {"filled": int(n or 0)}


# ============================================================================================ ZEKİ taslak

DRAFT_SYSTEM = (
    "Sen deneyimli bir kitap çevirmenisin. {src} metni {tgt} diline çeviriyorsun. Sana numaralı cümleler JSON "
    "olarak verilecek. Her cümleyi anlamı, tonu ve üslubu koruyarak, doğal bir {tgt} ile çevir. Cümleleri "
    "birleştirme ya da bölme; her numaraya tam olarak bir çeviri ver. «terimler» listesindeki karşılıkları kullan. "
    "Özel adları ve sayıları koru. «baglam» yalnız anlamak içindir, onu çevirme. Cevabın yalnız bir JSON dizisi "
    'olsun, başka hiçbir şey yazma: [{{"n": <numara>, "t": "<çeviri>"}}].'
)


def _batches(rows: list[Any], words: int = 600, count: int = 40) -> Iterable[list[Any]]:
    cur: list[Any] = []
    n = 0
    for r in rows:
        if cur and (n + r.words > words or len(cur) >= count):
            yield cur
            cur, n = [], 0
        cur.append(r)
        n += r.words
    if cur:
        yield cur


def _parse_draft(answer: str) -> dict[int, str]:
    m = re.search(r"\[.*\]", answer or "", re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(0))
    except ValueError:
        return {}
    out = {}
    for d in data:
        if isinstance(d, dict) and isinstance(d.get("t"), str) and d["t"].strip():
            try:
                out[int(d.get("n"))] = d["t"].strip()
            except (TypeError, ValueError):
                continue
    return out


def start_draft(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str, body: dict[str, Any],
                chat: Optional[Callable[[list[dict[str, str]]], str]]) -> dict[str, Any]:
    if chat is None:
        raise TranslationError("Model bağlantısı tanımlı değil.", 503)
    chapter = body.get("chapter")
    with engine.begin() as conn:
        job = _job(conn, tenant, job_id, user, see_all)
        if not _roles(job, user, see_all)["manage"]:
            raise TranslationError("ZEKİ taslağını yalnız işi açan kişi ya da yetkili yönetici başlatır.", 403)
        with _lock:
            if job.draft_state == "calisiyor" or job_id in _running:
                raise TranslationError("Bu işte taslak zaten sürüyor.", 409)
            _running.add(job_id)
        q = sa.select(SEGMENTS).where(SEGMENTS.c.job_id == job_id, SEGMENTS.c.status == "bos",
                                      sa.or_(SEGMENTS.c.draft.is_(None), SEGMENTS.c.draft == ""))
        if chapter is not None:
            q = q.where(SEGMENTS.c.chapter == int(chapter))
        todo = conn.execute(q.order_by(SEGMENTS.c.no)).all()
        if not todo:
            _running.discard(job_id)
            raise TranslationError("Taslak bekleyen boş segment yok.", 409)
        terms = [t for t in _terms_for(conn, tenant, job) if t.status == "onayli" and t.target_term]
        conn.execute(sa.update(JOBS).where(JOBS.c.id == job_id).values(
            draft_state="calisiyor", draft_note=None, draft_done=0, draft_total=len(todo)))
    index = TermIndex(terms)
    system = DRAFT_SYSTEM.format(src=LANGS[job.source_lang], tgt=LANGS[job.target_lang])
    ids = [r.id for r in todo]

    def run() -> None:
        done = missed = 0
        state, note = "bitti", None
        try:
            for batch in _batches(todo):
                first = batch[0].no
                with engine.connect() as conn:
                    ctx = conn.execute(sa.select(SEGMENTS.c.source).where(
                        SEGMENTS.c.job_id == job_id, SEGMENTS.c.no.between(first - 3, first - 1)).order_by(SEGMENTS.c.no)).scalars().all()
                used: dict[str, str] = {}
                for r in batch:
                    for t, _, _ in index.find(r.source):
                        used[t.source_term] = t.target_term.split("|")[0].strip()
                payload = {"eser": job.title, "baglam": " ".join(ctx),
                           "terimler": [{"kaynak": k, "hedef": v} for k, v in used.items()],
                           "cumleler": [{"n": i, "t": r.source} for i, r in enumerate(batch, 1)]}
                got = _parse_draft(chat([{"role": "system", "content": system},
                                         {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]))
                with engine.begin() as conn:
                    for i, r in enumerate(batch, 1):
                        t = got.get(i)
                        if not t:
                            missed += 1
                            continue
                        # Bu arada çevirmen yazdıysa taslak yine yazılır, hedefe dokunulmaz.
                        conn.execute(sa.update(SEGMENTS).where(SEGMENTS.c.id == r.id).values(draft=t[:20000]))
                        done += 1
                    conn.execute(sa.update(JOBS).where(JOBS.c.id == job_id).values(draft_done=done + missed))
            note = f"{done} segmente taslak yazıldı" + (f"; {missed} segment için model cevap vermedi, yeniden başlatılabilir" if missed else "")
        except Exception as e:  # noqa: BLE001
            log.exception("translation draft failed")
            state, note = "hata", (f"{done} segmente taslak yazıldıktan sonra durdu: " + str(e))[:480]
        finally:
            _running.discard(job_id)
            with engine.begin() as conn:
                conn.execute(sa.update(JOBS).where(JOBS.c.id == job_id).values(draft_state=state, draft_note=note))

    threading.Thread(target=run, name=f"translation-draft-{job_id[:8]}", daemon=True).start()
    return {"segments": len(ids)}


# ============================================================================================ terim bankası

def _term_out(t: Any, hits: int = 0) -> dict[str, Any]:
    return {"id": t.id, "sourceLang": t.source_lang, "targetLang": t.target_lang, "source": t.source_term, "target": t.target_term,
            "forbidden": _forbidden(t), "note": t.note, "jobId": t.job_id, "status": t.status, "createdBy": t.created_by,
            "createdAt": _iso(t.created_at), "updatedBy": t.updated_by, "updatedAt": _iso(t.updated_at), "uses": hits}


def list_terms(engine: sa.engine.Engine, tenant: str, src: Optional[str], tgt: Optional[str], q: str = "",
               status: Optional[str] = None, job_id: Optional[str] = None) -> dict[str, Any]:
    with engine.connect() as conn:
        s = sa.select(TERMS).where(TERMS.c.tenant_id == tenant)
        if src:
            s = s.where(TERMS.c.source_lang == src)
        if tgt:
            s = s.where(TERMS.c.target_lang == tgt)
        if status in ("onayli", "aday"):
            s = s.where(TERMS.c.status == status)
        if job_id:
            s = s.where(sa.or_(TERMS.c.job_id.is_(None), TERMS.c.job_id == job_id))
        rows = conn.execute(s.order_by(sa.func.lower(TERMS.c.source_term))).all()
        jobs = {r.id: r.title for r in conn.execute(sa.select(JOBS.c.id, JOBS.c.title).where(JOBS.c.tenant_id == tenant)).all()}
    qf = fold(q.strip())
    items = []
    for t in rows:
        if qf and qf not in fold(t.source_term) and qf not in fold(t.target_term or "") and qf not in fold(t.note or ""):
            continue
        d = _term_out(t)
        d["jobTitle"] = jobs.get(t.job_id) if t.job_id else None
        items.append(d)
    return {"items": items, "languages": LANGS}


def _clean_term(body: dict[str, Any]) -> dict[str, Any]:
    src_term = " ".join(str(body.get("source") or "").split())[:300]
    if not src_term:
        raise TranslationError("Kaynak terim gerekli.")
    forb = body.get("forbidden") or []
    if isinstance(forb, str):
        forb = [x for x in re.split(r"[;\n]", forb)]
    return {"source_term": src_term, "target_term": " ".join(str(body.get("target") or "").split())[:300],
            "forbidden_json": json.dumps(sorted({" ".join(str(x).split()) for x in forb if str(x).strip()}), ensure_ascii=False),
            "note": str(body.get("note") or "").strip()[:2000] or None}


def _dup(conn: sa.Connection, tenant: str, src: str, tgt: str, term: str, job_id: Optional[str], skip: Optional[str] = None) -> Optional[Any]:
    q = sa.select(TERMS).where(TERMS.c.tenant_id == tenant, TERMS.c.source_lang == src, TERMS.c.target_lang == tgt,
                               sa.func.lower(TERMS.c.source_term) == term.lower(),
                               TERMS.c.job_id.is_(None) if job_id is None else TERMS.c.job_id == job_id)
    if skip:
        q = q.where(TERMS.c.id != skip)
    return conn.execute(q).first()


def create_term(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, body: dict[str, Any], propose: bool) -> dict[str, Any]:
    """Terim ekler. `propose`: çevirmenin önerisi (aday, işe bağlı); onaylı terimi yalnız terim yetkisi olan yazar."""
    v = _clean_term(body)
    job_id = str(body.get("jobId") or "").strip() or None
    with engine.begin() as conn:
        if job_id:
            job = _job(conn, tenant, job_id, user, see_all)
            src, tgt = job.source_lang, job.target_lang
        else:
            if propose:
                raise TranslationError("Öneri bir işe bağlı olmalı.")
            src, tgt = _lang(body.get("sourceLang"), "Kaynak"), _lang(body.get("targetLang"), "Hedef")
        if (propose or body.get("status") != "aday") and not v["target_term"]:
            raise TranslationError("Hedef karşılık gerekli.")
        if _dup(conn, tenant, src, tgt, v["source_term"], job_id):
            raise TranslationError("Bu terim bu dil çiftinde zaten var.", 409)
        tid = _new()
        conn.execute(sa.insert(TERMS).values(id=tid, tenant_id=tenant, source_lang=src, target_lang=tgt, job_id=job_id,
                                             status="aday" if propose or body.get("status") == "aday" else "onayli",
                                             created_by=user.lower(), created_at=_now(), **v))
        return {"id": tid}


def update_term(engine: sa.engine.Engine, tenant: str, user: str, term_id: str, body: dict[str, Any]) -> None:
    with engine.begin() as conn:
        t = conn.execute(sa.select(TERMS).where(TERMS.c.id == term_id, TERMS.c.tenant_id == tenant)).first()
        if t is None:
            raise TranslationError("Terim bulunamadı.", 404)
        v = _clean_term({"source": body.get("source", t.source_term), "target": body.get("target", t.target_term),
                         "forbidden": body.get("forbidden", _forbidden(t)), "note": body.get("note", t.note)})
        if "status" in body:
            if body["status"] not in ("onayli", "aday"):
                raise TranslationError("Durum «onayli» ya da «aday» olmalı.")
            v["status"] = body["status"]
        if "global" in body and body["global"]:
            v["job_id"] = None
        if (v.get("status", t.status) == "onayli") and not v["target_term"]:
            raise TranslationError("Onaylı terimin hedef karşılığı olmalı.")
        if _dup(conn, tenant, t.source_lang, t.target_lang, v["source_term"], v.get("job_id", t.job_id), skip=term_id):
            raise TranslationError("Bu terim bu dil çiftinde zaten var.", 409)
        conn.execute(sa.update(TERMS).where(TERMS.c.id == term_id).values(updated_by=user.lower(), updated_at=_now(), **v))


def delete_term(engine: sa.engine.Engine, tenant: str, term_id: str) -> str:
    with engine.begin() as conn:
        t = conn.execute(sa.select(TERMS).where(TERMS.c.id == term_id, TERMS.c.tenant_id == tenant)).first()
        if t is None:
            raise TranslationError("Terim bulunamadı.", 404)
        conn.execute(sa.delete(TERMS).where(TERMS.c.id == term_id))
        return t.source_term


def import_terms(engine: sa.engine.Engine, tenant: str, user: str, src: str, tgt: str, data: bytes) -> dict[str, Any]:
    """CSV/TSV: kaynak, hedef, [yasak karşılıklar (; ile)], [not]. İlk satır başlıksa atlanır. Var olan terim güncellenir."""
    src, tgt = _lang(src, "Kaynak"), _lang(tgt, "Hedef")
    text = data.decode("utf-8-sig", errors="replace")
    if not text.strip():
        raise TranslationError("Dosya boş.")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = list(csv.reader(io.StringIO(text), dialect))
    if rows and fold(rows[0][0]).strip() in ("kaynak", "source", "kaynak terim", "terim"):
        rows = rows[1:]
    added = updated = skipped = 0
    now = _now()
    with engine.begin() as conn:
        for r in rows:
            if len(r) < 2 or not r[0].strip() or not r[1].strip():
                skipped += 1
                continue
            v = _clean_term({"source": r[0], "target": r[1], "forbidden": r[2] if len(r) > 2 else "", "note": r[3] if len(r) > 3 else ""})
            old = _dup(conn, tenant, src, tgt, v["source_term"], None)
            if old is not None:
                conn.execute(sa.update(TERMS).where(TERMS.c.id == old.id).values(status="onayli", updated_by=user.lower(), updated_at=now, **v))
                updated += 1
            else:
                conn.execute(sa.insert(TERMS).values(id=_new(), tenant_id=tenant, source_lang=src, target_lang=tgt, job_id=None,
                                                     status="onayli", created_by=user.lower(), created_at=now, **v))
                added += 1
    return {"added": added, "updated": updated, "skipped": skipped}


def export_terms(engine: sa.engine.Engine, tenant: str, src: Optional[str], tgt: Optional[str]) -> bytes:
    data = list_terms(engine, tenant, src, tgt)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["kaynak", "hedef", "yasak", "not", "kaynak dil", "hedef dil", "durum", "iş"])
    for t in data["items"]:
        w.writerow([t["source"], t["target"], "; ".join(t["forbidden"]), t["note"] or "", t["sourceLang"], t["targetLang"],
                    "onaylı" if t["status"] == "onayli" else "aday", t.get("jobTitle") or ""])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def term_candidates(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str) -> list[dict[str, Any]]:
    """Kaynakta cümle ortasında büyük harfle en az 3 kez geçen (özel ad) kelime ve ikili öbekler, bankada yoksa.
    Çeviride tutarlı yazılması gereken adları çıkarır; model kullanmaz."""
    with engine.connect() as conn:
        job = _job(conn, tenant, job_id, user, see_all)
        rows = conn.execute(sa.select(SEGMENTS.c.source, SEGMENTS.c.heading).where(SEGMENTS.c.job_id == job_id)).all()
        known = {" ".join(fold(t.source_term).split()) for t in _terms_for(conn, tenant, job)}
    counts: Counter = Counter()
    examples: dict[str, str] = {}
    lower_seen: set[str] = set()
    for src, heading in rows:
        if heading:
            continue
        toks = re.findall(r"[^\W\d_][^\W_'’-]*(?:['’-][^\W\d_]+)?", src)
        for w in toks:
            if w[:1].islower():
                lower_seen.add(fold(w))
        i = 1   # cümlenin ilk kelimesi büyük harfle başlar; ad sayılmaz
        while i < len(toks):
            w = toks[i]
            if not w[:1].isupper() or len(w) < 3 or (w.isupper() and len(w) > 5):
                i += 1
                continue
            key = w
            if i + 1 < len(toks) and toks[i + 1][:1].isupper() and len(toks[i + 1]) >= 2:
                key = f"{w} {toks[i + 1]}"
                i += 1
            counts[key] += 1
            examples.setdefault(key, src[:240])
            i += 1
    out = []
    for k, n in counts.most_common():
        if n < 3:
            break
        fk = " ".join(fold(k).split())
        if fk in known or (" " not in k and fk in lower_seen):
            continue
        out.append({"term": k, "count": n, "example": examples[k]})
    return out


# ============================================================================================ kalite raporu

def quality(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str) -> dict[str, Any]:
    with engine.connect() as conn:
        job = _job(conn, tenant, job_id, user, see_all)
        base = _summary(conn, job, _counts(conn, [job_id])[job_id], user, see_all)
        rows = conn.execute(sa.select(SEGMENTS).where(SEGMENTS.c.job_id == job_id).order_by(SEGMENTS.c.no)).all()
        terms = _terms_for(conn, tenant, job)
        errs = conn.execute(sa.select(ERRORS).where(ERRORS.c.job_id == job_id)).all()
        events = conn.execute(sa.select(EVENTS.c.username, EVENTS.c.action, EVENTS.c.words, EVENTS.c.at)
                              .where(EVENTS.c.job_id == job_id).order_by(EVENTS.c.at)).all()
    index = TermIndex(terms)
    jl = job_checks(rows)
    by_code: Counter = Counter()
    flagged: list[dict[str, Any]] = []
    term_uses = term_ok = 0
    per_term: dict[str, dict[str, Any]] = {}
    for r in rows:
        hits = index.find(r.source)
        issues = check_segment(r.source, r.target or "", hits) + jl.get(r.id, [])
        if (r.target or "").strip():
            for t in {t.id: t for t, _, _ in hits}.values():
                if t.status != "onayli" or not t.target_term:
                    continue
                ok = target_has(r.target, t.target_term)
                term_uses += 1
                term_ok += ok
                d = per_term.setdefault(t.id, {"source": t.source_term, "target": t.target_term, "uses": 0, "ok": 0})
                d["uses"] += 1
                d["ok"] += ok
        for i in issues:
            by_code[i["code"]] += 1
        if issues:
            flagged.append({"id": r.id, "no": r.no, "chapter": r.chapter, "source": r.source, "target": r.target, "status": r.status, "issues": issues})
    reviewed = [r for r in rows if r.status == "onaylandi"]
    ewc = sum(r.words for r in reviewed)
    by_seg = {r.id: r for r in rows}
    cat: dict[str, dict[str, int]] = {k: {s: 0 for s in SEVERITIES} for k in CATEGORIES}
    apt = 0
    for e in errs:
        if e.category in cat and e.severity in SEVERITIES:
            cat[e.category][e.severity] += 1
            apt += SEVERITIES[e.severity][1]
    mqm = round((1 - apt / ewc) * 100, 2) if ewc else None
    edited = [r for r in reviewed if r.submitted is not None and r.submitted != r.target]
    wsum = sum(r.words for r in reviewed) or 0
    edit_rate = None
    if wsum:
        edit_rate = round(sum((1 - difflib.SequenceMatcher(a=r.submitted or r.target, b=r.target, autojunk=False).ratio()) * r.words
                              for r in reviewed) / wsum * 100, 2)
    chapters: dict[int, dict[str, Any]] = {}
    for r in rows:
        c = chapters.setdefault(r.chapter, {"no": r.chapter, "title": r.chapter_title, "words": 0, "done": 0, "approved": 0,
                                            "issues": 0, "errors": 0, "penalty": 0, "reviewedWords": 0})
        c["words"] += r.words
        if r.status in DONE:
            c["done"] += r.words
        if r.status == "onaylandi":
            c["approved"] += r.words
            c["reviewedWords"] += r.words
    for f in flagged:
        chapters[f["chapter"]]["issues"] += len(f["issues"])
    for e in errs:
        s = by_seg.get(e.segment_id)
        if s is not None and e.severity in SEVERITIES:
            chapters[s.chapter]["errors"] += 1
            chapters[s.chapter]["penalty"] += SEVERITIES[e.severity][1]
    for c in chapters.values():
        c["mqm"] = round((1 - c["penalty"] / c["reviewedWords"]) * 100, 2) if c["reviewedWords"] else None
    daily: dict[str, dict[str, int]] = defaultdict(lambda: {"cevrildi": 0, "onaylandi": 0, "geri": 0})
    people: dict[str, dict[str, int]] = defaultdict(lambda: {"cevrildi": 0, "onaylandi": 0, "geri": 0})
    for u, a, w, at in events:
        d = (at if at.tzinfo else at.replace(tzinfo=timezone.utc)).date().isoformat()
        daily[d][a] += int(w)
        people[u][a] += int(w)
    error_list = [{"id": e.id, "segmentNo": by_seg[e.segment_id].no if e.segment_id in by_seg else None, "segmentId": e.segment_id,
                   "category": e.category, "severity": e.severity, "note": e.note, "by": e.created_by, "at": _iso(e.created_at),
                   "source": by_seg[e.segment_id].source if e.segment_id in by_seg else "",
                   "target": by_seg[e.segment_id].target if e.segment_id in by_seg else ""} for e in errs]
    error_list.sort(key=lambda x: (x["segmentNo"] or 0))
    return {
        **base,
        "mqm": {"score": mqm, "penalty": apt, "reviewedWords": ewc, "weights": {k: w for k, (_, w) in SEVERITIES.items()},
                "categories": cat, "errors": len(errs)},
        "edits": {"segments": len(edited), "reviewed": len(reviewed), "rate": edit_rate},
        "checks": {"byCode": dict(by_code), "segments": len(flagged), "labels": QA_LABELS, "items": flagged},
        "terms": {"uses": term_uses, "ok": term_ok, "items": sorted(per_term.values(), key=lambda d: (d["ok"] - d["uses"], -d["uses"]))},
        "chapters": [chapters[k] for k in sorted(chapters)],
        "daily": [{"date": k, **v} for k, v in sorted(daily.items())],
        "people": [{"username": k, **v} for k, v in sorted(people.items())],
        "errorList": error_list, "categoryLabels": CATEGORIES,
        "severityLabels": {k: v[0] for k, v in SEVERITIES.items()},
    }


def quality_csv(report: dict[str, Any]) -> bytes:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    labels = report["checks"]["labels"]
    w.writerow(["segment", "bölüm", "durum", "tür", "kod", "açıklama", "kaynak", "hedef"])
    for f in report["checks"]["items"]:
        for i in f["issues"]:
            w.writerow([f["no"], f["chapter"], f["status"], "otomatik denetim", labels.get(i["code"], i["code"]), i["text"], f["source"], f["target"]])
    for e in report["errorList"]:
        w.writerow([e["segmentNo"], "", "", "inceleme hatası", f"{report['categoryLabels'].get(e['category'])} / "
                    f"{report['severityLabels'].get(e['severity'])}", e["note"] or "", e["source"], e["target"]])
    return ("﻿" + buf.getvalue()).encode("utf-8")


def translators(engine: sa.engine.Engine, tenant: str) -> list[dict[str, Any]]:
    """İşlerimizdeki çevirmenlerin karnesi: iş sayısı, çevrilen kelime, inceleme puanı, teslim."""
    with engine.connect() as conn:
        jobs = conn.execute(sa.select(JOBS).where(JOBS.c.tenant_id == tenant, JOBS.c.translator.isnot(None))).all()
        if not jobs:
            return []
        counts = _counts(conn, [j.id for j in jobs])
        rev = {jid: (int(w or 0)) for jid, w in conn.execute(sa.select(SEGMENTS.c.job_id, sa.func.sum(SEGMENTS.c.words)).where(
            SEGMENTS.c.job_id.in_([j.id for j in jobs]), SEGMENTS.c.status == "onaylandi").group_by(SEGMENTS.c.job_id)).all()}
        pen: dict[str, int] = defaultdict(int)
        for jid, sev in conn.execute(sa.select(ERRORS.c.job_id, ERRORS.c.severity).where(ERRORS.c.job_id.in_([j.id for j in jobs]))).all():
            pen[jid] += SEVERITIES.get(sev, ("", 0))[1]
    out: dict[str, dict[str, Any]] = {}
    for j in jobs:
        d = out.setdefault(j.translator, {"username": j.translator, "name": j.translator_name, "jobs": 0, "active": 0, "completed": 0,
                                          "onTime": 0, "late": 0, "words": 0, "wordsDone": 0, "reviewedWords": 0, "penalty": 0,
                                          "pairs": set()})
        c = counts[j.id]
        d["name"] = d["name"] or j.translator_name
        d["jobs"] += 1
        d["pairs"].add(f"{j.source_lang}→{j.target_lang}")
        stage = _stage(c)
        if stage == "tamamlandi":
            d["completed"] += 1
            if j.due_date and j.completed_at:
                ca = j.completed_at if j.completed_at.tzinfo else j.completed_at.replace(tzinfo=timezone.utc)
                d["onTime" if ca.date() <= j.due_date else "late"] += 1
        elif stage != "kaynak":
            d["active"] += 1
        d["words"] += sum(c["words"].values())
        d["wordsDone"] += c["words"].get("cevrildi", 0) + c["words"].get("onaylandi", 0)
        d["reviewedWords"] += rev.get(j.id, 0)
        d["penalty"] += pen.get(j.id, 0)
    res = []
    for d in out.values():
        d["pairs"] = sorted(d["pairs"])
        d["mqm"] = round((1 - d["penalty"] / d["reviewedWords"]) * 100, 2) if d["reviewedWords"] else None
        res.append(d)
    return sorted(res, key=lambda d: (-d["active"], -d["wordsDone"]))


# ============================================================================================ dışa / içe aktarım

_DOCX_CT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
            '</Types>')
_DOCX_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
              '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
              '</Relationships>')
_DOC_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
             '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
             '</Relationships>')
_STYLES = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
           '<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/>'
           '<w:pPr><w:spacing w:after="160" w:line="300" w:lineRule="auto"/></w:pPr><w:rPr><w:sz w:val="24"/></w:rPr></w:style>'
           '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>'
           '<w:pPr><w:keepNext/><w:spacing w:before="360" w:after="200"/><w:outlineLvl w:val="0"/></w:pPr>'
           '<w:rPr><w:b/><w:sz w:val="32"/></w:rPr></w:style></w:styles>')


def _xml_text(s: str) -> str:
    # XML 1.0'da geçersiz denetim karakterleri atılır.
    return xml_escape(re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", s or ""))


def build_docx(paras: list[tuple[str, bool]]) -> bytes:
    body = []
    for text, heading in paras:
        ppr = '<w:pPr><w:pStyle w:val="Heading1"/></w:pPr>' if heading else ""
        body.append(f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{_xml_text(text)}</w:t></w:r></w:p>')
    doc = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
           '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + "".join(body) + '<w:sectPr/></w:body></w:document>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _DOCX_CT)
        z.writestr("_rels/.rels", _DOCX_RELS)
        z.writestr("word/_rels/document.xml.rels", _DOC_RELS)
        z.writestr("word/styles.xml", _STYLES)
        z.writestr("word/document.xml", doc)
    return buf.getvalue()


def _target_paragraphs(rows: list[Any], mark_missing: bool) -> tuple[list[tuple[str, bool]], int]:
    paras: dict[int, list[str]] = {}
    heads: dict[int, bool] = {}
    missing = 0
    for r in rows:
        t = (r.target or "").strip()
        if not t:
            missing += 1
            t = f"[ÇEVRİLMEDİ] {r.source}" if mark_missing else r.source
        paras.setdefault(r.para, []).append(t)
        heads[r.para] = bool(r.heading)
    return [(" ".join(paras[p]), heads[p]) for p in sorted(paras)], missing


def export_docx(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str) -> tuple[bytes, str, int]:
    with engine.connect() as conn:
        job = _job(conn, tenant, job_id, user, see_all)
        rows = conn.execute(sa.select(SEGMENTS).where(SEGMENTS.c.job_id == job_id).order_by(SEGMENTS.c.no)).all()
    if not rows:
        raise TranslationError("Bu işte segment yok.", 409)
    paras, missing = _target_paragraphs(rows, True)
    return build_docx(paras), f"{_safe(job.title)}-{job.target_lang}.docx", missing


def _safe(name: str) -> str:
    return re.sub(r"[^\w\-]+", "-", name, flags=re.UNICODE).strip("-")[:80] or "ceviri"


_XLF_NS = "urn:oasis:names:tc:xliff:document:1.2"
_STATE = {"bos": "new", "taslak": "needs-review-translation", "cevrildi": "translated", "onaylandi": "signed-off"}


def export_xliff(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str) -> tuple[bytes, str]:
    with engine.connect() as conn:
        job = _job(conn, tenant, job_id, user, see_all)
        rows = conn.execute(sa.select(SEGMENTS).where(SEGMENTS.c.job_id == job_id).order_by(SEGMENTS.c.no)).all()
    if not rows:
        raise TranslationError("Bu işte segment yok.", 409)
    out = [f'<?xml version="1.0" encoding="UTF-8"?>\n<xliff version="1.2" xmlns="{_XLF_NS}">',
           f'<file original="{_xml_text(job.title)}" source-language="{job.source_lang}" target-language="{job.target_lang}" '
           f'datatype="plaintext" product-name="ZEKİ AI" product-version="{job.source_version}"><body>']
    chapter = None
    for r in rows:
        if r.chapter != chapter:
            if chapter is not None:
                out.append("</group>")
            chapter = r.chapter
            out.append(f'<group id="bolum-{r.chapter}" resname="{_xml_text(r.chapter_title)}">')
        state = _STATE.get(r.status, "new")
        tgt = f'<target state="{state}">{_xml_text(r.target)}</target>' if (r.target or "").strip() else ""
        locked = ' translate="no"' if r.status == "onaylandi" else ""
        out.append(f'<trans-unit id="{r.id}" resname="{r.no}"{locked}><source>{_xml_text(r.source)}</source>{tgt}</trans-unit>')
    if chapter is not None:
        out.append("</group>")
    out.append("</body></file></xliff>")
    return "\n".join(out).encode("utf-8"), f"{_safe(job.title)}-{job.source_lang}-{job.target_lang}.xlf"


def _inner_text(el: Any) -> str:
    """<target> içindeki düz metin; satır içi etiketlerin (g, x, mrk…) metni korunur."""
    return "".join(el.itertext()) if el is not None else ""


def import_xliff(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str, data: bytes) -> dict[str, Any]:
    """XLIFF 1.2 (ya da 2.0) içe aktarımı: yalnız bu işin segment kimlikleri, onaylı segmentlere dokunulmaz.
    Durum translated/final/signed-off/reviewed ise çevrildi, değilse taslak."""
    head = data[:4096].decode("utf-8", errors="ignore")
    if "<!DOCTYPE" in head.upper() or "<!ENTITY" in head.upper():
        raise TranslationError("XLIFF dosyasında DOCTYPE/ENTITY kabul edilmez.")
    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as e:
        raise TranslationError("XLIFF dosyası okunamadı.") from e
    units: dict[str, tuple[str, str]] = {}
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag == "trans-unit":
            tgt = next((c for c in el if c.tag.split("}")[-1] == "target"), None)
            if tgt is not None:
                units[el.get("id") or ""] = (_inner_text(tgt), tgt.get("state") or "")
        elif tag == "unit":   # XLIFF 2.0
            segs = [c for c in el.iter() if c.tag.split("}")[-1] == "segment"]
            for sg in segs:
                tgt = next((c for c in sg if c.tag.split("}")[-1] == "target"), None)
                if tgt is not None:
                    units[el.get("id") or ""] = (_inner_text(tgt), sg.get("state") or "")
    done_states = {"translated", "final", "signed-off", "reviewed", "needs-review-l10n"}
    updated = confirmed = skipped_locked = unknown = unchanged = 0
    now = _now()
    with engine.begin() as conn:
        job = _job(conn, tenant, job_id, user, see_all)
        if not _roles(job, user, see_all)["translate"]:
            raise TranslationError("Bu işte çevirmen değilsiniz.", 403)
        rows = {r.id: r for r in conn.execute(sa.select(SEGMENTS).where(SEGMENTS.c.job_id == job_id).with_for_update()).all()}
        for uid, (text, state) in units.items():
            s = rows.get(uid)
            if s is None:
                unknown += 1
                continue
            if s.status == "onaylandi":
                skipped_locked += 1
                continue
            text = re.sub(r"\s+", " ", text).strip()
            if not text:
                continue
            status = "cevrildi" if state in done_states else "taslak"
            if text == (s.target or "") and status == s.status:
                unchanged += 1
                continue
            v: dict[str, Any] = {"target": text, "status": status, "updated_by": user.lower(), "updated_at": now}
            if status == "cevrildi":
                v.update(submitted=text, translated_by=user.lower(), translated_at=now)
                if s.status != "cevrildi":
                    _event(conn, job_id, s, user, "cevrildi")
                confirmed += 1
            conn.execute(sa.update(SEGMENTS).where(SEGMENTS.c.id == uid).values(**v))
            updated += 1
    if not units:
        raise TranslationError("Dosyada hedef metni olan segment yok.")
    return {"updated": updated, "confirmed": confirmed, "locked": skipped_locked, "unknown": unknown, "unchanged": unchanged}


def to_redaction(engine: sa.engine.Engine, tenant: str, user: str, see_all: bool, job_id: str, desk_admin: bool) -> dict[str, Any]:
    """Biten çeviriyi M3 Redaksiyon'a yeni metin sürümü olarak gönderir (eser dosyası yoksa açılır)."""
    with engine.connect() as conn:
        job = _job(conn, tenant, job_id, user, see_all)
        if not _roles(job, user, see_all)["manage"]:
            raise TranslationError("Redaksiyona yalnız işi açan kişi ya da yetkili yönetici aktarır.", 403)
        rows = conn.execute(sa.select(SEGMENTS).where(SEGMENTS.c.job_id == job_id).order_by(SEGMENTS.c.no)).all()
    if not rows:
        raise TranslationError("Bu işte segment yok.", 409)
    open_ = sum(1 for r in rows if r.status not in DONE)
    if open_:
        raise TranslationError(f"{open_} segment henüz çevrilmedi; çeviri bitmeden redaksiyona aktarılamaz.", 409)
    paras, _ = _target_paragraphs(rows, False)
    data = build_docx(paras)
    work_id = job.work_id
    try:
        if work_id is None:
            members = [m for m in (job.translator, job.reviewer) if m]
            work_id = desk.create_work(engine, tenant, user, {"title": job.title, "author": job.author, "members": members})["id"]
        out = desk.upload_manuscript(engine, tenant, user, desk_admin or see_all, work_id,
                                     f"{_safe(job.title)}-{job.target_lang}-ceviri.docx", data)
    except desk.DeskError as e:
        raise TranslationError(str(e), e.status) from e
    with engine.begin() as conn:
        conn.execute(sa.update(JOBS).where(JOBS.c.id == job_id).values(work_id=work_id))
    return {"workId": work_id, "version": out["version"], "chapters": out["chapters"]}
