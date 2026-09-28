"""Türkçe konuşma tanıma aday ölçümü (geçici; TT GPU'da, GPU 0, bellek tavanlı).

Veri: FLEURS tr_tr test (CC-BY-4.0). Koşullar: temiz · telefon (300–3400 Hz, 8 kHz μ-law) · kalabalık (başka
konuşmacılardan uğultu SNR 10 dB + tarayıcı kaydı gibi Opus 32 kb/sn). Ölçü: WER/CER (Türkçe küçük harf, noktalama ve
kesme işareti atılır, şapka düşer, sayılar yazıya çevrilir), 60 sn ses işlem süresi, GPU belleği.
Kullanım: python3 olc.py <model_dizini> <ad> [--cpu]
"""
import csv, json, os, random, re, subprocess, sys, tarfile, time, io, wave
import numpy as np
import torch
import torchaudio.functional as AF

W = "/w"
MODEL, NAME = sys.argv[1], sys.argv[2]
CPU = "--cpu" in sys.argv
LIMIT = int(os.environ.get("OLC_LIMIT", "0"))
SR = 16000
dev = "cpu" if CPU else "cuda"
if not CPU:
    # BI modeli aynı kartta: bu süreç 10 GB'ı geçemez (aşarsa kendisi OOM olur, başkası değil).
    torch.cuda.set_per_process_memory_fraction(10 * 1024**3 / torch.cuda.get_device_properties(0).total_memory, 0)

# ------------------------------------------------------------------ veri
WAV = f"{W}/fleurs/wav"
if not os.path.isdir(WAV):
    os.makedirs(WAV + ".tmp", exist_ok=True)
    with tarfile.open(f"{W}/fleurs/data/tr_tr/audio/test.tar.gz") as t:
        for m in t.getmembers():
            if m.isfile() and m.name.endswith(".wav"):
                open(f"{WAV}.tmp/{os.path.basename(m.name)}", "wb").write(t.extractfile(m).read())
    os.rename(WAV + ".tmp", WAV)

rows = []
with open(f"{W}/fleurs/data/tr_tr/test.tsv", encoding="utf-8") as f:
    for r in csv.reader(f, delimiter="\t", quoting=csv.QUOTE_NONE):
        if len(r) >= 3 and os.path.exists(f"{WAV}/{r[1]}"):
            rows.append((r[1], r[2]))
seen, uniq = set(), []
for fn, txt in rows:
    if fn not in seen:
        seen.add(fn); uniq.append((fn, txt))
rows = uniq[:LIMIT] if LIMIT else uniq


def load(fn):
    import soundfile as sf
    a, sr = sf.read(f"{WAV}/{fn}", dtype="float32", always_2d=False)
    if a.ndim > 1:
        a = a.mean(axis=1)
    if sr != SR:
        a = AF.resample(torch.from_numpy(a), sr, SR).numpy()
    return a


ALAN = os.environ.get("OLC_ALAN", "")
if ALAN:
    # Sahada telefonla okunan alan cümleleri: <dizin>/alan-cumleleri.tsv + <kimlik>.(m4a|wav|webm|ogg|mp3)
    rows = []
    with open(f"{ALAN}/alan-cumleleri.tsv", encoding="utf-8") as f:
        for i, line in enumerate(f):
            k, _, txt = line.rstrip("\n").partition("\t")
            if i == 0 or not txt:
                continue
            got = [x for x in os.listdir(ALAN) if x.rsplit(".", 1)[0] == k and not x.endswith(".tsv")]
            if got:
                rows.append((f"{ALAN}/{got[0]}", txt))

    def load(fn):  # noqa: F811 — her biçim ffmpeg ile
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", fn, "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                             capture_output=True, check=True).stdout
        return np.frombuffer(raw, dtype="<f4").astype(np.float32)

    os.environ.setdefault("OLC_CONDS", "temiz")

audio = {fn: load(fn) for fn, _ in rows}
print(f"{len(rows)} kayıt, {sum(len(a) for a in audio.values()) / SR / 60:.1f} dk", flush=True)


