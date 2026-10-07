#!/usr/bin/env python3
"""Çizgi film çocuk sesleri: tariften aday üretimi, ölçüm ve aday seçimi (docs/analiz/sesli-okuma-cocuk-sesleri.md).

Yöntem ses kataloğununkiyle aynıdır (docs/analiz/sesli-okuma-zeki-sesleri.md): her tarif birkaç tohumla aynı cümleyi
okur; ses servisi (`book-voice`, VoxCPM2) `measure: true` ile her adayın ortanca perdesini (f0, pyin), sesli oranını ve
Türkçe tanıyıcıyla harf hatasını (cer) döndürür. Ses yalnız yazılı İngilizce tariften tasarlanır: gerçek kişi kaydı,
klon ya da dış ses havuzu yoktur.

Seçim: cer ≤ CER_MAX ve sesli oranı ≥ VOICED_MIN olan adaylardan, perdesi sesin hedef bandında (BAND) olanlar hedef
perdeye (TARGET) yakınlıklarına göre sıralanır; her sesten ilk ADAY_SAYISI aday (önce her tariften en iyisi, tarif
çeşitliliği için) dinlemeye gider. Bant dışı aday elenmez, listede «bant dışı» diye kalır: perde tek başına çocuk sesini
yetişkin kadın sesinden ayırmaz, son karar kullanıcının kulağıdır.

GPU'da GEÇİCİ kapta çalışır (çalışan kaplara dokunmaz, model kabını gateway açar/kapatır):

    docker run --rm --network editor-net --user 1000:1000 \
        -e GW_URL=http://editor-gateway:8000 -e GW_KEY=<editor-studio'daki EDITOR_GATEWAY_KEY> \
        -v /data/editor/ses-havuzu/cocuk:/out -v <repo>/apps/editor/deploy/ses:/s:ro \
        --entrypoint python <editor-py-studio imajı> /s/cocuk_sesleri.py <adım>

Adımlar:
    uret   her (ses, tarif, tohum) için /out/ham/<ses>/<tarif>-s<tohum>.wav + .json (ölçüm); kaldığı yerden sürer
    sec    /out/olcum.json (bütün adaylar) + /out/aday/<ses>-<sıra>.wav (ses başına ADAY_SAYISI) + /out/aday/liste.json;
           ölçüm tablosunu Markdown olarak stdout'a yazar
"""

from __future__ import annotations

import base64
import json
import os
import pathlib
import shutil
import sys
import time

OUT = pathlib.Path(os.environ.get("OUT", "/out"))
# Çocuğun ağzına uygun, Türkçenin özel harflerini (ı, ğ, ş, ç, ö, ü) taşıyan cümle; kataloğa girerse klonda referans
# metnidir (voices_zeki.CHILD_TEXT ile aynı olmalı).
TEXT = ("Anne, bak! Bahçede kocaman bir kaplumbağa var. Adını Pamuk koyalım mı? "
        "Ben ona her gün su veririm, şimdi söz veriyorum.")
# 1. tur (a–d) dört tohum; 2. tur (e–h) altı tohum (1. turda hiçbir aday harf hatası eşiğini geçmedi, bkz. belge).
SEEDS = [11, 23, 47, 89]
SEEDS2 = [11, 23, 47, 89, 131, 197]
# 3. tur: bantta ikiden az aday kalan seste en iyi iki tarife altı tohum daha.
EK_TOHUM = {("kucuk-kiz", "d"): [233, 307, 401, 509, 613, 727], ("kucuk-kiz", "h"): [233, 307, 401, 509, 613, 727]}
# Harf hatası eşiği: katalogdaki %5 bu cümlede tutmaz — katalogdaki genç seslerin tarifleri aynı çocuk cümlesini
# okuyunca (TABAN, 12 kayıt) harf hatası 0,053–0,213, ortanca 0,080 çıktı (ünlemli konuşma cümlesi, «Pamuk» özel adı;
# tanıyıcı yetişkin konuşmasıyla eğitilmiş). Eşik: yetişkin genç sesin bu cümledeki ortancası + 2 puan.
CER_MAX = 0.10
VOICED_MIN = 0.5
ADAY_SAYISI = 3
# Hedef perde (Hz) ve kabul bandı: 7–10 yaş ~250–280 Hz, 4–6 yaş ~280–320 Hz (konuşma perdesi yaşla iner; yetişkin
# kadın ~165–230 Hz). Bant ölçüm sırasını belirler, eleme ölçütü değildir.
TARGET = {"cocuk-erkek": 265, "cocuk-kiz": 275, "kucuk-erkek": 300, "kucuk-kiz": 310}
BAND = {"cocuk-erkek": (230, 330), "cocuk-kiz": (235, 340), "kucuk-erkek": (260, 380), "kucuk-kiz": (265, 390)}

