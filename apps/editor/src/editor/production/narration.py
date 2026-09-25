"""Sesli okuma: sayfa planının metnini Türkçe seslendirir, her kelimenin sesteki yerini çıkarır.

Hedef (kullanıcı kararı 2026-09-25): «Türkçe seslendirme yapılır, e-kitapta okunan kelime vurgulanır.» Model seçimi
ve lisanslar: docs/analiz/sesli-okuma-model-secimi.md (seslendirme VoxCPM2, kelime zamanı Türkçe CTC hizalayıcı;
ikisi gateway'in `book-voice` takma adında, `images/voice/server.py`). Model yalnız servis tarafındadır; bu modül
metni okunuşa çevirir, sayfayı parçalara böler, servisi çağırır, zamanları ekrandaki kelimelere bağlar.

Okunuş (kitaptan bağımsız, genel Türkçe kuralları): sayılar ("1923'te" → "bin dokuz yüz yirmi üçte"), sıra sayıları
("3. sınıf", "XX. yüzyıl"), ondalık ("3,5"), binlik ayırıcı ("2.500"), tarih ("25.09.2026"), saat ("14:30"), yüzde,
para ve birimler, aralık ("7-9"), bilinen kısaltmalar ("Dr.", "vb.", "M.Ö."), harf harf okunan kısaltmalar ("TBMM",
"ABD'nin"), editörün telaffuz sözlüğü (işe ve yayınevine kayıtlı; iş sözlüğü önce gelir).

Kelime eşlemesi: ekrandaki her kelime (boşlukla ayrılan parça) bir ya da birden çok okunuş kelimesine açılır; zamanı
açılan kelimelerin ilkinin başı ile sonuncusunun sonudur. Hizalayıcı bir kelimeyi bulamazsa zaman komşularının
arasından harf sayısıyla orantılı tahmin edilir (`estimated`).

İş klasöründe (`<iş>/ses/`):
    ayar.json           {narrator, characters: {konuşan: ses}, updated_by, updated_at}
    sozluk.json         iş sözlüğü [{word, say, by, at}]
    sayfa/<pid>.mp3     sayfanın sesi
    sayfa/<pid>.json    zamanlar (media_overlay'deki sayfa kaydı) + girdinin özeti (hash): metin, ses ya da sözlük
                        değişince sayfa «güncel değil» görünür
Yayınevi düzeyinde (`<storage>/production/_ses/`): sozluk.json (yayınevi sözlüğü), sesler/<ses>.wav|json (her ses bir
kez tarifle üretilen referans; sonra hep o referansla okunur, kitap boyunca aynı ses kalır).

EPUB bağlantısı: `media_overlay(job)` bütün kitabın kelime zamanlarını verir, `smil(...)` bir sayfanın SMIL 3.0
belgesini yazar (EPUB 3 Media Overlays). Biçim `media_overlay`'in belgesinde.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

ALIAS = "book-voice"
DIR = "ses"
VERSION = 1

# ------------------------------------------------------------------ sesler
# Ses tarifle tasarlanır (gerçek kişi kaydı gerekmez); tarif modelin en iyi anladığı dilde (İngilizce), ad Türkçe.
VOICES: list[dict] = [
    {"id": "anlatici-kadin", "label": "Kadın anlatıcı", "note": "sıcak, sakin", "group": "anlatici",
     "design": "A warm, calm middle-aged woman storyteller, clear gentle diction, unhurried pace"},
    {"id": "anlatici-erkek", "label": "Erkek anlatıcı", "note": "derin, yumuşak", "group": "anlatici",
     "design": "A calm middle-aged man storyteller with a deep, soft and friendly voice, clear diction, unhurried pace"},
    {"id": "genc-kadin", "label": "Genç kadın", "note": "canlı, içten", "group": "karakter",
     "design": "A young woman in her twenties, lively and sincere, bright voice"},
    {"id": "genc-erkek", "label": "Genç erkek", "note": "enerjik", "group": "karakter",
     "design": "A young man in his twenties, energetic and friendly voice"},
    {"id": "cocuk-kiz", "label": "Küçük kız", "note": "neşeli", "group": "karakter",
     "design": "A cheerful little girl about eight years old, high playful voice"},
    {"id": "cocuk-erkek", "label": "Küçük oğlan", "note": "meraklı", "group": "karakter",
     "design": "A curious little boy about eight years old, lively childlike voice"},
    {"id": "yasli-kadin", "label": "Yaşlı kadın", "note": "şefkatli", "group": "karakter",
     "design": "A kind elderly grandmother in her seventies, soft affectionate slightly shaky voice"},
    {"id": "yasli-erkek", "label": "Yaşlı adam", "note": "bilge", "group": "karakter",
     "design": "A wise elderly grandfather in his seventies, low warm slow voice"},
]
VOICE_IDS = {v["id"] for v in VOICES}
DEFAULT_NARRATOR = "anlatici-kadin"
# Referans cümle: Türkçe seslerin hepsini (ı, ğ, ş, ç, ö, ü) taşır; ses bir kez bununla üretilir, sonra klonlanır.
REF_TEXT = "Bir varmış bir yokmuş; dağların eteğinde, şirin bir köyde, meraklı ve güler yüzlü bir çocuk yaşarmış."
REF_SEED = 20260925


def voice(vid: str) -> dict:
    for v in VOICES:
        if v["id"] == vid:
            return v
    raise KeyError(vid)


# Karakter tarifinden (artplan: species/look, İngilizce) sese öneri: genel kelimeler, kitaba özel değil.
_GUESS = [
    (r"\b(grand(ma|mother)|old (woman|lady)|granny|elderly woman|nine)\b", "yasli-kadin"),
    (r"\b(grand(pa|father)|old man|elderly man|dede)\b", "yasli-erkek"),
    (r"\b(girl|daughter)\b", "cocuk-kiz"),
    (r"\b(boy|son)\b", "cocuk-erkek"),
    (r"\b(woman|mother|mom|lady|aunt|teacher \(female\))\b", "genc-kadin"),
    (r"\b(man|father|dad|uncle)\b", "genc-erkek"),
]


def guess_voice(species: str, look: str = "") -> str | None:
    t = f"{species} {look}".lower()
    for pat, vid in _GUESS:
        if re.search(pat, t):
            return vid
    return None


# ------------------------------------------------------------------ Türkçe yardımcıları
VOWELS = "aeıioöuüâîû"
_UP = str.maketrans({"i": "İ", "ı": "I"})
_LO = str.maketrans({"I": "ı", "İ": "i"})


def tr_lower(s: str) -> str:
    return s.translate(_LO).lower()


def tr_upper(s: str) -> str:
    return s.translate(_UP).upper()


def _last_vowel(w: str) -> str:
    for ch in reversed(tr_lower(w)):
        if ch in VOWELS:
            return ch
    return "e"


def _harmony4(w: str) -> str:
    """Dört yönlü ünlü uyumu (ı/i/u/ü)."""
    return {"a": "ı", "ı": "ı", "â": "ı", "e": "i", "i": "i", "î": "i", "o": "u", "u": "u", "û": "u",
            "ö": "ü", "ü": "ü"}[_last_vowel(w)]


ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
SCALES = [(10**18, "kentilyon"), (10**15, "katrilyon"), (10**12, "trilyon"), (10**9, "milyar"), (10**6, "milyon"),
          (10**3, "bin")]
MONTHS = ["ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz", "ağustos", "eylül", "ekim", "kasım",
          "aralık"]


def _under1000(n: int) -> list[str]:
    h, r = divmod(n, 100)
    out = []
    if h:
        out += (["yüz"] if h == 1 else [ONES[h], "yüz"])
    t, o = divmod(r, 10)
    if t:
        out.append(TENS[t])
    if o:
        out.append(ONES[o])
    return out


def number(n: int) -> str:
    """Tam sayının okunuşu: 1923 → «bin dokuz yüz yirmi üç», 1000 → «bin», 0 → «sıfır», -5 → «eksi beş»."""
    if n == 0:
        return "sıfır"
    if n < 0:
        return "eksi " + number(-n)
    out = []
    for scale, name in SCALES:
        q, n = divmod(n, scale)
        if q:
            out += ([name] if scale == 1000 and q == 1 else [number(q), name])
    out += _under1000(n)
    return " ".join(out)


def ordinal(n: int) -> str:
    """Sıra sayısı: 1 → birinci, 3 → üçüncü, 4 → dördüncü, 20 → yirminci, 100 → yüzüncü."""
    words = number(n).split()
    return " ".join(words[:-1] + [ordinal_word(words[-1])])


def ordinal_word(w: str) -> str:
    if w == "dört":
        return "dördüncü"
    v = _harmony4(w)
    return w + ("nc" + v if tr_lower(w)[-1] in VOWELS else v + "nc" + v)


VOICELESS = "fstkçşhp"
BACK = "aıouâû"
# Kaynaştırma harfi: ünsüzle biten gövdede düşer, ünlüyle biten gövdede gelir (ilgi, belirtme, yönelme, iyelik).
_BUFFER_DROP = {"nin": "in", "nın": "ın", "nun": "un", "nün": "ün", "yi": "i", "yı": "ı", "yu": "u", "yü": "ü",
                "ye": "e", "ya": "a", "si": "i", "sı": "ı", "su": "u", "sü": "ü", "yle": "le", "yla": "la"}
_BUFFER_ADD = {"in": "nin", "ın": "nın", "un": "nun", "ün": "nün", "i": "yi", "ı": "yı", "u": "yu", "ü": "yü",
               "e": "ye", "a": "ya"}


def reharmonize(stem: str, suffix: str) -> str:
    """Yazılışa göre çekilmiş eki okunuşun gövdesine uydurur: ünlü uyumu, d/t ve c/ç benzeşmesi, kaynaştırma
    harfi. Yazılış ile okunuş aynı sesle bitiyorsa değişmez («1923'te» → «üçte»); «TL'lik» → «liralık»,
    «ABD'nin» → «a be denin»."""
    suf = tr_lower(suffix)
    stem = tr_lower(stem)
    if not suf or not stem:
        return suf
    ends_vowel = stem[-1] in VOWELS
    if not ends_vowel and suf in _BUFFER_DROP:
        suf = _BUFFER_DROP[suf]
    elif ends_vowel and suf in _BUFFER_ADD:
        suf = _BUFFER_ADD[suf]
    out, last = [], _last_vowel(stem)
    for k, ch in enumerate(suf):
        if ch in "ae":
            ch = "a" if last in BACK else "e"
            last = ch
        elif ch in "ıiuü":
            ch = _harmony4(last)
            last = ch
        elif k == 0 and ch in "dt":
            ch = "t" if stem[-1] in VOICELESS else "d"
        elif k == 0 and ch in "cç":
            ch = "ç" if stem[-1] in VOICELESS else "c"
        out.append(ch)
    return "".join(out)


def attach(reading: str, suffix: str) -> str:
    """Kesme işaretinden sonraki eki okunuşa ekler (ek okunuşa uydurulur); «dört» ünlüyle başlayan ekte yumuşar
    (4'ü → dördü)."""
    if not suffix:
        return reading
    head, _, last = reading.rpartition(" ")
    suf = reharmonize(last, suffix)
    if last == "dört" and suf[0] in VOWELS:
        last = "dörd"
    return (head + " " if head else "") + last + suf


def decimal(int_part: str, frac: str) -> str:
    zeros = len(frac) - len(frac.lstrip("0"))
    rest = frac.lstrip("0")
    tail = " ".join(["sıfır"] * zeros + ([number(int(rest))] if rest else []))
    return f"{number(int(int_part))} virgül {tail}".strip()


ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}


