"""book-music motor süreci: kendi sanal ortamında tek motoru yükler, istekleri satır satır işler (server.py başlatır).

    python worker.py <motor> <klasör>
    stdin:  {"kind", "prompt", "seconds", "bpm", "key", "lyrics", "seed", "out": wav yolu, "tmp": geçici klasör}
    stdout: {"ok": true, "seconds", "sample_rate", "truncated"} | {"ok": false, "error"}

Kütüphanelerin ilerleme yazıları cevap kanalını bozmasın diye asıl stdout ayrılır, süreç içindeki her yazı stderr'e
gider. Motor ilk istekte yüklenir; süreç kapanınca kart belleği tamamen boşalır.

Motorların çağrısı kaynak belgelerinden okundu (2026-10-07), GPU'da henüz koşturulmadı:
- Stable Audio 3: `StableAudioModel.generate(prompt, duration, seed)` (Stability-AI/stable-audio-3 README +
  stable_audio_3/model.py). Hub'dan çözmek yerine yerel `model_config.json` + `model.safetensors` ile
  `load_diffusion_cond`; metin kodlayıcısı (t5gemma) klasördeki kopyadan. Tempo ve ton istemin içinde.
- ACE-Step 1.5: docs/en/INFERENCE.md — `AceStepHandler.initialize_service(project_root, config_path)`,
  `LLMHandler.initialize(checkpoint_dir, lm_model_path, backend="pt")` (deponun Dockerfile'ı pt kullanır),
  `generate_music(dit, llm, GenerationParams, GenerationConfig)`. DiT `acestep-v15-xl-sft` (kartı: en yüksek kalite,
  50 adım, CFG) + LM `acestep-5Hz-lm-4B` (kartı: «Full quality (XL + 4B LM)»). Sözsüz: lyrics="[Instrumental]",
  instrumental=True. Tempo ve ton verilmez (tutması zayıf; parça kurguda sahneye uydurulur). ACE-Step yüklemede
  checkpoint klasörüne .py eşitlemesi yazabilir (model_downloader `_sync_model_code_files`); /model salt okunur
  olduğundan klasör /tmp'de küçük dosyalar kopya, ağırlıklar bağlantı olarak kurulur.
- YuE2: `YuE2Pipeline.from_pretrained(<yerel>, vae=<yerel>)`, şarkı `pipe(style, lyrics, cot="full", seed)`
  (m-a-p/YuE2-3B README). Sözsüz kip resmî instrumental betiğinin `run` akışıdır (skills/yue2-music/instrumental):
  YuE2 notayı yazar → Vocal notaları Ins'e taşınır → sözsüz istekle yeniden üretilir. Betik her adımda boru hattını
  yeniden açar; burada yüklü olan boru hattı verilir (kapatılmaz), sonuç dosyası aynıdır.
- MiniMax Music 3: diffusers `ModularPipeline.from_pretrained(<yerel>)` + `load_components(bfloat16)`,
  `pipe(prompt, lyrics, audio_duration, generator, output="audios")` (MiniMaxAI/MiniMax-Music3 README).
- HeartMuLa: heartlib README + examples/run_music_generation.py — `HeartMuLaGenPipeline.from_pretrained(<ckpt>,
  device, dtype={mula: bf16, codec: fp32}, version="3B")`, `pipe({"lyrics", "tags"}, max_audio_length_ms, save_path,
  topk=50, temperature=1.0, cfg_scale=3.0)` (örnek betiğin varsayılanı; README metni 1.5 der). Etiketler virgülle
  ayrılır, küçük harf. Tohum parametresi yok: torch tohumu çağrıdan önce verilir.
"""

import json
import os
import shutil
import sys
import tempfile
import traceback
from pathlib import Path

ENGINE, ROOT = sys.argv[1], Path(sys.argv[2])
REPLY = os.fdopen(os.dup(1), "w", buffering=1)
os.dup2(2, 1)
sys.stdout = sys.stderr
os.environ.setdefault("HF_HUB_OFFLINE", "1")

INSTRUMENTAL = "/opt/yue/skills/yue2-music/instrumental/scripts"
NO_VOCALS = "instrumental, no vocals, no singing, no spoken words"


def style_of(job: dict, instrumental: bool) -> str:
    """İstemin sonuna tempo ve ton eklenir (üç motorun belgesi de tarz metninde «96 BPM», «G major» yazar)."""
    parts = [job["prompt"].strip().rstrip(".,")]
    if job.get("key"):
        parts.append(job["key"])
    if job.get("bpm"):
        parts.append(f"{job['bpm']} BPM")
    if instrumental:
        parts.append(NO_VOCALS)
    return ", ".join(parts)


