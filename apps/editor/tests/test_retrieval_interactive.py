"""Kitaba sor'un metin araması hiçbir modeli beklemez (2026-10-02): sorgu embedding'i etkileşimli başlıkla gider
(gateway GPU kopyası kapalıysa CPU eşine verir), yeniden sıralayıcı hazır değilse adım atlanır ve adaylar embedding
benzerliği sırasıyla döner. Etkileşimli olmayan aramada eski davranış: hata yükselir."""
import asyncio
import types

import pytest

from editor import llm, outputs, retrieval


class _Q:
    async def collection_exists(self, _n):
        return True

    async def query_points(self, *_a, **_k):
        pts = [types.SimpleNamespace(score=0.9 - i / 10, payload={"page_no": i + 1, "kind": "text", "ref": f"r{i}",
                                                                 "text": f"parça {i}"}) for i in range(3)]
        return types.SimpleNamespace(points=pts)


@pytest.fixture()
def env(monkeypatch):
    sent = {}
    monkeypatch.setattr(outputs, "current", lambda gid, kind: {"available": True, "artifact": {"build_key": "k"}})
    monkeypatch.setattr(retrieval, "qdrant", lambda: _Q())

    class _L:
        def __init__(self, *_a):
            pass

        async def embed(self, texts, instruction=None, headers=None):
            sent["embed"] = headers
            return [[0.0] * retrieval.DIM]

        async def rerank(self, q, docs, instruction, headers=None):
            sent["rerank"] = headers
            raise llm.ModelError('{"error":{"error":"model_not_ready","alias":"book-reranker"}}')

    monkeypatch.setattr(retrieval, "Llm", _L)
    return sent


def test_interactive_search_skips_unready_reranker_and_keeps_similarity_order(env):
    out = asyncio.run(retrieval.search_book_evidence("g", "soru", 2, interactive=True))
    assert [o["page"] for o in out] == [1, 2] and out[0]["rerank_score"] is None
    assert env["embed"] == llm.INTERACTIVE and env["rerank"] == llm.NO_WAIT


def test_batch_search_still_raises_when_reranker_fails(env):
    with pytest.raises(llm.ModelError):
        asyncio.run(retrieval.search_book_evidence("g", "soru", 2))
    assert env["embed"] is None and env["rerank"] is None