def roman(s: str) -> int | None:
    if not s or any(ch not in ROMAN for ch in s):
        return None
    total, prev = 0, 0
    for ch in reversed(s):
        v = ROMAN[ch]
        total += -v if v < prev else v
        prev = max(prev, v)
    # Yalnız kurallı yazım (IIII, VV, IC gibi yazımlar Roma rakamı sayılmaz).
    return total if 0 < total < 4000 and _to_roman(total) == s else None


def _to_roman(n: int) -> str:
    out = ""
    for v, sym in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"),
                   (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out, n = out + sym, n - v
    return out


LETTERS = {"A": "a", "B": "be", "C": "ce", "Ç": "çe", "D": "de", "E": "e", "F": "fe", "G": "ge", "Ğ": "yumuşak ge",
           "H": "he", "I": "ı", "İ": "i", "J": "je", "K": "ke", "L": "le", "M": "me", "N": "ne", "O": "o", "Ö": "ö",
           "P": "pe", "R": "re", "S": "se", "Ş": "şe", "T": "te", "U": "u", "Ü": "ü", "V": "ve", "Y": "ye", "Z": "ze",
           "Q": "kü", "W": "dabılyu", "X": "iks"}


def spell(s: str) -> str:
    return " ".join(LETTERS.get(ch, ch) for ch in s)


def pronounceable(s: str) -> bool:
    """Büyük harfli kısaltma kelime gibi mi okunur (NATO, ODTÜ, TÜBİTAK) yoksa harf harf mi (TBMM, ABD, CHP)?
    Kural: ünlü var, başta ve sonda iki ünsüz yan yana yok, hiçbir yerde üç ünsüz yan yana yok."""
    low = tr_lower(s)
    if not any(ch in VOWELS for ch in low):
        return False
    pat = "".join("v" if ch in VOWELS else "c" for ch in low)
    return not (pat.startswith("cc") or pat.endswith("cc") or "ccc" in pat)


# Bilinen kısaltmalar (genel Türkçe yazım; nokta dahil birebir). Değer okunuştur.
ABBR = {
    "Dr.": "doktor", "Prof.": "profesör", "Doç.": "doçent", "Av.": "avukat", "Op.": "operatör", "Uzm.": "uzman",
    "Yrd.": "yardımcı", "Öğr.": "öğretim", "Gör.": "görevlisi", "Arş.": "araştırma", "Sn.": "sayın",
    "Hz.": "hazreti", "Gen.": "general", "Alb.": "albay", "Yzb.": "yüzbaşı", "Bkz.": "bakınız", "bkz.": "bakınız",
    "vb.": "ve benzeri", "vs.": "vesaire", "vd.": "ve diğerleri", "örn.": "örneğin", "Örn.": "örneğin",
    "yy.": "yüzyıl", "M.Ö.": "milattan önce", "M.S.": "milattan sonra", "MÖ": "milattan önce", "MS": "milattan sonra",
    "T.C.": "Türkiye Cumhuriyeti", "A.Ş.": "anonim şirketi", "Ltd.": "limited", "Şti.": "şirketi",
    "Cad.": "caddesi", "Sok.": "sokağı", "Mah.": "mahallesi", "Blv.": "bulvarı", "No.": "numara", "no.": "numara",
    "Tel.": "telefon", "tel.": "telefon", "a.g.e.": "adı geçen eser", "age.": "adı geçen eser",
}
SENTENCE_ABBR = {"vb.", "vs.", "vd."}          # cümle sonunda da yazılabilir: sonrası büyük harfse cümle biter
UNITS = {"km": "kilometre", "m": "metre", "cm": "santimetre", "mm": "milimetre", "kg": "kilogram", "g": "gram",
         "gr": "gram", "mg": "miligram", "lt": "litre", "l": "litre", "ml": "mililitre", "sn": "saniye",
         "dk": "dakika", "sa": "saat", "°C": "santigrat derece", "°": "derece", "m²": "metrekare", "m2": "metrekare",
         "km²": "kilometrekare", "km2": "kilometrekare", "ha": "hektar", "TL": "lira", "₺": "lira", "$": "dolar",
         "€": "avro", "£": "sterlin", "kr": "kuruş", "kuruş": "kuruş"}
CURRENCY = {"₺": "lira", "$": "dolar", "€": "avro", "£": "sterlin"}
OPEN_P = "\"'“‘«(["
CLOSE_P = "\"'”’»)]"
SENT_END = re.compile(r"(\.\.\.|…|[.!?])+$")
APOS = "'’"


# ------------------------------------------------------------------ okunuş
@dataclass
class Word:
    """Ekrandaki bir kelime: metindeki yeri ve okunuşu."""
    i: int
    text: str
    start: int                      # birimin düz metninde karakter başı
    end: int
    spoken: str                     # okunuş (noktalama dahil; boş olabilir: yalnız işaret)
    say: list[str] = field(default_factory=list)   # hizalanacak okunuş kelimeleri (noktalamasız)


def _tokens(text: str) -> list[tuple[int, int, str]]:
    return [(m.start(), m.end(), m.group()) for m in re.finditer(r"\S+", text)]


def _split_punct(tok: str) -> tuple[str, str, str]:
    """(baştaki işaretler, çekirdek, sondaki işaretler). Kısaltma noktası çekirdekte kalır, karar çekirdekte verilir."""
    a = 0
    while a < len(tok) and tok[a] in OPEN_P + "–—-" and not (tok[a] == "-" and tok[a + 1:a + 2].isdigit()):
        a += 1
    b = len(tok)
    while b > a and tok[b - 1] in CLOSE_P + ",;:!?…":
        b -= 1
    return tok[:a], tok[a:b], tok[b:]


def _lex_key(w: str) -> str:
    return tr_lower(w.strip())


class Lexicon:
    """Editörün telaffuz sözlüğü: yazılış → okunuş. İş sözlüğü yayınevi sözlüğünden önce gelir. Kelime kesme
    işaretiyle ek alabilir: «Timaş'ın» → «tımaşın»."""

    def __init__(self, *entries: list[dict]):
        self.map: dict[str, str] = {}
        for lst in reversed(entries):                  # sonraki (yayınevi) önce yazılır, öncelikli (iş) üstüne
            for e in lst or []:
                if e.get("word", "").strip() and e.get("say", "").strip():
                    self.map[_lex_key(e["word"])] = e["say"].strip()

    def get(self, core: str) -> str | None:
        k = _lex_key(core)
        if k in self.map:
            return self.map[k]
        for ap in APOS:
            if ap in core:
                base, _, suf = core.partition(ap)
                if _lex_key(base) in self.map and suf.isalpha():
                    return attach(self.map[_lex_key(base)], suf)
        return None


_NUM = r"\d+"
_RE_INT = re.compile(rf"^(-?)({_NUM})(?:[{APOS}](\w+))?$")
_RE_THOUS = re.compile(rf"^(\d{{1,3}}(?:\.\d{{3}})+)(?:[{APOS}](\w+))?$")
_RE_DEC = re.compile(rf"^(-?)(\d+),(\d+)(?:[{APOS}](\w+))?$")
_RE_DATE = re.compile(rf"^(\d{{1,2}})[./](\d{{1,2}})[./](\d{{4}})(?:[{APOS}](\w+))?$")
_RE_TIME = re.compile(rf"^(\d{{1,2}})[:.](\d{{2}})(?:[{APOS}](\w+))?$")
_RE_PCT = re.compile(rf"^%(\d+(?:,\d+)?)(?:[{APOS}](\w+))?$")
_RE_RANGE = re.compile(rf"^(\d+)[-–](\d+)(?:[{APOS}](\w+))?$")
_RE_ORD = re.compile(r"^(\d+)\.$")
_RE_NUM_UNIT = re.compile(r"^(\d+(?:,\d+)?)(km²|km2|m²|m2|km|cm|mm|kg|mg|ml|lt|gr|°C|°|TL|₺|m|g|l)$")
_RE_CUR = re.compile(rf"^([₺$€£])(\d+(?:[.,]\d+)*)(?:[{APOS}](\w+))?$|^(\d+(?:[.,]\d+)*)([₺$€£])(?:[{APOS}](\w+))?$")
_RE_ACR = re.compile(rf"^([A-ZÇĞİÖŞÜ]{{2,8}})(?:[{APOS}](\w+))?$")


def _num_reading(s: str) -> str:
    """«2.500» / «3,5» / «150» → okunuş."""
    if "," in s:
        a, b = s.split(",", 1)
        return decimal(a.replace(".", ""), b)
    return number(int(s.replace(".", "")))


def _is_num(tok: str | None) -> bool:
    return bool(tok) and bool(re.match(r"^\d+(?:[.,]\d+)*$", _split_punct(tok)[1]))


def read_core(core: str, prev: str | None, nxt: str | None, lex: Lexicon, all_caps: bool = False) -> tuple[str, bool]:
    """Bir çekirdeğin okunuşu ve «çekirdeğin sonundaki nokta cümle sonu mu». `prev`/`nxt`: komşu ham kelimeler."""
    said = lex.get(core)
    if said is not None:
        return said, False
    if core.endswith(".") and lex.get(core[:-1]) is not None:
        return lex.get(core[:-1]), True
    nxt_core = _split_punct(nxt)[1] if nxt else ""
    nxt_lower = bool(nxt_core) and (nxt_core[0].islower() or nxt_core[0].isdigit())
    if core in ABBR:
        end = core in SENTENCE_ABBR and (nxt is None or (nxt_core[:1].isupper()))
        return ABBR[core], end
    if prev is not None and _is_num(prev) and core in UNITS:
        return UNITS[core], False
    for ap in APOS:                                    # birim + ek: «km'lik» → kilometrelik
        base, _, suf = core.partition(ap)
        if suf and prev is not None and _is_num(prev) and base in UNITS and suf.isalpha():
            return attach(UNITS[base], suf), False
    if m := _RE_DATE.match(core):
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        if 1 <= d <= 31 and 1 <= mo <= 12:
            return attach(f"{number(d)} {MONTHS[mo - 1]} {number(y)}", m[4] or ""), False
    if m := _RE_TIME.match(core):
        h, mi = int(m[1]), int(m[2])
        if h <= 24 and mi <= 59:
            r = number(h) + ("" if mi == 0 else " " + ("sıfır " if mi < 10 else "") + number(mi))
            return attach(r, m[3] or ""), False
    if m := _RE_THOUS.match(core):
        return attach(number(int(m[1].replace(".", ""))), m[2] or ""), False
    if m := _RE_DEC.match(core):
        return attach(("eksi " if m[1] else "") + decimal(m[2], m[3]), m[4] or ""), False
    if m := _RE_PCT.match(core):
        return attach("yüzde " + _num_reading(m[1]), m[2] or ""), False
    if m := _RE_RANGE.match(core):
        return attach(f"{number(int(m[1]))} ila {number(int(m[2]))}", m[3] or ""), False
    if m := _RE_CUR.match(core):
        if m[1]:
            return attach(f"{_num_reading(m[2])} {CURRENCY[m[1]]}", m[3] or ""), False
        return attach(f"{_num_reading(m[4])} {CURRENCY[m[5]]}", m[6] or ""), False
    if m := _RE_NUM_UNIT.match(core):
        return f"{_num_reading(m[1])} {UNITS[m[2]]}", False
    if m := _RE_ORD.match(core):
        # «3. sınıf», «1. Dünya Savaşı» sıra sayısı; yalnız bloğun son kelimesiyse asıl sayı + cümle sonu.
        if nxt is not None:
            return ordinal(int(m[1])), False
        return number(int(m[1])), True
    if m := _RE_INT.match(core):
        return attach(("eksi " if m[1] else "") + number(int(m[2])), m[3] or ""), False
    # Roma rakamı: «XX. yüzyıl», «II. Abdülhamit» sıra; tek harfli I/V/X yalnız ardından küçük harfle gelirse (baş
    # harf kısaltmasıyla karışmasın: «C. Yılmaz»).
    if core.endswith(".") and (r := roman(core[:-1])):
        if len(core) > 2 or (core[0] in "IVX" and nxt_lower):
            return ordinal(r), False
    if (m := _RE_ACR.match(core)) and not all_caps:
        acr = m[1]
        # İki harfli büyük yazım çoğu kez ünlemdir («AH», «OF»): ünlüsü varsa kelime gibi okunur; «AB» gibi
        # kısaltmalar sözlükle düzeltilir.
        as_word = any(ch in "AEIİOÖUÜ" for ch in acr) if len(acr) == 2 else pronounceable(acr)
        return attach(tr_lower(acr) if as_word else spell(acr), m[2] or ""), False
    if all_caps and core.isupper():
        return tr_lower(core), False
    return core, False


def read(text: str, lex: Lexicon | None = None) -> list[Word]:
    """Bir birimin (paragraf, balon, serbest yazı) kelimeleri ve okunuşları."""
    lex = lex or Lexicon()
    toks = _tokens(text)
    letters = [ch for ch in text if ch.isalpha()]
    all_caps = len(letters) >= 3 and all(ch.isupper() for ch in letters)   # başlık/bağırış: kelimeler harf harf değil
    out = []
    for i, (s, e, tok) in enumerate(toks):
        pre, core, post = _split_punct(tok)
        prev = toks[i - 1][2] if i else None
        nxt = toks[i + 1][2] if i + 1 < len(toks) else None
        if not core:
            spoken, dot = "", False
        else:
            spoken, dot = read_core(core, prev, nxt, lex, all_caps)
        # Okunuşa yalnız prozodi işaretleri geçer; tırnak/parantez okunmaz.
        tail = "".join(ch for ch in post if ch in ",;:!?…")
        if dot and not tail:
            tail = "."
        elif core.endswith("...") and spoken == core:
            spoken, tail = core.rstrip("."), "…" + tail
        elif core.endswith(".") and spoken == core:          # sıradan cümle sonu noktası
            spoken, tail = core[:-1], "." + tail
        spoken = (spoken + tail) if spoken else ""
        say = [w for w in (re.sub(r"[^\w'’-]", " ", spoken).replace("'", "").replace("’", "").split()) if w]
        out.append(Word(i, tok, s, e, spoken, say))
    return out


def spoken_text(words: list[Word]) -> str:
    return " ".join(w.spoken for w in words if w.spoken)


# ------------------------------------------------------------------ sayfa → okuma birimleri
PAUSE = {".": 450, "!": 480, "?": 520, "…": 700, ",": 160, "block": 750, "heading": 1000, "bubble": 600,
         "page": 400}
SEG_CHARS = 280                   # bir üretim parçasının hedef uzunluğu (model uzun girdide kararsızlaşıyor); metin kesilmez


@dataclass
class Unit:
    id: str
    kind: str                     # para | dialogue | sound | heading | bubble | text
    speaker: str | None
    voice: str
    text: str
    words: list[Word]


def page_units(pg: dict, cfg: dict, lex: Lexicon) -> list[Unit]:
    """Sayfanın okunacak birimleri, okuma sırasıyla: kutular yukarıdan aşağı, soldan sağa (resmin üstündeki
    balonlar metinden önce okunur); yazı kutusundaki bloklar kendi sırasıyla. Şekil yazısı (tabela, rozet) süstür,
    okunmaz."""
    narrator = cfg.get("narrator") or DEFAULT_NARRATOR
    chars = cfg.get("characters") or {}
    items: list[tuple[float, float, int, list[Unit]]] = []
    order = 0

    def box_key(bx):
        return (round(float(bx.get("y", 0)) / 4), float(bx.get("x", 0))) if bx else (0, 0)

    tx = pg.get("text") or None
    if tx and tx.get("blocks"):
        us = []
        for b in tx["blocks"]:
            t = "".join(r.get("text", "") for r in b.get("runs") or []) if b.get("runs") else b.get("text", "")
            if t.strip():
                us.append(Unit(b["id"], b.get("kind", "para"), None, narrator, t, read(t, lex)))
        if us:
            items.append((*box_key(tx.get("box")), order, us))
            order += 1
    for bb in pg.get("bubbles") or []:
        if (bb.get("text") or "").strip():
            sp = bb.get("speaker")
            v = chars.get(sp) if sp else None
            items.append((*box_key(bb.get("box")), order,
                          [Unit(bb["id"], "bubble", sp, v if v in VOICE_IDS else narrator, bb["text"], read(bb["text"], lex))]))
            order += 1
    for t in pg.get("texts") or []:
        s = "".join(r.get("text", "") for r in t.get("runs") or [])
        if s.strip():
            items.append((*box_key(t.get("box")), order, [Unit(t["id"], "text", None, narrator, s, read(s, lex))]))
            order += 1
    items.sort(key=lambda it: (it[0], it[1], it[2]))
    return [u for it in items for u in it[3]]


@dataclass
class Piece:
    """Bir üretim parçası (cümle ya da uzun cümlenin virgülle bölünmüş kısmı)."""
    unit: int
    words: list[int]              # birimdeki kelime sıraları
    text: str
    voice: str
    pause_ms: int


def pieces(units: list[Unit]) -> list[Piece]:
    out: list[Piece] = []
    for ui, u in enumerate(units):
        cur: list[int] = []

        def flush(end_mark: str):
            if not any(u.words[k].say for k in cur):
                cur.clear()
                return
            text = " ".join(u.words[k].spoken for k in cur if u.words[k].spoken)
            out.append(Piece(ui, list(cur), text, u.voice, PAUSE.get(end_mark, PAUSE["."])))
            cur.clear()

        for k, w in enumerate(u.words):
            cur.append(k)
            sp = w.spoken.rstrip()
            mark = sp[-1:] if sp else ""
            length = sum(len(u.words[j].spoken) + 1 for j in cur)
            if mark in ".!?…":
                flush(mark)
            elif mark in ",;:" and length >= SEG_CHARS:
                flush(",")
            elif length >= SEG_CHARS * 1.6:              # hiç noktalama yoksa kelime sınırında böl
                flush(",")
        flush(".")
        if out and out[-1].unit == ui:
            end = {"heading": "heading", "bubble": "bubble"}.get(u.kind, "block")
            out[-1].pause_ms = max(out[-1].pause_ms, PAUSE[end])
    if out:
        out[-1].pause_ms = PAUSE["page"]
    return out


# ------------------------------------------------------------------ zamanlar
def fill_times(times: list[tuple[float, float] | None], weights: list[int], start: float, end: float
               ) -> tuple[list[tuple[float, float]], list[bool]]:
    """Eksik zamanları komşu bilinen zamanlar arasına ağırlıkla (harf sayısı) yayar. Dönen: (zamanlar, tahmin mi)."""
    n = len(times)
    out: list[tuple[float, float] | None] = list(times)
    est = [t is None for t in times]
    i = 0
    while i < n:
        if out[i] is not None:
            i += 1
            continue
        j = i
        while j < n and out[j] is None:
            j += 1
        lo = out[i - 1][1] if i > 0 else start
        hi = out[j][0] if j < n else end
        hi = max(hi, lo)
        total = sum(max(1, weights[k]) for k in range(i, j))
        t = lo
        for k in range(i, j):
            d = (hi - lo) * max(1, weights[k]) / total
            out[k] = (round(t, 3), round(t + d, 3))
            t += d
        i = j
    return [t for t in out if t is not None], est


GAP_JOIN = 0.5                    # sn: kelimeler arası bundan kısa boşluk önceki kelimeye katılır


def contiguous(times: list[tuple[float, float]], seg_end: float) -> list[tuple[float, float]]:
    """Hizalayıcı harfin en belirgin karelerini verir; kelimeler arası kısa boşluklar önceki kelimenin sonuna
    katılır (vurgu kelimeden kelimeye kesintisiz geçer), parçanın son kelimesi en çok 0,3 sn uzar."""
    out = list(times)
    for x in range(len(out) - 1):
        s, e = out[x]
        nxt = out[x + 1][0]
        if 0 < nxt - e < GAP_JOIN:
            out[x] = (s, nxt)
    if out:
        s, e = out[-1]
        out[-1] = (s, round(max(e, min(seg_end, e + 0.3)), 3))
    return out


def word_times(units: list[Unit], plist: list[Piece], seg_out: list[dict]) -> list[dict]:
    """Servisin parça başına okunuş-kelime zamanlarını ekrandaki kelimelere bağlar. Dönen: birim kayıtları
    (`media_overlay` sayfa kaydının `blocks` alanı)."""
    per_unit: dict[int, dict[int, dict]] = {}
    for p, seg in zip(plist, seg_out):
        say_times: list[tuple[float, float] | None] = []
        weights: list[int] = []
        owner: list[int] = []
        for k in p.words:
            for s in units[p.unit].words[k].say:
                owner.append(k)
                weights.append(len(s))
        got = seg.get("words") or []
        for x in range(len(owner)):
            w = got[x] if x < len(got) else None
            say_times.append((float(w["start"]), float(w["end"])) if w else None)
        filled, est = fill_times(say_times, weights, float(seg["start"]), float(seg["end"]))
        filled = contiguous(filled, float(seg["end"]))
        for x, k in enumerate(owner):
            rec = per_unit.setdefault(p.unit, {}).get(k)
            s, e = filled[x]
            if rec is None:
                per_unit[p.unit][k] = {"start": s, "end": e, "estimated": est[x]}
            else:
                rec["start"], rec["end"] = min(rec["start"], s), max(rec["end"], e)
                rec["estimated"] = rec["estimated"] or est[x]
    blocks = []
    for ui, u in enumerate(units):
        tm = per_unit.get(ui, {})
        words = []
        for w in u.words:
            t = tm.get(w.i)
            words.append({"i": w.i, "text": w.text, "char": [w.start, w.end], "spoken": w.spoken,
                          **({"start": t["start"], "end": t["end"], **({"estimated": True} if t["estimated"] else {})}
                             if t else {"start": None, "end": None})})
        timed = [x for x in words if x["start"] is not None]
        blocks.append({"id": u.id, "kind": u.kind, "speaker": u.speaker, "voice": u.voice, "text": u.text,
                       "start": timed[0]["start"] if timed else None, "end": timed[-1]["end"] if timed else None,
                       "words": words})
    return blocks


# ------------------------------------------------------------------ depo
def _root() -> Path:
    from . import studio
    return studio.root() / "_ses"


def ses_dir(d: Path) -> Path:
    p = d / DIR
    (p / "sayfa").mkdir(parents=True, exist_ok=True)
    return p


def _read(p: Path, default=None):
    return json.loads(p.read_text()) if p.exists() else default


def _write(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
    tmp.replace(p)


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def settings_of(d: Path) -> dict:
    """Sesler: anlatıcı + konuşan → ses. Kayıt yoksa karakter tariflerinden öneri (source: auto)."""
    cfg = _read(d / DIR / "ayar.json")
    if cfg:
        return cfg
    from . import studio
    chars = {}
    ap = studio.read(d, "artplan.json") or {}
    for c in ap.get("characters", []):
        v = guess_voice(c.get("species", ""), c.get("base_look") or c.get("look", ""))
        if v:
            chars[c["name"]] = v
    return {"narrator": DEFAULT_NARRATOR, "characters": chars, "source": "auto"}


def set_settings(d: Path, narrator: str, characters: dict, by: str) -> dict:
    if narrator not in VOICE_IDS:
        raise ValueError("Bilinmeyen ses")
    bad = [v for v in characters.values() if v not in VOICE_IDS]
    if bad:
        raise ValueError("Bilinmeyen ses: " + ", ".join(bad))
    cfg = {"narrator": narrator, "characters": {str(k)[:120]: v for k, v in characters.items()},
           "source": "editor", "updated_by": by, "updated_at": _now()}
    _write(ses_dir(d) / "ayar.json", cfg)
    return cfg


def lexicon_entries(d: Path | None, scope: str) -> list[dict]:
    p = (_root() / "sozluk.json") if scope == "publisher" else (d / DIR / "sozluk.json")
    return _read(p, [])


def set_lexicon(d: Path, scope: str, entries: list[dict], by: str) -> list[dict]:
    """Sözlüğün tamamını yazar (liste). Aynı yazılış iki kez girilirse sonuncusu kalır. Tavan yok."""
    if scope not in ("job", "publisher"):
        raise ValueError("kapsam: job | publisher")
    old = {_lex_key(e["word"]): e for e in lexicon_entries(d, scope)}
    out: dict[str, dict] = {}
    for e in entries:
        w, s = str(e.get("word", "")).strip()[:120], str(e.get("say", "")).strip()[:240]
        if not w or not s:
            continue
        k = _lex_key(w)
        prev = old.get(k)
        same = prev and prev.get("say") == s
        out[k] = {"word": w, "say": s, "by": prev["by"] if same else by, "at": prev["at"] if same else _now()}
    p = (_root() / "sozluk.json") if scope == "publisher" else (ses_dir(d) / "sozluk.json")
    _write(p, list(out.values()))
    return list(out.values())


def lexicon(d: Path) -> Lexicon:
    return Lexicon(lexicon_entries(d, "job"), lexicon_entries(None, "publisher"))


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]


def page_input(d: Path, pg: dict, cfg: dict | None = None, lex: Lexicon | None = None) -> tuple[list[Unit], list[Piece], str]:
    cfg = cfg or settings_of(d)
    lex = lex or lexicon(d)
    units = page_units(pg, cfg, lex)
    plist = pieces(units)
    h = _hash({"v": VERSION, "p": [(p.text, p.voice, p.pause_ms) for p in plist],
               "w": [[w.text for w in u.words] for u in units]})
    return units, plist, h


def page_record(d: Path, pid: str) -> dict | None:
    return _read(d / DIR / "sayfa" / f"{pid}.json")


def audio_path(d: Path, pid: str) -> Path:
    return d / DIR / "sayfa" / f"{pid}.mp3"


def status(d: Path) -> list[dict]:
    """Sayfa başına durum: done (güncel ses var) | stale (metin/ses/sözlük değişti) | missing | empty (okunacak yok)."""
    from . import plan as plan_mod
    pl = plan_mod.load(d)
    if pl is None:
        raise plan_mod.NoPlan(d.name)
    cfg, lex = settings_of(d), lexicon(d)
    out = []
    for pg in pl["pages"]:
        units, plist, h = page_input(d, pg, cfg, lex)
        rec = page_record(d, pg["id"])
        st = "empty" if not plist else ("missing" if not rec or not audio_path(d, pg["id"]).exists()
                                        else "done" if rec.get("hash") == h else "stale")
        out.append({"id": pg["id"], "no": plan_mod.page_no(pl, pg["id"]), "status": st,
                    "duration": rec.get("duration") if rec else None,
                    "estimated": bool(rec and rec.get("estimated")), "words": sum(len(u.words) for u in units)})
    return out


def page_view(d: Path, pid: str) -> dict:
    """Ekran için sayfa: kayıt güncelse zamanlı bloklar, değilse okunuşlu ama zamansız bloklar."""
    from . import plan as plan_mod
    pl = plan_mod.load(d)
    if pl is None:
        raise plan_mod.NoPlan(d.name)
    pg = plan_mod._page(pl, pid)
    units, plist, h = page_input(d, pg)
    rec = page_record(d, pid)
    if rec and rec.get("hash") == h and audio_path(d, pid).exists():
        return {**rec, "status": "done"}
    blocks = word_times(units, [], [])
    return {"page": pid, "no": plan_mod.page_no(pl, pid), "status": "stale" if rec else ("empty" if not plist else "missing"),
            "duration": None, "blocks": blocks}


# ------------------------------------------------------------------ servis
class VoiceUnavailable(RuntimeError):  # noqa: N818
    """Seslendirme servisi bu kurulumda açık değil (takma ad yok ya da ulaşılamıyor)."""


def _endpoint() -> tuple[str, dict]:
    direct = os.environ.get("EDITOR_VOICE_URL", "").rstrip("/")
    if direct:
        return direct, {}
    from ..config import settings
    s = settings()
    return s.gateway_url.rstrip("/"), {"authorization": f"Bearer {s.gateway_key}"}


async def _call(body: dict, timeout: float = 1800.0) -> dict:
    import httpx
    url, headers = _endpoint()
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0)) as c:
        try:
            r = await c.post(f"{url}/v1/audio/narrate", json={"model": ALIAS, **body}, headers=headers)
        except httpx.HTTPError as e:
            raise VoiceUnavailable(f"seslendirme servisine ulaşılamadı: {type(e).__name__}") from None
    if r.status_code == 404:
        raise VoiceUnavailable("seslendirme servisi bu kurulumda açık değil")
    r.raise_for_status()
    return r.json()