# ------------------------------------------------------------------ ACE-Step 1.5
SMALL = {".py", ".json", ".txt", ".jinja", ".md"}


def checkpoint_farm(src: Path, dst: Path) -> Path:
    """Salt okunur ağırlık klasörünün yazılabilir gölgesi: küçük dosyalar kopya, ağırlıklar sembolik bağlantı."""
    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src)
        if ".cache" in rel.parts or p.is_dir():
            continue
        t = dst / rel
        t.parent.mkdir(parents=True, exist_ok=True)
        if p.suffix in SMALL:
            shutil.copy2(p, t)
        else:
            t.symlink_to(p)
    return dst


class AceStep15:
    DIT, LM = "acestep-v15-xl-sft", "acestep-5Hz-lm-4B"
    STEPS = 50                                   # SFT: 50 adım + CFG (kart); turbo'nun 8 adımı/shift=3 burada değil

    def __init__(self):
        farm = checkpoint_farm(ROOT, Path(tempfile.mkdtemp(prefix="ace-")) / "checkpoints")
        os.environ["ACESTEP_CHECKPOINTS_DIR"] = str(farm)
        from acestep.handler import AceStepHandler
        from acestep.llm_inference import LLMHandler
        self.dit, self.llm = AceStepHandler(), LLMHandler()
        _ok(self.dit.initialize_service(project_root=str(farm.parent), config_path=self.DIT, device="cuda"))
        _ok(self.llm.initialize(checkpoint_dir=str(farm), lm_model_path=self.LM, backend="pt", device="cuda"))

    def run(self, job: dict) -> dict:
        import soundfile as sf
        from acestep.inference import GenerationConfig, GenerationParams, generate_music
        song = job["kind"] == "song"
        caption = job["prompt"].strip().rstrip(".,") + ("" if song else ", " + NO_VOCALS)
        p = GenerationParams(task_type="text2music", caption=caption[:512],
                             lyrics=job["lyrics"] if song else "[Instrumental]", instrumental=not song,
                             vocal_language="tr" if song else "unknown",
                             duration=min(600.0, max(10.0, float(job["seconds"]))),
                             inference_steps=self.STEPS, seed=int(job["seed"]))
        c = GenerationConfig(batch_size=1, use_random_seed=False, seeds=[int(job["seed"])], audio_format="wav")
        res = generate_music(self.dit, self.llm, p, c, save_dir=job["tmp"])
        if not res.success:
            raise RuntimeError(res.error or res.status_message)
        a = res.audios[0]
        sr = int(a["sample_rate"])
        sf.write(job["out"], a["tensor"].T.float().numpy(), sr)
        return {"seconds": a["tensor"].shape[-1] / sr, "sample_rate": sr, "truncated": False}


def _ok(res):
    """initialize/initialize_service (durum, başarı) döndürür; başarısızsa hata."""
    if isinstance(res, tuple) and len(res) == 2 and res[1] is False:
        raise RuntimeError(str(res[0])[:400])


# ------------------------------------------------------------------ HeartMuLa
class HeartMuLa:
    def __init__(self):
        import torch
        from heartlib import HeartMuLaGenPipeline
        cuda = torch.device("cuda")
        self.pipe = HeartMuLaGenPipeline.from_pretrained(str(ROOT), device={"mula": cuda, "codec": cuda},
                                                         dtype={"mula": torch.bfloat16, "codec": torch.float32},
                                                         version="3B", lazy_load=False)

    def run(self, job: dict) -> dict:
        import soundfile as sf
        import torch
        seed = int(job["seed"])
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        tags = ",".join(t.strip().lower() for t in style_of(job, False).split(",") if t.strip())
        with torch.no_grad():
            self.pipe({"lyrics": job["lyrics"], "tags": tags}, max_audio_length_ms=int(float(job["seconds"]) * 1000),
                      save_path=job["out"], topk=50, temperature=1.0, cfg_scale=3.0)
        info = sf.info(job["out"])
        return {"seconds": info.duration, "sample_rate": info.samplerate, "truncated": False}


# ------------------------------------------------------------------ Stable Audio 3
def _local_text_encoder(node, folder: Path):
    """model_config.json'daki t5gemma kodlayıcısını klasördeki kopyaya yönlendirir (hub'a gidilmez)."""
    if isinstance(node, dict):
        name = str(node.get("model_name", "")) + str(node.get("subfolder", "")) + str(node.get("repo_id", ""))
        if "t5gemma" in name and (folder / "config.json").is_file():
            node["model_path"] = str(folder)
            node.pop("repo_id", None)
            node.pop("subfolder", None)
        for v in node.values():
            _local_text_encoder(v, folder)
    elif isinstance(node, list):
        for v in node:
            _local_text_encoder(v, folder)


