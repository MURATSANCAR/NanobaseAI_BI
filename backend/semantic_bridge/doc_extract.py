"""Belgeden alıntılı alan çıkarımının ortak parçaları (öneri 12 başvuru ön okuması, öneri 13 sözleşme şartları).

Belge okuma `doc_read` ile yapılır (metin katmanı, taranmış sayfa OCR). Bu modül okunan belgenin üstünde üç iş yapar:

1. **Maskeli okuma** (`masked`): modele gidecek her sayfa metni çağıranın maskesinden geçer (e-posta, telefon, IBAN,
   kimlik no, bilinen kişi adları). Modelin alıntıları bu maskeli metne karşı denetlenir; ekranda da maskeli alıntı
   görünür.
2. **Pencereleme** (`plan_windows`): uzun belge, editör motorundaki metin bütçesi mantığıyla bölüm bölüm modele gider.
   Birim sayfadır; sayfa bölünmez (bütçeden uzun tek sayfa paragraflarından parçalanır). Bir pencereye bütçeye sığan
   kadar ardışık birim girer; iki pencere `DOC_EXTRACT_OVERLAP_PAGES` birim örtüşür. Bütün pencereler okunur — sayı
   tavanı yoktur; kaç pencere okunduğu sonuçta yazılır.
3. **Alıntıdan okuma**: alıntı belgede birebir (katlamalı) aranır (`doc_read.find_quote`), bulunamayan alan atılır ve
   sayılır. Sayı, tarih, süre **alıntının kendisinden kodla** okunur (`number_in`, `date_in`, `years_in`); modelin
   yazdığı değer yalnız alıntıda birden çok aday varsa hangisini kastettiğini seçmeye yarar, hiçbir zaman değerin
   kendisi olmaz.

Saf modül: ağa, veritabanına ve modele kendisi gitmez.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Iterable, Optional

from semantic_bridge import doc_read as DR
from semantic_bridge import zeki_text as Z

DEFAULT_WINDOW_CHARS = 24000
DEFAULT_OVERLAP = 1


def settings(conf: Optional[Callable[[str], Any]] = None) -> dict[str, int]:
    """Pencere bütçesi (karakter) ve örtüşme (birim). Yönetim → «Zeki AI ortak araçlar»."""
    if conf is None:
        from semantic_bridge import admin as admin_mod

        conf = admin_mod.conf

    def num(key: str, default: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(str(conf(key) or default).strip())))
        except ValueError:
            return default

    return {"windowChars": num("DOC_EXTRACT_WINDOW_CHARS", DEFAULT_WINDOW_CHARS, 2000, 400000),
            "overlap": num("DOC_EXTRACT_OVERLAP_PAGES", DEFAULT_OVERLAP, 0, 5)}


# ================================================================================ maskeli okuma


def mask_names(text: str, names: Iterable[str], placeholder: str = "[kişi]") -> str:
    """Bilinen kişi adlarını (yazar, sözleşme tarafı) metinden çıkarır. Ad ve soyadın her biri de ayrıca (en az 3 harf)
    maskelenir; büyük/küçük harf ve Türkçe harf farkı gözetilmez."""
    s = str(text or "")
    parts: set[str] = set()
    for n in names or ():
        n = " ".join(str(n or "").split())
        if len(n) < 3:
            continue
        parts.add(n)
        parts.update(w for w in n.split() if len(w) >= 3)
    for p in sorted(parts, key=len, reverse=True):
        rx = "".join(_letter_class(ch) for ch in p)
        s = re.sub(r"(?<![\w])" + rx + r"(?![\w])", placeholder, s, flags=re.I)
    return s


#: Etiketli kişi bilgisi satırları («Adı Soyadı: …», «Adres: …»): etiket kalır, değer (satır sonuna kadar) gizlenir.
#: Sözleşme ve başvuru belgelerinde adı bilinmeyen tarafın kimliği böyle maskelenir.
_LABELED = re.compile(
    r"(?im)^(\s*(?:adı?\s*soyadı?|ad\s*[-/]?\s*soyad|unvanı?|t\.?\s*c\.?\s*kimlik(?:\s*no)?|kimlik\s*no|vergi\s*no|"
    r"adres(?:i)?|ikametgah|telefon|tel|gsm|e-?posta|iban|banka\s*hesab\w*|doğum\s*tarihi)\s*[:：]\s*)(\S.*)$")


def mask_labeled(text: str) -> str:
    return _LABELED.sub(lambda m: m.group(1) + "[kişisel bilgi]", str(text or ""))


def mask_all(text: str, names: Iterable[str] = ()) -> str:
    """Modele giden metnin tek maskesi: e-posta, telefon, IBAN, kart, kimlik no, etiketli kişi satırları, bilinen adlar."""
    return mask_names(mask_labeled(Z.mask_personal(text)), names)


_PAIRS = {"i": "iİıI", "ı": "ıIiİ", "s": "sşSŞ", "ş": "şŞsS", "g": "gğGĞ", "ğ": "ğĞgG", "u": "uüUÜ", "ü": "üÜuU",
          "o": "oöOÖ", "ö": "öÖoO", "c": "cçCÇ", "ç": "çÇcC"}


def _letter_class(ch: str) -> str:
    low = ch.lower() if ch not in "Iİ" else ("ı" if ch == "I" else "i")
    if low in _PAIRS:
        return "[" + _PAIRS[low] + "]"
    if ch.isspace():
        return r"\s+"
    return re.escape(ch)


def masked(reading: DR.Reading, fn: Callable[[str], str]) -> DR.Reading:
    """Okumanın maskeli kopyası (sayfa numarası, okuma türü ve güven aynen)."""
    pages = [{**p, "metin": fn(p["metin"]) if p.get("metin") else p.get("metin")} for p in reading.pages]
    return DR.Reading(filename=reading.filename, pages=pages, errors=list(reading.errors),
                      low_confidence=reading.low_confidence)


# ================================================================================ pencereleme


@dataclass
class Window:
    index: int
    pages: list[str] = field(default_factory=list)      # sayfa etiketleri, sırayla (parçalı sayfa bir kez)
    text: str = ""

    @property
    def span(self) -> str:
        if not self.pages:
            return ""
        return self.pages[0] if len(self.pages) == 1 else f"{self.pages[0]}–{self.pages[-1]}"


def _split_long(text: str, budget: int) -> list[str]:
    """Bütçeden uzun sayfa: paragraflardan, paragraf da uzunsa boşluktan bölünür. Hiçbir harf atılmaz."""
    out: list[str] = []
    cur = ""
    for para in re.split(r"(\n+)", text):
        if len(cur) + len(para) <= budget:
            cur += para
            continue
        if cur.strip():
            out.append(cur)
        cur = ""
        while len(para) > budget:
            cut = para.rfind(" ", 0, budget)
            cut = cut if cut > budget // 2 else budget
            out.append(para[:cut])
            para = para[cut:]
        cur = para
    if cur.strip():
        out.append(cur)
    return out


def plan_windows(reading: DR.Reading, budget: int = DEFAULT_WINDOW_CHARS, overlap: int = DEFAULT_OVERLAP) -> list[Window]:
    """Okunan sayfaları bütçeye sığan ardışık pencerelere böler (bkz. modül açıklaması). Okunamayan sayfa atlanır."""
    budget = max(200, int(budget))
    units: list[tuple[str, str]] = []
    for p in reading.pages:
        t = (p.get("metin") or "").strip()
        if not t:
            continue
        head = len(f"[s. {p['sayfa']}]\n")
        if len(t) + head <= budget:
            units.append((str(p["sayfa"]), t))
        else:
            units.extend((str(p["sayfa"]), piece.strip()) for piece in _split_long(t, budget - head - 1) if piece.strip())
    wins: list[Window] = []
    i = 0
    while i < len(units):
        j, size = i, 0
        while j < len(units):
            cost = len(units[j][1]) + len(f"[s. {units[j][0]}]\n") + 1
            if j > i and size + cost > budget:
                break
            size += cost
            j += 1
        chunk = units[i:j]
        pages: list[str] = []
        for s, _ in chunk:
            if s not in pages:
                pages.append(s)
        wins.append(Window(len(wins) + 1, pages, "\n".join(f"[s. {s}]\n{t}" for s, t in chunk)))
        if j >= len(units):
            break
        i = max(i + 1, j - max(0, overlap))
    return wins


# ================================================================================ model cevabı


def parse_json(raw: Any) -> dict[str, Any]:
    s = Z.strip_thinking(raw)
    s = re.sub(r"^```(?:json)?|```$", "", s, flags=re.M).strip()
    m = re.search(r"\{.*\}", s, flags=re.S)
    try:
        v = json.loads(m.group(0) if m else s)
    except ValueError:
        return {}
    return v if isinstance(v, dict) else {}


def unreadable_reply(raw: Any, data: dict[str, Any]) -> bool:
    """Model cevap verdi ama JSON okunamadı mı (boş nesne «{}» geçerli cevaptır: bölümde alan yok)."""
    s = Z.strip_thinking(raw)
    return bool(s) and not data and not re.search(r"\{\s*\}", s)


def items(v: Any, key: str = "alinti") -> list[dict[str, Any]]:
    """Modelin tek nesne ya da liste yazdığı alanı listeye çevirir; alıntısı boş olanlar atılır."""
    if isinstance(v, dict):
        v = [v]
    return [x for x in (v or []) if isinstance(x, dict) and str(x.get(key) or "").strip()]


def hit(quote: Any, reading: DR.Reading, min_len: int = 8) -> Optional[dict[str, Any]]:
    """Alıntı belgede birebir geçiyorsa {sayfa, okuma, guven}."""
    return DR.find_quote(quote, reading, min_len=min_len)


def evidence(quote: str, h: dict[str, Any]) -> dict[str, Any]:
    """Ekrana giden kanıt: alıntı, sayfa, okuma (OCR ise güveniyle)."""
    out = {"alinti": " ".join(str(quote).split())[:600], "sayfa": h["sayfa"], "okuma": h["okuma"]}
    if h["okuma"] == DR.OCR and h.get("guven") is not None:
        out["guven"] = h["guven"]
    return out


# ================================================================================ alıntıdan sayı, tarih, süre


def _fold(s: Any) -> str:
    return " ".join(Z.fold(s).replace("'", " ").split())


def numbers_in(quote: str) -> list[dict[str, Any]]:
    """Alıntıdaki sayılar (tarih hariç): Türkçe yazımla okunan değer, ölçek sözcüğüyle çarpılmış; yüzde işareti."""
    out = []
    for n in Z.tokens(quote):
        if n.kind != "sayi" or not n.values:
            continue
        out.append({"deger": round(n.values[0][0] * n.scale, 6), "yuzde": n.percent, "yazim": n.text})
    return out


def _same(a: float, b: float) -> bool:
    return abs(a - b) <= max(1e-9, abs(b) * 1e-9)


def number_in(quote: str, claimed: Any = None, *, percent: Optional[bool] = None,
              skip_years: bool = True) -> Optional[float]:
    """Alıntıdan tek sayı. Aday yoksa ya da birden çok farklı aday varsa ve modelin değeri tek birini göstermiyorsa
    None (alan boş kalır). `percent`: True yalnız yüzdeler, False yüzdeler hariç. Yıl gibi duran (1900–2100 arası
    ayraçsız tam sayı) sayılar para/oran adayı sayılmaz."""
    cands = []
    for n in numbers_in(quote):
        if percent is True and not n["yuzde"]:
            continue
        if percent is False and n["yuzde"]:
            continue
        if skip_years and not n["yuzde"] and re.fullmatch(r"(19|20)\d\d", n["yazim"]):
            continue
        cands.append(n["deger"])
    distinct: list[float] = []
    for v in cands:
        if not any(_same(v, d) for d in distinct):
            distinct.append(v)
    if not distinct:
        return None
    if claimed not in (None, ""):
        want = [round(v * t.scale, 6) for t in Z.tokens(str(claimed)) if t.kind == "sayi" for v, _ in t.values]
        match = [d for d in distinct if any(_same(d, w) for w in want)]
        if len(match) == 1:
            return match[0]
        if not match and len(distinct) > 1:
            return None
    return distinct[0] if len(distinct) == 1 else None


MONTHS = {"ocak": 1, "subat": 2, "mart": 3, "nisan": 4, "mayis": 5, "haziran": 6, "temmuz": 7, "agustos": 8,
          "eylul": 9, "ekim": 10, "kasim": 11, "aralik": 12}
_MONTH_DATE = re.compile(r"\b(\d{1,2})\s+(" + "|".join(MONTHS) + r")\s+(\d{4})\b")


def dates_in(quote: str) -> list[str]:
    """Alıntıdaki tam tarihler (gg.aa.yyyy, yyyy-aa-gg, «31 Aralık 2030»), ISO, sırayla ve tekrarsız."""
    found: list[tuple[int, tuple[int, int, int]]] = []
    for n in Z.tokens(quote):
        if n.kind == "tarih" and n.day:
            found.append((n.start, n.day))
    f = _fold(quote)
    for m in _MONTH_DATE.finditer(f):
        d, mo, y = int(m.group(1)), MONTHS[m.group(2)], int(m.group(3))
        found.append((10_000 + m.start(), (y, mo, d)))
    out: list[str] = []
    for _, (y, mo, d) in sorted(found):
        try:
            iso = date(y, mo, d).isoformat()
        except ValueError:
            continue
        if iso not in out:
            out.append(iso)
    return out


def date_in(quote: str, claimed: Any = None) -> Optional[str]:
    """Alıntıdaki tek tarih; birden çoksa modelin değerindeki tarih alıntıdakilerden biriyse o, değilse None."""
    ds = dates_in(quote)
    if len(ds) == 1:
        return ds[0]
    if len(ds) > 1 and claimed not in (None, ""):
        want = dates_in(str(claimed))
        match = [d for d in ds if d in want]
        return match[0] if len(match) == 1 else None
    return None


_DURATION = re.compile(r"(?<![\d.,])(\d{1,3})\s*(?:\([^)]{1,24}\)\s*)?(yil\w*|sene\w*|ay(?:lik|dir|da)?\b)")


def years_in(quote: str) -> Optional[float]:
    """Alıntıdaki tek süre yıl olarak («5 (beş) yıl» → 5, «18 ay» → 1,5). Birden çok farklı süre varsa None."""
    vals = set()
    for m in _DURATION.finditer(_fold(quote)):
        n = int(m.group(1))
        vals.add(round(n / 12.0, 4) if m.group(2).startswith("ay") else float(n))
    return vals.pop() if len(vals) == 1 else None


def ages_in(quote: str) -> Optional[tuple[Optional[int], Optional[int]]]:
    """Alıntıdaki hedef yaş: «8-12 yaş» → (8, 12); «12 yaş ve üzeri» → (12, None); «7 yaşından küçük» yok sayılmaz,
    (None, 7) döner. Yaş sözcüğü yoksa None."""
    f = _fold(quote)
    m = re.search(r"(\d{1,2})\s*(?:-|–|ile|ila)\s*(\d{1,2})\s*yas", f)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (min(a, b), max(a, b)) if 0 < min(a, b) and max(a, b) <= 99 else None
    m = re.search(r"(\d{1,2})\s*yas\w*\s*(ve\s*)?(uzeri|ustu|buyuk)", f)
    if m and 0 < int(m.group(1)) <= 99:
        return (int(m.group(1)), None)
    m = re.search(r"(\d{1,2})\s*yas\w*\s*(ve\s*)?(alti|kucuk)", f)
    if m and 0 < int(m.group(1)) <= 99:
        return (None, int(m.group(1)))
    return None


def has_word(quote: str, words: Iterable[str]) -> bool:
    f = " " + _fold(quote) + " "
    return any(w in f for w in words)


def sentences(text: str) -> list[str]:
    return [s.strip() for s in re.split(r"(?<=[.;!?])\s+|\n+", text or "") if s and s.strip()]
