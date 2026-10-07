"""book-video servisinin hesap kuralları: motor seçimi, kare sayısı, tuval, iyileştirme parametreleri. torch ve model
kodu içe aktarmaz; sunucu (server.py), işçiler (worker_*.py) ve modelsiz testler (tests/test_film.py) bunu çağırır.

Her sayı kaynağıyla birlikte yazılıdır (kaynak commit'leri Dockerfile'da sabit):
- Wan 2.2: 16 kare/sn, parça 4n+1 kare, en çok 81 (wan/configs, generate.py).
- MiniMax-H3: 24 kare/sn; kare sayısı 17n+5'e yukarı yuvarlanır ve 5–15 sn içinde kalmalı (diffusers
  modular_pipelines/minimax_h3/modular_pipeline.py `align_num_frames`, `min_duration`/`max_duration`;
  before_denoise.py: süre *yuvarlanmış* kare sayısıyla denetlenir → en çok 345 kare). Tuval: kısa kenar 768, alan
  tavanı 768×1344, iki eksen 32'nin katı (`resolve_canvas_size`).
- FastH3 8-Step V2: 9 sigma noktası = 8 ileri geçiş, video/ses kayması 10/3 (FastVideo
  examples/inference/basic/basic_fasth3_8step.py; ComfyUI şablonu video_fastvideo_fasth3_i2v.json: BasicScheduler
  simple/8, KSamplerSelect res_multistep, MiniMaxH3SigmaShift 10/3). H100 ölçü tuvali 960×544
  (basic_fasth3_h100.yaml request.sampling).
- SeedVR2 CLI: batch_size 4n+1; 4K için VAE döşemesi (numz/ComfyUI-SeedVR2_VideoUpscaler README «High Resolution»).
- Practical-RIFE: yalnız tam kat ara kare (`--multi`), oran kesirliyse kat alınıp sonra kare hızına indirilir.
"""

from __future__ import annotations

import math
import os

ENGINES = ("wan2.2", "h3", "fast-h3")
MODES = ("i2v", "s2v")
MAX_REFS = 8                  # H3 ref2va en çok 9 görsel; 1'i ilk kare

# ------------------------------------------------------------------ Wan 2.2
WAN_FPS = 16
WAN_CLIP = 81                 # bir parçanın en çok karesi (4n+1)


