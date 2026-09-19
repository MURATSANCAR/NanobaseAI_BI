from datetime import date

from semantic_layer.normalize import alias_tokens, clauses, fold, normalize_term, stem, tokenize
from semantic_layer.runtime.temporal import parse_temporal
from semantic_layer.tests.test_runtime import catalog  # noqa: F401


def test_fold_and_tokenize_turkish():
    assert fold("Toptan SATIŞLARI İade") == "toptan satislari iade"
    assert tokenize("Kanal bazında, net ciro?") == ["kanal", "bazinda", "net", "ciro"]


def test_stem_is_symmetric_and_protects_short_terms():
    assert stem("toptan") == "toptan"
    assert stem("satislari") == stem("satis") == "satis"
    assert stem("musterinin") == stem("musteri")
    assert normalize_term("Net Ciroya") == normalize_term("net ciro")


def test_clauses_and_alias_tokens():
    assert clauses("iade tutarı, aynı müşterinin (2026) satış") == ["iade tutarı", "aynı müşterinin", "2026", "satış"]
    assert alias_tokens("perakende_toplam") == ["perakende", "toplam"]
    assert alias_tokens("netCiro") == ["net", "ciro"]


def test_temporal_primitives():
    today = date(2026, 9, 6)
    slots, grain = parse_temporal("Son 30 günde toptan satış", today)
    assert slots[0].primitive == "LAST_N_DAYS" and slots[0].start == date(2026, 8, 7) and slots[0].end == date(2026, 9, 7)
    slots, grain = parse_temporal("2026 Ocak–Ağustos için ay bazında iskonto oranı", today)
    assert slots[0].primitive == "MONTH_RANGE" and slots[0].start == date(2026, 1, 1) and slots[0].end == date(2026, 9, 1) and grain == "MONTH"
    slots, _ = parse_temporal("Temmuz 2026'da en çok satan 15 kitap", today)
    assert slots[0].primitive == "MONTH" and slots[0].start == date(2026, 7, 1) and slots[0].end == date(2026, 8, 1)
    slots, _ = parse_temporal("geçen ay net ciro", today)
    assert slots[0].primitive == "LAST_MONTH" and slots[0].start == date(2026, 8, 1) and slots[0].end == date(2026, 9, 1)
    slots, _ = parse_temporal("yıl başından beri ciro", today)
    assert slots[0].primitive == "YTD" and slots[0].start == date(2026, 1, 1)


def test_ambiguous_recent_is_not_guessed():
    slots, _ = parse_temporal("Günlük satış tutarı (son günler) nedir?", date(2026, 9, 6))
    amb = [s for s in slots if s.ambiguous]
    assert amb and amb[0].primitive == "AMBIGUOUS_RECENT" and amb[0].start is None


def test_grain_plural_gore_forms():
    """"aylara göre" tek sayı dönüyordu: yalnız "aya göre" tanınıyordu."""
    today = date(2026, 9, 11)
    for q, want in [
        ("aylara göre net ciro", "MONTH"),
        ("net ciroyu aylara böl", "MONTH"),
        ("yıllara göre iade tutarı", "YEAR"),
        ("haftalara göre sipariş sayısı", "WEEK"),
        ("çeyreklere göre net ciro", "QUARTER"),
        ("günlere göre fatura adedi", "DAY"),
    ]:
        _, grain = parse_temporal(q, today)
        assert grain == want, (q, grain)


def test_singular_gore_is_a_comparison_not_a_grain():
    """"geçen yıla göre" karşılaştırmadır; yıllık kırılım sanılırsa karşılaştırma bozulur."""
    today = date(2026, 9, 11)
    for q in ("geçen yıla göre net ciro", "geçen haftaya göre sipariş", "geçen çeyreğe göre iade"):
        _, grain = parse_temporal(q, today)
        assert grain not in ("YEAR", "WEEK", "QUARTER"), (q, grain)


def test_yearly_breakdown_without_a_period_spans_every_observed_year(catalog, profiles):
    """"Yıllara göre net ciro" tek yıl döndürüyordu: dönemsiz soruya varsayılan "bu yıl" uygulanıyordu."""
    from semantic_layer.models import TemporalSlot
    from semantic_layer.runtime import periods
    from semantic_layer.runtime.resolver import SemanticResolver
    from semantic_layer.tests.conftest import DS, TENANT

    this_year = TemporalSlot(text="bu yıl", primitive="YEAR", start=date(2026, 1, 1), end=date(2027, 1, 1), grain="YEAR")
    r = SemanticResolver(catalog, TENANT, DS, profiles, default_temporal=this_year)
    sq = r.resolve("yıllara göre net ciro", today=date(2026, 7, 20))
    assert sq.grain == "YEAR"
    entity = next(s.mapping.entity for s in sq.metrics if s.mapping)
    first = periods.spans(r.tables_of[entity])[0].year
    assert len(sq.temporal) == 1 and sq.temporal[0].params.get("allYears"), [t.to_dict() for t in sq.temporal]
    assert sq.temporal[0].start == date(first, 1, 1) and sq.temporal[0].end == date(2027, 1, 1)


def test_a_named_year_still_wins_over_the_yearly_span(catalog, profiles):
    from semantic_layer.runtime.resolver import SemanticResolver
    from semantic_layer.tests.conftest import DS, TENANT

    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("2025 yılı yıllara göre net ciro", today=date(2026, 7, 20))
    assert not any(t.params.get("allYears") for t in sq.temporal)


def test_annual_alone_is_not_a_breakdown_over_years(catalog, profiles):
    """"yıllık net ciro" bu yılın tutarı olabilir; yıllara yayılmayı yalnız açık kırılım ister."""
    from semantic_layer.models import TemporalSlot
    from semantic_layer.runtime.resolver import SemanticResolver
    from semantic_layer.tests.conftest import DS, TENANT

    this_year = TemporalSlot(text="bu yıl", primitive="YEAR", start=date(2026, 1, 1), end=date(2027, 1, 1), grain="YEAR")
    r = SemanticResolver(catalog, TENANT, DS, profiles, default_temporal=this_year)
    sq = r.resolve("yıllık net ciro", today=date(2026, 7, 20))
    assert not any(t.params.get("allYears") for t in sq.temporal)
