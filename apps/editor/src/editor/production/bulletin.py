"""Kampüs sesli bülteni: kitaptan bağımsız metni ZEKİ AI sesiyle seslendirir (narration.py'nin okuyucusu ve modeli).

Köprü (Yönetim → Sesli bülten → «Metinden üret») metni ve sesi gönderir; iş Temporal'da `BulletinNarration` olarak
stüdyonun GPU sırasına girer (kitap işleriyle çakışmaz), bitince köprü mp3'ü alıp Kampüs'e taslak bülten olarak
kaydeder. Burada yalnız üretim: yayın, başlık, kim dinler köprünün işi.

Depo: `<stüdyo>/_ses/bulten/<id>/` → `istek.json` (metin, ses, isteyen), `durum.json` (queued | running | done |
fail, hata, süre), `ses.mp3`. Metin paragraflara, paragraf cümlelere bölünür; cümleler `SEG_CHARS`'a kadar bir
parçada toplanır (model uzun girdide kararsızlaşıyor; metin kesilmez). Okunuş yayınevi sözlüğüyle (rakam, tarih,
kısaltma kitaptaki gibi okunur). Bütün parçalar tek çağrıda gider; model sesi tek dosya olarak döner.
"""

from __future__ import annotations

import base64
import re
import secrets
import time
from pathlib import Path

from . import narration as N

TEXT_MAX = 30000                     # ~25 dk konuşma; daha uzunu ayrı bülten olmalı
SENTENCE_PAUSE = 450
PARAGRAPH_PAUSE = 800
BID = re.compile(r"^b[0-9a-f]{12}$")
_SENT = re.compile(r"(?<=[.!?…])\s+")


def root() -> Path:
    return N._root() / "bulten"


def _dir(bid: str) -> Path:
    if not BID.match(bid or ""):
        raise KeyError(bid)
    return root() / bid


def segments_of(text: str, lex: N.Lexicon | None = None) -> list[dict]:
    """Metin → [{text, pause_ms}] (ses referansı sonra eklenir). Boş paragraflar atlanır."""
    out: list[dict] = []
    for par in re.split(r"\n\s*\n", text.strip()):
        par = " ".join(par.split())
        if not par:
            continue
        spoken = N.spoken_text(N.read(par, lex)).strip()
        if not spoken:
            continue
        cur = ""
        for sent in _SENT.split(spoken):
            sent = sent.strip()
            if not sent:
                continue
            if cur and len(cur) + 1 + len(sent) > N.SEG_CHARS:
                out.append({"text": cur, "pause_ms": SENTENCE_PAUSE})
                cur = sent
            else:
                cur = f"{cur} {sent}".strip()
            # Tek cümle bile sınırı aşıyorsa kelime sınırından bölünür (sunucu parça başına 2.000 karakter alır).
            while len(cur) > 1800:
                cut = cur.rfind(" ", 0, 1800)
                cut = cut if cut > 0 else 1800
                out.append({"text": cur[:cut].strip(), "pause_ms": 150})
                cur = cur[cut:].strip()
        if cur:
            out.append({"text": cur, "pause_ms": PARAGRAPH_PAUSE})
    if out:
        out[-1]["pause_ms"] = 0
    return out


def create(text: str, voice: str, by: str, title: str | None = None) -> dict:
    """İsteği kaydeder (iş henüz başlamaz; API Temporal'a verir). Ses ve metin burada doğrulanır."""
    text = (text or "").strip()
    if not text:
        raise ValueError("Bülten metni boş.")
    if len(text) > TEXT_MAX:
        raise ValueError(f"Bülten metni en çok {TEXT_MAX:,} karakter olabilir.".replace(",", "."))
    vid = N.canonical(voice) or N.DEFAULT_NARRATOR
    if not N.is_voice(vid):
        raise ValueError("Bilinmeyen ses.")
    lex = N.Lexicon(N.lexicon_entries(None, "publisher"))
    if not segments_of(text, lex):
        raise ValueError("Okunacak metin yok.")
    bid = "b" + secrets.token_hex(6)
    d = _dir(bid)
    N._write(d / "istek.json", {"text": text, "voice": vid, "title": (title or "")[:300] or None, "by": by[:200],
                                "at": N._now()})
    set_state(bid, status="queued", progress=None, error=None)
    return state(bid)


def set_state(bid: str, **kw) -> None:
    p = _dir(bid) / "durum.json"
    cur = N._read(p, {}) or {}
    N._write(p, {**cur, **kw, "updated": time.time()})


def state(bid: str) -> dict:
    d = _dir(bid)
    req = N._read(d / "istek.json")
    if req is None:
        raise KeyError(bid)
    st = N._read(d / "durum.json", {}) or {}
    return {"id": bid, "status": st.get("status", "queued"), "error": st.get("error"), "voice": req["voice"],
            "title": req.get("title"), "chars": len(req["text"]), "segments": st.get("segments"),
            "duration": st.get("duration"), "seconds": st.get("seconds"), "by": req.get("by"), "at": req.get("at"),
            "ready": (d / "ses.mp3").exists()}


def audio_path(bid: str) -> Path:
    return _dir(bid) / "ses.mp3"


async def narrate(bid: str) -> dict:
    """İşçide koşar: metni okur, sesin referansını alır, tek çağrıda mp3 üretir ve kaydeder."""
    d = _dir(bid)
    req = N._read(d / "istek.json")
    if req is None:
        raise KeyError(bid)
    lex = N.Lexicon(N.lexicon_entries(None, "publisher"))
    segs = segments_of(req["text"], lex)
    if not segs:
        raise ValueError("Okunacak metin yok.")
    set_state(bid, status="running", segments=len(segs), error=None)
    ref = await N.voice_ref(req["voice"])
    t0 = time.time()
    out = await N._call({"segments": [{**s, "voice": ref} for s in segs], "format": "mp3", "align": False})
    tmp = d / "ses.mp3.tmp"
    tmp.write_bytes(base64.b64decode(out["audio"]))
    tmp.replace(d / "ses.mp3")
    set_state(bid, status="done", duration=out.get("duration"), seconds=round(time.time() - t0, 1))
    return state(bid)
