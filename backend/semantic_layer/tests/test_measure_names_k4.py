"""2026-09-25, müşteri VM'i (K4): tanımlı ölçü vardı ama soru ona bağlanmadı.
- "Ağustos 2026'da toplam satış fatura tutarı" → SUM(INVOICE.TOTALVAT): "satış fatura" filtreye gitti, kalan "tutarı"
  entity'deki ilk "…tutar" kolonundan birleştirildi — "fatura KDV tutarı". STLINE'da aynı yol "iskonto tutarı"nı buluyordu.
- "2026 ağustos toplam kdvli satış tutarı" dört kez soruldu, model üç ayrı formül yazdı (161,4 / 87,9 / 171,1 Mn).
- "son üç ay aylık …" dönemi hiç okunmadı (sayı "üç ay"ı yuttu), "geçen/geçtiğimiz üç ay" okunmadı.
- "toplam" dilbilgisi sayıldığı için "toplam KDV", "fatura toplam tutarı" gibi sertifikalı adlar hiç aranmadı."""
from __future__ import annotations

from datetime import date

from semantic_layer.evidence.engine import EvidenceEngine
from semantic_layer.history.question_facts import extract_question_facts
from semantic_layer.models import Mapping, SemanticType
from semantic_layer.normalize import fold
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.runtime.temporal import parse_temporal
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import _certify, catalog  # noqa: F401

TODAY = date(2026, 9, 27)
INV = "LG_{n0}_{n1}_INVOICE"


def test_last_n_months_said_four_ways_and_a_count_never_takes_the_unit():
    for q in ("son üç ay aylık satış faturası sayısı", "geçen üç ay satış tutarı",
              "geçtiğimiz üç ay için aylık kaç satış faturası kesilmiş", "son 3 ayda aylık kesilen satış"):
        slots, _ = parse_temporal(q, TODAY)
        assert [(s.primitive, s.start, s.end) for s in slots] == [("LAST_N_MONTHS", date(2026, 7, 1), date(2026, 10, 1))], (q, slots)
    slots, _ = parse_temporal("son yirmi dört ay ciro", TODAY)
    assert slots[0].params["n"] == 24, slots
    slots, _ = parse_temporal("geçen ay ciro", TODAY)
    assert slots[0].primitive == "LAST_MONTH", slots


def test_toplam_and_dahil_stay_inside_a_name_that_names_something():
    keys = {k for _, _, k in extract_question_facts("2026 ağustos toplam kdv", n_max=4).terms}
    assert "toplam kdv" in keys, keys
    keys = {k for _, _, k in extract_question_facts("2026 ağustos kdv dahil satış tutarı", n_max=4).terms}
    assert "kdv dahil satis tutar" in keys, keys
    keys = {k for _, _, k in extract_question_facts("2026 toplam tutar", n_max=4).terms}
    assert not any(k.startswith("toplam") for k in keys), keys       # measure words alone: still grammar


def test_a_composed_measure_column_must_be_named_by_the_question():
    pick = SemanticResolver._named_measure_column
    cands = [("TOTALVAT", "fatura kdv tutarı"), ("NETTOTAL", "satış tutar")]
    assert pick(cands, "tutar", "agustos satis fatura tutari".split()) == ("NETTOTAL", "satış tutar")
    assert pick(cands, "tutar", "iade faturalarinin toplam tutari".split()) is None
    assert pick([("DISTDISC", "iskonto tutarı")], "tutar", "satir tutari".split()) is None
    assert pick([("DISTDISC", "iskonto tutarı")], "tutar", "iskonto tutari".split()) == ("DISTDISC", "iskonto tutarı")


def _resolver(catalog, profiles):
    _certify(catalog, "fatura toplam", SemanticType.METRIC, Mapping(concept_id="", entity="INVOICE", table_pattern=INV,
             formula="SUM(INVOICE.NETTOTAL)"), synonyms=["fatura tutarı", "fatura toplam tutarı", "toplam tutar"])
    _certify(catalog, "fatura sayısı", SemanticType.METRIC, Mapping(concept_id="", entity="INVOICE", table_pattern=INV,
             formula="COUNT(INVOICE.LOGICALREF)"))
    _certify(catalog, "iade faturası", SemanticType.DIMENSION_VALUE, Mapping(concept_id="", entity="INVOICE", table_pattern=INV,
             column="TRCODE", operator="IN", values=["2", "3"]))
    _certify(catalog, "kdvli tutar", SemanticType.METRIC, Mapping(concept_id="", entity="INVOICE", table_pattern=INV,
             formula="SUM(INVOICE.NETTOTAL)"))
    EvidenceEngine(catalog, min_support=3).run(TENANT, DS, profiles)
    return SemanticResolver(catalog, TENANT, DS, profiles)


def _metrics(sq):
    return [fold((s.explain or {}).get("canonical") or s.term) for s in sq.slots if s.semantic_type == SemanticType.METRIC]


def test_the_document_noun_names_both_the_filter_and_the_measure(catalog, profiles):
    r = _resolver(catalog, profiles)
    for q in ("2025 yılı iade faturalarının toplamı ne kadar", "2025 yılı iade faturalarının toplam tutarı"):
        sq = r.resolve(q, today=TODAY)
        assert _metrics(sq) == ["fatura toplam"], (q, _metrics(sq), sq.explanation)
        assert any(s.mapping and s.mapping.column == "TRCODE" for s in sq.slots), (q, sq.slots)


def test_the_second_measure_of_a_list_is_read_on_the_table_already_read(catalog, profiles):
    r = _resolver(catalog, profiles)
    sq = r.resolve("2026 iade faturalarının sayısı ve toplam tutarı", today=TODAY)
    assert sorted(_metrics(sq)) == ["fatura sayisi", "fatura toplam"], (_metrics(sq), sq.explanation)


def test_a_measure_modifier_without_a_certified_measure_is_asked_not_guessed(catalog, profiles):
    r = _resolver(catalog, profiles)
    sq = r.resolve("2026 ağustos kdvli satış tutarı", today=TODAY)
    assert "kdvli" not in sq.unresolved, sq.unresolved
    assert any("kdvli tutar" in c for c in sq.clarification), sq.clarification
