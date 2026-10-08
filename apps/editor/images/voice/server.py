"""book-voice: Türkçe seslendirme + kelime zamanlaması servisi; gateway takma adı olarak istekte açılır.

Seslendirme VoxCPM2 (OpenBMB, Apache-2.0); kelime zamanı Türkçe wav2vec2 CTC modeliyle zorla hizalama
(Baybars/wav2vec2-xls-r-300m-cv8-turkish, Apache-2.0; hizalama torchaudio `forced_align`). Seçim ve lisanslar:
docs/analiz/sesli-okuma-model-secimi.md. Metnin okunuşa çevrilmesi (sayı, tarih, kısaltma, sözlük) burada değil,
editörün `production/narration.py`'sindedir; bu servise okunacak metin gelir.

Gateway kalıbı book-upscale ile aynı: komut vLLM biçimindedir (`/model --served-model-name … --gpu-memory-utilization …`);
`/model` altında iki klasör beklenir: `VoxCPM2/` ve `aligner/` (ağırlıklar MANIFEST'te sha256 ile). Kalan argümanlar
yok sayılır. `--gpu-memory-utilization` bu süreçte PyTorch'un bellek tavanıdır: gateway kartı modellerin payına göre
paylaştırır (FIT_TOGETHER), servis payını aşarsa yanındaki modelle bellek aşımına düşmesin diye kendi payında kalır.

Ses: tarifle tasarım (`voice.design`, gerçek kişi sesi gerekmez) ya da referansla klonlama (`voice.ref_audio` +
`voice.ref_text`; referans genellikle bir kez tarifle üretilmiş model çıktısıdır, kitap boyunca aynı ses kalır).

    GET  /health
    POST /v1/audio/narrate {model, segments: [{text, voice, pause_ms, words, style?, rate?, pause_before_ms?, clone?,
                            cfg?}], format: mp3|wav, align: bool, measure?: bool}
         → {audio: base64, format, sample_rate, duration, seconds,
            segments: [{start, end, aligned, words: [{start, end, score} | null, …]}]}

`words`: hizalanacak kelimeler (okunuşun kelimeleri, sırasıyla). Dönen `words` aynı uzunluktadır; hizalanamayan
kelime null döner (çağıran tahminle doldurur). Zamanlar saniye, bütün sesin başından.

İfade katmanı (editörün `production/expression.py`'si; ölçüm docs/analiz/sesli-okuma-ifade-katmani.md):
`style` parçanın ton talimatıdır ("whispering", "excited, faster" …) ve metnin başına `(style)` olarak girer.
`clone` referanslı seste klon kipidir: `full` referans sesi + metni (devam kipi, en tutarlı ses), `ref` yalnız
referans sesi (talimat bu kipte etkili); boşsa `style` varken `ref`, yokken `full`. `rate` konuşma hızıdır: üretimden
sonra perdeyi koruyan zaman esnetme (rubberband; yoksa atempo), kelime zamanları esnetilmiş sesten hizalanır.
`pause_before_ms` parçadan önce sessizliktir; `cfg` parçanın yönlendirme gücüdür (boşsa `--cfg`).
Tam klonda talimat metne girerse model onu sesli okur (ölçüm: harf hatası %45–111); tam klonda ton, `voice.prompt_audio`
ile verilir: aynı sesin referans cümlesini ifadeyle okuyan örnek, devam kipi onun tonunu sürdürür, kimlik referanstan.
Dönüşümlü ses (editörün voices_zeki.TRANSFORMS'u): `voice.transform` {path: world|praat, formant, pitch, range,
f0_floor, f0_ceil} varsa parça referansla (kaynak sesle) okunur, sonra perde + formant dönüşümüyle çevrilir; hizalama
ve ölçüm dönüşmüş sesten yapılır. Perde kaynak sesin referans kaydının ortancasına göre taşınır (satırın kendi
ortancasına göre değil): bütün satırlar aynı perdede kalır. Dönen parça `transform: <yol>` ile işaretlenir (editör
işaretsiz parçayı kabul etmez). Dönüşüm işlemcide (pyworld / parselmouth), satır başına ~1 sn.
`measure: true` her parçaya `measure` ekler (ortanca perde, enerji, sesli oranı, tanıyıcıyla harf hatası oranı):
ifade örneği adayları bununla seçilir.

Yalnız hizalama (insan kaydı; editörün `production/narration_human.py`'si): gövdede `recording` (base64 ses dosyası,
ffmpeg'in çözdüğü her biçim) ve `words` (kaydın okuduğu bütün okunuş kelimeleri, sırasıyla) varsa hiçbir şey
üretilmez, `segments` boş olabilir; kayıt 16 kHz'e çevrilip kelimeler tek hizalamada yerleştirilir. Uzun kayıtta
hizalayıcının çıktısı 30 sn'lik pencerelerle (iki yanda 1 sn bağlam) hesaplanıp birleştirilir, Viterbi yolu büyük
tabloda işlemcide çözülür (bellek kare × jeton). `format: none` ses döndürmez.

    POST /v1/audio/narrate {model, recording, words, align: true, format: none}
         → {audio: "", format, sample_rate: 16000, duration, seconds, aligned, segments: [],
            words: [{start, end, score} | null, …]}
"""

