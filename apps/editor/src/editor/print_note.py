"""Baskı/üretim notu ve kitabın dilinde olmayan çeviri kaynağı satırı: sayfada duran ama kitabın metni olmayan satırlar.

Sorun (2026-10-06 denetimi, 44 arşiv okuması — K20): dizgi dosyalarında (özalit, iç baskı, kapak) tasarımcının ve
matbaanın notları sayfanın metin katmanında kalıyor: «BIÇAK», «KAPAK içine baskı», «Pencere açıldığında görünen
kısım», «PANTONE 129», «EBAT: 22 X 22». Çeviri kitabın dizgi dosyasında özgün dilin satırları da duruyor («Ist ein
Geräusch aus dem Weltall zu hören?»). Bunlar bölüm adı oldu (dört kitapta bölümlerin hepsi), okumaya ve aramaya girdi.

Kural (kitaptan bağımsız; ad listesi yok, yalnız satırın kendisi ve kitabın geneli):
- Dizgi notu (`is_print_note`, `DIZGI`): satır yalnız baskı hazırlığında kullanılan bir terimden ibaret — «içine
  baskı», «pencere açıldığında görünen kısım», «Pantone 129», CMYK, taşma payı, özalit, selefon, sırt kalınlığı,
  spot lak. Öykünün diliyle karışan terimler («bıçak izi», «kesim çizgisi», «katlama çizgisi»: yara izi, etkinlik
  yönergesi) yok. Büyük harfle tek başına «BIÇAK» (kesim kalıbı) yalnız dizgi dosyasında (`is_production_file`:
  kitapta nottan ibaret bir dizgi satırı ya da en az iki tek başına «BIÇAK»): alfabe kitabının «BIÇAK»ı not değil.
  Notla metin aynı satırdaysa («KAPAK içine baskı İşte burada!») satır gövdedir; not parçası `strip_notes` ile
  çıkar (yalnız dizgi dosyasında).
- Ölçü satırı (`SPEC`): «EBAT: 22 X 22 SAYFA: 56» (tanıtım sayfasında başka kitabın künyesi), yalnız ölçüden ibaret
  satır («22 x 28 cm»). İçinde başka sözcük taşıyan ölçü («Boy Cetveli (20x110 cm)», «20 x 30 cm'lik kâğıt alın»)
  gövdedir.
- Künye satırı («1. Baskı Mart 2016», «Baskı ve Cilt: …», «Kapak Tasarımı: …», ISBN, sertifika) hiçbiri değildir:
  künye okuması onu okur.
- Kitabın dilinde olmayan satır (`is_foreign_line`): yalnız dizgi notu taşıyan dosyada (özalit/iç baskı: çeviri
  kaynağının katmanı orada kalır) ve kitap Türkçeyse (dili belli satırların çoğu Türkçe; dizgi dosyasında özgün
  dilin katmanı Türkçe metinden uzun olabilir, orada en az `PRODUCTION_TR_LINES` Türkçe satır yeter). En az
  `FOREIGN_MIN_WORDS` sözcük, Almanca/İngilizce/Fransızca işlev sözcüğü oranı yüksek, hiç Türkçe işareti yok,
  ortalama sözcük ≥ 3 harf (dağılmış harfli konuşma balonu «le tü kö an zam» değil). Rakamlı satır (dipnot, kaynakça),
  tırnakla açılan alıntı, özel ad ve kısa satır sayılmaz. Bu kapı bilerek dardır: iki dilli öğrenme kitabının
  İngilizce cümlesi, Türkçe kitabın İngilizce kaynakçası ve yabancı dildeki baskı (Fransızca «Nurdan Tacım») içeriktir.

Kullanan yerler: `source` (okunan metin bloğu: rol `print_note`, okumaya/aramaya/ad sayımına girmez — sayfa başlığı
gibi), `chapters` (PDF dizgi satırı bölüm açılışı aranmadan ayıklanır). Saf fonksiyonlar; DB yok.
"""
from __future__ import annotations

import re
import unicodedata

PRINT_NOTE = "print_note"
DIZGI, SPEC, FOREIGN = "dizgi", "spec", "foreign"
#: üretim notu en çok bu kadar sözcük (uzun satır gövde metnidir)
NOTE_MAX_WORDS = 16
FOREIGN_MIN_WORDS = 5
#: işlev sözcüğü oranı (satırın sözcüklerine göre) ve en az sayı
FOREIGN_MIN_RATIO = 0.2
FOREIGN_MIN_HITS = 2
#: dizgi dosyasında kitabı Türkçe saymaya yeten Türkçe satır sayısı
PRODUCTION_TR_LINES = 5

