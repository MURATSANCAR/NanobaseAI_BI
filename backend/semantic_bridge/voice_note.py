"""Zeki AI sesli not (M30 saha ziyareti, M31 okul ziyareti): konuşma → Türkçe metin.

Akış: telefon kaydı (tarayıcıda 16 kHz tek kanal WAV'a çevrilir) → köprü (yetki, boyut/süre sınırı, sıra) → GPU'daki
sesli not servisi (`apps/voice-note`, yalnız model) → isteğe bağlı Zeki AI düzeltmesi (noktalama, büyük harf, özel ad,
tutarların rakamla yazımı) → metin not alanına düşer, kişi düzeltip kendisi kaydeder.

Kurallar:
* **Ses saklanmaz.** Köprü gövdeyi bellekte okur, servise iletir, bırakır; dosyaya, veritabanına, günlüğe yazılmaz.
  Metin de burada saklanmaz (not alanına düşer; kaydetmek kişinin işi, kayıt M30/M31'in kendi tablosunda).
* **Düzeltme anlamı ve rakamı değiştiremez.** Modelin metni ham metinle karşılaştırılır: sayı değerleri çoklu küme olarak
  aynı olmalı («yirmi bin» = «20.000»), kelime farkı ve uzunluk oranı sınırda kalmalı; tutmazsa ham metin döner ve
  nedeni söylenir. Model rakam üretmez; yalnız söyleneni biçimler.
* **Sıra.** Köprü içinde geliş sırasını koruyan kapı (`VOICE_NOTE_SLOTS`); GPU'yu koruyan asıl sıra serviste
  (`VOICE_CONCURRENCY`). Bekleyen reddedilmez; `VOICE_NOTE_WAIT_SEC` dolarsa 503 + yeniden dene.
* Ekrana giden hiçbir metinde model/teknoloji adı yok («Zeki AI sesli not»).
"""
from __future__ import annotations

import io
import math
import re
import threading
import time
import wave
from collections import Counter, deque
from typing import Any, Callable, Optional

# ------------------------------------------------------------------ ayarlar


def settings_from(conf: Callable[..., str]) -> dict[str, Any]:
    """Ekran (Yönetim › Zeki AI sesli not) > ortam > varsayılan. Bağlantı adresi ve anahtarı yalnız ortamdan."""

    def i(key: str, default: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(str(conf(key, str(default)) or default))))
        except ValueError:
            return default

    def b(key: str, default: str) -> bool:
        return (conf(key, default) or default).strip().lower() in ("1", "true", "evet", "on")

    return {
        "enabled": b("VOICE_NOTE_ENABLED", "0"),
        "maxSeconds": i("VOICE_NOTE_MAX_SECONDS", 300, 5, 3600),
        "maxMb": i("VOICE_NOTE_MAX_MB", 20, 1, 200),
        "aiFix": b("VOICE_NOTE_AI_FIX", "1"),
        "slots": i("VOICE_NOTE_SLOTS", 2, 1, 64),
        "waitSec": i("VOICE_NOTE_WAIT_SEC", 180, 5, 3600),
        "context": b("VOICE_NOTE_CONTEXT", "0"),
        "vocabulary": (conf("VOICE_NOTE_VOCABULARY", "") or "").strip(),
        "url": (conf("VOICE_NOTE_URL", "") or "").strip().rstrip("/"),
        "token": (conf("VOICE_NOTE_TOKEN", "") or "").strip(),
        "extraHeader": (conf("VOICE_NOTE_EXTRA_HEADER", "") or "").strip(),
        "caFile": (conf("VOICE_NOTE_CA_FILE", "") or "").strip(),
        "timeoutSec": i("VOICE_NOTE_TIMEOUT_SEC", 300, 10, 3600),
    }


def ready(st: dict[str, Any]) -> bool:
    return bool(st["enabled"] and st["url"] and st["token"])


# ------------------------------------------------------------------ ses başlığı