from __future__ import annotations

import argparse
import base64
import io
import os
import re
import subprocess
import tempfile
import threading
import time

import numpy as np
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

ap = argparse.ArgumentParser()
ap.add_argument("model_dir")
ap.add_argument("--served-model-name", nargs="*")
ap.add_argument("--gpu-memory-utilization")
ap.add_argument("--port", type=int, default=8000)
ap.add_argument("--device", default="cuda")
ap.add_argument("--steps", type=int, default=10)            # VoxCPM2 akış adımı (hız/kalite)
ap.add_argument("--cfg", type=float, default=2.0)
ap.add_argument("--no-compile", action="store_true")
args, _ = ap.parse_known_args()

DEVICE = args.device if (args.device != "cuda" or torch.cuda.is_available()) else "cpu"
if DEVICE.startswith("cuda") and args.gpu_memory_utilization:
    torch.cuda.set_per_process_memory_fraction(float(args.gpu_memory_utilization))
TTS_DIR = os.path.join(args.model_dir, "VoxCPM2")
ALIGN_DIR = os.path.join(args.model_dir, "aligner")
_lock = threading.Lock()                                      # tek sıra: model aynı anda tek istek


def _load():
    from voxcpm import VoxCPM
    tts = VoxCPM(voxcpm_model_path=TTS_DIR, zipenhancer_model_path=None, enable_denoiser=False,
                 optimize=not args.no_compile and DEVICE.startswith("cuda"), device=DEVICE)
    aligner = None
    if os.path.isdir(ALIGN_DIR):
        # Dil modeli (language_model/) hizalamada kullanılmaz: sade işlemci.
        from transformers import AutoModelForCTC, Wav2Vec2Processor
        proc = Wav2Vec2Processor.from_pretrained(ALIGN_DIR)
        model = AutoModelForCTC.from_pretrained(ALIGN_DIR).to(DEVICE).eval()
        aligner = (proc, model)
    return tts, aligner


TTS, ALIGNER = None, None
SR = 48000
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.on_event("startup")
def _startup() -> None:
    global TTS, ALIGNER, SR
    t0 = time.time()
    TTS, ALIGNER = _load()
    SR = int(getattr(TTS.tts_model, "sample_rate", 48000))
    peak = torch.cuda.max_memory_reserved() / 2**30 if DEVICE.startswith("cuda") else 0.0
    print(f"book-voice hazır: {time.time() - t0:.1f} sn, aygıt {DEVICE}, bellek {peak:.1f} GiB", flush=True)


@app.get("/health")
def health() -> dict:
    mem = {}
    if DEVICE.startswith("cuda"):
        mem = {"reserved_gib": round(torch.cuda.memory_reserved() / 2**30, 2),
               "peak_gib": round(torch.cuda.max_memory_reserved() / 2**30, 2)}
    return {"ok": TTS is not None, "aligner": ALIGNER is not None, "sample_rate": SR, "device": DEVICE,
            "transforms": ["world", "praat"], **mem}


class Transform(BaseModel):
    path: str = Field(pattern="^(world|praat)$")   # world: WORLD vokoder; praat: Praat «Change gender»
    formant: float = Field(ge=0.7, le=1.5)          # formant oranı: yeni(f) = eski(f / oran)
    pitch: float = Field(ge=60, le=500)             # hedef ortanca perde (Hz)
    range: float = Field(1.0, ge=0.3, le=2.0)       # perde aralığı çarpanı (log düzlemde ortanca çevresinde)
    f0_floor: float = Field(100, ge=40, le=400)     # perde arama tabanı/tavanı (kaynak sesin cinsine göre)
    f0_ceil: float = Field(500, ge=150, le=1000)


