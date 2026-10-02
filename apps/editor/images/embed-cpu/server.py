"""book-embedding-cpu: Qwen3-Embedding-8B'nin CPU kopyası; GPU kopyası kapalıyken küçük istekleri (Kitaba sor'un
sorgu embedding'i) gateway buraya verir (models.yaml `cpu_twin`).

Gateway komutu vLLM biçimindedir (`/model --served-model-name … --gpu-memory-utilization …`); burada yalnız model
klasörü ve ad kullanılır, kalanı yok sayılır. Gömme vLLM'deki Qwen3-Embedding ile aynıdır: sol dolgu, son token,
L2 normalize. Ölçüldü 2026-10-02 (Xeon 6740P, 32 çekirdek, bf16): yükleme 1,3 sn, tek soru 0,15 sn, dizindeki GPU
vektörleriyle kosinüs 0,9999.

    GET  /health
    POST /v1/embeddings  {model, input: str | [str]} → OpenAI biçimi {data: [{index, embedding}], usage}
"""

import argparse
import asyncio
import os
import time

import torch
import torch.nn.functional as F
import uvicorn
from fastapi import FastAPI, HTTPException
from transformers import AutoModel, AutoTokenizer

ap = argparse.ArgumentParser()
ap.add_argument("model_dir")
ap.add_argument("--served-model-name", nargs="*")
ap.add_argument("--max-model-len", type=int, default=8192)
ap.add_argument("--port", type=int, default=8000)
args, _ = ap.parse_known_args()

torch.set_num_threads(int(os.environ.get("EMBED_CPU_THREADS", "32")))
tok = AutoTokenizer.from_pretrained(args.model_dir, padding_side="left")
model = AutoModel.from_pretrained(args.model_dir, dtype=torch.bfloat16).eval()
NAMES = set(args.served_model_name or [])
LOCK = asyncio.Lock()          # tek ileri geçiş; iş parçacıkları zaten bütün çekirdekleri kullanıyor
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health() -> dict:
    return {"ok": True}


def _embed(texts: list[str]) -> tuple[list[list[float]], int]:
    batch = tok(texts, padding=True, truncation=True, max_length=args.max_model_len, return_tensors="pt")
    with torch.inference_mode():
        last = model(**batch).last_hidden_state[:, -1]
    return F.normalize(last.float(), p=2, dim=1).tolist(), int(batch["attention_mask"].sum())


@app.post("/v1/embeddings")
async def embeddings(body: dict) -> dict:
    if NAMES and body.get("model") not in NAMES:
        raise HTTPException(404, f"unknown model {body.get('model')}")
    inputs = body.get("input")
    texts = [inputs] if isinstance(inputs, str) else inputs
    if not isinstance(texts, list) or not texts or not all(isinstance(t, str) for t in texts):
        raise HTTPException(400, "input must be a string or a list of strings")
    t0 = time.time()
    async with LOCK:
        vecs, tokens = await asyncio.to_thread(_embed, texts)
    return {"object": "list", "model": body.get("model"),
            "data": [{"object": "embedding", "index": i, "embedding": v} for i, v in enumerate(vecs)],
            "usage": {"prompt_tokens": tokens, "total_tokens": tokens}, "seconds": round(time.time() - t0, 3)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
