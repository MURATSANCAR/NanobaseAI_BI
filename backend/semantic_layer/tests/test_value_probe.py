"""A word the vocabulary never had, looked up in the data before the prompt is written."""
from __future__ import annotations

from semantic_layer.models import ColumnProfile, SchemaProfile
from semantic_layer.runtime.value_probe import ValueProbe, facts_block


def _col(name, dtype="nvarchar(30)", **kw):
    return ColumnProfile(name=name, data_type=dtype, **kw)


CATEGORY = _col("SPECODE2", distinct_count=3,
                top_values=[("Çocuk Kitapları", 1209), ("Edebiyat", 479), ("Sanat", 441)])
NAME = _col("NAME", "nvarchar(200)")
SECRET = _col("TCKN", "varchar(11)", sensitive=True, sensitivity_reason="kimlik numarası")
AMOUNT = _col("TOTAL", "decimal(18,2)")

ITEMS = SchemaProfile(datasource_id="d", table_name="LG_411_ITEMS", table_pattern="LG_{n0}_ITEMS",
                      entity="ITEMS", schema_name="dbo", columns=[CATEGORY, NAME, SECRET, AMOUNT])


class _Conn:
    def __init__(self):
        self.asked: list[tuple] = []

    def search_values(self, schema, table, column, needle, limit):
        self.asked.append((table, column, needle))
        return [("Çocuk Kitapları Serisi", 12)] if column == "NAME" else []


class _Broken(_Conn):
    def search_values(self, *a, **k):
        raise RuntimeError("database said no")


def test_a_word_that_is_a_value_comes_back_with_its_exact_spelling():
    """The question says "çocuk"; the data says "Çocuk Kitapları". Told which, the model stops
    guessing at capitalisation and suffixes."""
    hits = ValueProbe(_Conn(), [ITEMS]).find("çocuk", ["ITEMS"])
    assert hits, "the value is in the inventory the scan already took"
    assert hits[0].value == "Çocuk Kitapları" and hits[0].column == "SPECODE2"
    assert "1209" in hits[0].as_fact()


def test_an_inventoried_column_is_answered_without_asking_the_database():
    conn = _Conn()
    ValueProbe(conn, [ITEMS]).find("çocuk", ["ITEMS"])
    assert not [a for a in conn.asked if a[1] == "SPECODE2"], "the scan already read this column"


def test_personal_data_is_never_searched():
    """A question containing a name must not become a scan for that name."""
    conn = _Conn()
    ValueProbe(conn, [ITEMS]).find("12345678901", ["ITEMS"])
    assert not [a for a in conn.asked if a[1] == "TCKN"], conn.asked


def test_a_number_column_is_not_searched_for_words():
    conn = _Conn()
    ValueProbe(conn, [ITEMS]).find("kitap", ["ITEMS"])
    assert not [a for a in conn.asked if a[1] == "TOTAL"], conn.asked


def test_a_failing_database_leaves_the_prompt_as_it_was():
    hits = ValueProbe(_Broken(), [ITEMS]).find("kitap", ["ITEMS"])
    assert facts_block(hits) == "(yok)" or hits, "a failure adds nothing; it never raises"


def test_a_word_too_short_to_mean_anything_is_not_looked_up():
    conn = _Conn()
    assert ValueProbe(conn, [ITEMS]).find("ay", ["ITEMS"]) == []
    assert conn.asked == []


def test_nothing_found_says_nothing():
    assert facts_block([]) == "(yok)"


def test_the_facts_carry_spelling_and_weight():
    hits = ValueProbe(_Conn(), [ITEMS]).find("çocuk", ["ITEMS"])
    block = facts_block(hits)
    assert "Çocuk Kitapları" in block and "ITEMS.SPECODE2" in block
    assert "aynen" in block, "the model is told to use the spelling, not approximate it"


def test_a_question_stripped_of_its_turkish_characters_still_finds_the_value():
    """The resolver flattens what the person typed ("çocuk" → "cocuk") while the data keeps its
    accents. Compared as typed, the two never meet and a question is refused over an accent."""
    hits = ValueProbe(_Conn(), [ITEMS]).find("cocuk", ["ITEMS"])
    assert hits and hits[0].value == "Çocuk Kitapları", hits


def test_a_name_that_was_never_inventoried_is_still_searched_for():
    """A category code is inventoried; a company name is not. Ranking the inventoried columns first
    is right, looking at only those is not — it excludes exactly the columns a question naming a
    company needs."""
    conn = _Conn()
    hits = ValueProbe(conn, [ITEMS]).find("kitapları", ["ITEMS"])
    assert any(a[1] == "NAME" for a in conn.asked), conn.asked
    assert any("Serisi" in h.value for h in hits), hits


def test_one_entity_is_looked_in_once_however_many_years_it_spans():
    """An entity split one table per fiscal year has a dozen profiles carrying identical columns.
    Walked as they come, every candidate slot goes to copies of the same column and the search never
    reaches a second one — which is how a probe with twelve slots searched exactly one column."""
    years = [SchemaProfile(datasource_id="d", table_name=f"LG_{y}_ITEMS", table_pattern="LG_{n0}_ITEMS",
                           entity="ITEMS", schema_name="dbo", row_count=n,
                           columns=[CATEGORY, NAME, AMOUNT])
             for y, n in (("015", 100), ("115", 900), ("411", 50))]
    cands = ValueProbe(_Conn(), years)._candidates(["ITEMS"], None, "kitap")
    names = [c.name for _, c in cands]
    assert len(names) == len(set(names)), names
    assert {p.table_name for p, _ in cands} == {"LG_115_ITEMS"}, "the fullest table is the one to look in"
