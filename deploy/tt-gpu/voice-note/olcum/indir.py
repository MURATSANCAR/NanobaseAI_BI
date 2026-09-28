import os, time
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
from huggingface_hub import snapshot_download, hf_hub_download

t0 = time.time()
for f in ("data/tr_tr/test.tsv", "data/tr_tr/audio/test.tar.gz"):
    p = hf_hub_download("google/fleurs", f, repo_type="dataset", local_dir="/w/fleurs")
    print("ok", p, round(time.time() - t0), flush=True)

PAT = ["*.json", "*.txt", "*.safetensors", "*.jinja", "*.model"]
for repo in ("openai/whisper-large-v3-turbo", "turkmedstt/whisper-large-v3-turkish-general",
             "Qwen/Qwen3-ASR-1.7B-hf", "openai/whisper-large-v3"):
    d = "/w/models/" + repo.replace("/", "__")
    pat = PAT
    if repo.startswith("openai/whisper-large-v3") and repo.endswith("v3"):
        pat = ["*.json", "*.txt", "model.safetensors"]
    snapshot_download(repo, local_dir=d, allow_patterns=pat, max_workers=8)
    print("ok", repo, round(time.time() - t0), flush=True)
print("BITTI", flush=True)