# ses → {tarif kodu: İngilizce tarif}. Bilinen tuzak (voices_lively): «lively/playful» erkek sesini tizleştirir; burada
# istenen tiz bölge, ama yetişkin kadına kaymaması için her tarifte yaş açıkça yazılır.
TARIFLER: dict[str, dict[str, str]] = {
    "cocuk-erkek": {
        "a": "An eight-year-old boy with a clear, high-pitched child's voice, natural and curious, speaking like a "
             "primary school pupil",
        "b": "A young boy around nine years old, a bright, light child voice before puberty, sincere and cheerful, "
             "clear diction",
        "c": "Child voice actor: a seven-year-old boy in an animated film, high, clear and energetic, but natural, not "
             "exaggerated",
        "d": "A little schoolboy, about eight, soft high child's voice, slightly shy and curious, speaking at a "
             "moderate pace",
        # 2. tur: perde kelimesi yok («high/tiny» 1. turda 330–530 Hz çizgi film cıyaklamasına kaçtı); yaş + sakin, net
        # okuma
        "e": "An eight-year-old boy reading aloud from his school book, calm, clear and natural, careful pronunciation",
        "f": "A ten-year-old boy with a natural child's voice, not squeaky, speaking calmly and clearly at a moderate "
             "pace",
        "g": "Voice of a young boy, age nine, warm and clear, relaxed tone, articulate, like a child narrator in a family "
             "film",
        "h": "A primary school boy, about eight years old, speaking slowly and clearly to his mother, gentle and sincere",
    },
    "cocuk-kiz": {
        "a": "An eight-year-old girl with a clear, high-pitched child's voice, natural and curious, speaking like a "
             "primary school pupil",
        "b": "A young girl around nine years old, a bright, light child voice, sincere and cheerful, clear diction",
        "c": "Child voice actor: a seven-year-old girl in an animated film, high, clear and energetic, but natural, not "
             "exaggerated",
        "d": "A little schoolgirl, about eight, soft high child's voice, sweet and curious, speaking at a moderate pace",
        "e": "An eight-year-old girl reading aloud from her school book, calm, clear and natural, careful pronunciation",
        "f": "A ten-year-old girl with a natural child's voice, not squeaky, speaking calmly and clearly at a moderate "
             "pace",
        "g": "Voice of a young girl, age nine, warm and clear, relaxed tone, articulate, like a child narrator in a "
             "family film",
        "h": "A primary school girl, about eight years old, speaking slowly and clearly to her mother, gentle and "
             "sincere",
    },
    "kucuk-erkek": {
        "a": "A five-year-old little boy with a tiny, very high, soft child's voice, innocent and sweet, speaking slowly "
             "and carefully",
        "b": "A small kindergarten boy, about four years old, a very young child's voice, high and light, cute and "
             "excited",
        "c": "Child voice actor: a six-year-old boy in a cartoon, very high, small and bright voice, innocent and "
             "natural",
        "d": "A preschool boy around five, high thin little voice, curious and a bit shy, speaking slowly with short "
             "pauses",
        "e": "A six-year-old boy speaking slowly and carefully, clear pronunciation, calm and sweet, natural child voice, "
             "not squeaky",
        "f": "A five-year-old boy telling his mother about his day, soft and natural little child's voice, slow and "
             "clear",
        "g": "Voice of a small boy, age five, gentle and innocent, relaxed and articulate, like a little child in a family "
             "film",
        "h": "A kindergarten boy, about six years old, calm, clear and sincere, speaking slowly word by word",
    },
    "kucuk-kiz": {
        "a": "A five-year-old little girl with a tiny, very high, soft child's voice, innocent and sweet, speaking "
             "slowly and carefully",
        "b": "A small kindergarten girl, about four years old, a very young child's voice, high and light, cute and "
             "excited",
        "c": "Child voice actor: a six-year-old girl in a cartoon, very high, small and bright voice, innocent and "
             "natural",
        "d": "A preschool girl around five, high thin little voice, curious and a bit shy, speaking slowly with short "
             "pauses",
        "e": "A six-year-old girl speaking slowly and carefully, clear pronunciation, calm and sweet, natural child "
             "voice, not squeaky",
        "f": "A five-year-old girl telling her mother about her day, soft and natural little child's voice, slow and "
             "clear",
        "g": "Voice of a small girl, age five, gentle and innocent, relaxed and articulate, like a little child in a "
             "family film",
        "h": "A kindergarten girl, about six years old, calm, clear and sincere, speaking slowly word by word",
    },
}


