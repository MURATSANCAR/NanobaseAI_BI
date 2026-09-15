"""A request written the way a manager writes it, not the way a catalog is keyed.

Measured live on 2026-09-15: the sentence below stopped at a clarification about "olan", read
"31 ağustosa kadar" as year-to-today and "2025 … 8 aylık" as the whole of 2025. Each of those is a
reading of ordinary Turkish, not a catalog gap, and none may reach the person as a question."""
from datetime import date

from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.runtime.temporal import parse_temporal
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import catalog  # noqa: F401

TODAY = date(2026, 9, 15)
PROMPT = ("Yılbaşından 31 ağustosa kadar tüm satış yerlerimizle olan ciromuz. 2025 yılını da aynı şekilde "
          "8 aylık olarak yan sütuna ekleyin. Satış noktalarının hangi vilayette olduğu ve hangi bmt ye "
          "bağlı olduğu da ayrıca yan sütunda bulunsun")


def test_a_range_that_ends_on_a_named_day_and_its_mirror_year():
    slots, _ = parse_temporal(PROMPT, today=TODAY)
    spans = [(s.start, s.end) for s in slots]
    assert (date(2026, 1, 1), date(2026, 9, 1)) in spans, spans
    assert (date(2025, 1, 1), date(2025, 9, 1)) in spans, spans
    assert len(slots) == 2, [s.text for s in slots]


def test_month_end_and_bare_day_forms():
    assert [(s.start, s.end) for s in parse_temporal("ağustos sonuna kadar ciro", today=TODAY)[0]] == [(date(2026, 1, 1), date(2026, 9, 1))]
    assert [(s.start, s.end) for s in parse_temporal("15 mayısa kadar satış", today=TODAY)[0]] == [(date(2026, 1, 1), date(2026, 5, 16))]
    assert [(s.start, s.end) for s in parse_temporal("2024 yılının ilk 6 ayı", today=TODAY)[0]] == [(date(2024, 1, 1), date(2024, 7, 1))]


def test_grammar_and_presentation_words_are_not_questions_for_the_person(catalog, profiles):
    sq = SemanticResolver(catalog, TENANT, DS, profiles).resolve(PROMPT, today=TODAY)
    assert not sq.clarification, sq.clarification
    assert "olan" not in sq.unhandled and "oldugu" not in sq.unhandled
    for w in ("yan", "sutuna", "sutunda", "ekleyin", "bulunsun", "olan", "oldugu", "ayrica", "sekilde", "kadar", "ayni"):
        assert w not in sq.unresolved, (w, sq.unresolved)
    assert sq.comparison and sq.comparison["current"]["end"] == "2026-09-01" and sq.comparison["reference"]["end"] == "2025-09-01", sq.comparison
    # what the catalog really lacks stays visible — that is the person's next job, not a guess
    assert {"vilayette", "bmt"} & set(sq.unresolved), sq.unresolved


def test_record_verbs_narrow_nothing(catalog, profiles):
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    for q in ("2026 ay bazında açılan sipariş sayısı", "En çok iade alan 10 müşteri kimler?", "kesilen faturaların toplam tutarı"):
        sq = r.resolve(q, today=TODAY)
        assert not sq.clarification, (q, sq.clarification)
        assert not sq.unhandled, (q, sq.unhandled)
