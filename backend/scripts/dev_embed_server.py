"""BGE-M3 embeddings over HTTP, for working on the router without the deployed stack.

The deployment runs an embedding service and this stands in for it locally, speaking the same
contract the rest of the code already uses:

    POST /v1/embeddings   {"texts": ["…"]}  →  {"embeddings": [[…1024 floats…]]}

Same model as the deployment (BAAI/bge-m3, 1024 dimensions), so a similarity measured here is the
similarity the deployment will measure. It runs on the CPU, which is slow enough to matter when
indexing ten thousand points and irrelevant for the one embedding a question needs.

    backend/.venv/bin/python backend/scripts/dev_embed_server.py     # :8083

`torch` and `sentence-transformers` are not in requirements-semantic.txt and should not be: nothing
that runs in production imports this file. Install them only to run it:

    uv pip install sentence-transformers
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

MODEL_NAME = os.environ.get("BI_EMBED_MODEL", "BAAI/bge-m3")
PORT = int(os.environ.get("BI_EMBED_PORT", "8083"))
#: BGE-M3 accepts 8192 tokens and the cost of a batch is set by its longest member, so the default
#: makes a catalog of short table descriptions as expensive as a corpus of documents. Nothing indexed
#: here is longer than a few hundred tokens.
MAX_TOKENS = int(os.environ.get("BI_EMBED_MAX_TOKENS", "512"))
_model = None


def model():
    global _model
    if _model is None:
        import torch
        from sentence_transformers import SentenceTransformer

        # Apple's GPU where there is one: indexing ten thousand points on four CPU threads takes
        # hours, and the same work on the integrated GPU takes minutes.
        device = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
        print(f"loading {MODEL_NAME} on {device} (first run downloads it) …", flush=True)
        _model = SentenceTransformer(MODEL_NAME, device=device)
        _model.max_seq_length = MAX_TOKENS
        print(f"ready: {_model.get_sentence_embedding_dimension()} dimensions, "
              f"{_model.max_seq_length} tokens", flush=True)
    return _model


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._send(400, {"error": "invalid json"})
        texts = body.get("texts") or body.get("input") or []
        if isinstance(texts, str):
            texts = [texts]
        if not texts:
            return self._send(400, {"error": "no texts"})
        vectors = model().encode(texts, normalize_embeddings=True, show_progress_bar=False,
                                 batch_size=int(os.environ.get("BI_EMBED_BATCH_SIZE", "16")))
        self._send(200, {"embeddings": [v.tolist() for v in vectors]})

    def do_GET(self) -> None:  # noqa: N802
        self._send(200, {"model": MODEL_NAME, "dimensions": model().get_sentence_embedding_dimension()})

    def _send(self, code: int, payload: dict) -> None:
        raw = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, fmt: str, *args) -> None:
        pass          # one line per embedded batch is noise while indexing ten thousand points


if __name__ == "__main__":
    model()           # load before binding, so a request never waits on a two-gigabyte download
    print(f"listening on http://127.0.0.1:{PORT}/v1/embeddings", flush=True)
    try:
        HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
