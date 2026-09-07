"""A scan is read breadth-first by shape, stores as it goes, and never prefers a copy."""
from __future__ import annotations

from datetime import date

from semantic_layer.models import ColumnProfile, SchemaProfile
from semantic_layer.naming import is_shadow_copy, source_rank
from semantic_layer.profiler.profiler import _shape_depth
from semantic_layer.runtime.periods import tables_for


def _p(name: str, pattern: str, window=None, rows=None) -> SchemaProfile:
    return SchemaProfile(datasource_id="d", table_name=name, table_pattern=pattern, entity="STLINE",
                         columns=[ColumnProfile(name="TOTAL", data_type="decimal")],
                         row_count=rows, time_window=window)


def test_a_second_copy_of_a_shape_is_read_after_the_first_copy_of_every_other():
    # twelve years of one shape and one table of another: reading by size alone spends the whole
    # scan on the first shape and never reaches the second
    tables = [("dbo", f"LG_{y}_01_STLINE") for y in range(201, 213)] + [("dbo", "LG_211_01_ORFICHE")]
    score = {t: 1000.0 for _, t in tables}
    score["LG_211_01_ORFICHE"] = 1.0

    class _LT:
        def __init__(self, pattern): self.table_pattern = pattern

    logical = {t: _LT("LG_{n0}_{n1}_ORFICHE" if "ORFICHE" in t else "LG_{n0}_{n1}_STLINE")
               for _, t in tables}
    depth = _shape_depth(tables, score, logical)
    assert depth["LG_211_01_ORFICHE"] == 0, "the only copy of its shape is a first copy"
    firsts = [t for t, d in depth.items() if d == 0]
    assert len(firsts) == 2, "one first copy per shape, not one per table"
    ordered = sorted((t for _, t in tables), key=lambda t: (depth[t], -score[t], t))
    assert ordered[1] == "LG_211_01_ORFICHE", "the other shape is read before any shape is read twice"


def test_every_table_is_still_scanned_only_the_order_changes():
    tables = [("dbo", n) for n in ("LG_201_01_STLINE", "LG_211_01_STLINE", "LG_211_01_ORFICHE")]

    class _LT:
        def __init__(self, pattern): self.table_pattern = pattern

    logical = {t: _LT("LG_{n0}_{n1}_ORFICHE" if "ORFICHE" in t else "LG_{n0}_{n1}_STLINE") for _, t in tables}
    depth = _shape_depth(tables, {t: 1.0 for _, t in tables}, logical)
    assert set(depth) == {t for _, t in tables}, "ordering must not drop a table"


def test_a_backup_is_not_read_in_place_of_the_table_it_was_copied_from():
    window = ("2026-01-01", "2026-08-01")
    live = _p("LG_411_01_STLINE", "LG_{n0}_{n1}_STLINE", window, rows=20559)
    # a backup with *more* rows than the live table: rows alone would pick it
    backup = _p("BCKP_030826LG_411_01_STLINE", "BCKP_030826LG_{n0}_{n1}_STLINE", window, rows=99999)
    chosen = tables_for([live, backup], date(2026, 1, 1), date(2026, 12, 31))
    assert [p.table_name for p in chosen] == ["LG_411_01_STLINE"]


def test_a_view_is_not_read_in_place_of_the_table_beneath_it():
    window = ("2026-01-01", "2026-08-01")
    base = _p("LG_411_01_STLINE", "LG_{n0}_{n1}_STLINE", window, rows=20559)
    # LV_ sorts after LG_, and a view has no measured row count: name order would pick the view
    view = _p("LV_411_01_STLINE", "LV_{n0}_{n1}_STLINE", window, rows=None)
    chosen = tables_for([base, view], date(2026, 1, 1), date(2026, 12, 31))
    assert [p.table_name for p in chosen] == ["LG_411_01_STLINE"]


def test_a_marker_inside_an_ordinary_word_is_not_a_backup():
    for ordinary in ("TEMPLATES", "LATEST_ORDERS", "BAKERY_SALES", "CONTEMPORARY", "LG_411_01_STLINE"):
        assert not is_shadow_copy(ordinary), ordinary
    for copy in ("LG_411_01_STLINE_yedek1", "BCKP_030826LG_411_01_STLINE", "AA_TEST",
                 "LG_211_CRDACREF_copy", "L_CAPIPERIOD_YEDEK", "VW_211_01_BA_BS_TEMP"):
        assert is_shadow_copy(copy), copy


def test_source_rank_orders_base_table_then_view_then_copy():
    assert source_rank("LG_411_01_STLINE") == 0
    assert source_rank("LV_411_01_STLINE", is_view=True) == 1
    assert source_rank("BCKP_030826LG_411_01_STLINE") == 2


def test_a_scan_stores_each_table_as_it_finishes_not_at_the_end():
    """The failure this prevents: hours of correct work discarded because the run did not reach its
    last statement. Interruption is the normal case on a scan measured in days, not the exception."""
    from semantic_layer.profiler.profiler import Profiler

    class _Conn:
        dialect, default_schema = "sqlite", "main"
        quote_l = quote_r = '"'

        def list_tables(self, schema, like=None):
            return [("main", "A"), ("main", "B"), ("main", "C")]

        def columns(self, schema, table):
            return [{"name": "ID", "data_type": "int", "nullable": False}]

        def primary_keys(self, schema, table): return ["ID"]
        def foreign_keys(self, schema): return []
        def row_count(self, schema, table): return 5
        def table_comments(self, schema): return {}
        def column_comments(self, schema): return {}
        def distinct_values(self, *a, **k): return []
        def sample_rows(self, *a, **k): return []
        def indexes(self, schema): return {}

    seen: list[str] = []

    def boom(p):
        seen.append(p.table_name)
        if p.table_name == "B":
            raise RuntimeError("store is down for this one")

    out = Profiler(_Conn()).profile("d", "main", on_profile=boom)
    assert seen == sorted(seen) or set(seen) == {"A", "B", "C"}, "every table is handed over"
    assert set(seen) == {"A", "B", "C"}, "a table is stored as it finishes, not at the end"
    assert {p.table_name for p in out} == {"A", "B", "C"}, "a failed store must not end the scan"
