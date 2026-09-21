"""Character-identity embeddings for drawn figures.

CCIP (deepghs/ccip) is trained for one question — are these two drawings the same
character? — and ships a threshold calibrated on that question, which no general
image encoder does. It answers in milliseconds per crop, where asking a 32B vision
model the same question costs seconds and does not scale to a corpus.

Its distance is a LEARNED metric, not a cosine: smaller means "same character", and
the published threshold belongs to the model variant. The service returns features
and computes the pairwise matrix on request, so the caller can keep the features and
re-cluster without re-reading the images.
"""

from __future__ import annotations

import base64
import io
import os

import numpy as np
from fastapi import FastAPI
from imgutils.metrics import ccip_batch_differences, ccip_default_threshold, ccip_extract_feature
from PIL import Image
from pydantic import BaseModel

MODEL = os.environ.get("EDITOR_CCIP_MODEL", "ccip-caformer_b36-24")
app = FastAPI(title="editor-embed")


class Images(BaseModel):
    images: list[str]          # base64 PNG/JPEG, one figure per image


class Features(BaseModel):
    features: list[list[float]]


def _img(b64: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")


@app.get("/health")
def health() -> dict:
    return {"model": MODEL, "threshold": float(ccip_default_threshold(MODEL))}


@app.post("/features")
def features(body: Images) -> dict:
    out = [ccip_extract_feature(_img(b), model=MODEL) for b in body.images]
    return {"model": MODEL, "features": [f.astype(float).tolist() for f in out]}


@app.post("/differences")
def differences(body: Features) -> dict:
    feats = [np.array(f, dtype=np.float32) for f in body.features]
    m = ccip_batch_differences(feats, model=MODEL) if len(feats) > 1 else np.zeros((len(feats), len(feats)))
    return {"model": MODEL, "threshold": float(ccip_default_threshold(MODEL)),
            "matrix": np.asarray(m, dtype=float).tolist()}
