"""book-voice (ÖNERİ, gateway'e henüz eklenmedi): Türkçe seslendirme + kelime zamanlaması servisi.

Seslendirme VoxCPM2 (OpenBMB, Apache-2.0); kelime zamanı Türkçe wav2vec2 CTC modeliyle zorla hizalama
(Baybars/wav2vec2-xls-r-300m-cv8-turkish, Apache-2.0; hizalama torchaudio `forced_align`). Seçim ve lisanslar:
docs/analiz/sesli-okuma-model-secimi.md. Metnin okunuşa çevrilmesi (sayı, tarih, kısaltma, sözlük) burada değil,
editörün `production/narration.py`'sindedir; bu servise okunacak metin gelir.

Gateway kalıbı book-upscale ile aynı: komut vLLM biçimindedir (`/model --served-model-name … --gpu-memory-utilization …`);
`/model` altında iki klasör beklenir: `VoxCPM2/` ve `aligner/`. Kalan argümanlar yok sayılır.

Ses: tarifle tasarım (`voice.design`, gerçek kişi sesi gerekmez) ya da referansla klonlama (`voice.ref_audio` +
`voice.ref_text`; referans genellikle bir kez tarifle üretilmiş model çıktısıdır, kitap boyunca aynı ses kalır).

    GET  /health
    POST /v1/audio/narrate {model, segments: [{text, voice, pause_ms, words}], format: mp3|wav, align: bool}
         → {audio: base64, format, sample_rate, duration, seconds,
            segments: [{start, end, aligned, words: [{start, end, score} | null, …]}]}

`words`: hizalanacak kelimeler (okunuşun kelimeleri, sırasıyla). Dönen `words` aynı uzunluktadır; hizalanamayan
kelime null döner (çağıran tahminle doldurur). Zamanlar saniye, bütün sesin başından.
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
    TTS, ALIGNER = _load()
    SR = int(getattr(TTS.tts_model, "sample_rate", 48000))


@app.get("/health")
def health() -> dict:
    return {"ok": TTS is not None, "aligner": ALIGNER is not None, "sample_rate": SR, "device": DEVICE}


class Voice(BaseModel):
    design: str | None = None          # tarif: "orta yaşlı, sıcak sesli kadın anlatıcı" (İngilizce de olur)
    ref_audio: str | None = None       # base64 WAV (klon)
    ref_text: str | None = None


class Segment(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice: Voice = Voice()
    pause_ms: int = Field(300, ge=0, le=5000)
    words: list[str] = []
    seed: int | None = None


class Narrate(BaseModel):
    model: str = "book-voice"
    segments: list[Segment] = Field(min_length=1)
    format: str = "mp3"
    align: bool = True


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


def _speak(seg: Segment, tmp: str) -> np.ndarray:
    text, ref = seg.text, None
    v = seg.voice
    if v.ref_audio:
        ref = os.path.join(tmp, f"ref-{abs(hash(v.ref_audio)) % 10**9}.wav")
        if not os.path.exists(ref):
            with open(ref, "wb") as f:
                f.write(base64.b64decode(v.ref_audio))
    elif v.design:
        text = f"({v.design.strip()}){text}"
    if seg.seed is not None:
        torch.manual_seed(seg.seed)
        np.random.seed(seg.seed % (2**32))
    kw = {"text": text, "cfg_value": args.cfg, "inference_timesteps": args.steps, "normalize": False, "denoise": False}
    if ref and v.ref_text:
        # Referans hem ses hem metinle verilir: en tutarlı klon (VoxCPM2 "ultimate cloning").
        kw.update(prompt_wav_path=ref, prompt_text=v.ref_text, reference_wav_path=ref)
    elif ref:
        kw.update(reference_wav_path=ref)
    wav = TTS.generate(**kw)
    return _fade(_trim(np.asarray(wav, dtype=np.float32)))


# ------------------------------------------------------------------ hizalama
_LOWER = str.maketrans({"I": "ı", "İ": "i"})


def _norm_word(w: str, vocab: dict) -> str:
    w = w.translate(_LOWER).lower()
    return "".join(ch for ch in w if ch in vocab)


def _resample16(wav: np.ndarray) -> torch.Tensor:
    import torchaudio.functional as AF
    t = torch.from_numpy(wav).float()[None]
    return AF.resample(t, SR, 16000)[0] if SR != 16000 else t[0]


@torch.inference_mode()
def _align(wav: np.ndarray, words: list[str]) -> list[dict | None]:
    """CTC Viterbi hizalama: her kelimenin başı/sonu (sn, segment başından) ve ortalama olasılığı."""
    if ALIGNER is None or not words:
        return [None] * len(words)
    import torchaudio.functional as AF
    proc, model = ALIGNER
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
    x = _resample16(wav)
    feats = proc(x.numpy(), sampling_rate=16000, return_tensors="pt").input_values.to(DEVICE)
    logits = model(feats).logits
    lp = torch.log_softmax(logits, dim=-1)
    T = lp.shape[1]
    if T < len(tokens):
        return [None] * len(words)
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


@app.post("/v1/audio/narrate")
def narrate(req: Narrate) -> dict:
    if TTS is None:
        raise HTTPException(503, "model yükleniyor")
    if req.format not in ("mp3", "wav"):
        raise HTTPException(400, "format: mp3 | wav")
    t0 = time.time()
    parts, out, pos = [], [], 0
    with _lock, tempfile.TemporaryDirectory() as tmp:
        for seg in req.segments:
            wav = _speak(seg, tmp)
            words = _align(wav, seg.words) if req.align else [None] * len(seg.words)
            start = pos / SR
            out.append({"start": round(start, 3), "end": round((pos + len(wav)) / SR, 3), "aligned": ALIGNER is not None,
                        "words": [None if w is None else {**w, "start": round(w["start"] + start, 3),
                                                          "end": round(w["end"] + start, 3)} for w in words]})
            gap = np.zeros(int(SR * seg.pause_ms / 1000), dtype=np.float32)
            parts += [wav, gap]
            pos += len(wav) + len(gap)
    full = np.concatenate(parts) if parts else np.zeros(1, dtype=np.float32)
    return {"audio": base64.b64encode(_encode(full, req.format)).decode(), "format": req.format, "sample_rate": SR,
            "duration": round(len(full) / SR, 3), "seconds": round(time.time() - t0, 2), "segments": out}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")
