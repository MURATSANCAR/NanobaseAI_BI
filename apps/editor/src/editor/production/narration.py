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
                        değişince sayfa «güncel değil» görünür. İnsan kaydında (`source: "human"`,
                        narration_human.py) yalnız metnin özeti (`text_hash`) bakılır; üzerine yapay ses yazılmaz
    insan/<yükleme>/    yüklenen insan kaydı: özgün dosya, hak beyanı, izin belgesi (narration_human.py)
Yayınevi düzeyinde (`<storage>/production/_ses/`): sozluk.json (yayınevi sözlüğü), sesler/<ses>.wav|json (her ses bir
kez tarifle üretilen referans; sonra hep o referansla okunur, kitap boyunca aynı ses kalır). Önerilen erkek anlatıcının
referansı pakette sabittir (`production/sesler/`, PINNED; sha256 kodda), yayınevi klasörüne yazılmaz.

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
# Gruplar ekranda başlık olur. Kütüphane (2026-09-27): her grupta kadın ve erkek adaylar; tarifler referans cümlesiyle
# üretilip temel frekansla (kadın > 165 Hz, erkek < 150 Hz ortanca) denetlendi — «lively/bright/energetic» gibi
# sözcükler erkek tarifini tiz sese kaydırıyordu, erkek tarifleri «calm … low/deep male voice» kalıbındadır. Ölçüm ve
# seçim: docs/analiz/sesli-okuma-model-secimi.md «Ses kütüphanesi». Varsayılanlar (DEFAULT_NARRATOR) kullanıcı seçene
# kadar değişmez.
GROUPS = {"anlatici": "Anlatıcı", "cocuk": "Çocuk kitabı anlatıcısı", "yetiskin": "Yetişkin kitap okuyucusu",
          "karakter": "Karakter sesleri"}


def _v(vid: str, label: str, note: str, group: str, design: str) -> dict:
    return {"id": vid, "label": label, "note": note, "group": group, "design": design}


