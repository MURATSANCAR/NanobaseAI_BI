"""Karşılaştırma isteyen soru, karşılaştırma üretilmeden başarılı sayılamaz.

"Geçen yıla göre" tek dönem olarak okunuyordu ve okunan dönem *referans* olandı: soru "bu yıl geçen
yıla göre nasıl" iken cevap yalnız geçen yılın rakamıydı. Ne karşılaştırma vardı, ne de eksikliği
söyleniyordu — tek bir sayı, başarılı görünerek dönüyordu.
"""
from __future__ import annotations

from datetime import date

from semantic_layer.models import TemporalSlot
from semantic_layer.runtime.audit import unmet_obligations
from semantic_layer.runtime.compiler import DeterministicCompiler, default_filters_provider
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import catalog, _run  # noqa: F401

THIS_YEAR = TemporalSlot(text="bu yıl", primitive="YEAR", start=date(2026, 1, 1), end=date(2027, 1, 1), grain="YEAR")


def _resolver(catalog, profiles):
    return SemanticResolver(catalog, TENANT, DS, profiles, default_temporal=THIS_YEAR)


def test_a_comparison_request_is_recorded_and_carries_both_periods(catalog, profiles):
    r = _resolver(catalog, profiles)
    sq = r.resolve("geçen yıla göre net ciro", today=date(2026, 7, 20))
    assert sq.comparison and sq.comparison["kind"] == "PERIOD"
    spans = {(t.start, t.end) for t in sq.temporal}
    assert (date(2026, 1, 1), date(2027, 1, 1)) in spans, sq.to_dict()
    assert (date(2025, 1, 1), date(2026, 1, 1)) in spans, sq.to_dict()
    assert any("karşılaştırma isteği" in e for e in sq.explanation)


def test_the_compiled_query_puts_the_two_periods_side_by_side(catalog, profiles, logo_db):
    """Kontrollü veri: 2026 ve 2025 rakamları farklı, ve ikisi de sonuçta ayrı sütun olarak görünür."""
    r = _resolver(catalog, profiles)
    comp = DeterministicCompiler(profiles, {"n0": "411", "n1": "01"}, "sqlite",
                                 default_filters=default_filters_provider(catalog, TENANT, DS))
    sq, out, cols, rows = _run(comp, catalog, r, logo_db, "geçen yıla göre net ciro")
    assert len(cols) >= 2, (cols, out.sql)
    assert unmet_obligations(sq, out.sql) == [], out.sql
    values = [v for v in rows[0]]
    assert len(values) >= 2 and values[0] != values[1], (cols, values)


def test_a_statement_that_dropped_one_period_is_reported_not_answered(catalog, profiles):
    """Yükümlülük denetimi: iki dönemden biri sorguya taşınmamışsa cevap başarılı sayılamaz."""
    r = _resolver(catalog, profiles)
    sq = r.resolve("geçen yıla göre satış tutarı", today=date(2026, 7, 20))
    only_reference = ("SELECT SUM(INVOICE.NETTOTAL) FROM LG_411_01_INVOICE AS INVOICE "
                      "WHERE INVOICE.DATE_ >= '2025-01-01' AND INVOICE.DATE_ < '2026-01-01'")
    problems = unmet_obligations(sq, only_reference)
    assert problems and "2026-01-01" in problems[0], problems

    both = ("SELECT SUM(CASE WHEN INVOICE.DATE_ >= '2026-01-01' AND INVOICE.DATE_ < '2027-01-01' THEN INVOICE.NETTOTAL END) AS bu_yil, "
            "SUM(CASE WHEN INVOICE.DATE_ >= '2025-01-01' AND INVOICE.DATE_ < '2026-01-01' THEN INVOICE.NETTOTAL END) AS gecen_yil "
            "FROM LG_411_01_INVOICE AS INVOICE")
    assert unmet_obligations(sq, both) == []


def test_a_reference_period_with_no_data_is_still_a_comparison(catalog, profiles, logo_db):
    """Önceki dönemde veri yoksa cevap yine iki sütun olmalı: boş bir dönem, karşılaştırmanın
    yapılmadığı anlamına gelmez; boş dönem NULL kalmalı, sıfıra çevrilmemeli."""
    r = SemanticResolver(catalog, TENANT, DS, profiles,
                         default_temporal=TemporalSlot(text="bu yıl", primitive="YEAR",
                                                       start=date(2026, 1, 1), end=date(2027, 1, 1), grain="YEAR"))
    comp = DeterministicCompiler(profiles, {"n0": "411", "n1": "01"}, "sqlite",
                                 default_filters=default_filters_provider(catalog, TENANT, DS))
    sq = r.resolve("geçen yıla göre net ciro", today=date(2026, 7, 20))
    # referansı veri olmayan bir yıla çek
    sq.temporal[1] = TemporalSlot(text="2019", primitive="YEAR", start=date(2019, 1, 1), end=date(2020, 1, 1), grain="YEAR")
    sq.comparison["reference"] = sq.temporal[1].to_dict()
    out = comp.compile(sq, catalog)
    assert out is not None, sq.to_dict()
    assert unmet_obligations(sq, out.sql) == [], out.sql
    cur = logo_db.execute(out.sql)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    assert len(cols) >= 2, cols
    # boş dönem sütunu vardır; değeri sıfır ya da NULL olabilir, ama sütun kaybolmaz
    assert len(rows[0]) >= 2 and rows[0][1] is None, rows