class Voice(BaseModel):
    design: str | None = None          # tarif: "orta yaşlı, sıcak sesli kadın anlatıcı" (İngilizce de olur)
    ref_audio: str | None = None       # base64 WAV (klon)
    ref_text: str | None = None
    prompt_audio: str | None = None    # base64 WAV: devam kipinin örnek sesi (ifade örneği; metni ref_text), kimlik ref_audio'dan
    transform: Transform | None = None  # dönüşümlü ses: okumadan sonra perde + formant (ortanca ref_audio'dan)


class Segment(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice: Voice = Voice()
    pause_ms: int = Field(300, ge=0, le=5000)
    words: list[str] = []
    seed: int | None = None
    style: str | None = Field(None, max_length=200)             # ifade: ton talimatı, "(style)metin"
    rate: float = Field(1.0, ge=0.7, le=1.4)                    # ifade: konuşma hızı (sonradan, perde korunur)
    pause_before_ms: int = Field(0, ge=0, le=3000)              # ifade: parçadan önce sessizlik
    clone: str | None = Field(None, pattern="^(full|ref)$")     # referanslı seste klon kipi (boş: style → ref)
    cfg: float | None = Field(None, ge=1.0, le=3.0)            # ifade: yönlendirme gücü (boş: sunucu varsayılanı)
    min_sec: float | None = Field(None, ge=0, le=10)            # kısa ünlem: üretilen ses bundan kısaysa yavaşlatılır
    gain_db: float = Field(0.0, ge=-30.0, le=12.0)              # ifade: üretimden sonra düzey (fısıltı alçak okunur)


class Narrate(BaseModel):
    model: str = "book-voice"
    segments: list[Segment] = []       # üretim kipinde en az bir parça (recording yokken)
    format: str = "mp3"
    align: bool = True
    measure: bool = False              # parça başına ölçü: perde, enerji, sesli oranı, tanıyıcıyla harf hatası
    recording: str | None = None       # yalnız hizalama: base64 ses dosyası (insan kaydı), üretim yok
    words: list[str] = []              # recording ile: kaydın bütün okunuş kelimeleri, sırasıyla



# ------------------------------------------------------------------ seslendirme
def _trim(wav: np.ndarray, thresh: float = 0.008, keep_ms: int = 40) -> np.ndarray:
    idx = np.where(np.abs(wav) > thresh)[0]
    if len(idx) == 0:
        return wav
    k = int(SR * keep_ms / 1000)
    return wav[max(0, idx[0] - k): idx[-1] + k]


def _fade(wav: np.ndarray, ms: int = 12) -> np.ndarray:
    n = min(int(SR * ms / 1000), len(wav) // 2)
    if n > 0:
        r = np.linspace(0, 1, n, dtype=np.float32)
        wav[:n] *= r
        wav[-n:] *= r[::-1]
    return wav


MIN_STRETCH = 0.6


def _stretch(wav: np.ndarray, rate: float) -> np.ndarray:
    """Konuşma hızı: perdeyi koruyan zaman esnetme (rate > 1 hızlı). rubberband yoksa atempo; ikisi de düşerse aynen."""
    if abs(rate - 1.0) < 0.01 or len(wav) == 0:
        return wav
    raw = np.clip(wav, -1, 1).astype("<f4").tobytes()
    for flt in (f"rubberband=tempo={rate:.3f}:transients=smooth:formant=preserved", f"atempo={rate:.3f}"):
        r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "f32le", "-ar", str(SR), "-ac", "1",
                            "-i", "pipe:0", "-af", flt, "-f", "f32le", "-ar", str(SR), "-ac", "1", "pipe:1"],
                           input=raw, capture_output=True)
        if r.returncode == 0 and r.stdout:
            return np.frombuffer(r.stdout, dtype="<f4").copy()
    return wav


