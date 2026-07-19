#!/usr/bin/env python3
"""Prove Cursor vs system retrieval gap for erp/sigorta."""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path("/data/nanobaseai/bi/frontend/backend")
sys.path.insert(0, str(ROOT))

env: dict[str, str] = {}
for p in (ROOT / "nanobase_api.env", ROOT / ".env"):
    if not p.is_file():
        continue
    for line in p.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            k, v = line.split("=", 1)
            env.setdefault(k.strip(), v.strip().strip("\"'"))

key = env.get("BI_EMBED_API_KEY") or env.get("OPENAI_API_KEY") or "nanobase-local"
os.environ.setdefault("BI_EMBED_API_KEY", key)
os.environ.setdefault("BI_EMBED_URL", env.get("BI_EMBED_URL", "http://127.0.0.1:8083/v1/embeddings"))
os.environ.setdefault("OPENAI_API_KEY", env.get("OPENAI_API_KEY", key))


def embed(text: str) -> list[float]:
    req = urllib.request.Request(
        "http://127.0.0.1:8083/v1/embeddings",
        data=json.dumps({"texts": [text]}).encode(),
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    emb = json.loads(urllib.request.urlopen(req, timeout=60).read())
    vec = (emb.get("embeddings") or emb.get("data") or [None])[0]
    if isinstance(vec, dict):
        vec = vec.get("embedding")
    return list(vec)


def search(coll: str, vec: list[float], filt=None):
    body = {"vector": vec, "limit": 5, "with_payload": True}
    if filt:
        body["filter"] = filt
    req = urllib.request.Request(
        f"http://127.0.0.1:6333/collections/{coll}/points/search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.loads(urllib.request.urlopen(req, timeout=30).read()).get("result") or []


def scroll_payload_stats(coll: str, limit: int = 30) -> dict:
    req = urllib.request.Request(
        f"http://127.0.0.1:6333/collections/{coll}/points/scroll",
        data=json.dumps({"limit": limit, "with_payload": True, "with_vector": False}).encode(),
        headers={"Content-Type": "application/json"},
    )
    pts = (json.loads(urllib.request.urlopen(req).read()).get("result") or {}).get("points") or []
    keys: set[str] = set()
    status_vals: set[str] = set()
    ds_vals: set[str] = set()
    has_status = 0
    for p in pts:
        pl = p.get("payload") or {}
        keys |= set(pl.keys())
        if "status" in pl:
            has_status += 1
            status_vals.add(str(pl.get("status")))
        if pl.get("datasource_id") is not None:
            ds_vals.add(str(pl.get("datasource_id")))
    return {
        "sampled": len(pts),
        "has_status_field_count": has_status,
        "status_vals": sorted(status_vals),
        "datasource_ids": sorted(ds_vals),
        "keys": sorted(keys),
    }


def chat_phases(sid: str, question: str) -> dict:
    p = subprocess.run(
        [
            "curl",
            "-sS",
            "-N",
            "-X",
            "POST",
            "http://127.0.0.1:8790/api/v1/bi/chat/stream",
            "-H",
            "Content-Type: application/json",
            "-d",
            json.dumps({"message": question, "session_id": f"cmp3-{sid}", "db_name": sid}),
            "--max-time",
            "90",
        ],
        capture_output=True,
        text=True,
    )
    raw = p.stdout
    phases = []
    for line in raw.splitlines():
        if "schema_retrieval" in line or "generating_sql" in line or "verified_cache" in line:
            phases.append(line[:240])
    m = re.search(r'"sql":"((?:\\.|[^"\\])*)"', raw)
    return {
        "phases": phases[:10],
        "sql": m.group(1)[:180] if m else None,
        "has_done": "event: done" in raw,
        "has_error": "event: error" in raw,
        "len": len(raw),
    }


async def awel(sid: str, question: str) -> dict:
    from nanobase_awel.retrieval.authorized import (
        build_qdrant_filter,
        retrieve_authorized_schema,
    )

    filt = build_qdrant_filter(tenant_id="default", datasource_id=sid)
    r = await retrieve_authorized_schema(question, tenant_id="default", datasource_id=sid)
    return {
        "filter": filt,
        "ok": r.get("ok"),
        "hits": len(r.get("hits") or []),
        "tables": (r.get("tables") or [])[:8],
        "error": r.get("error"),
    }


def main() -> None:
    out: dict = {}
    for sid, q in (("erp", "Kaç müşteri var?"), ("sigorta", "Kaç acente var?")):
        coll = f"bi_schema_{sid}"
        stats = scroll_payload_stats(coll)
        vec = embed(q)
        h_none = search(coll, vec, None)
        h_ds = search(
            coll, vec, {"must": [{"key": "datasource_id", "match": {"value": sid}}]}
        )
        h_status = search(
            coll,
            vec,
            {
                "must": [
                    {"key": "datasource_id", "match": {"value": sid}},
                    {"key": "status", "match": {"value": "ACTIVE"}},
                ]
            },
        )
        aw = asyncio.run(awel(sid, q))
        chat = chat_phases(sid, q)
        out[sid] = {
            "question": q,
            "payload_stats": {
                "sampled": stats["sampled"],
                "points_with_status": stats["has_status_field_count"],
                "status_vals": stats["status_vals"],
                "datasource_ids": stats["datasource_ids"],
                "has_status_key_in_union": "status" in stats["keys"],
            },
            "cursor_direct_qdrant": {
                "hits_unfiltered": len(h_none),
                "hits_datasource_only": len(h_ds),
                "hits_datasource_plus_status_ACTIVE": len(h_status),
                "top_ds_only": [
                    {
                        "table": (h.get("payload") or {}).get("table"),
                        "kind": (h.get("payload") or {}).get("kind"),
                        "score": h.get("score"),
                        "status": (h.get("payload") or {}).get("status"),
                    }
                    for h in h_ds[:3]
                ],
            },
            "system_awel_retrieve": aw,
            "system_chat_stream": chat,
        }
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
