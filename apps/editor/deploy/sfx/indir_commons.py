#!/usr/bin/env python3
"""Efekt havuzu — Wikimedia Commons ses dosyaları, resmî MediaWiki API'si ile (sayfa kazıma yok).

Kök kategoriler aşağıda; alt kategoriler DERINLIK kat inilir (Commons kategori ağı döngülü ve çok geniş: sınırsız inişte
«ses efekti» kökünden müzik aletlerine, ülkelere, radyo arşivlerine gidiliyor; derinlik bir tavan değil kapsam
tanımıdır ve belgede yazılı). Yalnız lisansı kamu malı (PD), CC0 ya da CC BY (SA/NC/ND OLMAYAN) dosyalar alınır;
CC BY dosyalar e-kitabın «ses efektleri kaynakçası»na yazar + başlık + lisans + bağlantıyla girer. Paylaşım-benzer
(BY-SA) bilinçli olarak alınmaz: karışımdaki sayfa sesini de aynı lisansa bağlardı.

Çıktı: <hedef>/dosyalar/<ad>, <hedef>/commons.jsonl (her dosya için başlık, lisans, lisans bağlantısı, yazar,
açıklama, kategoriler, sayfa bağlantısı, indirme adresi). Kaldığı yerden sürer.
Kullanım: indir_commons.py [hedef]   (varsayılan /data/editor/sfx/_indir/commons)
"""

from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://commons.wikimedia.org/w/api.php"
UA = {"User-Agent": "NanobaseEditorSFX/1.0 (https://nanobase.ai; editor@nanobase.ai) python-urllib"}
ROOTS = ["Audio files of animal sounds", "Animal sounds", "Audio files of sound effects", "Foley (sound effects)",
         "Sounds of nature", "Sounds of birds", "Audio files of Aves", "Sounds of rivers and streams",
         "Audio files of waterfalls", "Rainforest sounds", "Audio files of rain", "Audio files of thunder",
         "Audio files of wind", "Audio files of fire", "Audio files of vehicles", "Audio files of trains",
         "Audio files of bells", "Audio files of clocks", "Audio files of doors", "Audio files of explosions",
         "Audio files of machines", "Audio files of ambient sound", "Soundscapes", "Field recordings",
         "Audio files of household appliances", "Audio files of city sounds", "Audio files of footsteps"]
DERINLIK = 4
OK_LIC = re.compile(r"^(public domain|pd|cc0|cc[ -]?zero|cc by \d(\.\d)?|cc-by-\d(\.\d)?)", re.I)
BAD_LIC = re.compile(r"(sa|nc|nd)\b|share|noncommercial|noderiv|gfdl|gpl", re.I)


def api(**p):
    """MediaWiki API çağrısı; gövde POST ile gider (40 uzun dosya başlığı GET adresine sığmıyordu: HTTP 414)."""
    p.update(format="json", formatversion="2")
    err = None
    for t in range(6):
        try:
            req = urllib.request.Request(API, data=urllib.parse.urlencode(p).encode(), headers=UA)
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            time.sleep(5 * (t + 1))
            err = e
    raise RuntimeError(f"API: {err}")


def members(cat: str, kind: str):
    cont = {}
    while True:
        r = api(action="query", list="categorymembers", cmtitle="Category:" + cat, cmlimit=500, cmtype=kind, **cont)
        yield from r.get("query", {}).get("categorymembers", [])
        if "continue" not in r:
            return
        cont = {"cmcontinue": r["continue"]["cmcontinue"]}
        time.sleep(0.5)


def strip(s: str | None) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s or "")).strip()


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/data/editor/sfx/_indir/commons")
    (out / "dosyalar").mkdir(parents=True, exist_ok=True)
    seen_cat, files = set(), {}
    frontier = [(c, 0) for c in ROOTS]
    while frontier:
        cat, depth = frontier.pop(0)
        if cat in seen_cat:
            continue
        seen_cat.add(cat)
        for m in members(cat, "file"):
            files.setdefault(m["title"], cat)
        if depth < DERINLIK:
            for m in members(cat, "subcat"):
                frontier.append((m["title"].split(":", 1)[1], depth + 1))
        time.sleep(0.3)
    print(f"{len(seen_cat)} kategori, {len(files)} dosya adayı", flush=True)
    done = set()
    jl = out / "commons.jsonl"
    if jl.exists():
        done = {json.loads(line)["title"] for line in jl.read_text().splitlines() if line.strip()}
    skipped = out / "elenen.jsonl"
    titles = [t for t in files if t not in done]
    for k in range(0, len(titles), 40):
        batch = titles[k:k + 40]
        r = api(action="query", prop="imageinfo|categories", titles="|".join(batch), iiprop="url|mime|size|extmetadata",
                cllimit="max")
        for pg in r.get("query", {}).get("pages", []):
            ii = (pg.get("imageinfo") or [{}])[0]
            if not str(ii.get("mime", "")).startswith(("audio/", "application/ogg")):
                continue
            md = ii.get("extmetadata") or {}
            lic = strip((md.get("LicenseShortName") or {}).get("value"))
            row = {"title": pg["title"], "license": lic, "license_url": strip((md.get("LicenseUrl") or {}).get("value")),
                   "artist": strip((md.get("Artist") or {}).get("value"))[:300],
                   "description": strip((md.get("ImageDescription") or {}).get("value"))[:600],
                   "categories": [c["title"].split(":", 1)[1] for c in pg.get("categories", [])],
                   "root": files.get(pg["title"]), "page": ii.get("descriptionurl"), "url": ii.get("url"),
                   "mime": ii.get("mime"), "size": ii.get("size")}
            if not OK_LIC.match(lic) or BAD_LIC.search(lic.replace("public domain", "")):
                with skipped.open("a") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                continue
            name = re.sub(r"[^\w.\-]+", "_", pg["title"].split(":", 1)[1])[:180]
            dest = out / "dosyalar" / name
            if not dest.exists():
                try:
                    req = urllib.request.Request(ii["url"], headers=UA)
                    with urllib.request.urlopen(req, timeout=120) as resp:
                        dest.write_bytes(resp.read())
                except Exception as e:  # noqa: BLE001
                    print("İNMEDİ", pg["title"], e, flush=True)
                    continue
                time.sleep(0.5)
            row["file"] = f"dosyalar/{name}"
            with jl.open("a") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"{min(k + 40, len(titles))}/{len(titles)}", flush=True)
    print("BITTI", flush=True)


if __name__ == "__main__":
    main()