def _speak(seg: Segment, tmp: str) -> np.ndarray:
    text, ref = seg.text, None
    v = seg.voice
    style = (seg.style or "").strip().strip("()").strip()
    if v.ref_audio:
        ref = os.path.join(tmp, f"ref-{abs(hash(v.ref_audio)) % 10**9}.wav")
        if not os.path.exists(ref):
            with open(ref, "wb") as f:
                f.write(base64.b64decode(v.ref_audio))
        if style:
            text = f"({style}){text}"
    elif v.design:
        text = f"({v.design.strip()}{', ' + style if style else ''}){text}"
    elif style:
        text = f"({style}){text}"
    if seg.seed is not None:
        torch.manual_seed(seg.seed)
        np.random.seed(seg.seed % (2**32))
    kw = {"text": text, "cfg_value": seg.cfg or args.cfg, "inference_timesteps": args.steps, "normalize": False,
          "denoise": False}
    clone = seg.clone or ("ref" if style else "full")
    if ref and v.ref_text and clone == "full":
        # Referans hem ses hem metinle verilir: en tutarlı klon (VoxCPM2 "ultimate cloning"). `prompt_audio` varsa devam
        # kipi onun tonunu sürdürür (aynı sesin ifadeli örneği), kimlik yine referanstan.
        prompt = ref
        if v.prompt_audio:
            prompt = os.path.join(tmp, f"prompt-{abs(hash(v.prompt_audio)) % 10**9}.wav")
            if not os.path.exists(prompt):
                with open(prompt, "wb") as f:
                    f.write(base64.b64decode(v.prompt_audio))
        kw.update(prompt_wav_path=prompt, prompt_text=v.ref_text, reference_wav_path=ref)
    elif ref:
        # Yalnız referans sesi (VoxCPM2 "controllable cloning"): ses referanstan, ton talimattan.
        kw.update(reference_wav_path=ref)
    wav = TTS.generate(**kw)
    wav = _trim(_stretch(np.asarray(wav, dtype=np.float32), seg.rate))
    if seg.min_sec and len(wav) and len(wav) / SR < seg.min_sec:
        # Kısa ünlem yutulmasın («Tüh!» 0,2 sn, «O da ne!» 0,45 sn çıkıyordu): perdeyi koruyarak en az süreye esnetilir,
        # en çok MIN_STRETCH kadar (daha yavaşı yapay duyulur).
        wav = _stretch(wav, max(MIN_STRETCH, len(wav) / SR / seg.min_sec))
    if seg.gain_db:
        wav = (wav * np.float32(10 ** (seg.gain_db / 20))).astype(np.float32)
    if v.transform is not None and len(wav):
        if not ref:
            raise HTTPException(400, "voice.transform referans sesi (ref_audio) ister")
        wav = transform(wav, SR, v.transform, _ref_median(ref, v.transform))
    return _fade(wav)


# ------------------------------------------------------------------ dönüşüm (perde + formant)
_medians: dict[tuple, float] = {}


def _read_wav(path: str) -> tuple[np.ndarray, int]:
    import soundfile as sf
    x, fs = sf.read(path, dtype="float64")
    return (x.mean(axis=1) if x.ndim > 1 else x), int(fs)


def _median_f0(x: np.ndarray, fs: int, t: Transform) -> float:
    """Ortanca perde, dönüşümün kendi perde izleyicisiyle (world: harvest, praat: Praat Pitch)."""
    if t.path == "world":
        import pyworld as pw
        f0, _ = pw.harvest(np.ascontiguousarray(x, dtype=np.float64), fs, f0_floor=t.f0_floor, f0_ceil=t.f0_ceil)
        f0 = f0[f0 > 0]
    else:
        import parselmouth
        snd = parselmouth.Sound(np.ascontiguousarray(x, dtype=np.float64), sampling_frequency=fs)
        f0 = snd.to_pitch(pitch_floor=t.f0_floor, pitch_ceiling=t.f0_ceil).selected_array["frequency"]
        f0 = f0[f0 > 0]
    return float(np.median(f0)) if len(f0) else 0.0


def _ref_median(ref_path: str, t: Transform) -> float:
    """Kaynak sesin referans kaydının ortanca perdesi (dosya + izleyici + aralık başına bir kez)."""
    with open(ref_path, "rb") as f:
        key = (hash(f.read()), t.path, t.f0_floor, t.f0_ceil)
    if key not in _medians:
        _medians[key] = _median_f0(*_read_wav(ref_path), t)
    if _medians[key] <= 0:
        raise HTTPException(400, "referans kaydında perde bulunamadı")
    return _medians[key]