def frames_for(seconds: float, cap: int = WAN_CLIP) -> list[int]:
    """Wan: çekim süresini parçalara böler — her parça 4n+1 kare, en çok `cap`; ilk parçadan sonrakiler bir kare
    örtüşür (önceki parçanın son karesinden devam)."""
    total = max(17, round(seconds * WAN_FPS) + 1)
    out, left = [], total
    while left > 0:
        n = min(left + (1 if out else 0), cap)
        n = max(17, (n - 1) // 4 * 4 + 1)
        out.append(n)
        left -= n - (1 if len(out) > 1 else 0)
    return out


# ------------------------------------------------------------------ MiniMax-H3 / FastH3
H3_FPS = 24
H3_CHUNK, H3_KEEP = 17, 5     # VAE clip_length 17, tokens_chunk_size 5 → 17n+5
H3_MIN_FRAMES = 124           # 5 sn = 120 → 17n+5'e yukarı: 124
H3_MAX_FRAMES = 345           # 15 sn = 360; 362 = 15,08 sn reddedilir → 345
H3_SHORT_EDGE = 768
H3_MAX_PIXELS = 768 * 1344
FAST_H3_SHORT_EDGE = 544      # FastVideo H100 profili 960×544
CANVAS_MULTIPLE = 32


def h3_frames(seconds: float) -> int:
    """H3'ün üreteceği kare sayısı: istenen süre 17n+5'e yukarı yuvarlanır, 124–345 aralığına sıkıştırılır.
    5 sn'den kısa çekim 124 kare (5,17 sn) üretilip sunucuda istenen süreye kesilir."""
    n = max(H3_MIN_FRAMES, round(seconds * H3_FPS))
    while n % H3_CHUNK != H3_KEEP:
        n += 1
    return min(n, H3_MAX_FRAMES)


def h3_canvas(width: int, height: int, short_edge: int = H3_SHORT_EDGE,
              max_pixels: int = H3_MAX_PIXELS) -> tuple[int, int]:
    """İstenen en-boy oranından H3 tuvali (genişlik, yükseklik) — diffusers `resolve_canvas_size` ile aynı hesap."""
    ratio = width / height
    if not 0.25 <= ratio <= 4:
        raise ValueError(f"H3 en-boy oranı 1:4–4:1 aralığında olmalı, gelen {width}x{height}")
    w, h = (short_edge * ratio, float(short_edge)) if ratio >= 1 else (float(short_edge), short_edge / ratio)
    if w * h > max_pixels:
        s = (max_pixels / (w * h)) ** 0.5
        w, h = w * s, h * s
    m = CANVAS_MULTIPLE
    return max(m, round(w / m) * m), max(m, round(h / m) * m)


def h3_task(engine: str, mode: str, refs: int) -> str:
    """Motor + kip → H3 iş akışı.

    - i2v → `fl2va`: ilk kare tuvale bağlanır (geometri çıpası), ses üretimi atılır.
    - s2v, h3 → `ref2va`: <Picture 1> ilk kare, sonraki görseller karakter kartları, <Audio 1> bizim replik izimiz
      `fully_copy` (H3 rehberi: «The complete source audio serves as the target video's complete final audio track»);
      ağız bu sese göre üretilir. ref2va ilk kareyi bağlamaz, yalnız istemle «first frame» der.
    - s2v, fast-h3 → `fl2va+audio`: FastH3 yalnız transformer/ (t2va/fl2va) öğrencisidir, ref2va yoktur; ses ComfyUI
      `MiniMaxH3AddGuide` ile 0. kareye çıpalanır (koşul satırı, gürültüden arındırılmaz). Kartlar kullanılmaz.
    """
    if engine not in ("h3", "fast-h3"):
        raise ValueError(engine)
    if mode == "i2v":
        return "fl2va"
    return "ref2va" if engine == "h3" else "fl2va+audio"


DEFAULT_ENGINE = "h3"         # kullanıcı kararı 2026-10-07: h3 birinci, fast-h3 hızlı kip, wan2.2 yedek


def default_engine() -> str:
    e = os.environ.get("VIDEO_ENGINE", DEFAULT_ENGINE).strip() or DEFAULT_ENGINE
    if e not in ENGINES:
        raise ValueError(f"VIDEO_ENGINE geçersiz: {e!r} (seçenekler: {', '.join(ENGINES)})")
    return e


# Lisans kapısı. Kullanıcı 2026-10-07: kurumların hepsinin lisansı var (MiniMax H3 dahil) → varsayılan hepsi açık.
# VIDEO_LICENSED_ENGINES verilirse yalnız listedekiler açılır (örn. "wan2.2" ile H3 ve FastH3 kapatılır). Wan 2.2
# Apache-2.0 olduğu için her zaman açık. MiniMax H3 Community License IV.2: H3 kullanan ticari ürünün arayüzünde
# «MiniMax H3» adı belirgin gösterilir — ekran kararı kullanıcıda, bu kod ekrana ad yazmaz.
OPEN_LICENSE = {"wan2.2"}


def licensed_engines() -> set[str]:
    raw = os.environ.get("VIDEO_LICENSED_ENGINES")
    if raw is None or not raw.strip():
        return set(ENGINES)
    listed = {x.strip() for x in raw.split(",") if x.strip()}
    return OPEN_LICENSE | (listed & set(ENGINES))


def license_error(engine: str) -> str | None:
    """Motor bu kurulumda kapatılmışsa Türkçe neden (HTTP 409), açıksa None."""
    if engine in licensed_engines():
        return None
    return (f"«{engine}» motoru bu kurulumda lisans ayarıyla kapalı (VIDEO_LICENSED_ENGINES); açık motorlar: "
            f"{', '.join(sorted(licensed_engines()))}.")


def worker_of(engine: str) -> str:
    """Bir motorun işçisi; aynı anda karta tek işçi yüklenir, başka işçi istenince öbürü kapatılır."""
    return {"wan2.2": "wan", "h3": "h3", "fast-h3": "fasth3", "enhance": "enhance"}[engine]


def h3_prompt(task: str, prompt: str, refs: int) -> str:
    """Kendi istemimizi H3'ün beklediği biçime sarar (docs/VIDEO_PROMPT_WRITING_GUIDE_{base,ref}_en.md). H3'ün
    resmî «Context-IR» katmanı açık kaynak değil (yalnız ücretli API); bu sarma onun yerine geçen sade kalıptır.
    Bölüm adları rehberdeki gibi İngilizce; diyalog metni gelmediği için `<d>` yazılmaz."""
    p = prompt.strip()
    quiet = "Quiet ambient room tone only; nobody speaks."
    if task in ("fl2va", "fl2va+audio"):
        talk = (" The on-screen character speaks Turkish; lip movements follow the anchored dialogue audio exactly "
                "and the mouth closes during silences." if task == "fl2va+audio" else "")
        sound = "The character's spoken Turkish dialogue, clean and close." if task == "fl2va+audio" else quiet
        return ("For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully "
                f"referenced.\n\nintegrated_multimodal_description: [Shot 1] {p}{talk}\n\n"
                f"overall_soundscape: {sound}\n\nnon_diegetic_music: None.")
    cards = "".join(f"<Subject {i}> is the character shown in <Picture {i + 1}>; keep face, hair and clothing.\n"
                    for i in range(1, refs + 1))
    speaker = "<Subject 1>" if refs else "the on-screen character"
    return ("subject_definitions:\n<Picture 1> is the first frame of [Shot 1].\n" + cards +
            f"<Audio 1> is the complete Turkish dialogue track spoken by {speaker} (S1).\n\n"
            "summary:\n[keyframe completion + reference generation + audio reuse] The target video starts exactly "
            f"from <Picture 1> and {speaker} speaks the lines of <Audio 1>.\n\n"
            "retention_analysis:\n<Picture 1> ([Shot 1] first frame): fully_preserved - composition, lighting and "
            "style are kept.\n<Audio 1>: fully_copy - <Audio 1> is reused 1:1 as the target video's complete final "
            f"audio track.\n\ndetailed_description:\n[Shot 1] {p} {speaker} (S1) speaks in sync with <Audio 1>; lip "
            "movements match every syllable and the mouth closes during the silences of <Audio 1>.\n\n"
            "overall_soundscape:\n<Audio 1> is the only audible layer.\n\nnon_diegetic_music:\nNone.")


# ------------------------------------------------------------------ iyileştirme (SeedVR2 + RIFE)
TARGETS = {"1080p": 1080, "4k": 2160}     # kısa kenar
SEEDVR2_DIT = "seedvr2_ema_7b_sharp_fp16.safetensors"
SEEDVR2_VAE = "ema_vae_fp16.safetensors"
SEEDVR2_BATCH = 33                        # 4n+1; README CLI örneği


def target_size(width: int, height: int, target: str) -> tuple[int, int]:
    """Kısa kenarı hedefe getirilmiş, çift sayılı boyut (SeedVR2 `--resolution` kısa kenardır)."""
    short = TARGETS[target]
    if width <= height:
        w, h = short, short * height / width
    else:
        w, h = short * width / height, short
    return int(round(w / 2) * 2), int(round(h / 2) * 2)


def seedvr2_args(src: str, out: str, model_dir: str, target: str, frames: int) -> list[str]:
    """SeedVR2 CLI argümanları (inference_cli.py; bayraklar oradaki argparse'tan). Parti boyu çekim boyuna göre 4n+1:
    README «batch_size'ı çekim uzunluğuna eşitle» der; çekim 33'ten kısaysa tek parti."""
    batch = max(5, min(SEEDVR2_BATCH, (frames - 1) // 4 * 4 + 1))
    args = [src, "--output", out, "--output_format", "mp4", "--video_backend", "ffmpeg", "--model_dir", model_dir,
            "--dit_model", SEEDVR2_DIT, "--resolution", str(TARGETS[target]), "--batch_size", str(batch),
            "--uniform_batch_size", "--temporal_overlap", "3", "--color_correction", "lab", "--seed", "42",
            "--cuda_device", "0", "--tensor_offload_device", "cpu"]
    if target == "4k":
        args += ["--vae_encode_tiled", "--vae_decode_tiled", "--dit_offload_device", "cpu",
                 "--vae_offload_device", "cpu"]
    return args


def rife_multi(src_fps: float, dst_fps: int) -> int:
    """Kaç katına ara kare: kaynak ≥ hedefse 1 (RIFE yok, yalnız kare hızı süzgeci). Yoksa hedefi aşan en küçük kat;
    tam bölünen bir kat (en çok 4) varsa o (16→24: 3 kat = 48, 2'de bir kare; 24→30: 2 kat = 48 → 30 süzgeç)."""
    if src_fps >= dst_fps - 0.01:
        return 1
    m = math.ceil(dst_fps / src_fps - 1e-9)
    for k in range(m, 5):
        if abs((src_fps * k) % dst_fps) < 1e-6:
            return k
    return m


def rife_scale(height: int, width: int) -> float:
    """Practical-RIFE: 4K'da `--scale 0.5` (README «Try scale=0.5 for 4k video»; `--UHD` aynı şeyi yapar)."""
    return 0.5 if min(height, width) >= 2000 else 1.0
