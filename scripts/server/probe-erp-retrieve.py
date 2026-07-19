#!/usr/bin/env python3
import json
import urllib.request
from pathlib import Path

env: dict[str, str] = {}
for p in (
    Path("/data/nanobaseai/bi/frontend/backend/.env"),
    Path("/data/nanobaseai/bi/frontend/backend/nanobase_api.env"),
):
    if not p.is_file():
        continue
    for line in p.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip().strip("\"'"))

k = env.get("BI_EMBED_API_KEY") or env.get("OPENAI_API_KEY") or "nanobase-local"
print("embed_key_len", len(k), "keys", [x for x in env if "EMBED" in x or x == "OPENAI_API_KEY"])

req = urllib.request.Request(
    "http://127.0.0.1:8083/v1/embeddings",
    data=json.dumps({"texts": ["Kaç müşteri var?"]}).encode(),
    headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"},
)
emb = json.loads(urllib.request.urlopen(req, timeout=60).read())
vec = (emb.get("embeddings") or emb.get("data") or [None])[0]
if isinstance(vec, dict):
    vec = vec.get("embedding")
print("dim", len(vec) if vec else None)

body = {
    "vector": vec,
    "limit": 5,
    "with_payload": True,
    "filter": {"must": [{"key": "datasource_id", "match": {"value": "erp"}}]},
}
req2 = urllib.request.Request(
    "http://127.0.0.1:6333/collections/bi_schema_erp/points/search",
    data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json"},
)
res = json.loads(urllib.request.urlopen(req2, timeout=30).read())
hits = res.get("result") or []
print("filtered_hits", len(hits))
for h in hits[:3]:
    pl = h.get("payload") or {}
    print(" ", pl.get("table"), pl.get("kind"), h.get("score"))

body.pop("filter")
req3 = urllib.request.Request(
    "http://127.0.0.1:6333/collections/bi_schema_erp/points/search",
    data=json.dumps(body).encode(),
    headers={"Content-Type": "application/json"},
)
res3 = json.loads(urllib.request.urlopen(req3, timeout=30).read())
print("unfiltered_hits", len(res3.get("result") or []))

# also call through nanobase_awel
import asyncio
import os
import sys

sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
os.environ.setdefault("BI_EMBED_API_KEY", k)


async def go():
    from nanobase_awel.retrieval.authorized import retrieve_authorized_schema

    r = await retrieve_authorized_schema(
        "Kaç müşteri var?", tenant_id="default", datasource_id="erp"
    )
    print("awel_ok", r.get("ok"), "hits", len(r.get("hits") or []), "tables", (r.get("tables") or [])[:8], "err", r.get("error"))


asyncio.run(go())