VOICES: list[dict] = [
    _v("anlatici-kadin", "Kadın anlatıcı", "sıcak, sakin", "anlatici",
       "A warm, calm middle-aged woman storyteller, clear gentle diction, unhurried pace"),
    # Önerilen erkek anlatıcı (DEFAULT_MALE_NARRATOR): referansı sabit kayıttır (PINNED), tariften yeniden üretilmez.
    _v("anlatici-erkek-masalci", "Erkek anlatıcı · sıcak masalcı", "olgun, kadifemsi, yavaş", "anlatici",
       "A warm, mature man in his late forties telling a bedtime story to small children: deep, velvety, gentle voice "
       "with a soft smile in it, slow calm pace, very clear Turkish diction, natural pauses at commas and full stops, "
       "tender emphasis on key words"),
    _v("anlatici-kadin-berrak", "Kadın · berrak anlatıcı", "net, dengeli, her kitaba", "anlatici",
       "A clear, confident female narrator in her early forties with a warm mid-range voice, even steady pace, "
       "precise Turkish diction, friendly neutral tone that suits any book"),
    _v("anlatici-kadin-kadife", "Kadın · kadife ses", "alçak, yatıştırıcı, yavaş", "anlatici",
       "A soft-spoken woman in her fifties with a low, velvety, soothing female voice, slow relaxed pace, gentle "
       "warmth, clear careful Turkish pronunciation"),
    _v("anlatici-kadin-canli", "Kadın · canlı anlatıcı", "ifadeli, ölçülü", "anlatici",
       "An expressive woman in her thirties with a bright, engaging female voice, lively yet controlled pace, clear "
       "Turkish diction, natural storytelling intonation with light emphasis"),
    _v("anlatici-erkek-abi", "Erkek · anlatıcı ağabey", "genç, içten, sakin", "anlatici",
       "A young man in his early thirties with a soft low male voice reading a bedtime story, warm big-brother tone, "
       "calm measured pace, clear Turkish diction"),
    _v("anlatici-erkek-radyo", "Erkek · radyo tiyatrosu", "tok, sahne diksiyonu", "anlatici",
       "A deep-voiced man in his forties, a radio theatre narrator with a rich resonant low male voice, theatrical but "
       "warm, deliberate rhythm, dramatic pauses, polished Turkish stage diction, vivid voices in dialogue"),
    _v("masal-kadin-anne", "Kadın · masal okuyan anne", "yumuşak, ninni gibi", "cocuk",
       "A warm young mother in her thirties reading a fairy tale to a small child at bedtime: gentle smiling female "
       "voice, slow to medium pace, soft sing-song storytelling melody, very clear Turkish words"),
    _v("masal-kadin-ogretmen", "Kadın · anaokulu öğretmeni", "neşeli, merak dolu", "cocuk",
       "A cheerful kindergarten teacher, a woman in her late twenties, bright lively female voice full of wonder, "
       "medium pace, playful expressive intonation, clear simple Turkish diction"),
    _v("masal-kadin-nine", "Kadın · masalcı nine", "şefkatli, ağır", "cocuk",
       "A tender grandmother-like woman in her sixties telling a fairy tale: warm cozy female voice, slow unhurried "
       "pace, affectionate tone, clear Turkish pronunciation"),
    _v("masal-erkek-baba", "Erkek · masal okuyan baba", "yumuşak, güven veren", "cocuk",
       "A warm, gentle father in his late thirties reading a bedtime fairy tale: soft low male voice, slow to medium "
       "pace, calm smiling tone, clear Turkish diction, cozy and reassuring"),
    _v("masal-erkek-ogretmen", "Erkek · sınıf öğretmeni", "açık, sevecen", "cocuk",
       "A calm male primary school teacher in his forties with a warm low male voice, reading a storybook to his class, "
       "clear and kind, medium pace, clear Turkish diction"),
    _v("masal-erkek-dede", "Erkek · masalcı dede", "derin, ağır", "cocuk",
       "A kind grandfather in his sixties telling a fairy tale by the fire: warm deep elderly male voice, slow gentle "
       "pace, affectionate tone, clear Turkish words"),
    _v("yetiskin-kadin-roman", "Kadın · roman okuyucusu", "olgun, sakin", "yetiskin",
       "A calm, mature woman in her forties reading a literary novel aloud: warm low female voice, measured even pace, "
       "subtle emotional nuance, precise Turkish diction, audiobook narration style"),
    _v("yetiskin-kadin-deneme", "Kadın · deneme okuyucusu", "düşünceli, ölçülü", "yetiskin",
       "A thoughtful woman in her fifties reading an essay aloud: composed, articulate, clear mid-low female voice, "
       "steady reflective pace, restrained intonation, careful Turkish pronunciation"),
    _v("yetiskin-kadin-cagdas", "Kadın · çağdaş anlatı", "doğal, samimi", "yetiskin",
       "A young adult woman in her early thirties narrating contemporary fiction: natural intimate female voice, "
       "relaxed conversational pace, clear Turkish diction, understated expressiveness"),
    _v("yetiskin-erkek-roman", "Erkek · roman okuyucusu", "derin, ağır", "yetiskin",
       "A calm, mature man in his fifties reading a literary novel aloud: deep low male voice, measured unhurried pace, "
       "subtle nuance, precise Turkish diction, audiobook narration style"),
    _v("yetiskin-erkek-deneme", "Erkek · deneme okuyucusu", "düşünceli, ölçülü", "yetiskin",
       "A thoughtful man in his forties reading an essay aloud: composed, articulate baritone male voice, steady "
       "reflective pace, restrained intonation, careful Turkish pronunciation"),
    _v("yetiskin-erkek-cagdas", "Erkek · çağdaş anlatı", "genç, samimi", "yetiskin",
       "A calm young man in his thirties with a low baritone voice reading a modern novel aloud, intimate "
       "conversational pace, clear Turkish diction"),
    _v("genc-kadin", "Genç kadın", "canlı, içten", "karakter",
       "A young woman in her twenties, lively and sincere, bright voice"),
    _v("genc-erkek", "Genç erkek", "enerjik", "karakter", "A young man in his twenties, energetic and friendly voice"),
    _v("cocuk-kiz", "Küçük kız", "neşeli", "karakter", "A cheerful little girl about eight years old, high playful voice"),
    _v("cocuk-erkek", "Küçük oğlan", "meraklı", "karakter",
       "A curious little boy about eight years old, lively childlike voice"),
    _v("yasli-kadin", "Yaşlı kadın", "şefkatli", "karakter",
       "A kind elderly grandmother in her seventies, soft affectionate slightly shaky voice"),
    _v("yasli-erkek", "Yaşlı adam", "bilge", "karakter", "A wise elderly grandfather in his seventies, low warm slow voice"),
]
from .voices_lively import extend as _lively; GROUPS, VOICES = _lively(GROUPS, VOICES)  # noqa: E402,E702 — CANLI MASAL ANLATICISI kancası (voices_lively.py)
VOICE_IDS = {v["id"] for v in VOICES}
DEFAULT_NARRATOR = "anlatici-kadin"
# Erkek anlatıcı istendiğinde kullanılan ses (kullanıcı kararı 2026-09-27: «sıcak masalcı»). Eski «Erkek anlatıcı»
# (`anlatici-erkek`) bu sese yönlenir: kayıtlı ayar ve API isteği çalışır, ekranda ayrı satır olarak görünmez.
DEFAULT_MALE_NARRATOR = "anlatici-erkek-masalci"
ALIASES = {"anlatici-erkek": DEFAULT_MALE_NARRATOR}
RECOMMENDED = {DEFAULT_MALE_NARRATOR}
# Referans cümle: Türkçe seslerin hepsini (ı, ğ, ş, ç, ö, ü) taşır; ses bir kez bununla üretilir, sonra klonlanır.
REF_TEXT = "Bir varmış bir yokmuş; dağların eteğinde, şirin bir köyde, meraklı ve güler yüzlü bir çocuk yaşarmış."
REF_SEED = 20260925
# Sabit referanslar: aynı tarif ve tohum çalıştırmadan çalıştırmaya biraz farklı ses verebildiği için, kullanıcının
# dinleyip seçtiği referans kaydın kendisi pakette durur (`production/sesler/<ses>.wav`, imajla gelir) ve sha256'sı
# burada sabittir. Kayıt modelin tariften ürettiği sestir (REF_TEXT, REF_SEED; 48 kHz tek kanal, 8,5 sn, temel frekans
# 87 Hz), gerçek kişi kaydı değildir. Dosya yoksa ya da özeti tutmazsa ses üretilmez (tariften sessizce başka bir ses
# üretilmez). Seçim ve ölçüm: docs/analiz/sesli-okuma-model-secimi.md «Ses kütüphanesi».
PINNED_DIR = Path(__file__).with_name("sesler")
PINNED = {
    "anlatici-erkek-masalci": {"file": "anlatici-erkek-masalci.wav", "text": REF_TEXT,
                               "sha256": "41c9a3b283e3ceaed33a5e93ce8ef7b21ef3ae12210ff007399ceeecdcffc785"},
}
_pinned_ok: dict[str, tuple[float, int]] = {}


