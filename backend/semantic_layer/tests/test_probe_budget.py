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


def test_recertifying_on_stored_profiles_still_probes(store, settings, monkeypatch, profiles):
    """Re-running certification without re-profiling is the normal move after a catalog fix. It used to
    die at the last step, because skipping the profile also skipped building the connector the probe
    needs — so the run that fixes a catalog was the one that could not finish."""
    from semantic_layer import pipeline as pl

    for p in profiles:
        store.upsert_profile(p)
    built: list[str] = []

    def _fake_connector(*a, **k):
        built.append("yes")
        raise RuntimeError("no database here")

    monkeypatch.setattr(pl, "build_connector", _fake_connector)
    report = pl.run_pipeline(store, settings, skip_profile=True, probe=True, note="recertify")
    assert built, "the probe's connector is built even when the profile step is skipped"
    assert "no connector" in str(report.get("probe")), "and a probe that cannot run says so"
    assert report.get("certify"), "certification still completes"


def test_a_scope_too_large_drops_the_least_useful_tables_not_the_last_alphabetically():
    """When a scope matches more tables than the cap, which ones to drop is a decision about value.
    Cutting the list where it happens to end threw away the table that defines what this database's own
    codes mean — purely because of its initial."""
    from semantic_layer.profiler.profiler import Profiler

    class _Wide:
        dialect = "generic"
        supports_execution = False

        def list_tables(self, schema, like=None):
            # alphabetical, with the valuable ones deliberately late in the list
            return [("main", f"A_EMPTY_{i:02d}") for i in range(6)] + [("main", "Z_CODES"), ("main", "Z_ORDERS")]

        def columns(self, schema, table):
            return [{"name": "ID", "data_type": "int"}]

        def primary_keys(self, schema, table):
            return ["ID"]

        def foreign_keys(self, schema):
            return []

        def row_counts(self, schema):
            return {f"A_EMPTY_{i:02d}": 0 for i in range(6)} | {"Z_CODES": 9_400, "Z_ORDERS": 300_000}

        def row_count(self, schema, table):
            return self.row_counts(schema).get(table, 0)

        def sample_rows(self, schema, table, limit=20):
            return []

        def top_values(self, schema, table, column, limit):
            return []

    p = Profiler(_Wide(), max_tables=3)
    kept = {x.table_name for x in p.profile("ds", "main")}
    assert {"Z_ORDERS", "Z_CODES"} <= kept, kept
    assert p.truncated, "and what was dropped is reported, never silently"

    # ...but only because a bound was asked for. Left alone, the catalog holds the whole schema and
    # matches it table for table — a catalog smaller than the database cannot be planned or
    # reported against, and the difference is invisible from the outside.
    whole = Profiler(_Wide())
    profiles = whole.profile("ds", "main")
    assert len(profiles) == 8 and not whole.truncated
    assert [x.table_name for x in profiles] == [f"A_EMPTY_{i:02d}" for i in range(6)] + ["Z_CODES", "Z_ORDERS"], \
        "the catalog is emitted in discovery order even though the probe order is value-first"
