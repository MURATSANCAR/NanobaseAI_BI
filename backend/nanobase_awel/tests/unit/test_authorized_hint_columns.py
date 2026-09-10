"""Unit tests for denser column blocks in authorized retrieval hints."""

from __future__ import annotations

from nanobase_awel.retrieval import authorized as auth


def test_hint_includes_grouped_columns_from_hits(monkeypatch):
    async def _fake_embed(_text: str) -> list[float]:
        return [0.1] * 8

    class _Resp:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise RuntimeError("http")

        def json(self) -> dict:
            return self._payload

    class _Client:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url: str):
            return _Resp(200, {"result": {"status": "green"}})

        async def post(self, url: str, json=None):
            assert "search" in url
            return _Resp(
                200,
                {
                    "result": [
                        {
                            "score": 0.9,
                            "id": 1,
                            "payload": {
                                "datasource_id": "erp",
                                "kind": "table",
                                "schema": "public",
                                "table": "invoices",
                                "text": (
                                    "Table public.invoices\nColumns:\n"
                                    "- genel_toplam numeric\n- fatura_tarihi date\n"
                                ),
                            },
                        },
                        {
                            "score": 0.8,
                            "id": 2,
                            "payload": {
                                "datasource_id": "erp",
                                "kind": "column",
                                "schema": "public",
                                "table": "invoices",
                                "column": "status",
                                "text": "Column public.invoices.status",
                            },
                        },
                    ]
                },
            )

    monkeypatch.setattr(auth, "_embed", _fake_embed)
    monkeypatch.setattr(auth.httpx, "AsyncClient", _Client)

    import asyncio

    out = asyncio.run(
        auth.retrieve_authorized_schema("2026 ciro", tenant_id="default", datasource_id="erp")
    )
    hint = out["hint_extra"]
    assert "Authorized columns by table" in hint
    assert "genel_toplam" in hint
    assert "fatura_tarihi" in hint
    assert "status" in hint
    assert out["table_columns"]["public.invoices"]
