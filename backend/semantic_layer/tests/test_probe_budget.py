"""Discovery must never run unbounded against a customer's database."""

from __future__ import annotations

from semantic_layer.models import ColumnProfile, SchemaProfile
from semantic_layer.profiler.profiler import _key_shaped, infer_links


class CountingConnector:
    """Counts every query the inference makes, so a regression in the budget fails the test."""

    dialect = "sqlite"
    quote_l = quote_r = '"'
    default_schema = "main"

    def __init__(self):
        self.queries = 0

    def q(self, ident: str) -> str:
        return f'"{ident}"'

    def top_values(self, schema, table, column, limit):
        self.queries += 1
        return [(str(i), 1) for i in range(1, 41)]

    def execute(self, sql, limit):
        self.queries += 1
        return [], [{"n": 0}], False


def _profile(entity: str, columns: int, rows: int) -> SchemaProfile:
    cols = [ColumnProfile(name="id", data_type="int", is_primary_key=True)]
    cols += [ColumnProfile(name=f"ref{i}", data_type="int", distinct_count=rows // 2, top_values=[(str(v), 1) for v in range(1, 41)]) for i in range(columns)]
    return SchemaProfile(datasource_id="d", table_name=entity, table_pattern=entity, entity=entity, columns=cols, primary_key=["id"], row_count=rows)


def test_link_inference_respects_its_budget():
    profiles = [_profile(f"T{i}", 150, 1000) for i in range(40)]      # 40 tables × 150 candidate columns
    c = CountingConnector()
    infer_links(profiles, c, max_columns_per_table=20, max_targets=30, max_probes=2000)
    assert c.queries <= 2000, f"probe budget exceeded: {c.queries}"


def test_huge_tables_are_not_probed_as_targets():
    small, huge = _profile("SMALL", 2, 1000), _profile("HUGE", 2, 50_000_000)
    c = CountingConnector()
    infer_links([small, huge], c, max_target_rows=5_000_000)
    assert all(r["ref_entity"] != "HUGE" for p in (small, huge) for r in p.relationships)


def test_type_codes_are_not_mistaken_for_keys():
    """A column with a handful of values across a large table is a code, not a reference."""
    code = ColumnProfile(name="TRCODE", data_type="smallint", distinct_count=8, top_values=[(str(i), 1) for i in range(8)])
    key = ColumnProfile(name="CLIENTREF", data_type="int", distinct_count=250_000, top_values=[(str(i), 1) for i in range(40)])
    flag = ColumnProfile(name="CANCELLED", data_type="smallint", distinct_count=2, top_values=[("0", 1), ("1", 1)])
    assert not _key_shaped(code, 1_700_000) and not _key_shaped(flag, 1_700_000)
    assert _key_shaped(key, 1_700_000)
