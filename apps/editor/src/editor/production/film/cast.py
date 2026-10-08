"""Oyuncular: senaryonun karakterleri → görünüş (dizinin onaylı karakter kartı varsa o) ve ses (ses kataloğu).

Görünüş: kart varsa kartın İngilizce tarifi ve birincil referans görseli (characters.CardSet) — kart her çekimde
aynıdır; kart yoksa senaryonun `look_en`'i kullanılır ve ilk karede karakterin referansı üretilir (frames.py).
Ses: yaş + cinsiyet + rol kelimesinden katalogdaki sese (voices_zeki); aynı sesi iki ana karaktere vermemek için her
grupta sıradaki aday seçilir. Editör sesi değiştirir, dinler, onaylar.
"""

from __future__ import annotations

import re
from pathlib import Path

from .. import narration
from ..characters import CardSet
from . import spec, store

# (yaş, cinsiyet) → aday sesler (sırayla dağıtılır). Çocuk karakter önce çocuk sesleriyle okunur (ilkokul çağı, sonra
# okul öncesi; voices_zeki.CHILD_VOICES); onay bekleyen ses katalogda yoktur, kimliği genç sese gider (canonical) ve
# listede tek kez sayılır — o zaman çocuk karakter eskisi gibi genç sesle okunur.
CANDIDATES = {
    ("cocuk", "kadin"): ["cocuk-kiz", "kucuk-kiz", "genc-kadin", "masal-anne"],
    ("cocuk", "erkek"): ["cocuk-erkek", "kucuk-erkek", "genc-erkek", "masal-baba"],
    ("genc", "kadin"): ["genc-kadin", "roman-kadin"], ("genc", "erkek"): ["genc-erkek", "roman-erkek"],
    ("yetiskin", "kadin"): ["roman-kadin", "masal-anne", "tarih-kadin", "gelisim-kadin"],
    ("yetiskin", "erkek"): ["roman-erkek", "masal-baba", "tarih-erkek", "gelisim-erkek"],
    ("yasli", "kadin"): ["masal-nine", "tasavvuf-kadin"],
    ("yasli", "erkek"): ["masal-dede", "bilge-dede", "yasli-kaptan", "tasavvuf-erkek"],
}
ROLE_VOICES = [(re.compile(r"kötü|zalim|karanlık|düşman|cadı", re.I), "karanlik-lord"),
               (re.compile(r"kral|padişah|sultan|hükümdar", re.I), "yasli-kral"),
               (re.compile(r"kaptan|denizci|korsan", re.I), "yasli-kaptan"),
               (re.compile(r"bilge|derviş|hoca|öğretmen", re.I), "bilge-dede")]
NARRATOR = {"cizgi-film": "masal-anne", "fragman": "fragman-anlatici", "reels": "roman-kadin"}


def _ok(vid: str) -> bool:
    return narration.is_voice(vid)


def pick_voice(member: dict, used: set[str]) -> str:
    role = member.get("role", "")
    for rx, vid in ROLE_VOICES:
        if rx.search(role) and _ok(vid) and member.get("gender") != "kadin":
            return vid
    key = (member.get("age", "yetiskin"), member.get("gender", "belirsiz"))
    if key[1] == "belirsiz":
        key = (key[0], "kadin")
    cands = list(dict.fromkeys(narration.canonical(v) for v in CANDIDATES.get(key, CANDIDATES[("yetiskin", "kadin")])
                               if _ok(v)))
    if key[0] == "cocuk" and narration.LITTLE.search(f"{member.get('look_en', '')} {role}".lower()):
        little = [v for v in cands if v.startswith("kucuk-")]   # okul öncesi yaşı söyleyen tarif: küçük çocuk sesi önce
        cands = little + [v for v in cands if v not in little]
    for v in cands:
        if v not in used:
            return v
    return cands[0] if cands else narration.canonical("roman-kadin")


def build(d: Path, f: Path, script: dict, by: str) -> dict:
    cards = CardSet.for_job(d)
    used: set[str] = set()
    members = []
    for c in script.get("cast", []):
        card = cards.card(c["name"]) if cards else None
        refs = cards.ref_paths([c["name"]]) if cards else {}
        voice = pick_voice(c, used)
        used.add(voice)
        members.append({"name": c["name"], "role": c.get("role", ""), "age": c.get("age"), "gender": c.get("gender"),
                        "look_en": (card or {}).get("look_en") or c.get("look_en", ""),
                        "card": card["id"] if card else None, "ref": refs.get(c["name"]), "voice": voice})
    m = store.meta(f)
    old = store.read(f, "oyuncular.json") or {"rev": 0}
    rec = {"rev": old["rev"] + 1, "narrator": NARRATOR[m["format"]], "members": members, "by": by, "at": store.now()}
    store.write(f, "oyuncular.json", rec)
    store.set_stage(f, "oyuncular", status="hazir", count=len(members))
    store.log(f, by, "oyuncular hazırlandı", count=len(members))
    return rec


def load(f: Path) -> dict:
    rec = store.read(f, "oyuncular.json")
    if not rec:
        raise store.FilmError("Oyuncu listesi yok.")
    return rec


def set_voice(f: Path, name: str, voice: str, rev: int, by: str) -> dict:
    rec = load(f)
    if rec["rev"] != rev:
        raise store.FilmError("Oyuncu listesi bu arada değişti; sayfayı yenileyin.")
    vid = narration.canonical(voice)
    if not _ok(vid):
        raise store.FilmError("Bu ses katalogda yok.")
    if name == spec.NARRATOR:
        rec["narrator"] = vid
    else:
        mem = next((x for x in rec["members"] if x["name"] == name), None)
        if mem is None:
            raise store.FilmError("Böyle bir oyuncu yok.")
        mem["voice"] = vid
    rec.update(rev=rec["rev"] + 1, by=by, at=store.now())
    store.write(f, "oyuncular.json", rec)
    store.set_stage(f, "oyuncular", status="hazir", count=len(rec["members"]))
    store.log(f, by, "ses değişti", name=name, voice=vid)
    return rec


def voice_of(rec: dict, speaker: str) -> str:
    if speaker.casefold() == spec.NARRATOR:
        return rec["narrator"]
    for m in rec["members"]:
        if m["name"].casefold() == speaker.casefold():
            return m["voice"]
    return rec["narrator"]


_DRAWING = re.compile(r"\s*(?:Drawing|Art|Illustration)\s+style:[^.]*(?:\.|$)", re.I)


def card_lines(rec: dict, style: str | None = None) -> dict[str, str]:
    """Oyuncu → istem satırı (İngilizce görünüş). Film 2B değilse kartın kitaptan gelen çizim tarzı cümlesi düşer:
    3B filmde «thick black ink outlines» karakterleri 2B çizdiriyordu (2026-10-08)."""
    def look(m: dict) -> str:
        t = m["look_en"]
        return _DRAWING.sub("", t).strip() if style and style != "2b" else t
    return {m["name"]: f"{m['name']}: {look(m).rstrip('.')}." for m in rec["members"] if m.get("look_en")}