async def available() -> bool:
    """Gateway `book-voice` takma adını tanıyor mu (ya da doğrudan uç verilmiş mi)?"""
    import httpx
    if os.environ.get("EDITOR_VOICE_URL"):
        return True
    url, headers = _endpoint()
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(f"{url}/v1/models", headers=headers)
        return r.status_code == 200 and any(m.get("id") == ALIAS for m in r.json().get("data", []))
    except (httpx.HTTPError, ValueError):
        return False


async def voice_ref(vid: str) -> dict:
    """Sesin referansı (yayınevi düzeyinde, bir kez): tarifle üretilir, sonra hep bununla klonlanır."""
    v = voice(vid)
    root = _root() / "sesler"
    meta = _read(root / f"{vid}.json")
    wav = root / f"{vid}.wav"
    if meta and wav.exists() and meta.get("design") == v["design"]:
        return {"ref_audio": base64.b64encode(wav.read_bytes()).decode(), "ref_text": meta["text"]}
    out = await _call({"segments": [{"text": REF_TEXT, "voice": {"design": v["design"]}, "pause_ms": 0,
                                     "seed": REF_SEED}], "format": "wav", "align": False})
    root.mkdir(parents=True, exist_ok=True)
    wav.write_bytes(base64.b64decode(out["audio"]))
    _write(root / f"{vid}.json", {"id": vid, "design": v["design"], "text": REF_TEXT, "seed": REF_SEED, "at": _now(),
                                  "duration": out.get("duration")})
    return {"ref_audio": base64.b64encode(wav.read_bytes()).decode(), "ref_text": REF_TEXT}


