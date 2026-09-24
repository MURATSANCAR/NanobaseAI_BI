"""book-upscale: Real-ESRGAN x4plus (BSD-3) ile resim büyütme servisi; gateway takma adı olarak istekte açılır.

Gateway komutu vLLM biçimindedir (`/model --served-model-name … --gpu-memory-utilization …`); burada yalnız
model klasörü kullanılır, kalanı yok sayılır. Resim karo karo (512 px, 16 px örtüşme) 4× büyütülür, sonra
istenen ölçüye Lanczos ile indirilir: bellek resim boyundan bağımsız kalır.

    GET  /health
    POST /v1/images/upscale  {model, image: base64 PNG, width, height} → {image: base64 PNG, scale, seconds}
"""

import argparse
import base64
import io
import time

import numpy as np
import torch
import uvicorn
from fastapi import FastAPI, HTTPException
from PIL import Image
from pydantic import BaseModel
from spandrel import ModelLoader

ap = argparse.ArgumentParser()
ap.add_argument("model_dir")
ap.add_argument("--served-model-name", nargs="*")
ap.add_argument("--gpu-memory-utilization")
ap.add_argument("--weights", default="RealESRGAN_x4plus.pth")
ap.add_argument("--tile", type=int, default=512)
ap.add_argument("--port", type=int, default=8000)
args, _ = ap.parse_known_args()

model = ModelLoader().load_from_file(f"{args.model_dir}/{args.weights}").cuda().eval().half()
SCALE = model.scale
TILE, PAD = args.tile, 16
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/health")
def health() -> dict:
    return {"ok": True, "scale": SCALE}


class Req(BaseModel):
    model: str = "book-upscale"
    image: str
    width: int
    height: int


@torch.inference_mode()
def _upscale(img: Image.Image) -> Image.Image:
    x = torch.from_numpy(np.asarray(img, dtype=np.float32) / 255.0).permute(2, 0, 1)[None].cuda().half()
    _, _, H, W = x.shape
    out = torch.zeros((1, 3, H * SCALE, W * SCALE), dtype=torch.float16, device="cuda")
    for y in range(0, H, TILE):
        for x0 in range(0, W, TILE):
            y1, x1 = min(y + TILE, H), min(x0 + TILE, W)
            ya, xa = max(y - PAD, 0), max(x0 - PAD, 0)
            yb, xb = min(y1 + PAD, H), min(x1 + PAD, W)
            t = model(x[:, :, ya:yb, xa:xb])
            oy, ox = (y - ya) * SCALE, (x0 - xa) * SCALE
            out[:, :, y * SCALE:y1 * SCALE, x0 * SCALE:x1 * SCALE] = \
                t[:, :, oy:oy + (y1 - y) * SCALE, ox:ox + (x1 - x0) * SCALE]
    arr = (out[0].clamp(0, 1).permute(1, 2, 0).float().cpu().numpy() * 255.0).round().astype("uint8")
    return Image.fromarray(arr)


@app.post("/v1/images/upscale")
def upscale(r: Req) -> dict:
    t = time.time()
    try:
        img = Image.open(io.BytesIO(base64.b64decode(r.image))).convert("RGB")
    except Exception:
        raise HTTPException(400, "görsel okunamadı") from None
    if not (16 <= r.width <= 12000 and 16 <= r.height <= 12000):
        raise HTTPException(400, "hedef ölçü geçersiz")
    big = _upscale(img) if (r.width > img.width or r.height > img.height) else img
    out = big.resize((r.width, r.height), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    out.save(buf, "PNG", compress_level=3)
    torch.cuda.empty_cache()
    return {"image": base64.b64encode(buf.getvalue()).decode(), "scale": SCALE, "seconds": round(time.time() - t, 2)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")