#: Yalnız baskı hazırlığında geçen terimler. Satırın uzunluğu korunarak küçültülmüş metinde aranır (`_lower`): eşleşme
#: yeri özgün satırda aynı yerdir.
_DIZGI = re.compile(
    r"(?:kapak\s+i[çc]i(?:ne)?\s+|i[çc]ine\s+)bask[ıi]|pencere\s+a[çc][ıi]ld[ıi][ğg][ıi]nda\s+g[öo]r[üu]nen\s+k[ıi]s[ıi]m|"
    r"\bpantone\s*\d+\s*[a-z]{0,3}\b|\bcmyk\b|\bta[şs]ma\s+pay[ıi]\b|\b[öo]zalit\b|\bselefon\b|"
    r"\bs[ıi]rt\s+kal[ıi]nl[ıi][ğg][ıi]\b|\bspot\s+lak\b")
_EBAT = re.compile(r"\bebat\s*:")
_DIMENSION = re.compile(r"\b\d{1,3}(?:[.,]\d)?\s*x\s*\d{1,3}(?:[.,]\d)?\s*(?:cm|mm)?(?![\w])")
#: «BIÇAK» (bıçak = kesim kalıbı): büyük harfle yazılmış sözcük (özgün satırda aranır)
_KNIFE = re.compile(r"(?<![^\W\d_])BIÇAK(?![^\W\d_])")
#: künye satırı: üretim notu değil (künye okuması okur)
_IMPRINT = re.compile(r"\bbaski ve cilt\b|\bmatbaa|\bsertifika|\bisbn\b|\b\d+\s*\.?\s*baski\b|\bbaski\s*:|"
                      r"\bkapak tasarim|\byayin yonetmeni|\bcopyright\b|©")


def _lower(t: str) -> str:
    """Türkçe küçük harf, uzunluk korunur (İ → i, I → ı; tek karakter)."""
    return "".join("i" if ch == "İ" else "ı" if ch == "I" else (ch.lower()[:1] or ch) for ch in t)


def note_spans(text: str, *, knife: bool = True) -> list[tuple[int, int]]:
    """Satırdaki dizgi notu parçaları (başlangıç, bitiş): «KAPAK içine baskı», «PANTONE 129», (`knife`) «BIÇAK»."""
    t = text or ""
    out = [m.span() for m in _DIZGI.finditer(_lower(t))]
    if knife:
        out += [m.span() for m in _KNIFE.finditer(t)]
    return sorted(out)


def strip_notes(text: str, *, knife: bool = True) -> str:
    """Satırın dizgi notu parçaları çıkarılmış hâli (boşluklar tek): «KAPAK içine baskı İşte burada!» → «İşte
    burada!». Not taşımayan satır olduğu gibi döner."""
    spans = note_spans(text, knife=knife)
    if not spans:
        return text
    out, at = [], 0
    for s, e in spans:
        if s >= at:
            out.append(text[at:s])
        at = max(at, e)
    out.append(text[at:])
    return " ".join("".join(out).split())


def fold(t: str) -> str:
    """Katlanmış metin: Türkçe küçük harf, i/ı ayrımsız, aksansız, boşluklar tek."""
    t = unicodedata.normalize("NFC", t or "").replace("İ", "i").replace("I", "ı").casefold().replace("ı", "i")
    t = "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c))
    return " ".join(t.replace("×", "x").split())


def _words(t: str) -> list[str]:
    return re.findall(r"[^\W\d_]+(?:['’][^\W\d_]+)?", t or "")


def knife_only(text: str) -> bool:
    """Satır yalnız büyük harfli «BIÇAK» (ve dizgi notu) taşıyor: «BIÇAK», «BIÇAK KAPAK içine baskı»."""
    return bool(_KNIFE.search(text or "")) and not re.search(r"[^\W\d_]", strip_notes(text, knife=True))


def _spec_only(f: str) -> bool:
    """Katlanmış satır ölçü/sayfa künyesinden ibaret («ebat: 22 x 22 sayfa: 56», «22 x 28 cm»)."""
    rest = _DIMENSION.sub(" ", f)
    rest = re.sub(r"\b(ebat|sayfa|boyut|olcu|cm|mm)\b", " ", rest)
    return not re.search(r"[^\W\d_]", rest)