def wav_seconds(data: bytes) -> Optional[float]:
    """WAV başlığından süre (sn); WAV değilse None. Ses çözülmez."""
    if len(data) < 44 or data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        return None
    try:
        with wave.open(io.BytesIO(data)) as w:
            return w.getnframes() / float(w.getframerate() or 1)
    except (wave.Error, EOFError):
        return None


# ------------------------------------------------------------------ sıra kapısı


class GateTimeout(Exception):
    pass


class Gate:
    """Köprü içi, geliş sırasını koruyan kapı: aynı anda en çok `slots` istek servise gider, gerisi sırada bekler."""

    def __init__(self) -> None:
        self._cv = threading.Condition()
        self._line: deque[int] = deque()
        self._next = 0
        self.running = 0

    def enter(self, slots: int, timeout: float) -> tuple[float, int]:
        """Sıra gelince döner: (bekleme ms, girişteki önündeki kişi sayısı). Süre dolarsa GateTimeout."""
        t0 = time.monotonic()
        with self._cv:
            me = self._next
            self._next += 1
            self._line.append(me)
            ahead = len(self._line) - 1 + self.running
            deadline = t0 + timeout
            while not (self._line[0] == me and self.running < max(1, slots)):
                left = deadline - time.monotonic()
                if left <= 0:
                    self._line.remove(me)
                    self._cv.notify_all()
                    raise GateTimeout()
                self._cv.wait(left)
            self._line.popleft()
            self.running += 1
            self._cv.notify_all()
        return (time.monotonic() - t0) * 1000, ahead

    def leave(self) -> None:
        with self._cv:
            self.running = max(0, self.running - 1)
            self._cv.notify_all()

    def view(self) -> dict[str, int]:
        with self._cv:
            return {"running": self.running, "waiting": len(self._line)}


# ------------------------------------------------------------------ sayılar (düzeltme denetimi)

_ONES = {"sıfır": 0, "bir": 1, "iki": 2, "üç": 3, "dört": 4, "beş": 5, "altı": 6, "yedi": 7, "sekiz": 8, "dokuz": 9}
_TENS = {"on": 10, "yirmi": 20, "otuz": 30, "kırk": 40, "elli": 50, "altmış": 60, "yetmiş": 70, "seksen": 80, "doksan": 90}
_SCALES = {"bin": 1_000, "milyon": 1_000_000, "milyar": 1_000_000_000, "trilyon": 1_000_000_000_000}
_ORDINALS = {"birinci": 1, "ikinci": 2, "üçüncü": 3, "dördüncü": 4, "beşinci": 5, "altıncı": 6, "yedinci": 7,
             "sekizinci": 8, "dokuzuncu": 9, "onuncu": 10}
#: Ek alabilen sayı kökleri. «on» (o-na/o-nu), «bir», «bin», «yüz», «altı» başka kelimelerle karıştığı için ekli biçimde
#: sayı sayılmaz; kesme işaretli ek her zaman ayrılır (on'u, 15'inde).
_SUFFIXABLE = {**{k: v for k, v in _ONES.items() if k not in ("bir", "altı")},
               **{k: v for k, v in _TENS.items() if k != "on"}, "milyon": 1_000_000, "milyar": 1_000_000_000}
#: Sayı kökünden sonra gelen ek: ünlüyle ya da d/t/y/s/l/n/ş/c/ç ile başlar, en çok 8 harf (beşinde, dördüncü, onar değil).
_SUFFIX_RE = re.compile(r"[aeıioöuüdtyslnşcç][a-zçğıöşü]{0,7}")
_MUTATE = {"dörd": "dört"}
_NUM_RE = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?")
_DATE_RE = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{2,4})\b")
_TIME_RE = re.compile(r"\b(\d{1,2}):(\d{2})\b")


