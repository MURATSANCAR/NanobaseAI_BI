"""Unit tests for dynamic (non-static) full10 quality fixes."""

from __future__ import annotations

import asyncio

from nanobase_api.chat_gateway import _normalize_gateway_error
from nanobase_awel.operators.llm_operator import _compact_user_prompt
from nanobase_awel.operators.schema_reference_validator import find_unknown_columns
from nanobase_awel.operators.sql_shape_guard import (
    guard_sql_shape,
    rewrite_order_by_select_aliases,
)
from nanobase_awel.retrieval import authorized as auth
from nanobase_awel.workflows.sql_repair import is_repairable
from query_gateway.infrastructure.database.postgres_executor import _map_psycopg_error


def test_parse_missing_tables_from_error():
    msg = (
        "Yetkisiz veya bilinmeyen tablo referansı: public.musteriler. "
        "Yalnızca yetkili şema bağlamındaki tabloları kullanın."
    )
    assert "public.musteriler" in auth.parse_missing_tables_from_error(msg)


def test_table_name_matches_fold_and_exact():
    assert auth._table_name_matches("public.musteriler", "public.musteriler")
    assert auth._table_name_matches("musteriler", "public.musteriler")
    assert auth._table_name_matches("musteri", "public.musteriler")  # substring len>=5? musteri is 7
    assert not auth._table_name_matches("ab", "public.abcdef")


def test_expand_tables_from_index_merges_match(monkeypatch):
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

        async def post(self, url: str, json=None):
            assert "scroll" in url
            return _Resp(
                200,
                {
                    "result": {
                        "points": [
                            {
                                "id": 1,
                                "payload": {
                                    "datasource_id": "erp",
                                    "kind": "table",
                                    "schema": "public",
                                    "table": "musteriler",
                                    "text": (
                                        "Table public.musteriler\nColumns:\n"
                                        "- id uuid\n- unvan text\n- risk_limit numeric\n"
                                    ),
                                },
                            },
                            {
                                "id": 2,
                                "payload": {
                                    "datasource_id": "erp",
                                    "kind": "column",
                                    "schema": "public",
                                    "table": "musteriler",
                                    "column": "il_id",
                                    "data_type": "integer",
                                },
                            },
                        ]
                    }
                },
            )

    monkeypatch.setattr(auth.httpx, "AsyncClient", _Client)
    existing = {
        "ok": True,
        "tables": ["public.faturalar"],
        "table_columns": {"public.faturalar": ["id", "genel_toplam"]},
        "table_column_types": {},
        "hits": [],
        "hint_extra": "old",
    }
    out = asyncio.get_event_loop().run_until_complete(
        auth.expand_tables_from_index(
            ["public.musteriler"],
            tenant_id="default",
            datasource_id="erp",
            existing=existing,
        )
    )
    assert "public.musteriler" in out["expanded_tables"]
    assert "public.musteriler" in out["tables"]
    assert "unvan" in out["table_columns"]["public.musteriler"]
    assert out["table_column_types"]["public.musteriler"].get("il_id") == "integer"
    assert "Authorized columns by table" in out["hint_extra"]


def test_find_unknown_columns_blocks_invented():
    sql = """
    SELECT io.durum, io.id
    FROM public.alis_faturalari AS io
    """
    bad = find_unknown_columns(
        sql,
        {"public.alis_faturalari": ["id", "genel_toplam", "fatura_tarihi", "vade_tarihi"]},
    )
    assert bad
    assert bad[0][1] == "durum"


def test_find_unknown_columns_allows_known():
    sql = "SELECT f.genel_toplam FROM public.faturalar f WHERE f.id = 1"
    assert (
        find_unknown_columns(sql, {"public.faturalar": ["id", "genel_toplam"]}) == []
    )


def test_guard_blocks_unknown_column_with_table_columns():
    sql = "SELECT io.durum FROM public.alis_faturalari AS io"
    r = guard_sql_shape(
        sql,
        allowed_tables=["public.alis_faturalari"],
        table_columns={"public.alis_faturalari": ["id", "genel_toplam"]},
    )
    assert r.blocked
    assert r.code == "COLUMN_NOT_FOUND"


def test_order_by_select_alias_rewrite():
    sql = """
    SELECT miktar * alis_fiyat AS toplam_deger
    FROM public.stok_bakiyeleri
    ORDER BY toplam_deger DESC
    """
    out, ok = rewrite_order_by_select_aliases(sql)
    assert ok
    assert "order by 1" in out.lower().replace("\n", " ")
    r = guard_sql_shape(sql, allowed_tables=["public.stok_bakiyeleri"])
    assert "rewrote_order_by_select_alias" in r.warnings
    assert not r.blocked or r.code != "COLUMN_NOT_FOUND"


def test_cast_maps_to_type_conversion():
    class E(Exception):
        pgcode = "42804"

    mapped = _map_psycopg_error(E("cannot cast type bigint to date"))
    assert mapped.code == "QUERY_TYPE_CONVERSION_FAILED"
    assert is_repairable("QUERY_TYPE_CONVERSION_FAILED")
    code, _ = _normalize_gateway_error(
        "HTTP_400", "execution failed: cannot cast type bigint to date"
    )
    assert code == "QUERY_TYPE_CONVERSION_FAILED"


def test_compact_user_prompt_truncates_authorized_block():
    inner = "x" * 5000
    user = f"Q?\n<authorized_schema_context>\n{inner}\n</authorized_schema_context>\nend"
    out = _compact_user_prompt(user, ratio=0.45)
    assert len(out) < len(user)
    assert "truncated for retry" in out
    assert "<authorized_schema_context>" in out