def print_note_kind(text: str, *, knife: bool = True) -> str | None:
    """«dizgi» (baskı hazırlık notu), «spec» (ölçü satırı) ya da None. Dizgi notu ile kitabın metni aynı satırdaysa
    («KAPAK içine baskı İşte burada!») satır not değildir: not parçası `strip_notes` ile çıkar. `knife`: tek başına
    büyük harfli «BIÇAK» da dizgi notu sayılır (`book_context` karar verir). Künye ve uzun satır not değildir."""
    t = " ".join((text or "").split())
    if not t or len(t.split()) > NOTE_MAX_WORDS:
        return None
    f = fold(t)
    if _IMPRINT.search(f):
        return None
    if note_spans(t, knife=knife):
        return DIZGI if not re.search(r"[^\W\d_]", strip_notes(t, knife=knife)) else None
    if _EBAT.search(f) or (_DIMENSION.search(f) and _spec_only(f)):
        return SPEC
    return None


def is_print_note(text: str, *, knife: bool = True) -> bool:
    """Satır baskı/üretim notu mu (dizgi notu ya da ölçü satırı)."""
    return print_note_kind(text, knife=knife) is not None


# ------------------------------------------------------------------ kitabın dilinde olmayan satır
#: Türkçe işlev sözcükleri (başka dillerde de sözcük olanlar — de, da, en, ne, o, su, her — yok)
_TR_WORDS = frozenset({
    "ve", "bir", "bu", "ile", "icin", "cok", "gibi", "daha", "ama", "mi", "mu", "ki", "var", "yok", "sonra", "kadar",
    "ben", "sen", "biz", "siz", "onu", "ona", "diye", "olan", "olarak", "degil", "hic", "sey", "nasil", "neden",
    "bana", "sana", "beni", "seni", "cunku", "hem", "veya", "kim", "hangi", "nerede", "simdi", "artik", "icinde",
    "uzerinde", "gore", "bunu", "buna", "sonra", "once", "evet", "hayir"})
_FOREIGN = {
    "de": frozenset({"der", "die", "das", "und", "ist", "nicht", "ein", "eine", "einen", "einem", "dem", "den",
                     "des", "mit", "auf", "sich", "wir", "ich", "du", "er", "sie", "zu", "von", "im", "wo", "was",
                     "wie", "auch", "aber", "noch", "hier", "uns", "fur", "wenn", "sind", "aus", "bei", "nach",
                     "oder", "dass", "ja", "nein", "mal", "deinem", "deinen", "dein", "kein", "schon", "jetzt"}),
    "en": frozenset({"the", "and", "of", "to", "is", "are", "was", "were", "it", "you", "that", "with", "for",
                     "on", "this", "be", "have", "has", "not", "what", "where", "he", "she", "they", "we", "his",
                     "her", "from", "will", "can", "there", "their", "your", "at", "by"}),
    "fr": frozenset({"le", "la", "les", "et", "des", "une", "un", "est", "du", "que", "qui", "dans", "pour", "pas",
                     "sur", "avec", "il", "elle", "nous", "vous", "ce", "au", "aux", "sont", "mais", "ou", "je",
                     "tu", "son", "sa", "ses"}),
}
#: Türkçeye özgü harf (Azerice dışında başka dilde yok)
_TR_LETTERS = re.compile(r"[ğışĞŞİ]")
#: sık Türkçe ek (yabancı dilde bu biçimde bitmesi seyrek): yalnız «Türkçe değil» kararını engeller
_TR_SUFFIX = re.compile(r"(yor|yordu|m[ıiuü]ş|acak|ecek|lar|ler|lar[ıi]|ler[ıi]|[ıiuü]nda|[ıiuü]nde)$")
_QUOTE_OPEN = re.compile(r"^\s*[«“\"'‘„]")


def turkish_marks(text: str, *, suffix: bool = True) -> int:
    """Satırdaki Türkçe işaretli sözcük sayısı: Türkçeye özgü harf, Türkçe işlev sözcüğü, (`suffix`) Türkçe ek."""
    n = 0
    for w in _words(text):
        lw = w.replace("I", "ı").replace("İ", "i").lower()
        if _TR_LETTERS.search(w) or fold(w) in _TR_WORDS or (suffix and len(lw) >= 5 and _TR_SUFFIX.search(lw)):
            n += 1
    return n


def _foreign_hits(words: list[str]) -> tuple[str | None, int]:
    best, hits = None, 0
    for lang, vocab in _FOREIGN.items():
        h = sum(1 for w in words if w in vocab)
        if h > hits:
            best, hits = lang, h
    return best, hits


