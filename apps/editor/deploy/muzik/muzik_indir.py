"""Kitaptan çizgi film — müzik modelleri: /data/editor/models/book-music altına indirir (2026-10-07).

indir.py ile aynı desen: konteyner salt okunur, günlük kapalı, --restart no; HF_HOME/TMPDIR/HOME /data altında.
Başlatma: _indirme/muzik_baslat.sh (anahtar dosyası varsa kaba salt okunur bağlar). Durum: _indirme/muzik-durum.json
(model başına repo, sabit revizyon, bayt). Yarım kalan kaldığı yerden sürer; biten atlanır, yeniden koşmak güvenlidir.

Kullanıcı kararı 2026-10-07: kurumun bütün motorlar için lisansı var. Sıra = öncelik:
  stable-audio-3/  Stable Audio 3.0 Medium — film müziği ANA. HF'de KAPILI: kullanıcı HF'de şartları kabul edip okuma
                   anahtarını /data/editor/secrets/hf-token'a koyunca indirilir; yoksa «anahtar bekleniyor».
  yue2/            YuE2-3B + YuE2-Vae (yalnız çıkarım dosyaları) — tema şarkısı ANA + sözsüz yedek
  minimax-music3/  MiniMax Music 3, diffusers modüler düzeni (qwen_7B/ ve *.pth SGLang içindir, alınmaz) — şarkı yedeği
  acestep15/       ACE-Step 1.5: ana depo (VAE, metin kodlayıcı, turbo, LM 1.7B — kod bunları «ana bileşen» sayar,
                   yoksa kendisi indirmeye kalkar) + acestep-v15-xl-sft (kartı: «Highest Quality», 4B DiT, CFG) +
                   acestep-5Hz-lm-4B (kartı: «Full quality (XL + 4B LM)») — film müziği yedeği (ticari serbest, MIT)
  heartmula/       HeartMuLa-oss-3B-happy-new-year + HeartCodec-oss-20260123 + HeartMuLaGen — şarkı yedeği (Apache-2.0)
HF depolarında LICENSE dosyası olmayanlara kod deposunun LICENSE'ı sabit commit'ten yazılır.
"""
import json, os, time, urllib.request
from huggingface_hub import snapshot_download

ROOT = "/data/editor/models"
DST = f"{ROOT}/book-music"
STATE = f"{ROOT}/_indirme/muzik-durum.json"
TOKEN_FILE = "/run/hf-token"            # muzik_baslat.sh /data/editor/secrets/hf-token'ı buraya salt okunur bağlar
LIC = ["LICENSE*", "README.md", "THIRD_PARTY_NOTICES.md", "NOTICE", "licenses/*"]
SA3 = ("stable-audio-3", "stabilityai/stable-audio-3-medium", "d4d3579395a8ac0df4ab13b5b1d7138ce7290f81", None)
PLAN = [  # (klasör, repo, sabit revizyon, allow)
    ("yue2/YuE2-Vae", "m-a-p/YuE2-Vae", "152733a19ad43aa67e367f9b5503ef8075bb5126",
     ["config.json", "weights_manifest.json", "model.safetensors", "modeling_vae.py", *LIC]),
    ("yue2/YuE2-3B", "m-a-p/YuE2-3B", "8f24312f187763b9854adeec87e437e2b03bbff1",
     ["config.json", "generation_config.json", "yue2_generation_config.json", "weights_manifest.json",
      "model.safetensors", "qwen.tiktoken", "modeling_yue2.py", "examples/*", "yue2_infer-0.1.5-py3-none-any.whl",
      *LIC]),
    ("minimax-music3", "MiniMaxAI/MiniMax-Music3", "fbdf52fbaaca799592917417eb05f1899f1255ec",
     ["config.json", "modular_model_index.json", "condition_encoder/*", "language_model/*", "rvq_depth_decoder/*",
      "scheduler/*", "tokenizer/*", "transformer/*", "vocoder/*", "scripts/*", *LIC]),
    ("acestep15", "ACE-Step/Ace-Step1.5", "19671f406d603126926c1b7e2adc169acbcade22", None),
    ("acestep15/acestep-v15-xl-sft", "ACE-Step/acestep-v15-xl-sft", "d06de46b4622f781cf07f4a013a67d591ca52819", None),
    ("acestep15/acestep-5Hz-lm-4B", "ACE-Step/acestep-5Hz-lm-4B", "0a3ec94b557aea7d508da38b31cfe7341f6ff737", None),
    ("heartmula", "HeartMuLa/HeartMuLaGen", "9906b2bcd4598772a32cad4aec0760170fe0d177",
     ["gen_config.json", "tokenizer.json"]),
    ("heartmula/HeartCodec-oss", "HeartMuLa/HeartCodec-oss-20260123", "f889dab0532cfa4bf459f2a3367eb6d346b8eeda", None),
    ("heartmula/HeartMuLa-oss-3B", "HeartMuLa/HeartMuLa-oss-3B-happy-new-year",
     "41f6fc68490e11dc43fdabaa6b5767946408c903", None),
]
LICENSES = [  # (hedef, kaynak) — HF deposunda LICENSE yoksa kod deposunun sabit commit'inden
    ("heartmula/LICENSE",
     "https://raw.githubusercontent.com/HeartMuLa/heartlib/96ef96e0ee2346e8a3ca3300aabfdff85e0231be/LICENSE"),
    ("acestep15/LICENSE",
     "https://raw.githubusercontent.com/ace-step/ACE-Step-1.5/ca1e85fe9430179831e6bc6be790c332190a3866/LICENSE"),
]


