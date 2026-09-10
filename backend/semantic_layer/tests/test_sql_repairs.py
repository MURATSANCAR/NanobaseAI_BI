"""Small, exact repairs to what a model writes — the label the person reads is never changed."""
from __future__ import annotations

from semantic_layer.runtime.compiler import extract_sql, quote_numeric_aliases


def test_a_column_named_after_a_year_is_quoted_not_renamed():
    """Asked for two years side by side the model writes AS 2025_ciro — a syntax error unquoted, and
    the whole answer was thrown away for it. The name is what the person reads, so it is kept."""
    out = quote_numeric_aliases("SELECT SUM(x) AS 2025_net_ciro, SUM(y) AS 2026_net_ciro FROM t")
    assert out == "SELECT SUM(x) AS [2025_net_ciro], SUM(y) AS [2026_net_ciro] FROM t"


def test_an_alias_that_is_already_quoted_is_left_alone():
    for already in ('SELECT a AS [2025_x] FROM t', 'SELECT a AS "2025_x" FROM t', "SELECT a AS `2025_x` FROM t"):
        assert quote_numeric_aliases(already) == already, already


def test_an_ordinary_alias_is_untouched():
    for ok in ("SELECT a AS ciro_2025 FROM t", "SELECT a AS ciro FROM t", "SELECT a AS _2025 FROM t"):
        assert quote_numeric_aliases(ok) == ok, ok


def test_the_repair_runs_on_what_the_model_returns():
    sql = extract_sql("```sql\nSELECT SUM(x) AS 2026_ciro FROM t\n```")
    assert sql == "SELECT SUM(x) AS [2026_ciro] FROM t"


def test_a_refusal_is_still_a_refusal():
    assert extract_sql("NO_SQL: kapsam dışı") is None
    assert extract_sql("") is None
