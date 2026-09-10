"""The columns a question is shown: structural ones always, the tail only where the question reaches."""
from __future__ import annotations

from semantic_layer.models import ColumnProfile, SchemaProfile
from semantic_layer.runtime.compiler import ExistingCompiler


def _col(name, dtype="int", **kw):
    return ColumnProfile(name=name, data_type=dtype, **kw)


def _table(cols, relationships=()):
    return SchemaProfile(datasource_id="d", table_name="LG_411_01_STLINE",
                         table_pattern="LG_{n0}_{n1}_STLINE", entity="STLINE",
                         schema_name="dbo", columns=list(cols), primary_key=["LOGICALREF"],
                         relationships=list(relationships))


class _Index:
    """Scores only the columns whose name the question happens to contain."""

    def __init__(self, hits):
        self.hits = hits

    def search(self, question, limit=60):
        return [{"entity": e, "column": c, "score": 9.0} for e, c in self.hits]


def _compiler(profiles, index=None):
    c = ExistingCompiler(None, profiles, {}, dialect="tsql")
    c.columns = index
    return c


def test_the_date_column_survives_a_question_that_never_names_it():
    """"2026 net ciro" contains no word matching DATE_, and without it the model has nothing to
    filter a year on — it was being dropped and the question answered over every year at once."""
    p = _table([_col("LOGICALREF"), _col("DATE_", "datetime"), _col("TOTAL", "decimal")]
               + [_col(f"FILLER{i}") for i in range(40)])
    c = _compiler([p], _Index([("STLINE", "TOTAL")]))
    shown, _ = c.prompt_columns(p, _q())
    names = {x.name for x in shown}
    assert "DATE_" in names, "the time axis is structural, not lexical"
    assert "LOGICALREF" in names, "the key is structural too"
    assert "FILLER7" not in names, "a column the question does not reach is not sent"


def test_a_join_column_survives_even_with_no_declared_foreign_key():
    """This schema declares no foreign keys at all; the vendor dictionary's relationships are the
    join graph there is, and a join column dropped from the prompt cannot be joined on."""
    p = _table([_col("LOGICALREF"), _col("STOCKREF")] + [_col(f"FILLER{i}") for i in range(40)],
               relationships=[{"column": "STOCKREF", "ref_entity": "ITEMS", "ref_column": "LOGICALREF"}])
    c = _compiler([p], _Index([]))
    shown, _ = c.prompt_columns(p, _q())
    assert "STOCKREF" in {x.name for x in shown}


def test_the_tail_is_kept_where_the_question_reaches_it():
    p = _table([_col("LOGICALREF")] + [_col(f"COL{i}") for i in range(40)])
    c = _compiler([p], _Index([("STLINE", "COL13")]))
    names = {x.name for x in c.prompt_columns(p, _q())[0]}
    assert "COL13" in names and "COL14" not in names


def test_focus_off_sends_every_column():
    p = _table([_col("LOGICALREF")] + [_col(f"COL{i}") for i in range(40)])
    c = _compiler([p], _Index([]))
    c.column_focus = False
    assert len(c.prompt_columns(p, _q())[0]) == 41


def test_two_questions_at_once_do_not_get_each_other_s_columns():
    """The compiler is shared by every concurrent request. A one-slot cache keyed by "the last
    question" would hand one request the columns scored for another's, and drop the right ones."""
    import threading

    p = _table([_col("LOGICALREF")] + [_col(f"COL{i}") for i in range(40)])

    class _PerQuestion:
        def search(self, question, limit=60):
            return [{"entity": "STLINE", "column": f"COL{len(question) % 40}", "score": 9.0}]

    c = _compiler([p], _PerQuestion())
    seen: dict[str, set] = {}
    errors: list = []

    def ask(text):
        try:
            for _ in range(30):
                got = c._scored_columns(text)
                if seen.setdefault(text, got) != got:
                    errors.append(text)
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    ts = [threading.Thread(target=ask, args=(t,)) for t in ("kisa", "biraz daha uzun bir soru", "orta boy")]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors, f"a question was given another question's columns: {errors[:3]}"
    assert len({tuple(sorted(v)) for v in seen.values()}) == 3


def _q():
    from semantic_layer.models import SemanticQuery
    return SemanticQuery(question="2026 net ciro nedir?", tenant_id="t", datasource_id="d")