def log(m):
    print(time.strftime("%F %T"), m, flush=True)


def save(done):
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(done, f, indent=1, ensure_ascii=False)
    os.replace(tmp, STATE)


def size_of(path, top_only=False):
    if top_only:
        return sum(os.path.getsize(os.path.join(path, f)) for f in os.listdir(path)
                   if os.path.isfile(os.path.join(path, f)))
    return sum(os.path.getsize(os.path.join(r, f)) for r, _, fs in os.walk(path)
               if "/.cache" not in r for f in fs)


def fetch(done, d, repo, rev, allow, token=None):
    for attempt in range(1, 200):
        try:
            log(f"BASLA {repo} rev={rev} deneme={attempt}")
            snapshot_download(repo, revision=rev, local_dir=f"{DST}/{d}", allow_patterns=allow, max_workers=8,
                              token=token)
            # alt klasörü olan kökte (acestep15, heartmula) yalnız bu deponun dosyaları sayılır
            size = size_of(f"{DST}/{d}", top_only=allow is not None or d in ("acestep15",))
            done[d] = {"ok": True, "repo": repo, "revision": rev, "bytes": size, "bitis": time.strftime("%F %T")}
            save(done)
            log(f"BITTI {repo} {size/1e9:.2f} GB")
            return
        except Exception as e:  # ağ kopması vb.: bekle, kaldığı yerden sür
            if token and any(x in repr(e) for x in ("401", "403", "GatedRepo")):
                raise                                # anahtar yetkisiz: denemeyi sürdürmenin anlamı yok
            log(f"HATA {repo}: {e!r}")
            time.sleep(min(30 * attempt, 600))


def main():
    done = json.load(open(STATE)) if os.path.exists(STATE) else {}
    for k in ("yue2", "minimax-music3"):           # önceki planın «indirilmedi» kayıtları
        done.pop(k, None)
    save(done)
    d, repo, rev, allow = SA3
    if not done.get(d, {}).get("ok"):
        token = open(TOKEN_FILE).read().strip() if os.path.isfile(TOKEN_FILE) else ""
        if token:
            try:
                fetch(done, d, repo, rev, allow, token=token)
            except Exception as e:
                done[d] = {"ok": False, "repo": repo, "revision": rev, "durum": f"anahtar reddedildi: {e!r}"[:300]}
                save(done)
        else:
            done[d] = {"ok": False, "repo": repo, "revision": rev, "beklenen_bayt": 10445316199,
                       "durum": "anahtar bekleniyor: HF'de şartları kabul edip okuma anahtarını "
                                "/data/editor/secrets/hf-token'a koyun, sonra _indirme/muzik_baslat.sh"}
            save(done)
    for d, repo, rev, allow in PLAN:
        if not done.get(d, {}).get("ok"):
            fetch(done, d, repo, rev, allow)
    for rel, url in LICENSES:
        if done.get(rel, {}).get("ok"):
            continue
        urllib.request.urlretrieve(url, f"{DST}/{rel}.part")
        os.replace(f"{DST}/{rel}.part", f"{DST}/{rel}")
        done[rel] = {"ok": True, "url": url, "bytes": os.path.getsize(f"{DST}/{rel}")}
        save(done)
    log("HEPSI BITTI")


if __name__ == "__main__":
    main()