# Taban: katalogdaki genç seslerin (voices_zeki genc-kadin / genc-erkek) tarifleri aynı çocuk cümlesini okur. Çocuk
# adaylarının harf hatası eşiği geçememesi sesten mi, cümleden/tanıyıcıdan mı, bununla ayrılır (yetişkin seste aynı
# cümlenin hatası).
TABAN = {
    "taban-genc-kadin": {"t": "A young woman in her twenties with a clear, bright, natural voice, lively but not "
                              "exaggerated, reading a young adult novel"},
    "taban-genc-erkek": {"t": "A young man in his twenties with a clear, warm, natural voice, lively but not "
                              "exaggerated, reading a young adult novel"},
}


def uret(taban: bool = False) -> None:
    import httpx
    url, key = os.environ["GW_URL"].rstrip("/"), os.environ["GW_KEY"]
    h = {"authorization": f"Bearer {key}"}
    t0 = time.time()
    with httpx.Client(timeout=httpx.Timeout(1800, connect=10)) as c:
        for ses, tarifler in (TABAN if taban else TARIFLER).items():
            d = OUT / "ham" / ses
            d.mkdir(parents=True, exist_ok=True)
            for kod, design in tarifler.items():
                for seed in (SEEDS if kod <= "d" else SEEDS2) + EK_TOHUM.get((ses, kod), []):
                    f = d / f"{kod}-s{seed}.wav"
                    mf = f.with_suffix(".json")
                    if f.exists() and mf.exists():
                        continue
                    body = {"model": "book-voice", "format": "wav", "align": False, "measure": True,
                            "segments": [{"text": TEXT, "voice": {"design": design}, "pause_ms": 0, "seed": seed}]}
                    for attempt in range(20):        # model kabı açılırken 503/zaman aşımı: bekleyip yeniden dene
                        try:
                            r = c.post(f"{url}/v1/audio/narrate", json=body, headers=h)
                            r.raise_for_status()
                            break
                        except httpx.HTTPError as e:
                            print(f"tekrar {attempt}: {type(e).__name__} {e}"[:200], flush=True)
                            time.sleep(30)
                    else:
                        raise SystemExit("20 deneme başarısız")
                    j = r.json()
                    f.write_bytes(base64.b64decode(j["audio"]))
                    row = {"ses": ses, "tarif": kod, "seed": seed, "file": f"ham/{ses}/{f.name}", "design": design,
                           "duration": j["duration"], **j["segments"][0].get("measure", {})}
                    mf.write_text(json.dumps(row, ensure_ascii=False))
                    print(json.dumps(row, ensure_ascii=False), flush=True)
    print(f"BITTI {time.time() - t0:.0f} sn", flush=True)


