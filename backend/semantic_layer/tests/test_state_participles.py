"""A participle names a state, and a state this deployment records is a labelled code.

"iptal edilmemiş sipariş" asked for nothing before this: the resolver could not say what condition the
word imposed, so it asked the person instead of reading the label the source itself writes next to the
code. These tests hold that reading to the catalog: the word must reach the labelled value, the
negative must exclude it, and two columns answering to the same word must still ask.
"""
from __future__ import annotations

from datetime import date

from semantic_layer.models import ColumnProfile, SchemaProfile, SemanticType
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import catalog  # noqa: F401

TODAY = date(2026, 7, 20)


def orders(extra=()):
    status = ColumnProfile(name="statuscode", data_type="int", distinct_count=4,
                           top_values=[("100000002", 180), ("100000001", 41)],
                           value_labels={"1": "Taslak", "100000000": "Sevk Edildi",
                                         "100000001": "İptal Edildi", "100000002": "Sipariş"})
    amount = ColumnProfile(name="new_kdvlitoplamtutar", data_type="money")
    return SchemaProfile(datasource_id=DS, table_name="new_siparisBase", table_pattern="new_siparisBase",
                         entity="NEW_SIPARISBASE", schema_name="Timas_MSCRM.dbo", description="Sipariş",
                         columns=[status, amount, *extra], row_count=333_063)


def resolve(catalog, profiles, question):
    return SemanticResolver(catalog, TENANT, DS, profiles).resolve(question, today=TODAY)


def state_slots(sq):
    return [s for s in sq.slots if (s.explain or {}).get("source") == "value_label"]


def test_a_state_word_reaches_the_code_the_source_named(catalog, profiles):
    profiles = profiles + [orders()]
    sq = resolve(catalog, profiles, "iptal edilen sipariş sayısı")
    found = state_slots(sq)
    assert found, sq.to_dict()
    m = found[0].mapping
    assert (m.entity, m.column, m.operator, m.values) == ("NEW_SIPARISBASE", "STATUSCODE", "IN", ["100000001"])
    assert found[0].semantic_type == SemanticType.DIMENSION_VALUE
    assert "İptal Edildi" in found[0].explain["why"]


def test_the_negative_excludes_that_code_instead_of_asking(catalog, profiles):
    profiles = profiles + [orders()]
    sq = resolve(catalog, profiles, "iptal edilmemiş sipariş sayısı")
    found = state_slots(sq)
    assert found, sq.to_dict()
    assert found[0].mapping.operator == "NOT IN" and found[0].mapping.values == ["100000001"]
    assert not any("iptal" in c.lower() or "edilmemis" in c.lower() for c in sq.clarification), sq.clarification


def test_two_columns_answering_to_the_same_word_still_ask(catalog, profiles):
    twin = ColumnProfile(name="new_sevkdurumu", data_type="int", distinct_count=2,
                         value_labels={"1": "İptal Edildi", "2": "Sevk Edildi"})
    profiles = profiles + [orders(extra=[twin])]
    sq = resolve(catalog, profiles, "iptal edilen sipariş sayısı")
    assert not state_slots(sq), "two readings is ambiguity, not a decision"


def test_a_word_with_no_label_behind_it_is_still_asked_about(catalog, profiles):
    profiles = profiles + [orders()]
    sq = resolve(catalog, profiles, "zımbalanan sipariş sayısı")
    assert not state_slots(sq)
    assert sq.clarification, "nothing in the catalog explains the word, so the person is asked"


def described_invoice():
    """A source that says what a column is for and never says what its values mean — Logo's own shape."""
    cancelled = ColumnProfile(name="CANCELLED", data_type="smallint",
                              description="İptal Edilmiş (Cancelled)")
    total = ColumnProfile(name="NETTOTAL", data_type="money", description="Net Toplam")
    return SchemaProfile(datasource_id=DS, table_name="LG_411_01_INVOICE", table_pattern="LG_{n0}_{n1}_INVOICE",
                         entity="LG_INVOICE", schema_name="dbo", description="Fatura",
                         columns=[cancelled, total], row_count=81_760)


def test_a_described_column_carries_the_word_instead_of_asking(catalog, profiles):
    sq = resolve(catalog, profiles + [described_invoice()], "iptal edilmemiş fatura sayısı")
    assert sq.qualifier_columns, sq.to_dict()
    want = sq.qualifier_columns[0]
    assert (want["entity"], want["column"], want["negative"]) == ("LG_INVOICE", "CANCELLED", True)
    assert not any("iptal" in c.lower() or "edilmemis" in c.lower() for c in sq.clarification), sq.clarification


def test_the_gate_refuses_an_answer_that_ignores_that_column(catalog, profiles):
    from semantic_layer.runtime.audit import unmet_obligations

    sq = resolve(catalog, profiles + [described_invoice()], "iptal edilmemiş fatura sayısı")
    ignored = unmet_obligations(sq, "SELECT COUNT(*) AS adet FROM dbo.LG_411_01_INVOICE")
    assert any("CANCELLED" in u for u in ignored), ignored
    honoured = unmet_obligations(sq, "SELECT COUNT(*) AS adet FROM dbo.LG_411_01_INVOICE WHERE CANCELLED = 0")
    assert not any("CANCELLED" in u for u in honoured), honoured


def test_a_word_two_columns_describe_is_still_asked_about(catalog, profiles):
    twin = ColumnProfile(name="CANCELDATE", data_type="datetime", description="İptal Edilme Tarihi")
    prof = described_invoice()
    prof.columns.append(twin)
    sq = resolve(catalog, profiles + [prof], "iptal edilmemiş fatura sayısı")
    assert not sq.qualifier_columns and sq.clarification


def test_a_shortlist_where_nothing_can_be_dropped_costs_no_model_call(catalog, profiles):
    """A certified catalog that names every table pins every table; the call then decides nothing.

    This is what a grown vocabulary does: once each CRM table had approved everyday names, the
    selector was shown 282 tables, kept 282, and charged the person ninety seconds for it.
    """
    from semantic_layer.runtime.compiler import ExistingCompiler

    class _Selector:
        def __init__(self):
            self.calls = 0

        def select(self, *a, **kw):
            self.calls += 1
            raise AssertionError("bir şey elenemiyorken seçiciye sorulmamalı")

    sq = resolve(catalog, profiles + [orders()], "iptal edilen sipariş sayısı")
    compiler = ExistingCompiler.__new__(ExistingCompiler)
    compiler.selector, compiler.selector_mode = _Selector(), "on"
    compiler.by_entity = {p.entity: p for p in profiles}
    compiler.catalog_entities = {"CLCARD", "INVOICE", "STLINE"}
    kept = compiler.narrow(sq, ["CLCARD", "INVOICE", "STLINE"])
    assert kept == ["CLCARD", "INVOICE", "STLINE"] and compiler.selector.calls == 0
