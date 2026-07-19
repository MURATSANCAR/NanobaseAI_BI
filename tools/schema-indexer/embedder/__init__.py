from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _http_json(
    method: str,
    url: str,
    body: dict | None = None,
    headers: dict | None = None,
    timeout: int = 120,
) -> Any:
    data = None if body is None else json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={"Content-Type": "application/json", "Accept": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} -> {e.code}: {raw[:600]}") from e


def load_embed_api_key() -> str:
    preferred = ("BI_EMBED_API_KEY", "EMBEDDING_API_KEY", "CONTRACT_API_KEY")
    for k in preferred:
        if os.environ.get(k):
            return os.environ[k].strip()
    roots = [
        Path("/data/nanobaseai/bi/frontend/backend"),
        Path(__file__).resolve().parents[3] / "backend",
        Path(__file__).resolve().parents[2].parent / "backend",
    ]
    parsed: dict[str, str] = {}
    for root in roots:
        for name in (".env", "nanobase_api.env", "contract.env"):
            env = root / name
            if not env.is_file():
                continue
            try:
                text = env.read_text(encoding="utf-8")
            except PermissionError:
                continue
            for line in text.splitlines():
                if "=" not in line or line.strip().startswith("#"):
                    continue
                k, v = line.split("=", 1)
                parsed[k.strip()] = v.strip().strip('"').strip("'")
    for k in preferred:
        if parsed.get(k):
            return parsed[k]
    raise SystemExit("Missing BI_EMBED_API_KEY / CONTRACT_API_KEY")


class BgeM3Embedder:
    def __init__(self, url: str, api_key: str | None = None, batch_size: int = 8):
        self.url = url.rstrip("/")
        self.api_key = api_key or load_embed_api_key()
        self.batch_size = batch_size

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        endpoint = self.url if self.url.endswith("/embeddings") else f"{self.url}/v1/embeddings"
        # Avoid double /v1/embeddings if URL already includes it
        if self.url.endswith("/v1/embeddings"):
            endpoint = self.url
        for i in range(0, len(texts), self.batch_size):
            chunk = texts[i : i + self.batch_size]
            res = _http_json(
                "POST",
                endpoint,
                {"texts": chunk},
                headers={"Authorization": f"Bearer {self.api_key}"},
            )
            vectors = res.get("embeddings") or res.get("data")
            if isinstance(vectors, list) and vectors and isinstance(vectors[0], dict):
                vectors = [v["embedding"] for v in sorted(vectors, key=lambda x: x.get("index", 0))]
            if not isinstance(vectors, list) or len(vectors) != len(chunk):
                raise RuntimeError(f"bad embed response keys={list(res.keys())}")
            out.extend(vectors)
        return out
