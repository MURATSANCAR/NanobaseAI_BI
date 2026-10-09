"""Görüntüden efekt sesi (foley): her çekimin kendi videosundan senkron efekt + ortam sesi (2026-10-08/09).

Arşivden seçilen efekt çekimin başına konuyordu, hareketle senkron değildi (paket açma sesi). HunyuanVideo-Foley
(images/foley, `editor-foley:1`) videoya bakıp sesi üretir; çıktıda zaman zaman anlamsız «konuşma» olur, Demucs ile
insan sesi kolu ayrılıp atılır (özgün `foley/ham/<çekim>.wav`). Kurgu `foley/<çekim>.wav`'ı arşiv efektinin ve sahne
ortamının yerine kullanır (mix.foley_files).

Bu modül iş listesini kurar; üretim konteynerde toplu koşar (model bir kez yüklenir). Kurallar kitaptan bağımsızdır.
"""

from __future__ import annotations

import json
from pathlib import Path

from . import spec, store
from . import script as script_mod
from .shoot import source_of

NEGATIVE = "speech, talking, voice, singing, choir, music"


def prompt_of(shot: dict) -> str:
    """Foley istemi: çekimde görünen hareket + senaryonun efekt/ortam tarifleri (İngilizce; metin kodlayıcı İngilizce
    eğitilmiş, Türkçe tarif zayıf eşleşiyordu)."""
    parts = [f"Realistic sound effects and room tone: {(shot.get('action_en') or '').strip()}"]
    sfx = [x for x in shot.get("sfx", []) if x.strip()]
    if sfx:
        parts.append("Sounds: " + ", ".join(sfx) + ".")
    if (shot.get("ambience") or "").strip():
        parts.append(f"Ambience: {shot['ambience'].strip()}.")
    return " ".join(parts)


def jobs(f: Path, mount: str | None = None) -> list[dict]:
    """Toplu iş listesi [{video, prompt, out}]: seçili çekimin (dudak senkronlu kopyası varsa o) sesi henüz
    üretilmemiş ya da çekim değişmişse. `mount`: konteynerde film klasörünün yolu (varsayılan aynı yol)."""
    sc = script_mod.load(f)
    rec = store.read(f, "cekimler.json") or {"shots": {}}
    stamp = store.read(f, "foley.json") or {}
    root = mount or str(f)
    out = []
    for s in spec.shots(sc):
        x = rec["shots"].get(s["id"])
        if not x or not x.get("selected"):
            continue
        v = x["versions"][x["selected"] - 1]
        wav = f / "foley" / f"{s['id']}.wav"
        if wav.is_file() and stamp.get(s["id"]) == v["file"]:
            continue
        src = source_of(f, v)
        out.append({"video": f"{root}/cekim/{src.name}", "prompt": prompt_of(s), "out": f"{root}/foley/{s['id']}.wav",
                    "shot": s["id"], "file": v["file"]})
    return out


def mark_done(f: Path, done: list[dict]) -> None:
    """Üretilen işlerin çekim sürümünü kaydeder (çekim değişince ses yeniden üretilir)."""
    stamp = store.read(f, "foley.json") or {}
    for j in done:
        stamp[j["shot"]] = j["file"]
    store.write(f, "foley.json", stamp)


def write_jobs(f: Path, path: Path, mount: str | None = None) -> int:
    (f / "foley").mkdir(exist_ok=True)
    js = jobs(f, mount)
    path.write_text(json.dumps(js, ensure_ascii=False, indent=1))
    return len(js)