async def narrate_page(d: Path, pid: str, by: str) -> dict:
    """Bir sayfayı seslendirir ve kaydeder: ses/sayfa/<pid>.mp3 + .json. Okunacak metin yoksa eski kayıt silinir."""
    from . import plan as plan_mod
    pl = plan_mod.load(d)
    if pl is None:
        raise plan_mod.NoPlan(d.name)
    pg = plan_mod._page(pl, pid)
    units, plist, h = page_input(d, pg)
    sd = ses_dir(d) / "sayfa"
    if not plist:
        for p in (sd / f"{pid}.json", sd / f"{pid}.mp3"):
            p.unlink(missing_ok=True)
        return {"page": pid, "status": "empty"}
    refs = {vid: await voice_ref(vid) for vid in {p.voice for p in plist}}
    body = {"segments": [{"text": p.text, "voice": refs[p.voice], "pause_ms": p.pause_ms,
                          "words": [s for k in p.words for s in units[p.unit].words[k].say]} for p in plist],
            "format": "mp3", "align": True}
    t0 = time.time()
    out = await _call(body)
    blocks = word_times(units, plist, out["segments"])
    est = any(w.get("estimated") for b in blocks for w in b["words"])
    rec = {"version": VERSION, "page": pid, "no": plan_mod.page_no(pl, pid), "hash": h,
           "audio": f"{DIR}/sayfa/{pid}.mp3", "format": "mp3", "duration": out["duration"], "estimated": est,
           "blocks": blocks, "by": by, "at": _now(), "seconds": round(time.time() - t0, 1),
           "voices": sorted(refs)}
    tmp = sd / f"{pid}.mp3.tmp"
    tmp.write_bytes(base64.b64decode(out["audio"]))
    tmp.replace(sd / f"{pid}.mp3")
    _write(sd / f"{pid}.json", rec)
    return {"page": pid, "status": "done", "duration": out["duration"]}


