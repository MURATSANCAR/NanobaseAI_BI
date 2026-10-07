#!/usr/bin/env python3
"""Çocuk sesleri, 2. yöntem: tını dönüştürme + klon (docs/analiz/sesli-okuma-cocuk-sesleri.md, «2. yöntem»).

1. yöntemde (cocuk_sesleri.py, yalnız tarif) kullanıcı adayları dinledi: «daha iyilerini üret». Bu yöntemde çocuk tınısı
modele tarif ettirilmez, temiz okuyan bir kayıttan sinyal işlemeyle yapılır: çocuk sesi = yüksek F0 + kısa ses yolu
(formantlar ~%15–25 yukarı). Kaynak kayıtlar yalnız bizim modelimizin ürettiği seslerdir (katalogdaki sabit kayıtlar ve
1. yöntemin adayları); gerçek kişi kaydı, dış ses havuzu yok.

Adımlar (her biri kaldığı yerden sürer; çıktı OUT=/out altında):
    donustur  CPU. Her kaynak kayıt iki yolla çevrilir:
              praat  Praat «Change gender» (parselmouth): formant oranı × yeni ortanca perde × perde aralığı ızgarası
              world  WORLD vokoder (pyworld): F0 log düzleminde hedef ortancaya taşınır (aralık çarpanıyla), spektral
                     zarf ve aperiyodiklik frekans ekseninde formant oranıyla sıkıştırılır: yeni(f) = eski(f / oran)
              → v2/donusum/<kaynak>/<yol>-f<oran>-p<perde>-r<aralık>.wav + .json (ölçüm)
    olc       CPU. Taban: katalogdaki sabit kayıtlar + 1. yöntemin bütün adayları aynı ölçümle → v2/taban.json
    klon      GPU, yalnız gateway üzerinden book-voice. Her ses için kısa liste (shortlist: en çocuksu + temiz kol), sabit kayıt
              düzeniyle (narration.voice_ref: ref_audio + ref_text, tam klon) iki metni okur: ölçüm cümlesi + paragraf
              → v2/klon/<aday>-{cumle,paragraf}.wav + .json (servisin ölçümü)
    klonolc   CPU. Klonların yaş/cinsiyet ölçümü + konuşmacı benzerliği (klon↔dönüştürülmüş referans, klon↔çevrilmemiş
              kaynak)
    sec       bileşik puan (score) ile sıralama; ses başına ADAY_SAYISI aday + 1. yöntemin ilk adayı → aday2/,
              liste.json, sec.md; önerilenlerin çift benzerliği ve hazır PINNED satırları

Ölçümler (hepsi CPU): perde (librosa pyin, 60–700 Hz, etkin konuşma kareleri), harf hatası (ses servisindeki Türkçe
hizalayıcının açgözlü çözümü, servisle aynı kural), yaş/cinsiyet (audeering wav2vec2-large-robust-24-ft-age-gender:
kadın/erkek/çocuk olasılığı + yaş; CC BY-NC-SA 4.0 — yalnız ölçüm aracı, ürüne girmez), konuşmacı benzerliği (microsoft
wavlm-base-plus-sv x-vektörü, kosinüs).

Sıralama: harf hatası ≤ CER_MAX, sonra çocuk olasılığı (yüksek), tahmini yaşın hedefe yakınlığı (7–10 → 8,5; 4–6 → 5),
sonra perdenin hedefe yakınlığı.

Çalıştırma (GPU host'unda geçici kap; çalışan kaplara dokunmaz):
    CPU adımları: docker run --rm --network none --user 1000:1000 -e HOME=/tmp -e PYTHONUSERBASE=/v2/pylib \
        -v /data/editor/ses-havuzu/cocuk:/out -v /data/editor/ses-havuzu/cocuk/v2:/v2 \
        -v /data/editor/models/book-voice/aligner:/aligner:ro \
        -v /data/editor/releases/<sürüm>/src/editor/production/sesler/zeki:/zeki:ro \
        -v <betik klasörü>:/s:ro --entrypoint python editor-voice:5 /s/cocuk_donustur.py <adım>
      (parselmouth + pyworld /v2/pylib'e bir kez `pip install --user` ile; modeller /v2/hf altında)
    klon: cocuk_sesleri.py ile aynı kap (editor-py-studio imajı, editor-net, GW_URL/GW_KEY)
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import re
import shutil
import sys
import time

# librosa'nın numba önbelleği: aynı anda açılan süreçler ortak önbelleği okurken çöküyordu (segfault ip 0); süreç başına
# ayrı klasör (numba içe aktarılmadan önce).
os.environ["NUMBA_CACHE_DIR"] = f"/tmp/numba-{os.getpid()}"

OUT =pathlib.Path(os.environ.get("OUT", "/out"))
V2 = OUT / "v2"
ZEKI = pathlib.Path(os.environ.get("ZEKI", "/zeki"))
ALIGN_DIR = os.environ.get("ALIGN_DIR", "/aligner")
HF = pathlib.Path(os.environ.get("HF_DIR", "/v2/hf"))

READER_TEXT = ("Kitabın ilk sayfasını açtığında, yıllardır beklediği cevabın orada olduğunu bilmiyordu. "
               "Satırlar ilerledikçe, kendi hikâyesini başka birinin kaleminden okuyormuş gibi hissetti.")
CHILD_TEXT = ("Anne, bak! Bahçede kocaman bir kaplumbağa var. Adını Pamuk koyalım mı? "
              "Ben ona her gün su veririm, şimdi söz veriyorum.")
# Klonun uzun metinde tınıyı tutup tutmadığı için (kitaptan bağımsız, bu iş için yazıldı; 60 kelime).
PARAGRAPH = ("Sabah uyandığımda pencereden dışarı baktım ve gözlerime inanamadım. Bütün bahçe bembeyaz olmuştu! "
             "Hemen montumu giydim, eldivenlerimi taktım ve koşarak aşağı indim. Kardeşimle birlikte kocaman bir "
             "kardan adam yapmaya karar verdik. Önce küçük bir kartopu yuvarladık, sonra o büyüdükçe büyüdü. Burnuna "
             "havuç, gözlerine iki düğme koyduk. Annem balkondan bize el salladı ve gülümsedi.")

# kaynak → (dosya, metin, cinsiyet, Praat perde tabanı/tavanı). Katalogdan en temiz okuyanlar (sabit kayıtlar, harf
# hatası 0,013–0,033) + 1. yöntemin dinlemeye giden adayları ve setin en temiz kaydı.
CATALOG = {"genc-kadin": "k", "roman-kadin": "k", "masal-anne": "k", "gelisim-kadin": "k",
           "genc-erkek": "e", "gelisim-erkek": "e"}
TUR1 = ["cocuk-erkek-1", "cocuk-erkek-2", "cocuk-erkek-3", "cocuk-kiz-1", "cocuk-kiz-2", "cocuk-kiz-3",
        "kucuk-erkek-1", "kucuk-erkek-2", "kucuk-erkek-3", "kucuk-kiz-1", "kucuk-kiz-2", "kucuk-kiz-3"]
TUR1_EK = {"kucuk-kiz-d613": "ham/kucuk-kiz/d-s613.wav"}
PITCH_RANGE = {"k": (100, 500), "e": (60, 300), "c": (150, 650)}

FORMANT = [1.12, 1.18, 1.24, 1.30]
PITCH = [250, 270, 290, 310, 330]
RANGE = [1.0, 1.2, 1.4]
WORLD_RANGE = [1.2]

VOICES = {   # ses → (cinsiyet, hedef yaş, perde aralığı, hedef perde)
    "cocuk-erkek": ("e", 8.5, (250, 290), 270), "cocuk-kiz": ("k", 8.5, (250, 290), 275),
    "kucuk-erkek": ("e", 5.0, (290, 330), 305), "kucuk-kiz": ("k", 5.0, (290, 330), 310),
}
CER_MAX = 0.10
ADAY_SAYISI = 3


def sources() -> dict[str, dict]:
    out = {k: {"file": ZEKI / f"{k}.wav", "text": READER_TEXT, "sex": s, "kind": "katalog"} for k, s in CATALOG.items()}
    for a in TUR1:
        out[f"tur1-{a}"] = {"file": OUT / "aday" / f"{a}.wav", "text": CHILD_TEXT, "sex": "c", "kind": "tur1",
                            "of": a.rsplit("-", 1)[0]}
    for a, f in TUR1_EK.items():
        out[f"tur1-{a}"] = {"file": OUT / f, "text": CHILD_TEXT, "sex": "c", "kind": "tur1", "of": "kucuk-kiz"}
    return out


# ------------------------------------------------------------------ ölçüm
_M: dict = {}


def _models():
    if _M:
        return _M
    import torch
    import torch.nn as nn
    from transformers import (AutoFeatureExtractor, AutoModelForCTC, Wav2Vec2Model, Wav2Vec2PreTrainedModel,
                              Wav2Vec2Processor, WavLMForXVector)
    torch.set_num_threads(int(os.environ.get("THREADS", "4")))

    class Head(nn.Module):
        def __init__(self, config, n):
            super().__init__()
            self.dense = nn.Linear(config.hidden_size, config.hidden_size)
            self.dropout = nn.Dropout(config.final_dropout)
            self.out_proj = nn.Linear(config.hidden_size, n)

        def forward(self, x):
            return self.out_proj(self.dropout(torch.tanh(self.dense(self.dropout(x)))))

    class AgeGender(Wav2Vec2PreTrainedModel):    # model kartındaki sınıf: yaş (0–1 → ×100) + kadın/erkek/çocuk
        def __init__(self, config):
            super().__init__(config)
            self.wav2vec2 = Wav2Vec2Model(config)
            self.age = Head(config, 1)
            self.gender = Head(config, 3)
            self.post_init()

        def forward(self, x):
            h = self.wav2vec2(x)[0].mean(dim=1)
            return self.age(h), torch.softmax(self.gender(h), dim=1)

    ag_dir = HF / "wav2vec2-large-robust-24-ft-age-gender"
    _M["ag_proc"] = AutoFeatureExtractor.from_pretrained(ag_dir)
    _M["ag"] = AgeGender.from_pretrained(ag_dir).eval()
    _M["al_proc"] = Wav2Vec2Processor.from_pretrained(ALIGN_DIR)
    _M["al"] = AutoModelForCTC.from_pretrained(ALIGN_DIR).eval()
    sv_dir = HF / "wavlm-base-plus-sv"
    _M["sv_fe"] = AutoFeatureExtractor.from_pretrained(sv_dir)
    _M["sv"] = WavLMForXVector.from_pretrained(sv_dir).eval()
    _M["torch"] = torch
    return _M


def _load16(path) -> "np.ndarray":   # noqa: F821
    import librosa
    y, _ = librosa.load(str(path), sr=16000, mono=True)
    return y


def _lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


_LOWER = str.maketrans({"I": "ı", "İ": "i"})


def _clean(t: str) -> str:
    return re.sub(r"[^a-zçğıöşüâîû]", "", t.translate(_LOWER).lower())


def measure(path, text: str | None) -> dict:
    """Perde, sesli oranı, harf hatası (metin varsa), çocuk/kadın/erkek olasılığı, tahmini yaş."""
    import librosa
    import numpy as np
    m = _models()
    torch = m["torch"]
    y = _load16(path)
    rms = librosa.feature.rms(y=y, frame_length=400, hop_length=160)[0]
    db = 20 * np.log10(rms + 1e-9)
    active = db > db.max() - 35
    f0, vflag, _ = librosa.pyin(y, fmin=60, fmax=700, sr=16000, frame_length=1024, hop_length=160)
    n = min(len(f0), len(active))
    voiced = vflag[:n] & active[:n] & ~np.isnan(f0[:n])
    out = {"f0": round(float(np.median(f0[:n][voiced])), 1) if voiced.sum() > 5 else None,
           "voiced_ratio": round(float(voiced.sum() / max(1, active[:n].sum())), 3),
           "duration": round(len(y) / 16000, 2)}
    # Bozulma belirtileri: ani perde sıçraması (art arda iki sesli karede > 7 yarım ton; pyin oktav hatası da buraya
    # düşer, o yüzden oran olarak) ve enerji patlaması (etkin konuşma ortancasının 15 dB üstündeki kareler).
    pair = voiced[:-1] & voiced[1:]
    jump = np.abs(12 * np.log2(f0[1:n][pair[:n - 1]] / f0[:n - 1][pair[:n - 1]])) if pair.any() else np.array([])
    out["sicrama"] = round(float((jump > 7).mean()), 4) if jump.size else 0.0
    med_db = float(np.median(db[:n][active[:n]])) if active.any() else 0.0
    out["patlama"] = round(float((db[:n][active[:n]] > med_db + 15).mean()), 4) if active.any() else 0.0
    with torch.inference_mode():
        if text:
            feats = m["al_proc"](y, sampling_rate=16000, return_tensors="pt").input_values
            heard = m["al_proc"].batch_decode(m["al"](feats).logits.argmax(-1))[0]
            want, got = _clean(text), _clean(heard)
            out["cer"] = round(_lev(want, got) / max(1, len(want)), 3)
        x = m["ag_proc"](y, sampling_rate=16000, return_tensors="pt").input_values
        age, g = m["ag"](x)
    out.update(age=round(float(age[0, 0]) * 100, 1), p_kadin=round(float(g[0, 0]), 3),
               p_erkek=round(float(g[0, 1]), 3), p_cocuk=round(float(g[0, 2]), 3))
    return out


def embed(path):
    m = _models()
    torch = m["torch"]
    y = _load16(path)
    with torch.inference_mode():
        e = m["sv"](**m["sv_fe"](y, sampling_rate=16000, return_tensors="pt", padding=True)).embeddings[0]
    return torch.nn.functional.normalize(e, dim=-1)


# ------------------------------------------------------------------ dönüşüm
def _praat(src: dict, fr: float, pitch: int, rng: float):
    import parselmouth
    from parselmouth.praat import call
    snd = parselmouth.Sound(str(src["file"]))
    lo, hi = PITCH_RANGE[src["sex"]]
    new = call(snd, "Change gender", lo, hi, fr, pitch, rng, 1.0)
    return new.values[0], new.sampling_frequency


def _world(src: dict, fr: float, pitch: int, rng: float):
    import numpy as np
    import pyworld as pw
    import soundfile as sf
    x, fs = sf.read(str(src["file"]), dtype="float64")
    if x.ndim > 1:
        x = x.mean(axis=1)
    lo, hi = PITCH_RANGE[src["sex"]]
    f0, t = pw.harvest(x, fs, f0_floor=lo, f0_ceil=hi)
    sp = pw.cheaptrick(x, f0, t, fs)
    ap = pw.d4c(x, f0, t, fs)
    v = f0 > 0
    med = float(np.median(f0[v]))
    nf0 = np.zeros_like(f0)
    nf0[v] = np.exp(np.log(pitch) + rng * (np.log(f0[v]) - np.log(med)))
    bins = sp.shape[1]
    src_idx = np.arange(bins) / fr                 # yeni(f) = eski(f / oran): formantlar oranla yukarı
    warp = lambda a: np.stack([np.interp(src_idx, np.arange(bins), r) for r in a])   # noqa: E731
    nsp, nap = warp(sp), np.clip(warp(ap), 0, 1)
    y = pw.synthesize(nf0, np.ascontiguousarray(nsp), np.ascontiguousarray(nap), fs)
    return y / max(1e-6, np.abs(y).max()) * min(0.95, np.abs(x).max() * 1.0 + 1e-6), fs


def _jobs():
    for sid, src in sources().items():
        for fr in FORMANT:
            for p in PITCH:
                for r in RANGE:
                    yield sid, "praat", fr, p, r
                for r in WORLD_RANGE:
                    yield sid, "world", fr, p, r


def _one(job):
    import numpy as np
    import soundfile as sf
    sid, way, fr, p, r = job
    src = sources()[sid]
    d = V2 / "donusum" / sid
    d.mkdir(parents=True, exist_ok=True)
    f = d / f"{way}-f{fr:.2f}-p{p}-r{r:.1f}.wav"
    mf = f.with_suffix(".json")
    if mf.exists():
        return json.loads(mf.read_text())
    y, fs = (_praat if way == "praat" else _world)(src, fr, p, r)
    y = np.clip(np.asarray(y, dtype=np.float32), -1, 1)
    sf.write(str(f), y, int(fs), subtype="PCM_16")
    row = {"id": f"{sid}/{f.stem}", "kaynak": sid, "kaynak_tur": src["kind"], "kaynak_cins": src["sex"],
           "of": src.get("of"), "yol": way, "formant": fr, "perde_hedef": p, "aralik": r,
           "file": str(f.relative_to(OUT)), "text": "READER_TEXT" if src["text"] == READER_TEXT else "CHILD_TEXT",
           **measure(f, src["text"])}
    mf.write_text(json.dumps(row, ensure_ascii=False))
    return row


def _pmap(fn, items: list) -> list:
    """Paralel çalıştırma. multiprocessing.Pool ölen işçinin işini sonsuza dek bekliyordu (2026-10-07: aynı anda
    açılan işçiler numba önbelleğinde çöktü); burada işçi ölürse havuz kırılır, kalan işler yeni havuzla yeniden denenir
    (en çok 3 tur), yine olmayan None döner. Çökme nedeni: süreç başına ayrı NUMBA_CACHE_DIR ile giderildi (dosya başı)."""
    from concurrent.futures import ProcessPoolExecutor
    from concurrent.futures.process import BrokenProcessPool
    from multiprocessing import get_context
    res: list = [None] * len(items)
    todo = list(range(len(items)))
    t0 = time.time()
    for _round in range(3):
        if not todo:
            break
        failed = []
        with ProcessPoolExecutor(int(os.environ.get("WORKERS", "32")), mp_context=get_context("spawn")) as ex:
            futs = {ex.submit(fn, items[i]): i for i in todo}
            done = 0
            for fut, i in futs.items():
                try:
                    res[i] = fut.result()
                except BrokenProcessPool:
                    failed.append(i)
                except Exception as e:  # noqa: BLE001 — tek işin hatası diğerlerini durdurmaz
                    print(f"hata {items[i]}: {type(e).__name__} {e}"[:300], flush=True)
                done += 1
                if done % 100 == 0:
                    print(f"{done}/{len(todo)} {time.time() - t0:.0f} sn", flush=True)
        todo = failed
    if todo:
        print(f"yapılamayan {len(todo)}: {[items[i] for i in todo][:5]}", flush=True)
    return res


def donustur() -> None:
    jobs = list(_jobs())
    missing = [s for s, src in sources().items() if not src["file"].exists()]
    if missing:
        raise SystemExit(f"kaynak yok: {missing}")
    t0 = time.time()
    _pmap(_one, jobs)
    print(f"BITTI donustur {len(jobs)} {time.time() - t0:.0f} sn", flush=True)


def _taban_one(item):
    tid, path, text = item
    return {"id": tid, "file": str(path), **measure(path, text)}


def olc() -> None:
    items = []
    for p in sorted(ZEKI.glob("*.wav")):
        items.append((f"katalog/{p.stem}", p, None))   # katalog metni sese göre değişir; harf hatası 1. ölçümde var
    for p in sorted((OUT / "ham").glob("*/*.wav")):
        items.append((f"tur1/{p.parent.name}/{p.stem}", p, CHILD_TEXT))
    t0 = time.time()
    rows = [r for r in _pmap(_taban_one, items) if r]
    (V2 / "taban.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    print(f"BITTI olc {len(rows)} {time.time() - t0:.0f} sn", flush=True)


# ------------------------------------------------------------------ sıralama
def _eligible(r: dict, ses: str) -> bool:
    sex, _age, (lo, hi), _t = VOICES[ses]
    if r["kaynak_tur"] == "tur1" and not (r["of"] or "").endswith("kiz" if sex == "k" else "erkek"):
        return False
    if r["kaynak_tur"] == "katalog" and sex == "k" and r["kaynak_cins"] != "k":
        return False                              # kız çocuğu yalnız kadın kaynaktan; erkek çocuğu iki kaynaktan
    return lo <= r["perde_hedef"] <= hi


def _key(r: dict, ses: str, child=None, age=None, f0=None) -> tuple:
    _sex, tage, _rng, tf0 = VOICES[ses]
    c = r["p_cocuk"] if child is None else child
    a = r["age"] if age is None else age
    f = r.get("f0") if f0 is None else f0
    return (-round(c, 2), abs(a - tage), abs((f or 0) - tf0))


def _rows() -> list[dict]:
    return [json.loads(p.read_text()) for p in sorted((V2 / "donusum").glob("*/*.json"))]


# Klona gidecek referansların kısa listesi. Ölçüm (2026-10-07): dönüştürülmüş kayıtta çocuksuluk ile tanıyıcının harf
# hatası birlikte artıyor — katalog kaynağında formant 1,12 → cer ortanca 0,039 / çocuk olasılığı 0,003; 1,30 → 0,229 /
# 0,427 (en çocuksu kayıtlar cer 0,29–0,43). Tanıyıcı yetişkin konuşmasıyla eğitilmiş; sayfayı da referans değil klon
# okur (klon telaffuzu modelden gelir). Bu yüzden harf hatası eşiği (CER_MAX) son elemededir (iki klon metni); burada
# referansa gevşek eşik (REF_CER_MAX) ve iki kol: en çocuksu KLON_COCUKSU + referansı da eşiği geçen KLON_TEMIZ.
REF_CER_MAX = 0.40
KLON_COCUKSU, KLON_TEMIZ = 5, 3


def shortlist() -> dict[str, list[dict]]:
    rows = _rows()
    out = {}
    for ses in VOICES:
        mine = sorted([r for r in rows if _eligible(r, ses)], key=lambda r: _key(r, ses))
        pick, seen = [], set()
        for limit, n in ((REF_CER_MAX, KLON_COCUKSU), (CER_MAX, KLON_TEMIZ)):
            got = 0
            for r in mine:                        # çeşitlilik: aynı kaynak+yol bir kez
                k = (r["kaynak"], r["yol"])
                if (r.get("cer") or 1) <= limit and k not in seen:
                    pick.append(r)
                    seen.add(k)
                    got += 1
                    if got == n:
                        break
        out[ses] = pick
    return out


# ------------------------------------------------------------------ klon (GPU, gateway)
def klon() -> None:
    import httpx
    url, key = os.environ["GW_URL"].rstrip("/"), os.environ["GW_KEY"]
    h = {"authorization": f"Bearer {key}"}
    texts = {"READER_TEXT": READER_TEXT, "CHILD_TEXT": CHILD_TEXT}
    sl = shortlist()
    (V2 / "kisa-liste.json").write_text(json.dumps(sl, ensure_ascii=False, indent=1))
    d = V2 / "klon"
    d.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    with httpx.Client(timeout=httpx.Timeout(1800, connect=10)) as c:
        for ses, rows in sl.items():
            for i, r in enumerate(rows, 1):
                ref = {"ref_audio": base64.b64encode((OUT / r["file"]).read_bytes()).decode(),
                       "ref_text": texts[r["text"]]}
                for kind, text in (("cumle", CHILD_TEXT), ("paragraf", PARAGRAPH)):
                    f = d / f"{ses}-{i}-{kind}.wav"
                    mf = f.with_suffix(".json")
                    if mf.exists():
                        continue
                    # sayfa okumasıyla aynı: sabit kayıt + metni, tam klon, tohum yok (narration.narrate_page)
                    body = {"model": "book-voice", "format": "wav", "align": False, "measure": True,
                            "segments": [{"text": text, "voice": ref, "pause_ms": 0}]}
                    for attempt in range(20):
                        try:
                            resp = c.post(f"{url}/v1/audio/narrate", json=body, headers=h)
                            resp.raise_for_status()
                            break
                        except httpx.HTTPError as e:
                            print(f"tekrar {attempt}: {type(e).__name__} {e}"[:200], flush=True)
                            time.sleep(30)
                    else:
                        raise SystemExit("20 deneme başarısız")
                    j = resp.json()
                    f.write_bytes(base64.b64decode(j["audio"]))
                    row = {"ses": ses, "sira": i, "ref": r["id"], "kind": kind, "file": str(f.relative_to(OUT)),
                           "servis": j["segments"][0].get("measure", {}), "duration": j["duration"]}
                    mf.write_text(json.dumps(row, ensure_ascii=False))
                    print(json.dumps(row, ensure_ascii=False), flush=True)
    print(f"BITTI klon {time.time() - t0:.0f} sn", flush=True)


def _klon_one(mf):
    row = json.loads(pathlib.Path(mf).read_text())
    if "olcum" in row:
        return row
    sl = json.loads((V2 / "kisa-liste.json").read_text())
    ref = sl[row["ses"]][row["sira"] - 1]
    src = sources()[ref["kaynak"]]
    text = CHILD_TEXT if row["kind"] == "cumle" else PARAGRAPH
    e = embed(OUT / row["file"])
    row["olcum"] = measure(OUT / row["file"], text)
    row["benzerlik_ref"] = round(float(e @ embed(OUT / ref["file"])), 3)
    row["benzerlik_kaynak"] = round(float(e @ embed(src["file"])), 3)
    pathlib.Path(mf).write_text(json.dumps(row, ensure_ascii=False))
    return row


def klonolc() -> None:
    files = sorted((V2 / "klon").glob("*.json"))
    rows = [r for r in _pmap(_klon_one, [str(f) for f in files]) if r]
    print(f"BITTI klonolc {len(rows)}", flush=True)


# ------------------------------------------------------------------ ikinci tanıyıcı
# Hizalayıcı (wav2vec2, yetişkin Türkçe konuşması) çocuksu kayıtlarda harf hatasını yükseltiyor mu? İkinci görüş:
# Whisper large-v3-turbo (MIT), aynı temizlik kuralıyla harf hatası. Yetişkin taban (katalog kayıtları, genç seslerin
# çocuk cümlesi) ile çocuksu adaylar aynı ölçümle karşılaştırılır. CPU, geçici kap.
FILM_TEXT = ("Yıllar önce, bu dağların ardında bir köy vardı. Kimse adını hatırlamaz artık. "
             "Ama ben hatırlarım, evlat. Otur da sana anlatayım.")
FILM_VOICES = {"masal-dede", "bilge-dede", "karanlik-lord", "yasli-kral", "yasli-kaptan", "fragman-anlatici"}
_W: dict = {}


def _whisper_one(item):
    path, text = item
    import torch
    if not _W:
        from transformers import pipeline
        torch.set_num_threads(int(os.environ.get("THREADS", "4")))
        _W["asr"] = pipeline("automatic-speech-recognition", model=str(HF / "whisper-large-v3-turbo"),
                             device="cpu", torch_dtype=torch.float32)
    y = _load16(path)
    heard = _W["asr"]({"raw": y, "sampling_rate": 16000}, return_timestamps=len(y) > 30 * 16000,
                      generate_kwargs={"language": "turkish", "task": "transcribe"})["text"]
    want, got = _clean(text), _clean(heard)
    return {"file": str(pathlib.Path(path).relative_to(OUT)) if str(path).startswith(str(OUT)) else str(path),
            "text_kind": "paragraf" if text == PARAGRAPH else "cumle", "heard": heard.strip(),
            "cer_w": round(_lev(want, got) / max(1, len(want)), 3)}


def whisper() -> None:
    items = []
    for p in sorted(ZEKI.glob("*.wav")):
        items.append((p, FILM_TEXT if p.stem in FILM_VOICES else READER_TEXT))
    for p in sorted((OUT / "ham").glob("taban-*/*.wav")):
        items.append((p, CHILD_TEXT))
    for a in TUR1:
        items.append((OUT / "aday" / f"{a}.wav", CHILD_TEXT))
    for r in json.loads((V2 / "kisa-liste.json").read_text()).values():
        for x in r:
            src = sources()[x["kaynak"]]
            items.append((OUT / x["file"], src["text"]))
    for p in sorted((V2 / "klon").glob("*.wav")):
        items.append((p, PARAGRAPH if p.stem.endswith("paragraf") else CHILD_TEXT))
    t0 = time.time()
    rows = [r for r in _pmap(_whisper_one, items) if r]
    (V2 / "whisper.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1))
    print(f"BITTI whisper {len(rows)} {time.time() - t0:.0f} sn", flush=True)


def _cer_w() -> dict[str, float]:
    p = V2 / "whisper.json"
    return {r["file"]: r["cer_w"] for r in json.loads(p.read_text())} if p.exists() else {}


# ------------------------------------------------------------------ seçim
# Bileşik puan (ana oturumun seçim ölçütü, 2026-10-07). Eleme: iki metnin (cümle + paragraf) harf hatası ortalaması ve
# paragrafınki ayrı ayrı ≤ CER_MAX. Puan = 0,45·çocuk olasılığı + 0,25·yaş yakınlığı + 0,20·(1 − cer/0,10)
# + 0,10·paragrafta referans tınısına benzerlik; çocuk olasılığı ve yaş iki klonun ortalaması (sayfa okuması klondur).
# Bozulma: paragrafta perde sıçraması > SICRAMA_MAX ya da enerji patlaması > PATLAMA_MAX → CEZA ve not.
W_CHILD, W_AGE, W_CER, W_SIM = 0.45, 0.25, 0.20, 0.10
SICRAMA_MAX, PATLAMA_MAX, CEZA = 0.02, 0.01, 0.10
PAIR_WARN = 0.85


def score(ses: str, kc: dict, kp: dict, key: str = "cer") -> dict:
    """key: «cer» hizalayıcının, «cer_w» Whisper'ın harf hatası."""
    mc, mp = kc["olcum"], kp["olcum"]
    tage = VOICES[ses][1]
    v = lambda m: 1.0 if m.get(key) is None else m[key]   # noqa: E731 — 0,0 geçerli değerdir
    cer = (v(mc) + v(mp)) / 2
    child = (mc["p_cocuk"] + mp["p_cocuk"]) / 2
    age = (mc["age"] + mp["age"]) / 2
    sim = kp.get("benzerlik_ref")
    notes = []
    if sim is None:
        notes.append("klon benzerliği ölçülemedi")
    bozuk = mp.get("sicrama", 0) > SICRAMA_MAX or mp.get("patlama", 0) > PATLAMA_MAX
    if bozuk:
        notes.append(f"paragrafta bozulma belirtisi (sıçrama {mp.get('sicrama')}, patlama {mp.get('patlama')})")
    elendi = cer > CER_MAX or v(mp) > CER_MAX
    if elendi:
        notes.append(f"harf hatası eşiği ({key}: ortalama {cer:.3f}, paragraf {mp.get(key)})")
    puan = (W_CHILD * child + W_AGE * max(0.0, 1 - abs(age - tage) / 5) + W_CER * max(0.0, 1 - cer / CER_MAX)
            + W_SIM * min(1.0, max(0.0, sim or 0.0)) - (CEZA if bozuk else 0.0))
    return {"puan": round(puan, 4), "elendi": elendi, "cer_ort": round(cer, 3), "cocuk_ort": round(child, 3),
            "yas_ort": round(age, 1), "benzerlik": sim, "bozulma": bozuk, "notlar": notes}