def phone(a):
    t = torch.from_numpy(a)
    t = AF.highpass_biquad(t, SR, 300.0)
    t = AF.lowpass_biquad(t, SR, 3400.0)
    t = AF.resample(t, SR, 8000)
    t = AF.mu_law_decoding(AF.mu_law_encoding(t.clamp(-1, 1), 256), 256)
    return AF.resample(t, 8000, SR).numpy().astype(np.float32)


def opus(a, kbps=32):
    pcm = (np.clip(a, -1, 1) * 32767).astype(np.int16).tobytes()
    enc = subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-i", "-",
                          "-c:a", "libopus", "-b:a", f"{kbps}k", "-f", "ogg", "-"], input=pcm, capture_output=True, check=True).stdout
    dec = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "-", "-f", "s16le", "-ar", str(SR), "-ac", "1", "-"],
                         input=enc, capture_output=True, check=True).stdout
    return np.frombuffer(dec, dtype=np.int16).astype(np.float32) / 32768


rng = random.Random(7)
keys = list(audio)


def crowd(fn, a, snr=10.0):
    others = [audio[k] for k in rng.sample(keys, 6) if k != fn][:5]
    b = np.zeros_like(a)
    for o in others:
        o = np.tile(o, int(np.ceil(len(a) / len(o))))[: len(a)]
        b += o
    ps, pn = float(np.mean(a**2)) + 1e-9, float(np.mean(b**2)) + 1e-9
    y = a + b * np.sqrt(ps / (pn * 10 ** (snr / 10)))
    y = y / max(1.0, float(np.max(np.abs(y))))
    return opus(y.astype(np.float32))


# ------------------------------------------------------------------ normalleştirme
ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
BIG = [(10**12, "trilyon"), (10**9, "milyar"), (10**6, "milyon"), (1000, "bin")]


def say(n):
    if n == 0:
        return "sıfır"
    out = []
    for v, w in BIG:
        if n >= v:
            q, n = divmod(n, v)
            out.append(w if (v == 1000 and q == 1) else f"{say(q)} {w}")
    if n >= 100:
        q, n = divmod(n, 100)
        out.append("yüz" if q == 1 else f"{ONES[q]} yüz")
    if n >= 10:
        out.append(TENS[n // 10]); n %= 10
    if n:
        out.append(ONES[n])
    return " ".join(out)


def numwords(s):
    s = re.sub(r"%\s?(\d)", r"yüzde \1", s)
    s = re.sub(r"(\d)\.(\d{3})(?!\d)", r"\1\2", s)
    s = re.sub(r"(\d)\.(\d{3})(?!\d)", r"\1\2", s)
    s = re.sub(r"(\d+),(\d+)", lambda m: f"{m.group(1)} virgül {m.group(2)}", s)
    return re.sub(r"\d+", lambda m: f" {say(int(m.group()))} " if len(m.group()) < 16 else m.group(), s)


def norm(s):
    s = s.replace("İ", "i").replace("I", "ı").lower()
    s = s.translate(str.maketrans("âîû", "aiu"))
    s = re.sub(r"['’`´]", "", s)
    s = numwords(s)
    s = re.sub(r"[^\w\s]|_", " ", s)
    return " ".join(s.split())


def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i] + [0] * len(b)
        for j, y in enumerate(b, 1):
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y))
        prev = cur
    return prev[-1]


def score(refs, hyps):
    we = wn = ce = cn = 0
    for r, h in zip(refs, hyps):
        r, h = norm(r), norm(h)
        we += lev(r.split(), h.split()); wn += len(r.split())
        ce += lev(list(r.replace(" ", "")), list(h.replace(" ", ""))); cn += len(r.replace(" ", ""))
    return round(100 * we / max(1, wn), 2), round(100 * ce / max(1, cn), 2)


# ------------------------------------------------------------------ model
is_qwen = "Qwen3-ASR" in MODEL
dtype = torch.float32 if CPU else (torch.bfloat16 if is_qwen else torch.float16)
t0 = time.time()
if is_qwen:
    from transformers import AutoProcessor, Qwen3ASRForConditionalGeneration
    proc = AutoProcessor.from_pretrained(MODEL)
    model = Qwen3ASRForConditionalGeneration.from_pretrained(MODEL, dtype=dtype).to(dev).eval()