async def sample(text: str, vid: str, lex: Lexicon) -> bytes:
    """Kısa deneme sesi (sözlük satırını ya da sesi dinlemek için); kaydedilmez."""
    words = read(text, lex)
    spoken = spoken_text(words)
    if not spoken.strip():
        raise ValueError("Okunacak metin yok")
    out = await _call({"segments": [{"text": spoken, "voice": await voice_ref(vid), "pause_ms": 0}],
                       "format": "mp3", "align": False}, timeout=600)
    return base64.b64decode(out["audio"])


# ------------------------------------------------------------------ EPUB medya kaplaması
def media_overlay(job) -> dict:
    """Bütün kitabın kelime zamanları (EPUB 3 Media Overlays için). `job`: iş kimliği ya da iş klasörü.

    Dönen biçim:
    {
      "version": 1, "job": "<iş>", "format": "mp3", "complete": bool, "duration": toplam sn,
      "missing": [pid…], "stale": [pid…],          # sesi olmayan / metni değişmiş sayfalar (bu sayfalar pages'e girmez)
      "narrator": "<ses>", "narrators": ["Kadın anlatıcı", …],   # EPUB meta verisi (media:narrator) için
      "pages": [{
        "page": "p_1a2b3c4d", "no": 4,              # plan sayfa kimliği ve basılı sayfa no
        "audio": "/…/ses/sayfa/p_….mp3",             # dosyanın mutlak yolu
        "href": "ses/sayfa/p_….mp3",                  # iş klasörüne göre
        "duration": 12.34,
        "blocks": [{                                 # okuma sırasıyla: yazı blokları, balonlar, serbest yazılar
          "id": "c0b3",                              # plan kimliği (blok / balon b_… / serbest yazı t_…)
          "kind": "para|dialogue|sound|heading|bubble|text", "speaker": "Elif"|null, "voice": "<ses>",
          "text": "Elif pencereden baktı.",          # bloğun düz metni (run'ların birleşimi)
          "start": 0.12, "end": 2.31,
          "words": [{"i": 0, "id": "w-c0b3-0", "text": "Elif", "char": [0, 4],   # char: text içindeki [baş, son)
                     "start": 0.12, "end": 0.48, "estimated": true?}]   # zamanı olmayan kelime: start/end null
        }]
      }]
    }
    Zamanlar saniye, sayfanın ses dosyasının başından. Balon ve serbest yazı da ayrı blok olarak gelir; EPUB bunları
    sayfada nasıl gösteriyorsa kelime aralıklarını aynı kimlikle sarmalıdır.
    """
    from . import plan as plan_mod
    from . import studio
    d = job if isinstance(job, Path) else studio.job_dir(str(job))
    pl = plan_mod.load(d)
    if pl is None:
        raise plan_mod.NoPlan(d.name)
    rows = {r["id"]: r for r in status(d)}
    pages, missing, stale, total = [], [], [], 0.0
    for pg in pl["pages"]:
        st = rows[pg["id"]]["status"]
        if st == "missing":
            missing.append(pg["id"])
        elif st == "stale":
            stale.append(pg["id"])
        if st != "done":
            continue
        rec = page_record(d, pg["id"])
        for b in rec["blocks"]:
            for w in b["words"]:
                w["id"] = word_id(b["id"], w["i"])
        pages.append({"page": pg["id"], "no": rec["no"], "audio": str(audio_path(d, pg["id"])), "href": rec["audio"],
                      "duration": rec["duration"], "blocks": rec["blocks"]})
        total += float(rec["duration"] or 0)
    cfg = settings_of(d)
    used = {cfg.get("narrator") or DEFAULT_NARRATOR} | set((cfg.get("characters") or {}).values())
    return {"version": VERSION, "job": d.name, "format": "mp3", "complete": not missing and not stale,
            "duration": round(total, 3), "missing": missing, "stale": stale,
            "narrator": cfg.get("narrator") or DEFAULT_NARRATOR,
            "narrators": [voice(v)["label"] for v in sorted(used) if v in VOICE_IDS],
            "pages": pages}


