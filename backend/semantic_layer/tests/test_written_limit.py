"""A top-N said in words is a row limit; a number naming a span is not."""
from __future__ import annotations

from datetime import date

from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import catalog  # noqa: F401

TODAY = date(2026, 9, 16)


def resolve(catalog, profiles, q):
    return SemanticResolver(catalog, TENANT, DS, profiles).resolve(q, today=TODAY)


def test_a_written_ten_a_few_words_after_the_ranking_cue_is_the_row_limit(catalog, profiles):
    """2026-09-16, soru 5: 'on müşteri' istendi, 1.670 satır döndü — 'en çok' sayıdan dört kelime öndeydi."""
    sq = resolve(catalog, profiles, "En çok satış yaptığımız on müşteriyi kanal bazında sıralar mısın?")
    assert sq.limit == 10, (sq.limit, sq.ignored, sq.explanation)
    assert resolve(catalog, profiles, "İlk beş kanalın net cirosu").limit == 5


def test_a_number_naming_a_span_is_not_a_row_limit(catalog, profiles):
    assert resolve(catalog, profiles, "Alacaklarımızı otuz, altmış, doksan gün diye yaşlandırıp gösterebilir misin?").limit is None
    assert resolve(catalog, profiles, "En çok satan kanallarda son üç ay net ciro").limit is None


def test_a_counting_word_is_never_read_as_a_column(catalog, profiles):
    sq = resolve(catalog, profiles, "Toptan satış kaç tane?")
    assert not [s for s in sq.slots if s.term in ("tane", "adet")], sq.slots
    assert "tane" not in [c.get("term") for c in (sq.candidates or [])]


def test_a_count_over_a_certified_phrase_counts_that_phrases_entity(catalog, profiles):
    sq = resolve(catalog, profiles, "Toptan kaç tane?")
    counted = [s for s in sq.slots if (s.explain or {}).get("source") == "count_cue"]
    assert counted and counted[0].mapping.entity == "INVOICE", [(s.term, s.mapping.entity if s.mapping else None) for s in sq.slots]