else:
    from transformers import WhisperForConditionalGeneration, WhisperProcessor
    proc = WhisperProcessor.from_pretrained(MODEL)
    model = WhisperForConditionalGeneration.from_pretrained(MODEL, dtype=dtype).to(dev).eval()
load_s = time.time() - t0
BS = int(os.environ.get("OLC_BS", "16" if not is_qwen else "8"))
BEAMS = int(os.environ.get("OLC_BEAMS", "1"))


@torch.inference_mode()
def transcribe(arrs):
    if is_qwen:
        inp = proc.apply_transcription_request(list(arrs), language=["tr"] * len(arrs), sampling_rate=SR).to(dev, dtype)
        out = model.generate(**inp, max_new_tokens=448, num_beams=BEAMS, do_sample=False)
        return proc.decode(out[:, inp["input_ids"].shape[1]:], return_format="transcription_only")
    feats = proc.feature_extractor(list(arrs), sampling_rate=SR, return_tensors="pt", return_attention_mask=True)
    ids = model.generate(feats.input_features.to(dev, dtype), attention_mask=feats.attention_mask.to(dev),
                         language="tr", task="transcribe", num_beams=BEAMS, max_new_tokens=440)
    return proc.batch_decode(ids, skip_special_tokens=True)


def run(cond):
    arrs = [audio[fn] if cond == "temiz" else (phone(audio[fn]) if cond == "telefon" else crowd(fn, audio[fn])) for fn, _ in rows]
    hyps, t = [], time.time()
    for i in range(0, len(arrs), BS):
        hyps += [h.strip() for h in transcribe(arrs[i:i + BS])]
    el = time.time() - t
    w, c = score([r for _, r in rows], hyps)
    return {"wer": w, "cer": c, "sn": round(el, 1), "ornek": [{"ref": rows[i][1], "hyp": hyps[i]} for i in (0, 7, 42, 99, 250) if i < len(rows)],
            "hyps": hyps}


res = {"model": NAME, "dir": MODEL, "cihaz": dev, "yukleme_sn": round(load_s, 1), "n": len(rows), "bs": BS, "beams": BEAMS}
if not CPU:
    torch.cuda.reset_peak_memory_stats()

# 60 sn ses: art arda FLEURS kayıtları, 30 sn'lik iki parça (servis de ≤30 sn parçalara böler)
clip = np.concatenate([audio[fn] for fn, _ in rows[:40]])[: 60 * SR]
parts = [clip[:30 * SR], clip[30 * SR:]]
transcribe(parts)  # ısınma
times = []
for _ in range(1 if CPU else 3):
    if not CPU:
        torch.cuda.synchronize()
    t = time.time(); transcribe(parts)
    if not CPU:
        torch.cuda.synchronize()
    times.append(time.time() - t)
res["dk_ses_sn"] = round(sorted(times)[len(times) // 2], 2)
[transcribe([p]) for p in parts]  # tek parçalık ısınma
t = time.time(); [transcribe([p]) for p in parts]; res["dk_ses_sirali_sn"] = round(time.time() - t, 2)
if not CPU:
    res["bellek_60sn_gb"] = round(torch.cuda.max_memory_reserved() / 1024**3, 2)

if not CPU:
    conds = os.environ.get("OLC_CONDS", "temiz,telefon,kalabalik").split(",")
    for cond in conds:
        r = run(cond)
        (open(f"{W}/out/{NAME}.{cond}.hyp.json", "w")).write(json.dumps(r.pop("hyps"), ensure_ascii=False))
        res[cond] = r
        print(NAME, cond, r["wer"], r["cer"], r["sn"], flush=True)
    res["bellek_tepe_gb"] = round(torch.cuda.max_memory_reserved() / 1024**3, 2)
    res["agirlik_gb"] = round(sum(p.numel() * p.element_size() for p in model.parameters()) / 1024**3, 2)

sfx = "_cpu" if CPU else ("" if BEAMS == 1 else f"_b{BEAMS}")
open(f"{W}/out/{NAME}{sfx}.json", "w").write(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps({k: v for k, v in res.items() if k not in ("temiz", "telefon", "kalabalik")}, ensure_ascii=False), flush=True)