class StableAudio3:
    def __init__(self):
        from stable_audio_3.loading_utils import load_diffusion_cond
        from stable_audio_3.model import StableAudioModel
        cfg = json.loads((ROOT / "model_config.json").read_text())
        _local_text_encoder(cfg, ROOT / "t5gemma-b-b-ul2")
        model = load_diffusion_cond(cfg, str(ROOT / "model.safetensors"), device="cuda", model_half=True)
        model.use_lora, model.lora_names = False, []
        self.m = StableAudioModel(model, cfg, "cuda", True)

    def run(self, job: dict) -> dict:
        import soundfile as sf
        audio = self.m.generate(prompt=style_of(job, True), duration=float(job["seconds"]), seed=int(job["seed"]))
        sr = int(self.m.model.sample_rate)
        sf.write(job["out"], audio[0].T.float().cpu().numpy(), sr)
        return {"seconds": audio.shape[-1] / sr, "sample_rate": sr, "truncated": False}


# ------------------------------------------------------------------ YuE2
class _Kept:
    """Betiğin `with open_pipeline(args) as pipe` kalıbına yüklü boru hattını verir; çıkışta kapatmaz."""

    def __init__(self, pipe):
        self.pipe = pipe

    def __enter__(self):
        return self.pipe

    def __exit__(self, *exc):
        return False


class YuE2:
    def __init__(self):
        from yue2 import YuE2Pipeline
        self.pipe = YuE2Pipeline.from_pretrained(str(ROOT / "YuE2-3B"), vae=str(ROOT / "YuE2-Vae"), device="cuda",
                                                 local_files_only=True, progress=False)

    def run(self, job: dict) -> dict:
        import soundfile as sf
        if job["kind"] == "song":
            song = self.pipe(style=style_of(job, False), lyrics=job["lyrics"], cot="full", seed=int(job["seed"]))
            sf.write(job["out"], song.audio, song.sample_rate)
            return {"seconds": len(song.audio) / song.sample_rate, "sample_rate": song.sample_rate,
                    "truncated": any(song.truncated.values())}
        return self._instrumental(job)

    def _instrumental(self, job: dict) -> dict:
        import soundfile as sf
        if INSTRUMENTAL not in sys.path:
            sys.path.insert(0, INSTRUMENTAL)
        import instrumental as ins
        ins.open_pipeline = lambda _args: _Kept(self.pipe)
        out = Path(job["tmp"]) / "yue2"
        sys.argv = ["instrumental.py", "run", "--style", style_of(job, True), "--output", str(out),
                    "--models-root", str(ROOT), "--offline", "--seed", str(int(job["seed"])), "--id", "film"]
        rc = ins.main()
        if rc == 2:
            raise RuntimeError("sözsüz üretim başarısız (instrumental betiği çıkış 2)")
        audio, sr = sf.read(out / "generation" / "native" / "audio.flac")
        sf.write(job["out"], audio, sr)
        return {"seconds": len(audio) / sr, "sample_rate": sr, "truncated": rc == 1}


# ------------------------------------------------------------------ MiniMax Music 3
class MiniMaxMusic3:
    def __init__(self):
        import torch
        from diffusers import ModularPipeline
        self.pipe = ModularPipeline.from_pretrained(str(ROOT))
        self.pipe.load_components(dtype=torch.bfloat16)
        self.pipe.to("cuda")

    def run(self, job: dict) -> dict:
        import soundfile as sf
        import torch
        audio = self.pipe(prompt=style_of(job, False), lyrics=job["lyrics"], audio_duration=float(job["seconds"]),
                          generator=torch.Generator("cuda").manual_seed(int(job["seed"])), output="audios")[0]
        sr = int(self.pipe.sampling_rate)
        sf.write(job["out"], audio.T.float().cpu().numpy(), sr)
        return {"seconds": audio.shape[-1] / sr, "sample_rate": sr, "truncated": False}


KINDS = {"stable-audio-3": StableAudio3, "acestep15": AceStep15, "yue2": YuE2, "minimax-music3": MiniMaxMusic3,
         "heartmula": HeartMuLa}


def main():
    engine = None
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            job = json.loads(line)
            engine = engine or KINDS[ENGINE]()
            res = {"ok": True, **engine.run(job)}
        except Exception as e:  # noqa: BLE001 - hata cevapla döner, süreç ayakta kalır
            traceback.print_exc()
            res = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:400]}"}
        REPLY.write(json.dumps(res) + "\n")


if __name__ == "__main__":
    main()
