"""2026-09-25, müşteri VM'i: "2022 satış adedi", "2026 ağustos toplam satış miktarı", "kaç adet satış oldu" —
on gerçek sorunun hepsi SUM(LINENET) (tutar) döndü; "adet" n-gram eşleştiricide niteleyici sayılıp hiç eşleşmeye
girmiyor, "miktar" katalogda yok. Adet sözcüğü bir değer ölçüsünün yanındaysa o ölçünün sertifikalı adet karşılığı
("satış" ↔ "satılan adet") seçilir; karşılık yoksa tutar verilmez, geri sorulur."""
from __future__ import annotations

from datetime import date

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.models import Mapping, SemanticType
from semantic_layer.normalize import fold
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import _certify, catalog  # noqa: F401

TODAY = date(2026, 9, 25)
STL = "LG_{n0}_{n1}_STLINE"


def _resolver(catalog, profiles):
    _certify(catalog, "satış tutarı", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern=STL,
             formula="SUM(CASE WHEN STLINE.TRCODE IN (7, 8, 9) THEN STLINE.LINENET ELSE 0 END)",
             extra={"func": "SUM", "conditions": ["STLINE.INVOICEREF NOT IN (0)"]}), synonyms=["satış"])
    # "satilan adet" (STLINE.AMOUNT) ortak test kataloğunda zaten sertifikalı (test_runtime.catalog).
    _certify(catalog, "iade tutarı", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern=STL,
             formula="SUM(CASE WHEN STLINE.TRCODE IN (2, 3) THEN STLINE.LINENET ELSE 0 END)", extra={"func": "SUM"}), synonyms=["iade"])
    _certify(catalog, "iade adedi", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern=STL,
             formula="SUM(CASE WHEN STLINE.TRCODE IN (2, 3) THEN STLINE.AMOUNT ELSE 0 END)", extra={"func": "SUM"}))
    _certify(catalog, "brüt kâr marjı", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern=STL,
             formula="1 - SUM(STLINE.OUTCOST) / NULLIF(SUM(STLINE.TOTAL), 0)", extra={"func": "SUM"}), synonyms=["brüt"])
    _certify(catalog, "stok bakiyesi", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern=STL,
             formula="SUM(CASE WHEN STLINE.TRCODE IN (1, 2) THEN STLINE.AMOUNT ELSE -STLINE.AMOUNT END)",
             extra={"state_measure": True}), synonyms=["stok"])
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    return SemanticResolver(catalog, TENANT, DS, profiles)


def _metrics(sq):
    return [(fold((s.explain or {}).get("canonical") or s.term), s.mapping.formula if s.mapping else None) for s in sq.slots
            if s.semantic_type == SemanticType.METRIC]


def test_unit_word_after_a_value_measure_reads_its_quantity_twin(catalog, profiles):
    r = _resolver(catalog, profiles)
    for q in ("2022 satış adedi", "2026 ağustos toplam satış miktarı", "2026 mayıs satış adedi"):
        sq = r.resolve(q, today=TODAY)
        ms = _metrics(sq)
        assert [m for m, _ in ms] == ["satilan adet"], (q, ms, sq.explanation)
        assert not any("LINENET" in (f or "") for _, f in ms), (q, ms)
        assert not sq.clarification, (q, sq.clarification)


def test_unit_word_before_the_measure_reads_the_same_twin(catalog, profiles):
    sq = _resolver(catalog, profiles).resolve("2022'de kaç adet satış oldu", today=TODAY)
    assert [m for m, _ in _metrics(sq)] == ["satilan adet"], (_metrics(sq), sq.explanation)


def test_a_qualifier_the_twin_does_not_carry_is_asked_back_not_answered_with_the_amount(catalog, profiles):
    """"brüt satış adedi": brüt kâr marjı + satış tutarı döndü. Katalogda brüt adet ölçüsü yok → geri sorulur."""
    sq = _resolver(catalog, profiles).resolve("2026 şubat ayı brüt satış adedi", today=TODAY)
    assert sq.clarification and any("adet" in c for c in sq.clarification), (sq.clarification, sq.explanation)
    assert sq.unhandled, sq.unhandled


def test_a_certified_quantity_name_and_a_balance_unit_are_left_alone(catalog, profiles):
    r = _resolver(catalog, profiles)
    sq = r.resolve("2025 iade adedi", today=TODAY)
    assert [m for m, _ in _metrics(sq)] == ["iade adedi"], _metrics(sq)
    sq = r.resolve("stok adedi en yüksek on kitap", today=TODAY)
    ms = _metrics(sq)
    assert len(ms) == 1 and ms[0][0] == "stok bakiyesi", ms
    assert not sq.clarification, sq.clarification


def test_the_amount_is_still_the_amount(catalog, profiles):
    sq = _resolver(catalog, profiles).resolve("2022 satış tutarı", today=TODAY)
    assert [m for m, _ in _metrics(sq)] == ["satis tutari"], _metrics(sq)


def test_a_listed_unit_word_and_a_quantity_measure_keep_their_old_reading(catalog, profiles):
    """Tam set regresyonu 2026-09-25: "ciro, adet ve iade" bir liste; "sevk adedi"nde sevk zaten adet ölçüsü
    ("sevk edilen adet" eş anlamlısıyla). İkisinde de geri soru sorulmaz."""
    _certify(catalog, "sevkiyat", SemanticType.METRIC, Mapping(concept_id="", entity="STLINE", table_pattern=STL,
             formula="SUM(STLINE.AMOUNT)", extra={"func": "SUM", "conditions": ["STLINE.TRCODE IN (8)"]}), synonyms=["sevk", "sevk edilen adet"])
    r = _resolver(catalog, profiles)
    sq = r.resolve("2024 ile 2025'i ciro, adet ve iade açısından yan yana koy.", today=TODAY)
    assert not sq.clarification, sq.clarification
    sq = r.resolve("Kargo çıkış şubesine göre sevk adedi nasıl dağılıyor?", today=TODAY)
    assert not any("adet" in c for c in sq.clarification), sq.clarification