class PinnedVoiceMissing(ValueError):
    """Sabit referans kaydı kurulumda yok ya da bozuk (ekrana Türkçe cümleyle gider)."""


def canonical(vid: str | None) -> str | None:
    """Eski ses kimliklerini (ALIASES) güncel sese çevirir; bilinmeyeni olduğu gibi bırakır."""
    return ALIASES.get(vid, vid) if vid else vid


def pinned_ref(vid: str) -> bytes:
    """Sabit referans kaydının baytları; sha256 tutmazsa PinnedVoiceMissing. Özet dosya değişmedikçe bir kez hesaplanır."""
    meta = PINNED[vid]
    p = PINNED_DIR / meta["file"]
    try:
        st = p.stat()
        data = p.read_bytes()
    except OSError:
        raise PinnedVoiceMissing("Önerilen erkek anlatıcının ses kaydı bu kurulumda yok; kurulum denetlenmeli.") from None
    key = (st.st_mtime, st.st_size)
    if _pinned_ok.get(vid) != key:
        if hashlib.sha256(data).hexdigest() != meta["sha256"]:
            raise PinnedVoiceMissing("Önerilen erkek anlatıcının ses kaydı beklenen kayıt değil; kurulum denetlenmeli.")
        _pinned_ok[vid] = key
    return data