def _lower(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def _word_value(w: str) -> tuple[Optional[str], Optional[float]]:
    """(tür, değer): tür 'one'/'ten'/'hundred'/'scale'/'ord' ya da None."""
    w = w.split("'")[0].split("’")[0]
    if w in _ONES:
        return "one", _ONES[w]
    if w in _TENS:
        return "ten", _TENS[w]
    if w == "yüz":
        return "hundred", 100
    if w in _SCALES:
        return "scale", _SCALES[w]
    if w in _ORDINALS:
        return "ord", _ORDINALS[w]
    for stem, val in _SUFFIXABLE.items():
        for alt in (stem, *[k for k, v in _MUTATE.items() if v == stem]):
            if w.startswith(alt) and _SUFFIX_RE.fullmatch(w[len(alt):]):
                kind = "one" if stem in _ONES else ("ten" if stem in _TENS else "scale")
                return kind, val
    return None, None


def _digit(tok: str) -> Optional[float]:
    m = _NUM_RE.fullmatch(tok)
    if not m:
        return None
    return float(tok.replace(".", "").replace(",", "."))


def numbers(text: str) -> Counter:
    """Metinde söylenen/yazılan sayı değerleri (çoklu küme). «yirmi bin beş yüz» = «20.500» = 20500; «%15» = «yüzde
    on beş» = 15; tarih «15.10.2026» → 15, 10, 2026; tek başına «bir» (belirsiz tanımlık) sayılmaz."""
    s = _lower(text or "")
    s = _DATE_RE.sub(lambda m: f" {m.group(1)} {m.group(2)} {m.group(3)} ", s)
    s = _TIME_RE.sub(lambda m: f" {m.group(1)} {m.group(2)} ", s)
    s = re.sub(r"(\d)\s*(?=[a-zçğıöşü])", r"\1 ", s)            # 15'inde → 15 'inde; 20bin → 20 bin
    toks = re.findall(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?|[a-zçğıöşüâîû'’]+", s)
    out: Counter = Counter()
    total = cur = 0.0
    run: list[str] = []

    def flush() -> None:
        nonlocal total, cur, run
        if run and not (run == ["one:bir"]):
            out[_key(total + cur)] += 1
        total = cur = 0.0
        run = []

    for t in toks:
        d = _digit(t)
        if d is not None:
            if run:
                flush()
            cur = d
            run.append("digit")
            continue
        if t == "buçuk" and run:
            cur += 0.5
            run.append("half")
            continue
        kind, val = _word_value(t)
        if kind is None:
            flush()
            continue
        if kind == "ord":
            flush()
            out[_key(val)] += 1
            continue
        if kind == "one":
            if run and (run[-1].startswith("one") or run[-1] == "digit"):
                flush()
            cur += val
            run.append(f"one:{t}")
        elif kind == "ten":
            if run and (run[-1].startswith(("one", "ten")) or run[-1] == "digit"):
                flush()
            cur += val
            run.append("ten")
        elif kind == "hundred":
            if run and run[-1] == "digit":
                flush()
            cur = (cur or 1) * 100
            run.append("hundred")
        else:  # scale
            total += (cur or 1) * val
            cur = 0.0
            run.append("scale")
    flush()
    return out


def _key(v: float) -> str:
    return f"{v:.6g}" if not float(v).is_integer() else str(int(v))


# ------------------------------------------------------------------ kelime farkı


def _words(text: str) -> list[str]:
    s = _lower(text or "").translate(str.maketrans("âîû", "aiu"))
    s = re.sub(r"['’`´]", "", s)
    s = re.sub(r"[^\w\s]|_|\d", " ", s)
    return s.split()


def _lev(a: list[str], b: list[str]) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, y in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y))
        prev = cur
    return prev[-1]


_NUMWORDS = set(_ONES) | set(_TENS) | set(_SCALES) | {"yüz", "yüzde", "virgül", "buçuk"}


def check_fix(raw: str, fixed: str, *, max_word_ratio: float = 0.25) -> Optional[str]:
    """Düzeltilmiş metin kabul edilebilir mi: None = evet, değilse Türkçe neden."""
    if not fixed.strip():
        return "Zeki AI boş metin döndürdü."
    if numbers(raw) != numbers(fixed):
        return "Düzeltme sayıları değiştirdi; konuşmanın kendi metni gösteriliyor."
    ra = [w for w in _words(raw) if w not in _NUMWORDS and _word_value(w)[0] is None]
    fb = [w for w in _words(fixed) if w not in _NUMWORDS and _word_value(w)[0] is None]
    lim = max(2, math.ceil(max_word_ratio * max(len(ra), 1)))
    if _lev(ra, fb) > lim:
        return "Düzeltme metni fazla değiştirdi; konuşmanın kendi metni gösteriliyor."
    ln_r, ln_f = len(raw.strip()), len(fixed.strip())
    if ln_r and not (0.6 <= ln_f / ln_r <= 1.5):
        return "Düzeltme metnin uzunluğunu fazla değiştirdi; konuşmanın kendi metni gösteriliyor."
    return None


FIX_SYSTEM = (
    "Sen bir yazım düzelticisin. Sana sahada konuşularak söylenmiş ve otomatik olarak yazıya dökülmüş Türkçe bir ziyaret "
    "notu verilecek. Yalnız şunları yap: noktalama ve büyük harf; yazım ve bitişik/ayrı yazım hataları; özel adları "
    "(kişi, kurum, okul, kitabevi, kitap, yayınevi) doğru yaz — verilen ad listesinde karşılığı varsa listedeki yazımı "
    "kullan. Tutar, adet, yüzde ve tarihleri rakamla yazabilirsin (ör. «yirmi bin lira» → «20.000 TL», «yüzde on beş» → "
    "«%15»), ama değerlerini asla değiştirme. Yapma: cümle ekleme ya da çıkarma, özetleme, yorum, anlamı değiştirme, "
    "sayı ya da tarih uydurma, eksik görüneni tamamlama, argo/konuşma dilini resmileştirme. Yalnız düzeltilmiş metni yaz; "
    "açıklama, tırnak, başlık yok.")


def fix_prompt(raw: str, names: list[str]) -> list[dict[str, str]]:
    names = [n.strip() for n in names if n and n.strip()][:40]
    user = (f"Ad listesi: {', '.join(names)}\n\n" if names else "") + f"Metin:\n{raw}"
    return [{"role": "system", "content": FIX_SYSTEM}, {"role": "user", "content": user}]


def _strip_reply(s: str) -> str:
    s = (s or "").strip()
    s = re.sub(r"^(düzeltilmiş metin|metin)\s*:\s*", "", s, flags=re.IGNORECASE)
    if len(s) >= 2 and s[0] in "\"«“'" and s[-1] in "\"»”'":
        s = s[1:-1].strip()
    return s


def correct(llm: Any, raw: str, names: list[str]) -> dict[str, Any]:
    """Zeki AI düzeltmesi + denetim. Dönen: {metin, durum, neden}. durum: uygulandi | degismedi | atildi | yok."""
    if not raw.strip():
        return {"metin": raw, "durum": "degismedi", "neden": None}
    if llm is None:
        return {"metin": raw, "durum": "yok", "neden": "Zeki AI düzeltmesi şu an kullanılamıyor; konuşmanın kendi metni gösteriliyor."}
    try:
        fixed = _strip_reply(llm.chat(fix_prompt(raw, names), max_tokens=min(4096, 64 + len(raw) // 2), temperature=0))
    except Exception:  # noqa: BLE001 — düzeltme yardımcıdır; ham metin her zaman döner
        return {"metin": raw, "durum": "yok", "neden": "Zeki AI düzeltmesi şu an kullanılamıyor; konuşmanın kendi metni gösteriliyor."}
    why = check_fix(raw, fixed)
    if why:
        return {"metin": raw, "durum": "atildi", "neden": why}
    return {"metin": fixed, "durum": "uygulandi" if fixed != raw else "degismedi", "neden": None}


def context_hint(st: dict[str, Any], names: list[str]) -> str:
    """Servise giden isteğe bağlı ad/sözlük ipucu (varsayılan kapalı; `VOICE_NOTE_CONTEXT`)."""
    if not st.get("context"):
        return ""
    parts = [n.strip() for n in names if n and n.strip()]
    if st.get("vocabulary"):
        parts.append(st["vocabulary"])
    return ", ".join(parts)[:600]