def _ok(r: dict) -> bool:
    return r.get("cer") is not None and r["cer"] <= CER_MAX and (r.get("voiced_ratio") or 0) >= VOICED_MIN


def _in_band(r: dict) -> bool:
    lo, hi = BAND[r["ses"]]
    return r.get("f0") is not None and lo <= r["f0"] <= hi


def _key(r: dict) -> tuple:
    # bant içi önce, sonra hedef perdeye uzaklık, eşitlikte harf hatası
    return (not _in_band(r), abs((r.get("f0") or 0) - TARGET[r["ses"]]), r["cer"])


def sec() -> None:
    import hashlib
    allrows = [json.loads(p.read_text()) for p in sorted((OUT / "ham").glob("*/*.json"))]
    (OUT / "olcum.json").write_text(json.dumps(allrows, ensure_ascii=False, indent=1))
    rows = [r for r in allrows if r["ses"] in TARIFLER]
    taban = [r for r in allrows if r["ses"] in TABAN]
    if taban:
        print("| Taban sesi | Tohum | f0 (Hz) | Sesli oranı | cer |")
        print("|---|---|---|---|---|")
        for r in sorted(taban, key=lambda r: (r["ses"], r["seed"])):
            print(f"| {r['ses']} | {r['seed']} | {r.get('f0')} | {r.get('voiced_ratio')} | {r.get('cer')} |")
        print()
    adir = OUT / "aday"
    if adir.exists():
        shutil.rmtree(adir)
    adir.mkdir()
    secilen = []
    print("| Ses | Tarif | Tohum | f0 (Hz) | Sesli oranı | cer | Süre (sn) | Durum |")
    print("|---|---|---|---|---|---|---|---|")
    for ses in TARIFLER:
        mine = [r for r in rows if r["ses"] == ses]
        for r in sorted(mine, key=lambda r: (r["tarif"], r["seed"])):
            durum = ("geçti" if _ok(r) else "elendi") + ("" if _in_band(r) else ", bant dışı")
            print(f"| {ses} | {r['tarif']} | {r['seed']} | {r.get('f0')} | {r.get('voiced_ratio')} | {r.get('cer')} | "
                  f"{r['duration']} | {durum} |")
        good = sorted([r for r in mine if _ok(r)], key=_key)
        pick: list[dict] = []
        for r in good:                                   # önce her tariften en iyisi (çeşitlilik)
            if len(pick) < ADAY_SAYISI and r["tarif"] not in {p["tarif"] for p in pick}:
                pick.append(r)
        for r in good:
            if len(pick) < ADAY_SAYISI and r not in pick:
                pick.append(r)
        pick.sort(key=_key)
        for i, r in enumerate(pick, 1):
            dst = adir / f"{ses}-{i}.wav"
            shutil.copyfile(OUT / r["file"], dst)
            secilen.append({**r, "aday": dst.name, "sira": i, "bant_ici": _in_band(r),
                            "sha256": hashlib.sha256(dst.read_bytes()).hexdigest()})
    (adir / "liste.json").write_text(json.dumps({"text": TEXT, "adaylar": secilen}, ensure_ascii=False, indent=1))
    print()
    print("| Aday | Tarif | Tohum | f0 (Hz) | Sesli oranı | cer | Bant |")
    print("|---|---|---|---|---|---|---|")
    for r in secilen:
        print(f"| {r['aday']} | {r['tarif']} | {r['seed']} | {r['f0']} | {r['voiced_ratio']} | {r['cer']} | "
              f"{'içi' if r['bant_ici'] else 'dışı'} |")


if __name__ == "__main__":
    {"uret": uret, "taban": lambda: uret(taban=True), "sec": sec}[sys.argv[1]]()