def voice(vid: str) -> dict:
    """Tarifli ses ya da kütüphaneye yüklenmiş ses (kaldırılmış olsa da; `removed` alanıyla). Eski kimlik güncel sese."""
    vid = canonical(vid)
    for v in VOICES:
        if v["id"] == vid:
            return v
    from . import voices
    r = voices.get(vid) if voices.VID.match(vid or "") else None
    if r is None:
        raise KeyError(vid)
    return voices.as_voice(r)


def is_voice(vid: str | None) -> bool:
    """Seçilebilir ses mi (tarifli ya da kütüphanede kaldırılmamış yüklenmiş ses)."""
    if not vid:
        return False
    if vid in VOICE_IDS or vid in ALIASES:
        return True
    from . import voices
    return bool(voices.VID.match(vid)) and vid in voices.active_ids()


def all_voices() -> list[dict]:
    """Ekrandaki ses listesi: tarifli sesler + kütüphanede kaldırılmamış yüklenmiş sesler (grup sırasıyla). Önerilen
    ses (`recommended`) grubunda varsayılan anlatıcının hemen ardından, erkek anlatıcıların en üstünde gelir."""
    from . import voices
    out = [{**{k: v[k] for k in ("id", "label", "note", "group")},
            **({"recommended": True} if v["id"] in RECOMMENDED else {})} for v in VOICES]
    out += [voices.as_voice(r) for r in voices.entries()]
    order = list(GROUPS)
    return sorted(out, key=lambda v: order.index(v["group"]) if v["group"] in order else len(order))


# Karakter tarifinden (artplan: species/look, İngilizce) sese öneri: genel kelimeler, kitaba özel değil.
_GUESS = [
    (r"\b(grand(ma|mother)|old (woman|lady)|granny|elderly woman|nine)\b", "yasli-kadin"),
    (r"\b(grand(pa|father)|old man|elderly man|dede)\b", "yasli-erkek"),
    (r"\b(girl|daughter)\b", "cocuk-kiz"),
    (r"\b(boy|son)\b", "cocuk-erkek"),
    (r"\b(woman|mother|mom|lady|aunt|teacher \(female\))\b", "genc-kadin"),
    (r"\b(man|father|dad|uncle)\b", "genc-erkek"),
]


# Karşılaştırma/ilişki öbeği karakterin kendisini değil başkasını anlatır: «larger than the father», «like her
# brother», «son of the king» (2026-09-28: dişi vombat «Annesi» tarifteki «than the father» yüzünden erkek sesi aldı).
_OTHER = re.compile(r"\b(than|like|of|with|beside|behind|to|for|and)\s+(the|a|an|his|her|their|its|my|your)\s+\w+(\s+\w+)?")
_FEMALE = re.compile(r"\b(female|she|her|woman|girl|mother|mom|lady|queen|princess|sister|aunt)\b")
_MALE = re.compile(r"\b(male|he|his|man|boy|father|dad|king|prince|brother|uncle)\b")
_SWAP = {"genc-erkek": "genc-kadin", "yasli-erkek": "yasli-kadin", "cocuk-erkek": "cocuk-kiz",
         "genc-kadin": "genc-erkek", "yasli-kadin": "yasli-erkek", "cocuk-kiz": "cocuk-erkek"}


