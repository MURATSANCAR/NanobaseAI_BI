"""Value inventories are read as few times over a table as the connector allows — never fewer columns."""
from __future__ import annotations

from semantic_layer.profiler.profiler import Profiler


class _Conn:
    """A fake source that counts how many times the table is read and can fail one batch."""
    dialect, default_schema = "tsql", "dbo"
    quote_l = quote_r = '"'
    supports_execution = False
    BATCHABLE = ("int", "varchar")

    def __init__(self, fail_batch_with: str | None = None):
        self.batch_calls: list[list[str]] = []
        self.single_calls: list[str] = []
        self.fail_batch_with = fail_batch_with

    def list_tables(self, schema, like=None): return [("dbo", "T")]
    def columns(self, schema, table):
        return [{"name": "CODE", "data_type": "varchar(4)"}, {"name": "KIND", "data_type": "int"},
                {"name": "FLAG", "data_type": "bit"}, {"name": "TYPE_", "data_type": "smallint"},
                {"name": "ID", "data_type": "int"}]
    def primary_keys(self, schema, table): return ["ID"]
    def foreign_keys(self, schema): return []
    def row_count(self, schema, table): return 100
    def row_counts(self, schema): return {"T": 100}
    def table_comments(self, schema): return {}
    def column_comments(self, schema): return {}
    def sample_rows(self, schema, table, limit=20): return []
    def indexes(self, schema): return {}
    def batchable(self, dt): return any(dt.lower().startswith(t) for t in self.BATCHABLE)
    def top_values(self, schema, table, column, limit):
        self.single_calls.append(column)
        return [(f"{column}-v", 7)]
    def top_values_batch(self, schema, table, columns, limit):
        self.batch_calls.append(list(columns))
        if self.fail_batch_with and self.fail_batch_with in columns:
            raise RuntimeError("batch refused")
        return {c: [(f"{c}-v", 7)] for c in columns}


def _profiles(conn, batch=25):
    import os
    os.environ["SEMANTIC_PROBE_BATCH"] = str(batch)
    try:
        return Profiler(conn).profile("d", "dbo")
    finally:
        os.environ.pop("SEMANTIC_PROBE_BATCH", None)


def test_batchable_columns_are_read_together_and_the_rest_one_at_a_time():
    conn = _Conn()
    [p] = _profiles(conn)
    assert conn.batch_calls == [["CODE", "KIND"]], "int/varchar go in one read; smallint is not in this fake's batchable list"
    assert sorted(conn.single_calls) == ["FLAG", "TYPE_"], "bit and the non-batchable type go alone; the key is never probed"
    got = {c.name: c.top_values for c in p.columns if c.top_values}
    assert set(got) == {"CODE", "KIND", "FLAG", "TYPE_"}, "every candidate column still has its inventory"


def test_a_failed_batch_costs_time_not_coverage():
    conn = _Conn(fail_batch_with="KIND")
    [p] = _profiles(conn)
    assert conn.batch_calls == [["CODE", "KIND"]]
    assert sorted(conn.single_calls) == ["CODE", "FLAG", "KIND", "TYPE_"], "the batch's own columns are re-read one at a time"
    assert {c.name for c in p.columns if c.top_values} == {"CODE", "KIND", "FLAG", "TYPE_"}


def test_batching_is_off_unless_asked_for():
    import os
    conn = _Conn()
    os.environ.pop("SEMANTIC_PROBE_BATCH", None)
    Profiler(conn).profile("d", "dbo")
    assert conn.batch_calls == [], "off by default: not yet measured to read less"
    assert sorted(conn.single_calls) == ["CODE", "FLAG", "KIND", "TYPE_"]


def test_batching_off_reads_every_column_alone():
    conn = _Conn()
    _profiles(conn, batch=0)
    assert conn.batch_calls == []
    assert sorted(conn.single_calls) == ["CODE", "FLAG", "KIND", "TYPE_"]


def test_batches_are_bounded():
    conn = _Conn()
    _profiles(conn, batch=1)
    assert conn.batch_calls == [["CODE"], ["KIND"]]
