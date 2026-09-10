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


def test_backups_and_test_tables_are_left_out_of_the_scan_and_named():
    """Real tables with real rows that answer no question. Left in, each is a shape of its own, so
    the shape-first traversal treats a backup of a fact table as a first copy and gives it priority
    over tables nobody has read yet."""
    import logging
    import os

    from semantic_layer.profiler.profiler import Profiler

    class _Conn:
        dialect, default_schema = "tsql", "dbo"
        quote_l = quote_r = '"'

        def __init__(self):
            self.read: list[str] = []

        def list_tables(self, schema, like=None):
            return [("dbo", n) for n in ("LG_411_01_STLINE", "LG_411_01_STLINE_yedek1",
                                         "BCKP_030826LG_411_01_STLINE", "AA_TEST", "LG_411_ITEMS")]

        def columns(self, schema, table):
            self.read.append(table)
            return [{"name": "ID", "data_type": "int"}]

        def primary_keys(self, schema, table): return ["ID"]
        def foreign_keys(self, schema): return []
        def row_count(self, schema, table): return 5
        def row_counts(self, schema): return {}
        def table_comments(self, schema): return {}
        def column_comments(self, schema): return {}
        def sample_rows(self, schema, table, limit=20): return []
        def indexes(self, schema): return {}
        def top_values(self, *a, **k): return []

    conn = _Conn()
    out = Profiler(conn).profile("d", "dbo")
    assert {p.table_name for p in out} == {"LG_411_01_STLINE", "LG_411_ITEMS"}
    assert not any("yedek" in t.lower() or "BCKP" in t or t == "AA_TEST" for t in conn.read), conn.read

    os.environ["SEMANTIC_SKIP_SHADOW"] = "0"
    try:
        back = Profiler(_Conn()).profile("d", "dbo")
        assert len(back) == 5, "a deployment that wants them back says so"
    finally:
        os.environ.pop("SEMANTIC_SKIP_SHADOW", None)


def test_a_changed_only_run_reads_what_changed_and_prunes_nothing():
    """A nightly pass over a schema this size never finishes — the one here was killed by its own
    timeout every night having read a quarter of it, so a view added on Monday was still unknown on
    Friday. And a run that saw only what changed must never prune against what it saw: that list is
    not the schema, and pruning against it empties the catalog one quiet night at a time."""
    from datetime import datetime, timedelta

    from semantic_layer.profiler.profiler import Profiler

    dun = datetime(2026, 9, 7, 3, 0)
    bugun = datetime(2026, 9, 8, 3, 0)

    class _Conn:
        dialect, default_schema = "tsql", "dbo"
        quote_l = quote_r = '"'

        def __init__(self):
            self.read: list[str] = []

        def list_tables(self, schema, like=None):
            return [("dbo", n) for n in ("ESKI", "DEGISMIS", "YENI")]

        def modified_at(self, schema):
            return {"ESKI": dun - timedelta(days=30), "DEGISMIS": bugun}

        def columns(self, schema, table):
            self.read.append(table)
            return [{"name": "ID", "data_type": "int"}]

        def primary_keys(self, schema, table): return ["ID"]
        def foreign_keys(self, schema): return []
        def row_count(self, schema, table): return 1
        def row_counts(self, schema): return {}
        def table_comments(self, schema): return {}
        def column_comments(self, schema): return {}
        def sample_rows(self, schema, table, limit=20): return []
        def indexes(self, schema): return {}
        def top_values(self, *a, **k): return []

    conn = _Conn()
    out = Profiler(conn).profile("d", "dbo", known={"ESKI": dun, "DEGISMIS": dun})
    assert set(conn.read) == {"DEGISMIS", "YENI"}, conn.read
    assert {p.table_name for p in out} == {"DEGISMIS", "YENI"}, "untouched tables keep their stored profile"


def test_a_period_accounting_does_not_keep_its_books_in_is_left_out_of_scope():
    """The same fiscal year can exist twice under two firm codes, differing by a few percent. Which
    one is the record is an accounting decision; told which, the other leaves the scope rather than
    being picked per query by whichever happens to hold more rows."""
    import os

    from semantic_layer.profiler.profiler import Profiler

    class _Conn:
        dialect, default_schema = "tsql", "dbo"
        quote_l = quote_r = '"'

        def list_tables(self, schema, like=None):
            return [("dbo", n) for n in ("LG_015_01_INVOICE", "LG_105_01_INVOICE",
                                         "LG_411_01_INVOICE", "KAPAT_015_01")]

        def columns(self, schema, table): return [{"name": "ID", "data_type": "int"}]
        def primary_keys(self, schema, table): return ["ID"]
        def foreign_keys(self, schema): return []
        def row_count(self, schema, table): return 5
        def row_counts(self, schema): return {}
        def table_comments(self, schema): return {}
        def column_comments(self, schema): return {}
        def sample_rows(self, schema, table, limit=20): return []
        def indexes(self, schema): return {}
        def top_values(self, *a, **k): return []

    os.environ["SEMANTIC_EXCLUDE_CONTEXT"] = "015"
    try:
        out = Profiler(_Conn()).profile("d", "dbo")
    finally:
        os.environ.pop("SEMANTIC_EXCLUDE_CONTEXT", None)
    names = {p.table_name for p in out}
    assert names == {"LG_105_01_INVOICE", "LG_411_01_INVOICE"}, names


def test_change_times_from_two_different_clocks_are_compared_safely():
    """The engine records naive server time and the catalog records UTC with an offset. Compared
    directly they raise; compared carelessly they disagree by hours, and an hour's disagreement in
    the wrong direction skips a table that did change — a catalog that quietly goes stale."""
    from datetime import datetime, timedelta, timezone

    from semantic_layer.profiler.profiler import Profiler

    naive = datetime(2026, 9, 8, 3, 0)
    aware = datetime(2026, 9, 8, 3, 0, tzinfo=timezone.utc)

    class _Conn:
        dialect, default_schema = "tsql", "dbo"
        quote_l = quote_r = '"'

        def __init__(self):
            self.read: list[str] = []

        def list_tables(self, schema, like=None):
            return [("dbo", n) for n in ("SINIRDA", "COKESKI")]

        def modified_at(self, schema):
            # naive, from the engine; one table changed an hour after its profile, one long before
            return {"SINIRDA": naive + timedelta(hours=1), "COKESKI": naive - timedelta(days=90)}

        def columns(self, schema, table):
            self.read.append(table)
            return [{"name": "ID", "data_type": "int"}]

        def primary_keys(self, schema, table): return ["ID"]
        def foreign_keys(self, schema): return []
        def row_count(self, schema, table): return 1
        def row_counts(self, schema): return {}
        def table_comments(self, schema): return {}
        def column_comments(self, schema): return {}
        def sample_rows(self, schema, table, limit=20): return []
        def indexes(self, schema): return {}
        def top_values(self, *a, **k): return []

    conn = _Conn()
    # aware timestamps on the catalog side: the comparison must not raise, and must not skip SINIRDA
    Profiler(conn).profile("d", "dbo", known={"SINIRDA": aware, "COKESKI": aware})
    assert "SINIRDA" in conn.read, "a table that changed after its profile has to be read again"
    assert "COKESKI" not in conn.read, "one untouched for months does not"