def transform(x: np.ndarray, fs: int, t: Transform, ref_med: float) -> np.ndarray:
    """Perde + formant dönüşümü; uzunluk değişmez, tepe düzeyi kaynağınki (en çok 0,95).
    world: F0 log düzlemde `ref_med` → `pitch` (aralık çarpanıyla); spektral zarf ve aperiyodiklik frekans ekseninde
    formant oranıyla sıkıştırılır. deploy/ses/cocuk_donustur.py `_world` ve Levent pilotunun betiğiyle aynı hesap.
    praat: «Change gender»; satırın kendi ortancası `ref_med`'e göre taşınıp hedefe eşlenir (bütün satırlar aynı perde)."""
    x64 = np.ascontiguousarray(x, dtype=np.float64)
    if t.path == "world":
        import pyworld as pw
        f0, tt = pw.harvest(x64, fs, f0_floor=t.f0_floor, f0_ceil=t.f0_ceil)
        sp = pw.cheaptrick(x64, f0, tt, fs)
        ap = pw.d4c(x64, f0, tt, fs)
        v = f0 > 0
        nf0 = np.zeros_like(f0)
        nf0[v] = np.exp(np.log(t.pitch) + t.range * (np.log(f0[v]) - np.log(ref_med)))
        bins = sp.shape[1]
        idx = np.arange(bins) / t.formant
        warp = lambda a: np.stack([np.interp(idx, np.arange(bins), r) for r in a])   # noqa: E731
        y = pw.synthesize(nf0, np.ascontiguousarray(warp(sp)), np.ascontiguousarray(np.clip(warp(ap), 0, 1)), fs)
    else:
        import parselmouth
        from parselmouth.praat import call
        snd = parselmouth.Sound(x64, sampling_frequency=fs)
        own = _median_f0(x64, fs, t)
        target = t.pitch * (own / ref_med) ** t.range if own > 0 else t.pitch
        new = call(snd, "Change gender", t.f0_floor, t.f0_ceil, t.formant, float(target), t.range, 1.0)
        y = new.values[0]
        if int(new.sampling_frequency) != fs:
            y = np.interp(np.arange(int(len(y) * fs / new.sampling_frequency)) * new.sampling_frequency / fs,
                          np.arange(len(y)), y)
    y = np.asarray(y, dtype=np.float64)
    y = y[:len(x)] if len(y) >= len(x) else np.pad(y, (0, len(x) - len(y)))
    y = y / max(1e-6, np.abs(y).max()) * min(0.95, np.abs(x64).max() + 1e-6)
    return np.clip(y, -1, 1).astype(np.float32)


# ------------------------------------------------------------------ hizalama
_LOWER = str.maketrans({"I": "ı", "İ": "i"})


def _norm_word(w: str, vocab: dict) -> str:
    w = w.translate(_LOWER).lower()
    return "".join(ch for ch in w if ch in vocab)


def _resample16(wav: np.ndarray) -> torch.Tensor:
    import torchaudio.functional as AF
    t = torch.from_numpy(wav).float()[None]
    return AF.resample(t, SR, 16000)[0] if SR != 16000 else t[0]


HOP = 320                              # hizalayıcının kare adımı (16 kHz'de 20 ms)
WIN = 30 * 16000                       # uzun kayıtta pencere (HOP'un katı)
CTX = 16000                            # pencerenin iki yanındaki bağlam (HOP'un katı)


def _logprobs(x: torch.Tensor) -> torch.Tensor:
    """Hizalayıcının kare başına log olasılıkları [1, T, V]. Kısa seste tek geçiş (eski yol); uzun kayıtta pencerelerle,
    her pencere iki yandan bağlamla hesaplanır ve yalnız kendi karelerini verir (bellek sese göre büyümez)."""
    proc, model = ALIGNER
    n = x.shape[-1]
    if n <= WIN + 2 * CTX:
        feats = proc(x.numpy(), sampling_rate=16000, return_tensors="pt").input_values.to(DEVICE)
        return torch.log_softmax(model(feats).logits, dim=-1)
    outs = []
    for a in range(0, n, WIN):
        b = min(n, a + WIN)
        s, e = max(0, a - CTX), min(n, b + CTX)
        feats = proc(x[s:e].numpy(), sampling_rate=16000, return_tensors="pt").input_values.to(DEVICE)
        lp = torch.log_softmax(model(feats).logits, dim=-1)[0]
        off = (a - s) // HOP
        k = (b - a) // HOP if b < n else lp.shape[0] - off
        outs.append(lp[off:off + k].float().cpu())
    return torch.cat(outs)[None]


