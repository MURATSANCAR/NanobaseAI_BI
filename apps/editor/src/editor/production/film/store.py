"""Filmin klasörü ve durumu. Bir stüdyo işinin altında birden çok film olabilir (aynı kitaptan çizgi film + reels).

    <iş>/film/<fid>/
        film.json        biçim, üslup, ad, adımların durumu (STAGES), onaylar
        senaryo.json     çekim listesi (script.py) + denetim sonucu
        oyuncular.json   karakter → kart, ses (cast.py)
        ses/<çekim>-<n>.wav, ses.json       replik sesleri ve gerçek süreleri (dialogue.py)
        kare/<çekim>.vK.png, kareler.json   ilk kareler (frames.py)
        cekim/<çekim>.vK.mp4, cekimler.json video çekimleri (shoot.py)
        cikti/                           kurgu, altyazı, platform kesitleri, kapak (mix.py, social.py)
        kayit.jsonl      kim ne zaman ne yaptı (onaylar dahil)

Adım sırası değişmez; bir adım yeniden koşunca kendisinden sonraki adımların onayı düşer («güncel değil»).
"""

from __future__ import annotations

import json
import secrets
import threading
import time
from pathlib import Path

from .. import studio
from . import spec

DIR = "film"
STAGES = ("senaryo", "oyuncular", "ses", "kareler", "cekim", "kurgu", "paylasim")
NEEDS_APPROVAL = {"senaryo", "oyuncular", "kareler", "kurgu", "paylasim"}
_lock = threading.Lock()


class FilmError(ValueError):
    """Editöre gösterilecek Türkçe hata."""


def root(d: Path) -> Path:
    p = d / DIR
    p.mkdir(exist_ok=True)
    return p


def fdir(d: Path, fid: str) -> Path:
    if not (fid.startswith("f_") and fid[2:].isalnum() and len(fid) <= 12):
        raise FilmError("geçersiz film")
    p = root(d) / fid
    if not p.is_dir():
        raise FileNotFoundError(fid)
    return p


def read(f: Path, name: str, default=None):
    return studio.read(f, name, default)


def write(f: Path, name: str, obj) -> None:
    studio.write(f, name, obj)


def now() -> float:
    return time.time()


def log(f: Path, by: str, what: str, **extra) -> None:
    with _lock, (f / "kayit.jsonl").open("a") as fh:
        fh.write(json.dumps({"at": now(), "by": by, "what": what, **extra}, ensure_ascii=False) + "\n")


def events(f: Path) -> list[dict]:
    p = f / "kayit.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines() if x.strip()][::-1] if p.exists() else []


def create(d: Path, fmt: str, style: str, title: str, by: str) -> Path:
    if fmt not in spec.FORMATS:
        raise FilmError("bilinmeyen biçim")
    if style not in spec.STYLES:
        raise FilmError("bilinmeyen üslup")
    fid = "f_" + secrets.token_hex(4)
    f = root(d) / fid
    f.mkdir()
    write(f, "film.json", {"id": fid, "format": fmt, "style": style, "title": title.strip()[:120],
                           "created_by": by, "created_at": now(),
                           "stages": {s: {"status": "bekliyor"} for s in STAGES}})
    log(f, by, "film açıldı", format=fmt, style=style)
    return f


def films(d: Path) -> list[dict]:
    r = d / DIR
    if not r.is_dir():
        return []
    out = [read(p, "film.json") for p in sorted(r.iterdir()) if (p / "film.json").exists()]
    return sorted((x for x in out if x), key=lambda x: x["created_at"], reverse=True)


def meta(f: Path) -> dict:
    m = read(f, "film.json")
    if not m:
        raise FileNotFoundError(f.name)
    return m


def set_stage(f: Path, stage: str, **fields) -> dict:
    """Adımın durumunu yazar. `status="hazir"` olan adım yeniden üretildiyse sonraki adımlar «eski» olur."""
    with _lock:
        m = meta(f)
        st = m["stages"].setdefault(stage, {})
        rebuilt = fields.get("status") == "hazir" and st.get("status") in ("hazir", "onayli")
        st.update(fields, at=now())
        if fields.get("status") == "hazir":
            st.pop("approved_by", None)
            st.pop("approved_at", None)
        if rebuilt:
            for later in STAGES[STAGES.index(stage) + 1:]:
                if m["stages"].get(later, {}).get("status") in ("hazir", "onayli"):
                    m["stages"][later]["status"] = "eski"
        write(f, "film.json", m)
        return m


def approve(f: Path, stage: str, ok: bool, by: str) -> dict:
    if stage not in NEEDS_APPROVAL:
        raise FilmError("bu adım onay istemez")
    m = meta(f)
    st = m["stages"][stage]
    if st.get("status") not in ("hazir", "onayli"):
        raise FilmError("adım hazır değil")
    with _lock:
        m = meta(f)
        st = m["stages"][stage]
        if ok:
            st.update(status="onayli", approved_by=by, approved_at=now())
        else:
            st.update(status="hazir")
            st.pop("approved_by", None)
            st.pop("approved_at", None)
        write(f, "film.json", m)
    log(f, by, "onay" if ok else "onay geri alındı", stage=stage)
    return m


def require(f: Path, stage: str) -> None:
    """Bir sonraki adıma geçmeden önce: onay isteyen adım onaylı, istemeyen hazır olmalı."""
    st = meta(f)["stages"].get(stage, {})
    need = "onayli" if stage in NEEDS_APPROVAL else "hazir"
    ok = st.get("status") == need or (need == "hazir" and st.get("status") == "onayli")
    if not ok:
        label = {"senaryo": "Senaryo", "oyuncular": "Oyuncular", "ses": "Ses", "kareler": "Kareler",
                 "cekim": "Çekim", "kurgu": "Kurgu"}.get(stage, stage)
        raise FilmError(f"{label} adımı {'onaylanmadı' if need == 'onayli' else 'hazır değil'}.")
