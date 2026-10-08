"""Replik sesleri: her replik kendi karakterinin sesiyle ve duygusuyla seslendirme servisinde (gateway `book-voice`)
okunur; gerçek süre çekimin süresini belirler (spec.fit_seconds) — film görüntüden önce sesle kurulur.

Okunuş Sesli Okuma'nın Türkçe kurallarıdır (narration.read: sayı, kısaltma, sözlük). Duygu, Sesli Okuma'nın ölçülmüş
ifade tablosuna bağlanır (expression.TABLE: hız, önceki durak, fısıltı talimatı, üzüntü örneği) — yeni ölçüm
yapılmadan yeni ton eklenmez. Kısa ünlemde ton verilmez (expression.MIN_STYLE_WORDS), yalnız hız ve durak.

Kayıt `ses.json`: {"lines": {<çekim>: [{"i", "speaker", "voice", "emotion", "text", "file", "duration", "key"}]},
"seconds": {<çekim>: süre}}. Aynı ses + metin + duygu bir kez üretilir (anahtar), senaryo düzeltilince yalnız değişen
replik yeniden okunur.
"""

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from .. import expression as X
from .. import narration as N
from . import cast as cast_mod
from . import script as script_mod
from . import spec, store

VERSION = 1
# film duygusu → Sesli Okuma ifade etiketi (+ ek kazanç). Bağırma ayrı bir ton değil: öfkenin hızı + yüksek kazanç.
EMOTION = {"notr": ("notr", 0.0), "neseli": ("nese", 0.0), "heyecanli": ("heyecan", 0.0), "uzgun": ("uzuntu", 0.0),
           "korkmus": ("korku", 0.0), "ofkeli": ("ofke", 0.0), "bagirarak": ("ofke", 4.0),
           "fisiltiyla": ("fisilti", 0.0), "aglayarak": ("uzuntu", 0.0), "gulerek": ("nese", 0.0),
           "saskin": ("saskinlik", 0.0), "merakli": ("merak", 0.0), "yorgun": ("uzuntu", -2.0)}


def _key(ref: dict, spoken: str, emotion: str) -> str:
    h = hashlib.sha256(json.dumps({"v": VERSION, "ref": hashlib.sha256(ref["ref_audio"].encode()).hexdigest(),
                                   "t": spoken, "e": emotion,
                                   **({"tf": ref["transform"]} if ref.get("transform") else {})},
                                  sort_keys=True).encode())
    return h.hexdigest()[:20]


def segment(spoken: str, ref: dict, vid: str, emotion: str) -> tuple[dict, SimpleNamespace]:
    """Servis parçası + ifade kancasının beklediği parça nesnesi (expression.prepare)."""
    label, gain = EMOTION.get(emotion, ("notr", 0.0))
    row = X.TABLE[label]
    seg = {"text": spoken, "voice": ref, "pause_ms": 0}
    extra = None
    if label != "notr":
        extra = {"label": label, "tone": len(spoken.split()) >= X.MIN_STYLE_WORDS and bool(row["method"])}
        if row.get("rate", 1.0) != 1.0 and len(spoken.split()) >= X.RATE_MIN_WORDS:
            extra["rate"] = row["rate"]
        if row.get("gain_db") or gain:
            extra["gain_db"] = row.get("gain_db", 0.0) + gain
    return seg, SimpleNamespace(voice=vid, extra=extra)


async def synth(d: Path, f: Path, by: str, progress=lambda n, t, w="": None) -> dict:
    store.require(f, "oyuncular")
    sc = script_mod.load(f)
    cast = cast_mod.load(f)
    lex = N.lexicon(d)
    sd = f / "ses"
    sd.mkdir(exist_ok=True)
    old = store.read(f, "ses.json") or {"lines": {}}
    cached = {x["key"]: x for xs in old["lines"].values() for x in xs if (sd / x["file"]).exists()}
    store.set_stage(f, "ses", status="calisiyor")
    shots = spec.shots(sc)
    total = sum(len(s["lines"]) for s in shots) or 1
    refs: dict[str, dict] = {}
    lines, seconds, n = {}, {}, 0
    for s in shots:
        out = []
        for i, ln in enumerate(s["lines"]):
            n += 1
            progress(n, total, "Replikler seslendiriliyor")
            vid = cast_mod.voice_of(cast, ln["speaker"])
            if vid not in refs:
                refs[vid] = await N.voice_ref(vid)
            spoken = N.spoken_text(N.read(ln["text"], lex))
            if not spoken.strip():
                continue
            key = _key(refs[vid], spoken, ln["emotion"])
            if key in cached:
                out.append({**cached[key], "i": i})
                continue
            seg, piece = segment(spoken, refs[vid], vid, ln["emotion"])
            body = {"segments": [seg], "format": "wav", "align": False}
            await X.prepare(body, [piece])
            res = await N._call(body, timeout=900)
            name = f"{s['id']}-{i}-{key[:8]}.wav"
            (sd / name).write_bytes(base64.b64decode(res["audio"]))
            out.append({"i": i, "speaker": ln["speaker"], "voice": vid, "emotion": ln["emotion"], "text": ln["text"],
                        "file": name, "duration": float(res["duration"]), "key": key})
        lines[s["id"]] = out
        seconds[s["id"]] = spec.fit_seconds(float(s["seconds"]), [x["duration"] for x in out])
    rec = {"version": VERSION, "lines": lines, "seconds": seconds, "total": round(sum(seconds.values()), 2),
           "by": by, "at": store.now()}
    store.write(f, "ses.json", rec)
    store.set_stage(f, "ses", status="hazir", seconds=rec["total"])
    store.log(f, by, "replikler seslendirildi", lines=n)
    return rec


def load(f: Path) -> dict:
    rec = store.read(f, "ses.json")
    if not rec:
        raise store.FilmError("Replik sesleri yok.")
    return rec