@torch.inference_mode()
def _align(wav: np.ndarray, words: list[str]) -> list[dict | None]:
    """CTC Viterbi hizalama: her kelimenin başı/sonu (sn, segment başından) ve ortalama olasılığı."""
    if ALIGNER is None or not words:
        return [None] * len(words)
    return _align16(_resample16(wav), words)


@torch.inference_mode()
def _align16(x: torch.Tensor, words: list[str]) -> list[dict | None]:
    """`_align`'ın 16 kHz sesle çalışan gövdesi (insan kaydı doğrudan 16 kHz çözülür)."""
    if ALIGNER is None or not words:
        return [None] * len(words)
    import torchaudio.functional as AF
    proc, _model = ALIGNER
    vocab = proc.tokenizer.get_vocab()
    sep = proc.tokenizer.word_delimiter_token or "|"
    blank = proc.tokenizer.pad_token_id
    clean = [_norm_word(w, vocab) for w in words]
    keep = [i for i, c in enumerate(clean) if c]
    if not keep:
        return [None] * len(words)
    tokens, spans = [], []
    for j, i in enumerate(keep):
        if j and sep in vocab:
            tokens.append(vocab[sep])
        s = len(tokens)
        tokens += [vocab[ch] for ch in clean[i]]
        spans.append((i, s, len(tokens)))
    lp = _logprobs(x)
    T = lp.shape[1]
    if T < len(tokens):
        return [None] * len(words)
    if T * len(tokens) > 2e8:              # uzun kayıt: Viterbi geri izleme tablosu (kare × jeton) işlemcide
        lp = lp.cpu()
    targets = torch.tensor([tokens], dtype=torch.int32, device=lp.device)
    path, scores = AF.forced_align(lp, targets, blank=blank)
    # CTC çöküşü (tekrar birleşir, boşluk atılır) hedefle birebir: jeton başına [ilk kare, son kare) aralığı.
    toks = AF.merge_tokens(path[0], scores[0].exp(), blank=blank)   # blank verilmezse 0 sayılır (bu sözlükte «|»)
    if len(toks) != len(tokens):
        return [None] * len(words)
    sec = x.shape[-1] / 16000 / T
    out: list[dict | None] = [None] * len(words)
    for i, s, e in spans:
        part = toks[s:e]
        out[i] = {"start": round(part[0].start * sec, 3), "end": round(part[-1].end * sec, 3),
                  "score": round(float(sum(t.score for t in part) / len(part)), 3)}
    return out


# ------------------------------------------------------------------ ölçü (ifade örneği seçimi)
def _heard(wav: np.ndarray) -> str:
    """Hizalayıcı modelin açgözlü CTC çözümü (tanıyıcı olarak): anlaşılırlık denetimi için."""
    proc, model = ALIGNER
    x = _resample16(wav)
    feats = proc(x.numpy(), sampling_rate=16000, return_tensors="pt").input_values.to(DEVICE)
    with torch.inference_mode():
        ids = model(feats).logits.argmax(-1)
    return proc.batch_decode(ids)[0]


