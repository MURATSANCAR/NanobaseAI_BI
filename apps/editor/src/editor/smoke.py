"""Load every model through the gateway and make one real call to each.

  python -m editor.smoke [alias ...]      # default: all six, one after another

Each check prints cold-start + call time and a one-line result. Uses the
first rendered page in storage as the test image.
"""

from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from . import schemas
from .config import settings
from .llm import Llm, client, image_part

ORDER = ["book-embedding", "book-reranker", "book-vision-fast", "book-director",
         "book-vision-deep"]


def _page_png() -> bytes:
    pages = sorted(settings().storage.glob("books/*/pages/p0005.png"))
    return pages[0].read_bytes()


async def check(alias: str) -> str:
    llm = Llm(None)
    if alias == "book-embedding":
        v = await llm.embed(["Defne tableti arıyor.", "Max bir robottur."])
        return f"{len(v)} vektör, boyut {len(v[0])}"
    if alias == "book-reranker":
        s = await llm.rerank("Defne tableti nerede arıyor?",
                             ["Defne tabletin saklı olduğu yeri düşünmekten uyuyamamıştı.",
                              "Toprağın nem oranı yüzde 65."], instruction="Does the passage answer the question?")
        return f"skorlar ilgili={s[0]:.3f} ilgisiz={s[1]:.3f} ({'doğru sıra' if s[0] > s[1] else 'YANLIŞ SIRA'})"
    if alias in ("book-vision-fast", "book-vision-deep"):
        schema = schemas.obj({"characters": schemas.arr(schemas.STR), "scene": schemas.STR})
        out, _ = await llm.chat(alias, [{"role": "user", "content": [
            image_part(_page_png()),
            {"type": "text", "text": "Bu kitap sayfasında hangi figürler var ve sahne ne? JSON ver."}]}],
            schema=schema, max_tokens=8000 if alias.endswith("deep") else 1024)
        return f"figürler={out['characters']} sahne={out['scene'][:80]}"
    if alias == "book-director":
        r = await client().post("/v1/chat/completions", json={
            "model": alias, "max_tokens": 512,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "user", "content": "Kitaptaki işi başlat: dosya ornek.pdf"}],
            "tools": [{"type": "function", "function": {
                "name": "start_analysis_job", "description": "Kitap analiz işini başlatır",
                "parameters": {"type": "object", "properties": {"file_name": {"type": "string"}},
                               "required": ["file_name"]}}}]})
        msg = r.json()["choices"][0]["message"]
        calls = msg.get("tool_calls") or []
        return (f"araç çağrısı: {calls[0]['function']['name']}({calls[0]['function']['arguments']})"
                if calls else f"ARAÇ ÇAĞRISI YOK: {(msg.get('content') or '')[:120]}")
    raise ValueError(alias)


async def main(aliases: list[str]) -> int:
    bad = 0
    for a in aliases:
        t0 = time.time()
        try:
            res = await check(a)
            print(f"OK   {a:18s} {time.time() - t0:6.0f} sn  {res}", flush=True)
        except Exception as e:  # noqa: BLE001
            bad += 1
            print(f"FAIL {a:18s} {time.time() - t0:6.0f} sn  {str(e)[:600]}", flush=True)
    return bad


if __name__ == "__main__":
    sys.exit(asyncio.run(main(sys.argv[1:] or ORDER)))