def guess_voice(species: str, look: str = "") -> str | None:
    """Karakter tarifinden ses tahmini: önce tür/rol (species), sonra tarifin karakteri anlatan kısmı. Tarif açıkça
    öbür cinsiyeti söylüyorsa (ör. «female» + erkek kalıbı) eşleşen sesin karşı cinsi seçilir."""
    main = _OTHER.sub(" ", f"{species} {look}".lower())
    vid = None
    for t in (species.lower(), main):
        vid = next((v for pat, v in _GUESS if re.search(pat, t)), None)
        if vid:
            break
    if vid is None:                                       # yalnız «female/male» diyen hayvan tarifi: yetişkin ses
        return "genc-kadin" if re.search(r"\bfemale\b", main) else "genc-erkek" if re.search(r"\bmale\b", main) else None
    fem, mal = bool(_FEMALE.search(main)), bool(_MALE.search(main))
    if vid in ("genc-erkek", "yasli-erkek", "cocuk-erkek") and fem and not mal:
        return _SWAP[vid]
    if vid in ("genc-kadin", "yasli-kadin", "cocuk-kiz") and mal and not fem:
        return _SWAP[vid]
    return vid


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
PAUSE = {".": 450, "!": 480, "?": 520, "…": 700, ",": 160, ":": 300, "block": 750, "heading": 1000, "bubble": 600,
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
    narrator = canonical(cfg.get("narrator")) or DEFAULT_NARRATOR
    chars = {k: canonical(v) for k, v in (cfg.get("characters") or {}).items()}
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
                          [Unit(bb["id"], "bubble", sp, v if is_voice(v) else narrator, bb["text"], read(bb["text"], lex))]))
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


def _core_of(w: Word) -> str:
    return _split_punct(w.text)[1]


def sentence_mark(words: list[Word], k: int) -> str:
    """k. kelimede cümle bitiyorsa sonundaki işaret (. ! ? …), bitmiyorsa "". Ardından küçük harfle süren kelime cümleyi
    sürdürür: «“Pat!” diye», «“Farece…” dedi», «Ama… belki» (2026-09-28 tam kitap dinlemesi: tırnaktan sonra gelen
    «diye» ayrı parça olunca 1 sn kopuyordu)."""
    sp = words[k].spoken.rstrip()
    mark = sp[-1:] if sp else ""
    if mark not in ".!?…":
        return ""
    nxt = next((w for w in words[k + 1:] if w.say), None)
    if nxt is not None and _core_of(nxt)[:1].islower():
        return ""
    return mark


def _speech_starts(words: list[Word], k: int) -> bool:
    """k. kelimeden sonra konuşma başlıyor mu (iki nokta + açılan tırnak ya da tire): «fısıldıyordu: “Kaç!”»."""
    return k + 1 < len(words) and words[k].spoken.rstrip().endswith(":") and words[k + 1].text[:1] in OPEN_P + "–—-"


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
            end = sentence_mark(u.words, k)
            if end:
                flush(end)
            elif _speech_starts(u.words, k):             # anlatıcının girişi ile konuşma ayrı parça (ifade yalnız konuşmaya)
                flush(":")
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
        # eski kimlik (anlatici-erkek) güncel sese: ekran seçili sesi listede bulur, sayfalar yeni sesle «güncel değil»
        return {**cfg, "narrator": canonical(cfg.get("narrator")) or DEFAULT_NARRATOR,
                "characters": {k: canonical(v) for k, v in (cfg.get("characters") or {}).items()}}
    from . import studio
    chars = {}
    ap = studio.read(d, "artplan.json") or {}
    for c in ap.get("characters", []):
        v = guess_voice(c.get("species", ""), c.get("base_look") or c.get("look", ""))
        if v:
            chars[c["name"]] = v
    return {"narrator": DEFAULT_NARRATOR, "characters": chars, "source": "auto"}