def _lev(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _measure(wav: np.ndarray, text: str) -> dict:
    """Ortanca perde (Hz), etkin konuşmada ortalama enerji (dBFS), sesli kare oranı, harf hatası oranı."""
    import librosa
    y = _resample16(wav).numpy()
    rms = librosa.feature.rms(y=y, frame_length=400, hop_length=160)[0]
    db = 20 * np.log10(rms + 1e-9)
    active = db > db.max() - 35
    f0, vflag, _ = librosa.pyin(y, fmin=60, fmax=600, sr=16000, frame_length=1024, hop_length=160)
    n = min(len(f0), len(active))
    voiced = vflag[:n] & active[:n] & ~np.isnan(f0[:n])
    out = {"f0": round(float(np.median(f0[:n][voiced])), 1) if voiced.sum() > 5 else None,
           "energy_db": round(float(db[:n][active[:n]].mean()), 2) if active.any() else None,
           "voiced_ratio": round(float(voiced.sum() / max(1, active[:n].sum())), 3)}
    if ALIGNER is not None:
        clean = lambda t: re.sub(r"[^a-zçğıöşüâîû]", "", t.translate(_LOWER).lower())   # noqa: E731
        want, got = clean(text), clean(_heard(wav))
        out["cer"] = round(_lev(want, got) / max(1, len(want)), 3)
    return out


# ------------------------------------------------------------------ çıktı
def _encode(wav: np.ndarray, fmt: str) -> bytes:
    pcm = (np.clip(wav, -1, 1) * 32767).astype("<i2").tobytes()
    import wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm)
    if fmt == "wav":
        return buf.getvalue()
    # MP3 (EPUB medya kaplamasının çekirdek türü); tek kanal 64 kbit/s konuşma için yeter.
    r = subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "wav", "-i", "pipe:0",
                        "-codec:a", "libmp3lame", "-b:a", "64k", "-ac", "1", "-f", "mp3", "pipe:1"],
                       input=buf.getvalue(), capture_output=True, check=True)
    return r.stdout


def _decode16(data: bytes, tmp: str) -> np.ndarray:
    """Ses dosyası → 16 kHz tek kanal (ffmpeg; kapsayıcısı sona yazılan biçimler için dosyadan okunur)."""
    src = os.path.join(tmp, "kayit")
    with open(src, "wb") as f:
        f.write(data)
    r = subprocess.run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", src, "-ac", "1", "-ar", "16000",
                        "-f", "f32le", "pipe:1"], capture_output=True)
    if r.returncode != 0 or not r.stdout:
        raise HTTPException(400, "kayıt çözülemedi")
    return np.frombuffer(r.stdout, dtype="<f4").copy()


def _recording(req: Narrate) -> dict:
    """Yalnız hizalama: insan kaydında kelimelerin yeri. Üretim yok."""
    if TTS is None:                        # modeller birlikte açılır; açılış bitmeden hizalayıcı da hazır değil
        raise HTTPException(503, "model yükleniyor")
    t0 = time.time()
    try:
        data = base64.b64decode(req.recording or "", validate=True)
    except ValueError:
        raise HTTPException(400, "recording base64 değil") from None
    with _lock, tempfile.TemporaryDirectory() as tmp:
        x = _decode16(data, tmp)
        words = _align16(torch.from_numpy(x), req.words) if req.align else [None] * len(req.words)
    return {"audio": "", "format": "none", "sample_rate": 16000, "duration": round(len(x) / 16000, 3),
            "seconds": round(time.time() - t0, 2), "aligned": ALIGNER is not None, "segments": [], "words": words}


@app.post("/v1/audio/narrate")
def narrate(req: Narrate) -> dict:
    if req.recording is not None:
        return _recording(req)
    if TTS is None:
        raise HTTPException(503, "model yükleniyor")
    if not req.segments:
        raise HTTPException(400, "segments boş")
    if req.format not in ("mp3", "wav"):
        raise HTTPException(400, "format: mp3 | wav")
    t0 = time.time()
    parts, out, pos = [], [], 0
    with _lock, tempfile.TemporaryDirectory() as tmp:
        for seg in req.segments:
            wav = _speak(seg, tmp)
            words = _align(wav, seg.words) if req.align else [None] * len(seg.words)
            if seg.pause_before_ms:
                before = np.zeros(int(SR * seg.pause_before_ms / 1000), dtype=np.float32)
                parts.append(before)
                pos += len(before)
            start = pos / SR
            out.append({"start": round(start, 3), "end": round((pos + len(wav)) / SR, 3), "aligned": ALIGNER is not None,
                        "words": [None if w is None else {**w, "start": round(w["start"] + start, 3),
                                                          "end": round(w["end"] + start, 3)} for w in words],
                        **({"measure": _measure(wav, seg.text)} if req.measure else {}),
                        **({"transform": seg.voice.transform.path} if seg.voice.transform else {})})
            gap = np.zeros(int(SR * seg.pause_ms / 1000), dtype=np.float32)
            parts += [wav, gap]
            pos += len(wav) + len(gap)
    full = np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)
    return {"audio": base64.b64encode(_encode(full, req.format)).decode(), "format": req.format, "sample_rate": SR,
            "duration": round(len(full) / SR, 3), "seconds": round(time.time() - t0, 2), "segments": out}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")
