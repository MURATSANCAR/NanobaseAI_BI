"""A coded column answers a question written in words, because the source named its codes.

`statuscode` on a CRM order holds 100000001. No question contains that number; every question
contains "iptal". The source ships its own dictionary of those codes, so the word is searchable and
the code is what comes back — the filter has to be written against what the column actually holds.
"""
from __future__ import annotations

from semantic_layer.models import ColumnProfile, SchemaProfile
from semantic_layer.runtime.value_probe import ValueProbe


STATUS = ColumnProfile(
    name="statuscode", data_type="int", distinct_count=4,
    top_values=[("100000002", 180_413), ("100000000", 96_205), ("100000001", 41_120), ("1", 15_325)],
    value_labels={"1": "Taslak", "100000000": "Sevk Edildi",
                  "100000001": "İptal Edildi", "100000002": "Sipariş"})
UNNAMED = ColumnProfile(
    name="new_risketakilmasebebi", data_type="int", distinct_count=2,
    top_values=[("0", 900), ("1", 100)])
TEXT = ColumnProfile(name="new_aciklama", data_type="nvarchar(400)")

ORDERS = SchemaProfile(datasource_id="d", table_name="new_siparisBase", table_pattern="new_siparisBase",
                       entity="new_siparisBase", schema_name="Timas_MSCRM.dbo",
                       columns=[STATUS, UNNAMED, TEXT], row_count=333_063)


class _Conn:
    """A database that would answer, so a test that passes cannot be passing on a silent failure."""

    def __init__(self):
        self.asked: list[tuple] = []

    def search_values(self, schema, table, column, needle, limit):
        self.asked.append((table, column, needle))
        return []


def test_a_word_finds_the_code_it_stands_for():
    hits = ValueProbe(_Conn(), [ORDERS]).find("iptal", ["new_siparisBase"])
    assert hits, "the source named this code and the word is in its name"
    assert (hits[0].column, hits[0].value) == ("statuscode", "100000001")
    assert hits[0].rows == 41_120, "the count is the measured one, not the label's"


def test_the_word_is_matched_the_way_the_question_arrives():
    """The resolver folds Turkish characters before this point; the label keeps them. İ/i is where
    a Turkish schema breaks a naive comparison, so the whole label is matched too."""
    whole = ValueProbe(_Conn(), [ORDERS]).find("iptal edildi", ["new_siparisBase"])
    assert [h.value for h in whole] == ["100000001"]
    hits = ValueProbe(_Conn(), [ORDERS]).find("sevk", ["new_siparisBase"])
    assert [h.value for h in hits] == ["100000000"]


def test_a_coded_column_is_not_asked_of_the_database_twice():
    """The dictionary is the whole of what the codes mean; LIKE over integers cannot add to it."""
    conn = _Conn()
    ValueProbe(conn, [ORDERS]).find("iptal", ["new_siparisBase"])
    assert ("new_siparisBase", "statuscode", "iptal") not in conn.asked

def test_an_unnamed_code_column_stays_out_of_the_search():
    """Without the source's words, 0 and 1 mean nothing; the column is not made searchable by fiat."""
    hits = ValueProbe(_Conn(), [ORDERS]).find("sebep", ["new_siparisBase"])
    assert [h.column for h in hits] == []


def test_the_prompt_shows_the_code_with_its_word():
    assert STATUS.labelled_values()[:2] == [("100000002", "Sipariş"), ("100000000", "Sevk Edildi")]
    assert UNNAMED.labelled_values() == [("0", None), ("1", None)], "no word invented for a code"


def test_a_value_the_data_never_carries_is_not_offered():
    """The source names fifteen order statuses; this table has four. A filter on the other eleven
    returns nothing, so the prompt does not suggest them."""
    named = dict(STATUS.value_labels, **{"100000015": "Tamamlandı"})
    col = ColumnProfile(name="statuscode", data_type="int", distinct_count=4,
                        top_values=STATUS.top_values, value_labels=named)
    assert "Tamamlandı" not in [lbl for _, lbl in col.labelled_values()]


def test_labels_survive_the_store():
    from semantic_layer.store.catalog_store import CatalogStore
    back = CatalogStore._col_from_json(CatalogStore._col_to_json(STATUS))
    assert back.value_labels == STATUS.value_labels
    assert back.label_of("100000001") == "İptal Edildi"


def test_a_named_code_is_never_read_as_no_value():
    """0 is what an unset column looks like, and the sentinel detector marked it so. Here the source
    calls 0 "Etkin" and 332.463 of 333.063 orders are in it — hiding it hid the ordinary case."""
    col = ColumnProfile(name="statecode", data_type="int", distinct_count=2,
                        top_values=[("0", 332_463), ("1", 600)], sentinel_values=["0"],
                        value_labels={"0": "Etkin", "1": "Etkin değil"})
    assert col.labelled_values() == [("0", "Etkin"), ("1", "Etkin değil")]


def test_an_unnamed_sentinel_is_still_dropped():
    col = ColumnProfile(name="OWNER_REF", data_type="int", distinct_count=2,
                        top_values=[("0", 900), ("7", 100)], sentinel_values=["0"])
    assert col.meaningful_values() == [("7", 100)]


def test_a_nine_digit_code_set_is_not_a_phone_book():
    """Dynamics numbers its options 100000001. Nine digits matched the phone shape, and the columns
    that answer "hangi kanaldan" and "kaç sipariş iptal oldu" were withdrawn from the engine."""
    from semantic_layer.profiler import sensitivity
    codes = ["100000001", "100000002", "100000015", "862440000"]
    assert sensitivity.values_are_sensitive(codes) == "telefon biçimi", "the old reading"
    assert sensitivity.values_are_sensitive(codes, complete=True) is None


def test_a_column_of_actual_phone_numbers_is_still_personal_data():
    from semantic_layer.profiler import sensitivity
    numbers = [f"0532 111 22 {n:02d}" for n in range(80)]
    assert sensitivity.values_are_sensitive(numbers, complete=True) == "telefon biçimi"
    assert sensitivity.values_are_sensitive(numbers[:10], complete=False) == "telefon biçimi"


def test_a_short_complete_set_of_real_numbers_stays_out_of_reach_by_name():
    """The size rule speaks about values only; a column named for personal data keeps its mark."""
    from semantic_layer.profiler import sensitivity
    assert sensitivity.name_is_sensitive("DoNotPhone")
    assert sensitivity.classify("cep_telefonu", ["1", "2"])