def set_settings(d: Path, narrator: str, characters: dict, by: str) -> dict:
    if not is_voice(narrator):
        raise ValueError("Bilinmeyen ses")
    bad = [v for v in characters.values() if not is_voice(v)]
    if bad:
        raise ValueError("Bilinmeyen ses: " + ", ".join(bad))
    cfg = {"narrator": canonical(narrator), "characters": {str(k)[:120]: canonical(v) for k, v in characters.items()},
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


# Kısa ünlem (en çok EXCL_WORDS okunuş kelimesi, «!» ile biten parça) model tarafından çok kısa okunuyor: tam kitap
# dinlemesinde «Tüh!» 0,20 sn, «O da ne!» 0,40–0,46 sn (6,5–7,5 kelime/sn). Servise hece başına en az süre gider; daha kısa
# çıkarsa perdeyi koruyarak esnetilir (servis `min_sec`, en çok %40 yavaşlatma).
EXCL_WORDS = 3
EXCL_SYLLABLE_SEC = 0.28


def excl_min_sec(p: Piece, units: list[Unit]) -> float | None:
    if not p.text.rstrip().endswith("!"):
        return None
    say = [s for k in p.words for s in units[p.unit].words[k].say]
    if not say or len(say) > EXCL_WORDS:
        return None
    syl = sum(max(1, sum(1 for ch in tr_lower(s) if ch in VOWELS)) for s in say)
    return round(syl * EXCL_SYLLABLE_SEC, 2)


def page_input(d: Path, pg: dict, cfg: dict | None = None, lex: Lexicon | None = None) -> tuple[list[Unit], list[Piece], str]:
    cfg = cfg or settings_of(d)
    lex = lex or lexicon(d)
    units = page_units(pg, cfg, lex)
    plist = pieces(units)
    # İFADE KATMANI kancası (expression.py): cümlenin ifadesi parçaya işlenir (p.extra; cümle sonu duraklaması; vurgu),
    # servis gövdesine narrate_page'deki `expression.prepare` çevirir. İşaretsiz sayfada x None: özet eskisiyle aynı.
    from . import expression
    plist, x = expression.apply(d, pg, units, plist)
    ex = [excl_min_sec(p, units) for p in plist]
    h = _hash({"v": VERSION, "p": [(p.text, p.voice, p.pause_ms) for p in plist],
               "w": [[w.text for w in u.words] for u in units], **({"x": x} if x else {}),
               **({"e": ex} if any(ex) else {})})
    return units, plist, h


def text_hash(units: list[Unit]) -> str:
    """Yalnız sayfanın metni (ekrandaki kelimeler, okuma sırasıyla): insan kaydının güncelliği buna bakar. Ses seçimi,
    sözlük ve ifade işareti kaydın kendisini değiştirmez (narration_human.py)."""
    return _hash({"v": VERSION, "t": [[w.text for w in u.words] for u in units]})


def is_human(rec: dict | None) -> bool:
    return bool(rec) and rec.get("source") == "human"


def fresh(rec: dict | None, units: list[Unit], h: str) -> bool:
    """Sayfa kaydı güncel mi: yapay seste girdinin tamamının özeti, insan kaydında yalnız metnin özeti."""
    if not rec:
        return False
    return rec.get("text_hash") == text_hash(units) if is_human(rec) else rec.get("hash") == h


def page_record(d: Path, pid: str) -> dict | None:
    return _read(d / DIR / "sayfa" / f"{pid}.json")


def audio_path(d: Path, pid: str) -> Path:
    return d / DIR / "sayfa" / f"{pid}.mp3"


def status(d: Path) -> list[dict]:
    """Sayfa başına durum: done (güncel ses var) | stale (metin/ses/sözlük değişti) | missing | empty (okunacak yok).
    İnsan kaydında (`human`) güncellik yalnız metne bakar; `owner` kaydı okuyan kişidir."""
    from . import plan as plan_mod
    pl = plan_mod.load(d)
    if pl is None:
        raise plan_mod.NoPlan(d.name)
    cfg, lex = settings_of(d), lexicon(d)
    out = []
    for pg in pl["pages"]:
        units, plist, h = page_input(d, pg, cfg, lex)
        rec = page_record(d, pg["id"])
        has = bool(rec) and audio_path(d, pg["id"]).exists()
        st = "empty" if not plist else ("missing" if not has else "done" if fresh(rec, units, h) else "stale")
        human = has and bool(plist) and is_human(rec)
        out.append({"id": pg["id"], "no": plan_mod.page_no(pl, pg["id"]), "status": st,
                    "duration": rec.get("duration") if rec else None,
                    "estimated": bool(rec and rec.get("estimated")), "words": sum(len(u.words) for u in units),
                    "human": human, **({"owner": (rec.get("human") or {}).get("owner")} if human else {})})
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
    if fresh(rec, units, h) and audio_path(d, pid).exists():
        return {**rec, "status": "done"}
    blocks = word_times(units, [], [])
    return {"page": pid, "no": plan_mod.page_no(pl, pid), "status": "stale" if rec else ("empty" if not plist else "missing"),
            "duration": None, "blocks": blocks,
            **({"source": "human", "human": rec.get("human")} if is_human(rec) and plist else {})}


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
    """Sesin referansı (yayınevi düzeyinde, bir kez): tarifle üretilir, sonra hep bununla klonlanır. Sabit referanslı
    seste (PINNED) paketteki seçilmiş kayıttır. Kütüphaneye
    yüklenmiş seste referans kaydın kendisidir (metinsiz: model yalnız sesi örnek alır); kaldırılmış ses kullanılmaz."""
    vid = canonical(vid)
    v = voice(vid)
    if vid in PINNED:
        # seçilmiş sabit kayıt: tariften yeniden üretilmez (üretim her seferinde biraz farklı ses verebilir)
        return {"ref_audio": base64.b64encode(pinned_ref(vid)).decode(), "ref_text": PINNED[vid]["text"]}
    if v.get("uploaded"):
        if v.get("removed"):
            raise ValueError(f"«{v['label']}» sesi kütüphaneden kaldırıldı; başka bir ses seçin.")
        from . import voices
        return {"ref_audio": voices.ref_audio(vid), "ref_text": None}
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


async def narrate_page(d: Path, pid: str, by: str, keep_human: bool = False) -> dict:
    """Bir sayfayı seslendirir ve kaydeder: ses/sayfa/<pid>.mp3 + .json. Okunacak metin yoksa eski kayıt silinir.
    `keep_human`: sayfada insan kaydı varsa dokunulmaz (editör yapay sesle değiştirmeyi açıkça istemediyse)."""
    from . import plan as plan_mod
    pl = plan_mod.load(d)
    if pl is None:
        raise plan_mod.NoPlan(d.name)
    pg = plan_mod._page(pl, pid)
    units, plist, h = page_input(d, pg)
    sd = ses_dir(d) / "sayfa"
    if keep_human and is_human(page_record(d, pid)) and audio_path(d, pid).exists():
        return {"page": pid, "status": "human"}
    if not plist:
        for p in (sd / f"{pid}.json", sd / f"{pid}.mp3"):
            p.unlink(missing_ok=True)
        return {"page": pid, "status": "empty"}
    refs = {vid: await voice_ref(vid) for vid in {p.voice for p in plist}}
    body = {"segments": [{"text": p.text, "voice": refs[p.voice], "pause_ms": p.pause_ms,
                          "words": [s for k in p.words for s in units[p.unit].words[k].say],
                          **({"min_sec": m} if (m := excl_min_sec(p, units)) else {})} for p in plist],
            "format": "mp3", "align": True}
    t0 = time.time()
    from . import expression
    await expression.prepare(body, plist)          # İFADE KATMANI kancası: ifade örneği / talimat, hız, önceki durak
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
    await _efekt_kancasi(d, pid, by)
    return {"page": pid, "status": "done", "duration": out["duration"]}


async def _efekt_kancasi(d: Path, pid: str, by: str) -> None:
    """EFEKT SESLERİ KANCASI (production/sfx.py) — sesli okumadaki tek bağlantı noktası. Sayfa sesi yazıldıktan sonra
    efektler açıksa sayfanın efekt önerisi (hiç yoksa) çıkarılır ve efektli karışım yenilenir. Anlatım dosyasına ve
    kelime zamanlarına dokunulmaz (karışım ayrı dosya: ses/efekt/karisim/). Efekt tarafındaki hiçbir hata seslendirmeyi
    düşürmez: günlüğe yazılır, sayfa anlatımla hazırdır."""
    try:
        from . import sfx
        await sfx.after_narration(d, pid, by)
    except Exception:  # noqa: BLE001
        import logging
        logging.getLogger(__name__).exception("efekt karışımı yapılamadı (%s %s)", d.name, pid)


async def sample(text: str, vid: str, lex: Lexicon) -> bytes:
    """Kısa deneme sesi (sözlük satırını ya da sesi dinlemek için). Aynı ses ve okunuş için bir kez üretilir, yayınevi
    düzeyinde saklanır (`_ses/ornek/`): kütüphanedeki «dinle» düğmeleri ikinci kez beklemez."""
    words = read(text, lex)
    spoken = spoken_text(words)
    if not spoken.strip():
        raise ValueError("Okunacak metin yok")
    vid = canonical(vid)
    ref = await voice_ref(vid)
    key = _hash({"v": VERSION, "voice": vid, "ref": hashlib.sha256(ref["ref_audio"].encode()).hexdigest(),
                 "text": spoken})
    cache = _root() / "ornek" / f"{key}.mp3"
    if cache.exists():
        return cache.read_bytes()
    out = await _call({"segments": [{"text": spoken, "voice": ref, "pause_ms": 0}],
                       "format": "mp3", "align": False}, timeout=600)
    data = base64.b64decode(out["audio"])
    cache.parent.mkdir(parents=True, exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_bytes(data)
    tmp.replace(cache)
    return data


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
    people, machine = [], False            # anlatıcılar: insan kaydını okuyanlar + (yapay sesli sayfa varsa) sesler
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
        if is_human(rec):
            who = ((rec.get("human") or {}).get("owner") or "").strip()
            if who and who not in people:
                people.append(who)
        else:
            machine = True
    cfg = settings_of(d)
    used = {cfg.get("narrator") or DEFAULT_NARRATOR} | set((cfg.get("characters") or {}).values())  # settings_of: güncel kimlik
    return {"version": VERSION, "job": d.name, "format": "mp3", "complete": not missing and not stale,
            "duration": round(total, 3), "missing": missing, "stale": stale,
            "narrator": cfg.get("narrator") or DEFAULT_NARRATOR,
            "narrators": people + (_labels(sorted(used)) if machine or not people else []),
            "pages": pages}


def _labels(vids: list[str]) -> list[str]:
    out = []
    for v in vids:
        try:
            out.append(voice(v)["label"])
        except KeyError:
            continue
    return out


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
    clips = [(wid(b["id"], w["i"]), audio_href, w["start"], w["end"])
             for b in page["blocks"] for w in b["words"] if w.get("start") is not None]
    return smil_doc(clips, text_href, f"seq-{page['page']}", continuous=False)[0]


def smil_doc(clips: list[tuple[str, str, float, float]], text_href: str, seq_id: str, *,
             continuous: bool = True) -> tuple[str, float]:
    """SMIL 3.0 belgesi ve toplam süresi (sn). `clips`: okuma sırasıyla (kelime kimliği, ses dosyası, baş, son); bir
    belge birden çok sayfanın sesini taşıyabilir (akışkan e-kitapta bölüm). `continuous`: aynı sesteki ardışık iki
    kelimenin arası (cümle sonu, paragraf arası duraklaması) öndekine katılır; okuyucu klipten klibe geçerken
    duraklamaları atlamaz, ses doğal akar. Süre = kliplerin toplamı (OPF `media:duration`), milisaniyeyle toplanır."""
    items = [[c[0], c[1], int(round(float(c[2]) * 1000)), int(round(float(c[3]) * 1000))] for c in clips]
    if continuous:
        for k in range(len(items) - 1):
            if items[k + 1][1] == items[k][1] and items[k + 1][2] > items[k][3]:
                items[k][3] = items[k + 1][2]
    pars, total = [], 0
    for wid_, audio, a, b in items:
        b = max(b, a + 1)
        total += b - a
        pars.append(f'      <par id="par-{escape(wid_)}">'
                    f'<text src="{escape(text_href)}#{escape(wid_)}"/>'
                    f'<audio src="{escape(audio)}" clipBegin="{clock(a / 1000)}" clipEnd="{clock(b / 1000)}"/>'
                    f'</par>')
    doc = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<smil xmlns="http://www.w3.org/ns/SMIL" xmlns:epub="http://www.idpf.org/2007/ops" version="3.0">\n'
           '  <body>\n'
           f'    <seq id="{escape(seq_id)}" epub:textref="{escape(text_href)}" epub:type="bodymatter">\n'
           + "\n".join(pars) + "\n"
           '    </seq>\n'
           '  </body>\n'
           '</smil>\n')
    return doc, total / 1000