def foreign_language(text: str) -> str | None:
    """Satır uzun ve açıkça Almanca/İngilizce/Fransızca mı (hangi dil). Türkçe işareti taşıyan, kısa, rakamlı
    (dipnot, kaynakça), tırnakla açılan ya da harfleri dağılmış satır None."""
    t = " ".join((text or "").split())
    raw = _words(t)
    words = [fold(w) for w in raw]
    if len(words) < FOREIGN_MIN_WORDS or _QUOTE_OPEN.match(t) or re.search(r"\d", t):
        return None
    if sum(len(w) for w in words) < 3 * len(words) or turkish_marks(t):
        return None
    lang, hits = _foreign_hits(words)
    if lang is None or hits < FOREIGN_MIN_HITS or hits < FOREIGN_MIN_RATIO * len(words):
        return None
    content = [w for w, f in zip(raw, words) if len(f) >= 4 and f not in _FOREIGN[lang]]
    if len(content) < 2:
        return None
    # İngilizce/Fransızca ad öbeği («On the Origin of Species»): içerik sözcüklerinin çoğu büyük harfle başlar.
    # Almancada adlar zaten büyük harflidir; orada bakılmaz.
    if lang != "de" and 2 * sum(w[0].isupper() for w in content) >= len(content):
        return None
    return lang


def line_language(text: str) -> str | None:
    """Kitabın dilini saymak için: «tr», yabancı dil kodu ya da None (belirsiz). Ekten sayılmaz (Fransızca «parler»)."""
    words = [fold(w) for w in _words(text)]
    if len(words) < 3:
        return None
    tr = turkish_marks(text, suffix=False)
    lang, hits = _foreign_hits(words)
    if tr >= 2 and tr > hits:
        return "tr"
    if lang and hits >= 2 and hits > tr:
        return lang
    return None


def book_context(lines) -> dict:
    """Kitabın genelinden: {"turkish": bool, "tr": Türkçe satır, "foreign": yabancı satır, "dizgi": dizgi notu
    sayısı, "knives": tek başına «BIÇAK» satırı}. `lines`: kitabın satırları (ya da sayfa kenarlarından örnek)."""
    tr = foreign = dizgi = knives = 0
    for ln in lines:
        if not ln or not ln.strip():
            continue
        lang = line_language(ln)
        tr += lang == "tr"
        foreign += lang not in (None, "tr")
        if print_note_kind(ln, knife=False) == DIZGI:      # yalnız nottan ibaret satır (öyküdeki söz değil)
            dizgi += 1
        elif knife_only(ln):
            knives += 1
    # Dizgi dosyasında (özalit) özgün dilin katmanı Türkçe metinden uzun olabilir: Türkçe satır varsa (en az
    # `PRODUCTION_TR_LINES`) kitap Türkçedir. Başka dosyada dili belli satırların çoğu Türkçe olmalı.
    production = dizgi >= 1 or knives >= 2
    turkish = tr > foreign or (production and tr >= PRODUCTION_TR_LINES)
    return {"turkish": turkish, "tr": tr, "foreign": foreign, "dizgi": dizgi, "knives": knives}


def is_production_file(ctx: dict | None) -> bool:
    """Dosya baskı hazırlık (dizgi) dosyası mı: dizgi notu ya da en az iki tek başına «BIÇAK»."""
    return bool(ctx) and (ctx.get("dizgi", 0) >= 1 or ctx.get("knives", 0) >= 2)


def is_foreign_line(text: str, ctx: dict | None) -> bool:
    """Türkçe kitabın dizgi dosyasında özgün dilde kalmış satır (çeviri kaynağı kalıntısı). `ctx`: `book_context`."""
    return bool(ctx and ctx.get("turkish") and is_production_file(ctx) and foreign_language(text))


def note_kind(text: str, ctx: dict | None) -> str | None:
    """«dizgi», «spec», «foreign» ya da None (kitabın metni)."""
    kind = print_note_kind(text, knife=is_production_file(ctx))
    if kind:
        return kind
    return FOREIGN if is_foreign_line(text, ctx) else None


def block_is_note(text: str, ctx: dict | None) -> bool:
    """Metin bloğunun (bir ya da birkaç satır) bütün harfli satırları not mu (rol `print_note`). Notla gövdenin
    karıştığı blok gövde kalır; satırlara bölünmüş yabancı paragraf (OCR) bütünüyle bakılır."""
    lines = [ln for ln in (text or "").splitlines() if re.search(r"[^\W\d_]", ln)]
    if not lines:
        return False
    if all(note_kind(ln, ctx) for ln in lines):
        return True
    return len(lines) > 1 and note_kind(" ".join(lines), ctx) == FOREIGN