def _recommend(ranked: dict[str, list[dict]], sims) -> tuple[dict[str, dict], list[str]]:
    """Ses başına önerilen: elenmemiş adaylardan, önceden önerilenlere paragraf klonu benzerliği PAIR_WARN'ı aşmayan en
    yüksek puanlı (dört sesin birbirinden ayırt edilmesi). Bütün ses sıralamaları denenir; en az uyarı, sonra en yüksek
    toplam puan kazanır. Ayrışan aday yoksa en yüksek puanlı alınır ve uyarı yazılır."""
    from itertools import permutations
    best = None
    for order in permutations(ranked):
        pick, warns = {}, []
        for ses in order:
            ok = [c for c in ranked[ses] if not c["puan"]["elendi"]]
            if not ok:
                continue
            far = [c for c in ok if all(sims(c, p) <= PAIR_WARN for p in pick.values())]
            pick[ses] = far[0] if far else ok[0]
            if not far:
                warns.append(ses)
        total = sum(c["puan"]["puan"] for c in pick.values())
        cand = (len(warns), -total, pick, warns)
        if best is None or cand[:2] < best[:2]:
            best = cand
    return (best[2], best[3]) if best else ({}, [])


def sec() -> None:
    sl = json.loads((V2 / "kisa-liste.json").read_text())
    klon_rows = {}
    for p in (V2 / "klon").glob("*.json"):
        r = json.loads(p.read_text())
        klon_rows[(r["ses"], r["sira"], r["kind"])] = r
    adir = OUT / "aday2"
    if adir.exists():
        shutil.rmtree(adir)
    adir.mkdir()
    texts = {"READER_TEXT": READER_TEXT, "CHILD_TEXT": CHILD_TEXT}
    # harf hatasının kaynağı: CER_KAYNAK=cer (hizalayıcı, varsayılan) ya da cer_w (Whisper); öbürü tabloda yan yana
    key = os.environ.get("CER_KAYNAK", "cer")
    cw = _cer_w()
    ranked: dict[str, list[dict]] = {}
    for ses, refs in sl.items():
        cands = []
        for i, ref in enumerate(refs, 1):
            kc, kp = klon_rows.get((ses, i, "cumle")), klon_rows.get((ses, i, "paragraf"))
            if not kc or not kp or "olcum" not in kc or "olcum" not in kp:
                continue
            ref = {**ref, "cer_w": cw.get(ref["file"])}
            kc["olcum"]["cer_w"], kp["olcum"]["cer_w"] = cw.get(kc["file"]), cw.get(kp["file"])
            sc = score(ses, kc, kp, key)
            sc["diger"] = score(ses, kc, kp, "cer_w" if key == "cer" else "cer") if cw else None
            sha = hashlib.sha256((OUT / ref["file"]).read_bytes()).hexdigest()
            cands.append({
                "ses": ses, "kaynak_dosya": ref["file"], "sha256": sha, "klon_cumle_dosya": kc["file"],
                "klon_paragraf_dosya": kp["file"], "ref_text": texts[ref["text"]], "ref_text_adi": ref["text"],
                "yontem": {k: ref[k] for k in ("kaynak", "kaynak_tur", "yol", "formant", "perde_hedef", "aralik")},
                "puan": sc,
                "olcum_referans": {k: ref.get(k) for k in ("f0", "voiced_ratio", "cer", "cer_w", "age", "p_cocuk",
                                                            "p_kadin", "p_erkek", "sicrama", "patlama")},
                "klon_cumle": {**kc["olcum"], "benzerlik_ref": kc["benzerlik_ref"],
                               "benzerlik_kaynak": kc["benzerlik_kaynak"], "servis": kc["servis"]},
                "klon_paragraf": {**kp["olcum"], "benzerlik_ref": kp["benzerlik_ref"],
                                  "benzerlik_kaynak": kp["benzerlik_kaynak"], "servis": kp["servis"]}})
        cands.sort(key=lambda c: (c["puan"]["elendi"], -c["puan"]["puan"]))
        for n, c in enumerate(cands, 1):
            c["sira"], c["aday"] = n, f"{ses}-{n}"
        ranked[ses] = cands
    # konuşmacı benzerliği paragraf klonları arasında (sayfayı klon okur)
    emb = {c["klon_paragraf_dosya"]: embed(OUT / c["klon_paragraf_dosya"]) for cs in ranked.values() for c in cs}
    sims = lambda a, b: float(emb[a["klon_paragraf_dosya"]] @ emb[b["klon_paragraf_dosya"]])   # noqa: E731
    recommended, warns = _recommend(ranked, sims)
    hdr = ("| Aday | Puan (hizalayıcı / Whisper) | Yöntem | Kaynak | Formant | Perde hedefi / aralık | "
           "Referans f0 / cer h·w / çocuk / yaş | Klon cümle f0 / cer h·w / çocuk / yaş | "
           "Klon paragraf f0 / cer h·w / çocuk / yaş | Benzerlik paragraf↔ref / ↔kaynak | Not |")
    lines = [f"Sıralama harf hatası kaynağı: {key} (× = elendi)", "", hdr, "|" + "---|" * 11]
    f = lambda m: (f"{m.get('f0')} / {m.get('cer')}·{m.get('cer_w')} / {m['p_cocuk']:.2f} / "   # noqa: E731
                   f"{m['age']:.1f}")
    out = []
    for ses, cands in ranked.items():
        for c in cands:
            c["onerilen"] = recommended.get(ses) is c
            c["dinlemede"] = c["sira"] <= ADAY_SAYISI or c["onerilen"]
            if c["dinlemede"]:
                base = c["aday"]
                shutil.copyfile(OUT / c["kaynak_dosya"], adir / f"{base}-referans.wav")
                shutil.copyfile(OUT / c["klon_cumle_dosya"], adir / f"{base}-klon-cumle.wav")
                shutil.copyfile(OUT / c["klon_paragraf_dosya"], adir / f"{base}-klon-paragraf.wav")
                c["referans"] = f"{base}-referans.wav"
            sc = c["puan"]
            ph, pw = (sc, sc["diger"]) if key == "cer" else (sc["diger"], sc)
            pcell = f"{ph['puan']:.3f}{'×' if ph['elendi'] else ''} / " + (
                f"{pw['puan']:.3f}{'×' if pw['elendi'] else ''}" if pw else "—")
            y, kp = c["yontem"], c["klon_paragraf"]
            lines.append(f"| {c['aday']}{' **önerilen**' if c['onerilen'] else ''} | {pcell} | {y['yol']} | "
                         f"{y['kaynak']} | {y['formant']} | {y['perde_hedef']} / {y['aralik']} | "
                         f"{f(c['olcum_referans'])} | {f(c['klon_cumle'])} | {f(kp)} | {kp['benzerlik_ref']:.3f} / "
                         f"{kp['benzerlik_kaynak']:.3f} | {'; '.join(sc['notlar'])} |")
            out.append(c)
        prev = OUT / "aday" / f"{ses}-1.wav"         # karşılaştırma: 1. yöntemin ilk adayı
        if prev.exists():
            shutil.copyfile(prev, adir / f"{ses}-0-onceki.wav")
    pairs = []
    ids = sorted(recommended)
    for a_i, a in enumerate(ids):
        for b in ids[a_i + 1:]:
            s = round(sims(recommended[a], recommended[b]), 3)
            pairs.append({"a": a, "b": b, "benzerlik": s, "uyari": s > PAIR_WARN,
                          "ayni_kaynak": recommended[a]["yontem"]["kaynak"] == recommended[b]["yontem"]["kaynak"]})
    # ölçüt aracının ayırma gücü: aynı kaydın klonu ile referansı ↔ farklı kaynaklı adaylar
    all_c = [c for cs in ranked.values() for c in cs]
    diff = [sims(a, b) for i, a in enumerate(all_c) for b in all_c[i + 1:]
            if a["yontem"]["kaynak"] != b["yontem"]["kaynak"]]
    lines += ["", "| Önerilen çift (paragraf klonu) | Konuşmacı benzerliği | Aynı kaynak | Uyarı (> 0,85) |",
              "|---|---|---|---|"]
    lines += [f"| {p['a']} ↔ {p['b']} | {p['benzerlik']:.3f} | {'evet' if p['ayni_kaynak'] else 'hayır'} | "
              f"{'UYARI' if p['uyari'] else '—'} |" for p in pairs]
    if diff:
        diff.sort()
        lines += ["", f"Farklı kaynaklı aday çiftleri arasında benzerlik: en az {diff[0]:.3f}, ortanca "
                      f"{diff[len(diff) // 2]:.3f}, en çok {diff[-1]:.3f} ({len(diff)} çift)."]
    if warns:
        lines += [f"Ayrışan aday bulunamayan ses(ler): {', '.join(warns)}"]
    lines += ["", "PINNED satırları (sabitlenmedi; dosya sesler/zeki/<ses>.wav olarak konunca):"]
    lines += [f'    "{s}": _p("{s}", {r["ref_text_adi"]}, "{r["sha256"]}"),  # {r["aday"]}: {r["yontem"]["yol"]} '
              f'{r["yontem"]["kaynak"]} f{r["yontem"]["formant"]} p{r["yontem"]["perde_hedef"]} '
              f'r{r["yontem"]["aralik"]}' for s, r in sorted(recommended.items())]
    (adir / "liste.json").write_text(json.dumps({"cer_kaynak": key, "cumle": CHILD_TEXT, "paragraf": PARAGRAPH,
                                                 "adaylar": out, "onerilen_ciftler": pairs, "ayrisamayan": warns},
                                                ensure_ascii=False, indent=1))
    (adir / "sec.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    {"donustur": donustur, "olc": olc, "klon": klon, "klonolc": klonolc, "whisper": whisper,
     "sec": sec}[sys.argv[1]]()