def word_id(block_id: str, i: int) -> str:
    return f"w-{block_id}-{i}"


def clock(sec: float) -> str:
    """SMIL saat değeri: 0:00:01.234."""
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h}:{m:02d}:{s:02d}.{ms:03d}"


def smil(page: dict, text_href: str, audio_href: str, word_id_fn=None) -> str:
    """Bir sayfanın SMIL 3.0 belgesi (EPUB 3 Media Overlays): kelime başına bir <par>. `text_href`: sayfanın
    XHTML'i (EPUB içindeki göreli yol), `audio_href`: ses dosyası (aynı). Zamanı olmayan kelime atlanır."""
    wid = word_id_fn or word_id
    pars = []
    for b in page["blocks"]:
        for w in b["words"]:
            if w.get("start") is None:
                continue
            pars.append(f'      <par id="par-{escape(wid(b["id"], w["i"]))}">'
                        f'<text src="{escape(text_href)}#{escape(wid(b["id"], w["i"]))}"/>'
                        f'<audio src="{escape(audio_href)}" clipBegin="{clock(w["start"])}" clipEnd="{clock(w["end"])}"/>'
                        f'</par>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<smil xmlns="http://www.w3.org/ns/SMIL" xmlns:epub="http://www.idpf.org/2007/ops" version="3.0">\n'
            '  <body>\n'
            f'    <seq id="seq-{escape(page["page"])}" epub:textref="{escape(text_href)}" epub:type="bodymatter">\n'
            + "\n".join(pars) + "\n"
            '    </seq>\n'
            '  </body>\n'
            '</smil>\n')
