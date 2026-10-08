"""Tek çekim dudak senkronu (InfiniteTalk video-to-video): editor-lipsync imajında koşar.

Girdi: üretilmiş çekim (mp4, ör. 1344x768 @ 24 fps, 3-9 sn) + konuşmacı başına replik sesi (wav) ya da sessiz kip.
Çıktı: girdinin kare sayısına, fps'ine ve çözünürlüğüne birebir hizalı mp4.

Model hakkında bilinmesi gerekenler (InfiniteTalk d59847e ağırlıkları, kod 50aa0a9):
  - 25 fps çalışır (wav2vec gömmesi kare başına 1). Girdi önce 25 fps'e çevrilir, üretim 25 fps, sonra her çıktı karesi
    için zamanca en yakın üretim karesi seçilir → kare sayısı ve süre girdiyle aynı kalır.
  - "Seyrek kare" dublajı: girdi videodan yalnız her parçanın ilk karesi (81 karelik pencere, 9 kare devir → 0., 72.,
    144., ... kareler) koşul olur; aradaki baş/gövde hareketini model yeniden üretir. Kamera hareketi "taklit" edilir,
    birebir değildir. Bu yüzden --birlestir yama (yalnız konuşan kişinin kutusu üretimden, gerisi orijinal kare) var.
  - En çok 2 kişi (person1/person2). 2 kişide her kişinin kutusu şarttır; konuşmayan kişiye sessiz (sıfır) ses verilir,
    ağzı kapalı kalır. Üçüncü kişi arka plan sayılır → çok kişili sahnede --birlestir yama önerilir (kutulu kişiler
    üretimden, kutusuz 3. kişi ve arka plan orijinal kareden).
  - Ses gömme uzunluğu pencereden (81 kare = 3,24 sn) uzun olmalı: kısa çekimde ses sessizlikle uzatılır, çıktı kırpılır.
  - Kutu biçimi bu araçta x1,y1,x2,y2 (girdi videonun pikseli, sol-üst/sağ-alt). InfiniteTalk kendi JSON'unda maskeyi
    [satır_min, sütun_min, satır_max, sütun_max] diye dizinler (multitalk.py: human_mask[x_min:x_max, y_min:y_max]);
    dönüşüm burada yapılır.

Örnekler (konteyner içinde):
  python /srv/dub.py --video cekim.mp4 --konusmaci replik.wav --cikti dub.mp4 --hizli
  python /srv/dub.py --video cekim.mp4 --konusmaci ali.wav@120,80,600,760 --sessiz-kisi 700,90,1200,760 \
      --birlestir yama --cikti dub.mp4
  python /srv/dub.py --video cekim.mp4 --sessiz --cikti dub.mp4            # anlatım/dış ses: ağızlar kapalı
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace

import numpy as np

KOD = os.environ.get("INFINITETALK_KOD", "/opt/InfiniteTalk")
MODELLER = os.environ.get("MODELLER", "/data/editor/models")
WAV_SR = 16000
MODEL_FPS = 25
PENCERE = 81          # frame_num: 4n+1, eğitim penceresi
DEVIR = 9             # motion_frame
CIKTI_SR = 48000

log = logging.getLogger("dub")


# ----------------------------------------------------------------------------- yardımcılar
def kutu_coz(s: str, w: int, h: int) -> tuple[int, int, int, int]:
    try:
        x1, y1, x2, y2 = (int(round(float(v))) for v in s.split(","))
    except ValueError as e:
        raise SystemExit(f"kutu 'x1,y1,x2,y2' olmalı: {s!r}") from e
    x1, x2 = max(0, min(x1, x2)), min(w, max(x1, x2))
    y1, y2 = max(0, min(y1, y2)), min(h, max(y1, y2))
    if x2 - x1 < 16 or y2 - y1 < 16:
        raise SystemExit(f"kutu çok küçük ya da kare dışında: {s!r} (kare {w}x{h})")
    return x1, y1, x2, y2


def ffprobe(path: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path],
        check=True, capture_output=True, text=True).stdout
    d = json.loads(out)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    if v is None:
        raise SystemExit(f"video akışı yok: {path}")
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    return {"w": int(v["width"]), "h": int(v["height"]), "fps_str": v["r_frame_rate"], "fps": num / den,
            "ses_var": any(s["codec_type"] == "audio" for s in d["streams"])}


def kareleri_oku(path: str, w: int, h: int) -> np.ndarray:
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         check=True, capture_output=True).stdout
    n = len(raw) // (w * h * 3)
    if n == 0:
        raise SystemExit(f"kare okunamadı: {path}")
    return np.frombuffer(raw[: n * w * h * 3], np.uint8).reshape(n, h, w, 3)


def ses_yukle(path: str, sr: int) -> np.ndarray:
    import librosa
    y, _ = librosa.load(path, sr=sr, mono=True)
    return y.astype(np.float32)


def yukseklik_esitle(y: np.ndarray, sr: int, lufs: float = -23.0) -> np.ndarray:
    """generate_infinitetalk.loudness_norm ile aynı: -23 LUFS; sessiz/ölçülemeyen ses dokunulmadan döner."""
    import pyloudnorm as pyln
    if not np.any(y):
        return y
    meter = pyln.Meter(sr)
    loud = meter.integrated_loudness(y)
    if not math.isfinite(loud) or abs(loud) > 100:
        return y
    return pyln.normalize.loudness(y, loud, lufs).astype(np.float32)


def boyuta_getir(y: np.ndarray, n: int) -> np.ndarray:
    return y[:n] if len(y) >= n else np.concatenate([y, np.zeros(n - len(y), np.float32)])


def gomme(y: np.ndarray, extractor, encoder):
    """generate_infinitetalk.get_embedding ile aynı (wav2vec2 gizli katmanları, 25 fps'e örneklenmiş)."""
    import torch
    from einops import rearrange
    video_len = len(y) / WAV_SR * MODEL_FPS
    feat = np.squeeze(extractor(y, sampling_rate=WAV_SR).input_values)
    feat = torch.from_numpy(feat).float().unsqueeze(0)
    with torch.no_grad():
        emb = encoder(feat, seq_len=int(video_len), output_hidden_states=True)
    emb = torch.stack(emb.hidden_states[1:], dim=1).squeeze(0)
    return rearrange(emb, "b s d -> s b d").cpu().detach()


def alfa_maskesi(w: int, h: int, bolge: tuple[int, int, int, int], kutular: list[tuple[int, int, int, int]] | None,
                 yumusak: int, pay: float) -> np.ndarray:
    """Birleştirme maskesi (h, w, 1) float32. tam: üretim bölgesinin tamamı (kenarı içe doğru yumuşak);
    yama: kutuların pay kadar büyütülmüş birleşimi ∩ üretim bölgesi."""
    import cv2
    m = np.zeros((h, w), np.float32)
    bx1, by1, bx2, by2 = bolge
    if kutular:
        for x1, y1, x2, y2 in kutular:
            px, py = int((x2 - x1) * pay), int((y2 - y1) * pay)
            m[max(by1, y1 - py):min(by2, y2 + py), max(bx1, x1 - px):min(bx2, x2 + px)] = 1.0
    else:
        m[by1:by2, bx1:bx2] = 1.0
    if yumusak > 0:
        k = 2 * yumusak + 1
        m = cv2.erode(m, np.ones((yumusak, yumusak), np.uint8))  # yumuşak kenar üretim bölgesinin dışına taşmasın
        m = cv2.GaussianBlur(m, (k, k), yumusak / 2.0)
    return m[..., None]


# ----------------------------------------------------------------------------- ana akış
def argumanlar() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Tek çekim dudak senkronu (InfiniteTalk V2V)")
    p.add_argument("--video", required=True, help="girdi çekim (mp4)")
    p.add_argument("--cikti", required=True, help="çıktı mp4")
    p.add_argument("--konusmaci", action="append", default=[], metavar="WAV[@x1,y1,x2,y2]",
                   help="konuşan kişi: replik sesi ve (çok kişide şart) kutusu. En çok 2.")
    p.add_argument("--sessiz-kisi", action="append", default=[], metavar="x1,y1,x2,y2",
                   help="kadrajdaki konuşmayan kişi: ağzı kapalı tutulur (sıfır ses). Konuşmacı+sessiz ≤ 2.")
    p.add_argument("--sessiz", action="store_true",
                   help="hiç konuşan yok (dış ses/anlatım): tüm ağızlar kapalı. --konusmaci ile birlikte verilmez.")
    p.add_argument("--cozunurluk", choices=["480", "720"], default="720",
                   help="üretim kovası: 720 → 1344x768 girdi için 1280x704, 480 → 896x448 (sonra girdi boyutuna)")
    p.add_argument("--birlestir", choices=["tam", "yama"], default="tam",
                   help="tam: üretilen kare (kırpılan şeritler orijinalden); yama: yalnız kutular üretimden")
    p.add_argument("--yama-payi", type=float, default=0.15, help="yama kutusunun her yana büyütme oranı")
    p.add_argument("--yumusak", type=int, default=24, help="birleştirme kenar yumuşatma (piksel)")
    p.add_argument("--hizli", action="store_true",
                   help="lightx2v adım damıtma LoRA'sı: 4 adım, metin CFG 1, ses CFG 2, kaydırma 2")
    p.add_argument("--lora", default=None, help="LoRA dosyası (--hizli varsayılanı lightx2v T2V rank32)")
    p.add_argument("--lora-olcek", type=float, default=1.0)
    p.add_argument("--adim", type=int, default=None, help="örnekleme adımı (varsayılan 40; --hizli ile 4)")
    p.add_argument("--metin-cfg", type=float, default=None, help="varsayılan 5 (--hizli ile 1)")
    p.add_argument("--ses-cfg", type=float, default=None, help="varsayılan 4 (--hizli ile 2); dudak isabeti 3-5 arası")
    p.add_argument("--kaydirma", type=float, default=None, help="akış kaydırma (varsayılan 480:7, 720:11; --hizli 2)")
    p.add_argument("--teacache", action="store_true", help="TeaCache hızlandırma")
    p.add_argument("--teacache-esik", type=float, default=0.2)
    p.add_argument("--apg", action="store_true", help="adaptive projected guidance")
    p.add_argument("--renk-duzeltme", type=float, default=1.0, help="0-1, ilk kareye renk eşleme")
    p.add_argument("--prompt", default=None)
    p.add_argument("--tohum", type=int, default=42)
    p.add_argument("--ses-izi", choices=["replik", "orijinal", "yok"], default=None,
                   help="çıktının ses izi (varsayılan: konuşmada replik karışımı, sessiz kipte orijinal)")
    p.add_argument("--dusuk-bellek", action="store_true",
                   help="model parçalarını adım aralarında CPU'ya indir (offload) + DiT kalıcı parametre 0: çok yavaş")
    p.add_argument("--is-dizini", default=None, help="ara dosyalar (varsayılan geçici; verilirse silinmez)")
    p.add_argument("--wan", default=f"{MODELLER}/Wan2.1-I2V-14B-480P")
    p.add_argument("--wav2vec", default=f"{MODELLER}/chinese-wav2vec2-base")
    p.add_argument("--infinitetalk", default=f"{MODELLER}/InfiniteTalk")
    p.add_argument("--kuru", action="store_true", help="yalnız girdileri doğrula ve planı yaz, model yükleme")
    return p.parse_args()


def main() -> int:
    a = argumanlar()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s dub %(message)s", stream=sys.stderr)
    t0 = time.time()

    meta = ffprobe(a.video)
    W, H, fps = meta["w"], meta["h"], meta["fps"]

    # --- kişiler: (ses|None, kutu|None)
    if a.sessiz and a.konusmaci:
        raise SystemExit("--sessiz ile --konusmaci birlikte verilmez")
    if not a.sessiz and not a.konusmaci:
        raise SystemExit("en az bir --konusmaci ya da --sessiz gerekli")
    kisiler: list[tuple[str | None, tuple[int, int, int, int] | None]] = []
    for k in a.konusmaci:
        wav, _, kutu = k.partition("@")
        if not os.path.isfile(wav):
            raise SystemExit(f"ses yok: {wav}")
        kisiler.append((wav, kutu_coz(kutu, W, H) if kutu else None))
    for kutu in a.sessiz_kisi:
        kisiler.append((None, kutu_coz(kutu, W, H)))
    if a.sessiz and not kisiler:
        kisiler.append((None, None))
    if len(kisiler) > 2:
        raise SystemExit("InfiniteTalk en çok 2 kişi alır (person1/person2); 3. kişi için --birlestir yama kullanın")
    if len(kisiler) == 2 and any(k[1] is None for k in kisiler):
        raise SystemExit("2 kişide her kişinin kutusu şart (WAV@x1,y1,x2,y2 ve --sessiz-kisi x1,y1,x2,y2)")
    # yama: konuşan VE sessiz tutulan kişilerin kutuları üretimden gelir (H3 çekiminde konuşmayanın ağzı oynuyor
    # olabilir); kutusu verilmemiş 3. kişi orijinal karede kalır.
    yama_kutulari = [k[1] for k in kisiler if k[1] is not None]
    if a.birlestir == "yama" and not yama_kutulari:
        raise SystemExit("--birlestir yama için kişi kutusu gerekli (WAV@x1,y1,x2,y2 ya da --sessiz-kisi)")

    hizli = a.hizli
    adim = a.adim or (4 if hizli else 40)
    metin_cfg = a.metin_cfg if a.metin_cfg is not None else (1.0 if hizli else 5.0)
    ses_cfg = a.ses_cfg if a.ses_cfg is not None else (2.0 if hizli else 4.0)
    kova = f"infinitetalk-{a.cozunurluk}"
    kaydirma = a.kaydirma if a.kaydirma is not None else (2.0 if hizli else (7.0 if a.cozunurluk == "480" else 11.0))
    lora = a.lora or (f"{a.infinitetalk}/lora/Wan21_T2V_14B_lightx2v_cfg_step_distill_lora_rank32.safetensors"
                      if hizli else None)
    agirlik = f"{a.infinitetalk}/{'multi' if len(kisiler) == 2 else 'single'}/infinitetalk.safetensors"
    prompt = a.prompt or (
        "A 3D animated cartoon character with mouth closed, silent and still, listening, stylized 3D animation"
        if a.sessiz else
        "A 3D animated cartoon character is talking with clear natural lip movements, stylized 3D animation")
    ses_izi = a.ses_izi or ("orijinal" if a.sessiz else "replik")
    if ses_izi == "orijinal" and not meta["ses_var"]:
        log.warning("girdide ses izi yok → çıktı sessiz")
        ses_izi = "yok"

    is_dizini = a.is_dizini or tempfile.mkdtemp(prefix="dub-")
    os.makedirs(is_dizini, exist_ok=True)
    try:
        # --- girdi kareleri (orijinal hız) ve 25 fps koşul videosu
        orijinal = kareleri_oku(a.video, W, H)
        N = len(orijinal)
        sure = N / fps
        T25 = max(1, math.ceil(sure * MODEL_FPS - 1e-6))
        kosul = os.path.join(is_dizini, "kosul25.mp4")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", a.video, "-vf", f"fps={MODEL_FPS}", "-an",
                        "-c:v", "libx264", "-crf", "10", "-preset", "fast", "-pix_fmt", "yuv420p", kosul], check=True)

        # gömme penceresi şartı: len > PENCERE (multitalk.py: shape[0] <= frame_num → atlanır → assert)
        gerekli_kare = max(T25, PENCERE + 1) + 4
        ornek = math.ceil(gerekli_kare / MODEL_FPS * WAV_SR)
        sesler16 = []
        for wav, _ in kisiler:
            if wav is None:
                sesler16.append(np.zeros(ornek, np.float32))
                continue
            y = ses_yukle(wav, WAV_SR)
            if len(y) > math.ceil(sure * WAV_SR) + WAV_SR // 25:
                log.warning("%s çekimden uzun (%.2f sn > %.2f sn): çekim süresinde kesilir",
                            wav, len(y) / WAV_SR, sure)
                y = y[: math.ceil(sure * WAV_SR)]
            sesler16.append(boyuta_getir(yukseklik_esitle(y, WAV_SR), ornek))

        plan = {"girdi": a.video, "boyut": f"{W}x{H}", "fps": meta["fps_str"], "kare": N, "sure_sn": round(sure, 3),
                "uretim_kare_25fps": T25, "kisi": [{"ses": k[0] or "sessiz", "kutu": k[1]} for k in kisiler],
                "agirlik": agirlik, "kova": kova, "adim": adim, "metin_cfg": metin_cfg, "ses_cfg": ses_cfg,
                "kaydirma": kaydirma, "lora": lora, "teacache": a.teacache, "birlestir": a.birlestir,
                "ses_izi": ses_izi, "prompt": prompt}
        log.info("plan %s", json.dumps(plan, ensure_ascii=False))
        for yol in [agirlik, f"{a.wan}/Wan2.1_VAE.pth", f"{a.wav2vec}/config.json"] + ([lora] if lora else []):
            if not os.path.exists(yol):
                raise SystemExit(f"model dosyası yok: {yol}")
        if a.kuru:
            print(json.dumps({"kuru": True, **plan}, ensure_ascii=False))
            return 0

        # --- model (InfiniteTalk kodu sabit commit'te /opt/InfiniteTalk)
        sys.path.insert(0, KOD)
        import torch
        from transformers import Wav2Vec2FeatureExtractor
        from src.audio_analysis.wav2vec2 import Wav2Vec2Model
        import wan
        from wan.configs import WAN_CONFIGS

        extractor = Wav2Vec2FeatureExtractor.from_pretrained(a.wav2vec, local_files_only=True)
        encoder = Wav2Vec2Model.from_pretrained(a.wav2vec, local_files_only=True).to("cpu")
        encoder.feature_extractor._freeze_parameters()
        cond_audio = {}
        for i, y in enumerate(sesler16, 1):
            yol = os.path.join(is_dizini, f"{i}.pt")
            torch.save(gomme(y, extractor, encoder), yol)
            cond_audio[f"person{i}"] = yol
        del encoder
        toplam = os.path.join(is_dizini, "toplam16k.wav")
        import soundfile as sf
        sf.write(toplam, np.clip(np.sum(sesler16, axis=0), -1, 1), WAV_SR)

        girdi = {"prompt": prompt, "cond_video": kosul, "cond_audio": cond_audio, "video_audio": toplam}
        if len(kisiler) == 2:
            girdi["audio_type"] = "para"
            # InfiniteTalk dizinlemesi: [satır_min, sütun_min, satır_max, sütun_max]
            girdi["bbox"] = {f"person{i}": [k[1][1], k[1][0], k[1][3], k[1][2]] for i, k in enumerate(kisiler, 1)}

        t1 = time.time()
        boru = wan.InfiniteTalkPipeline(
            config=WAN_CONFIGS["infinitetalk-14B"], checkpoint_dir=a.wan, quant_dir=None, device_id=0, rank=0,
            t5_fsdp=False, dit_fsdp=False, use_usp=False, t5_cpu=False,
            lora_dir=[lora] if lora else None, lora_scales=[a.lora_olcek] if lora else None,
            quant=None, dit_path=None, infinitetalk_dir=agirlik)
        if a.dusuk_bellek:
            boru.vram_management = True
            boru.enable_vram_management(num_persistent_param_in_dit=0)
        t2 = time.time()
        ek = SimpleNamespace(use_teacache=a.teacache, teacache_thresh=a.teacache_esik, size=kova, use_apg=a.apg,
                             apg_momentum=-0.75, apg_norm_threshold=55)
        video = boru.generate_infinitetalk(
            girdi, size_buckget=kova, motion_frame=DEVIR, frame_num=PENCERE, shift=kaydirma, sampling_steps=adim,
            text_guide_scale=metin_cfg, audio_guide_scale=ses_cfg, seed=a.tohum, offload_model=a.dusuk_bellek,
            max_frames_num=max(T25, PENCERE), color_correction_strength=a.renk_duzeltme, extra_args=ek)
        t3 = time.time()
        tepe_gb = torch.cuda.max_memory_allocated() / 1e9
        uretim = ((video.float().clamp(-1, 1) + 1) * 127.5).round().to(torch.uint8)  # C T h w
        uretim = uretim.permute(1, 2, 3, 0).cpu().numpy()                             # T h w C
        del video, boru
        torch.cuda.empty_cache()
        if len(uretim) < T25:
            log.warning("üretim %d kare < beklenen %d: son kare tekrarlanır", len(uretim), T25)
        th, tw = uretim.shape[1:3]

        # --- geometri: resize_and_centercrop'un tersi (ölçek = max, ortadan kırpma)
        import cv2
        s = max(th / H, tw / W)
        sh, sw = math.ceil(s * H), math.ceil(s * W)
        ust, sol = int(round((sh - th) / 2.0)), int(round((sw - tw) / 2.0))
        bx1, by1 = int(round(sol / s)), int(round(ust / s))
        bw, bh = min(W - bx1, int(round(tw / s))), min(H - by1, int(round(th / s)))
        bolge = (bx1, by1, bx1 + bw, by1 + bh)
        alfa = alfa_maskesi(W, H, bolge, yama_kutulari if a.birlestir == "yama" else None,
                            a.yumusak, a.yama_payi)
        tam_kapsar = a.birlestir == "tam" and bolge == (0, 0, W, H)

        # --- ses izi
        ses_yolu = None
        if ses_izi == "replik":
            karisim = np.zeros(math.ceil(sure * CIKTI_SR), np.float32)
            for wav, _ in kisiler:
                if wav:
                    karisim += boyuta_getir(ses_yukle(wav, CIKTI_SR), len(karisim))
            ses_yolu = os.path.join(is_dizini, "replik48k.wav")
            sf.write(ses_yolu, np.clip(karisim, -1, 1), CIKTI_SR)

        # --- yazım: girdinin fps'i ve kare sayısı; her kare için zamanca en yakın 25 fps üretim karesi
        komut = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                 "-r", meta["fps_str"], "-i", "-"]
        if ses_izi == "replik":
            komut += ["-i", ses_yolu, "-map", "0:v", "-map", "1:a"]
        elif ses_izi == "orijinal":
            komut += ["-i", a.video, "-map", "0:v", "-map", "1:a:0"]
        komut += ["-c:v", "libx264", "-crf", "14", "-preset", "medium", "-pix_fmt", "yuv420p",
                  "-r", meta["fps_str"], "-frames:v", str(N)]
        if ses_izi != "yok":
            komut += ["-c:a", "aac", "-b:a", "192k", "-t", f"{sure:.6f}"]
        komut += ["-movflags", "+faststart", a.cikti]
        os.makedirs(os.path.dirname(os.path.abspath(a.cikti)), exist_ok=True)
        yazici = subprocess.Popen(komut, stdin=subprocess.PIPE)
        for i in range(N):
            j = min(int(round(i / fps * MODEL_FPS)), len(uretim) - 1)
            g = cv2.resize(uretim[j], (bw, bh), interpolation=cv2.INTER_LANCZOS4)
            if tam_kapsar:
                kare = g
            else:
                tuval = orijinal[i].astype(np.float32)
                yer = tuval.copy()
                yer[by1:by1 + bh, bx1:bx1 + bw] = g
                kare = np.clip(alfa * yer + (1 - alfa) * tuval, 0, 255).astype(np.uint8)
            yazici.stdin.write(np.ascontiguousarray(kare).tobytes())
        yazici.stdin.close()
        if yazici.wait() != 0:
            raise SystemExit("ffmpeg yazımı başarısız")

        cikti = ffprobe(a.cikti)
        ozet = {**plan, "cikti": a.cikti, "cikti_boyut": f"{cikti['w']}x{cikti['h']}", "cikti_fps": cikti["fps_str"],
                "uretim_boyut": f"{tw}x{th}", "uretim_bolgesi": bolge, "tepe_gpu_gb": round(tepe_gb, 1),
                "sn_yukleme": round(t2 - t1, 1), "sn_uretim": round(t3 - t2, 1), "sn_toplam": round(time.time() - t0, 1)}
        print(json.dumps(ozet, ensure_ascii=False))
        return 0
    finally:
        if not a.is_dizini:
            shutil.rmtree(is_dizini, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
