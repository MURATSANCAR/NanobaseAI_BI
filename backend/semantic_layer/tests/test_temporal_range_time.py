"""2026-09-26, müşteri VM'i (K3): "20.08.2026 03:00:00 ve 21.08.2026 03:00:00 arasındaki toplam net sipariş tutarı"
üç kez soruldu; iki günün kıyası olarak derlendi (iki kolon), ISO yazımı ("2026-08-20 03:00:00") yıl sanıldı,
"21.008.2026" okunmadı, "saat 03:00" tanımsız niteleyici diye reddedildi. Saat bu kayıtlarda sertifikalı bir alan
olmadığından aralık gün sınırıyla kurulur ve saat geri sorulur."""
from __future__ import annotations

from datetime import date

from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.runtime.temporal import parse_temporal
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import catalog  # noqa: F401

TODAY = date(2026, 9, 26)


def _one(q):
    slots, _ = parse_temporal(q, TODAY)
    assert len(slots) == 1, [(s.text, s.primitive) for s in slots]
    return slots[0]


def test_ve_arasinda_joins_two_dated_ends_into_one_span_and_keeps_the_times():
    for q in ("20.08.2026 03:00:00 ve 21.08.2026 03:00:00 arasındaki toplam net sipariş tutarı nedir?",
              "2026-08-20 03:00:00 ve 2026-08-21 03:00:00 arasındaki toplam net sipariş tutarı nedir?",
              "20.08.2026 03:00:00 ve 21.008.2026 03:00:00 arasındaki toplam net sipariş tutarı nedir?",
              "20 ağustos 2026 saat 03:00 ve 21 ağustos  2026 saat 03:00 arasındaki toplam net satış tutarı nedir?"):
        s = _one(q)
        assert (s.primitive, s.start, s.end) == ("RANGE", date(2026, 8, 20), date(2026, 8, 22)), (q, s)
        assert s.params.get("from_time", "").startswith("03:00") and s.params.get("to_time", "").startswith("03:00"), (q, s.params)


def test_a_bare_ve_still_means_two_periods_and_a_plain_day_has_no_time():
    slots, _ = parse_temporal("2025 ve 2026 cirosu yan yana", TODAY)
    assert [s.primitive for s in slots] == ["YEAR", "YEAR"], slots
    s = _one("20 ağustos 2026 toplam net sipariş tutarı nedir?")
    assert (s.primitive, s.start) == ("DATE", date(2026, 8, 20)) and "time" not in s.params, s
    s = _one("2026-08-20 günü satış")
    assert (s.primitive, s.start) == ("DATE", date(2026, 8, 20)), s


def test_a_time_of_day_is_asked_back_with_the_day_bounds(catalog, profiles):
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("20.08.2026 03:00:00 ve 21.08.2026 03:00:00 arasındaki toplam satış tutarı nedir?", today=TODAY)
    assert len(sq.temporal) == 1 and sq.temporal[0].primitive == "RANGE", sq.temporal
    assert any("saat" in c and "20.08.2026–21.08.2026" in c for c in sq.clarification), sq.clarification
    sq = r.resolve("20 ağustos 2026 toplam satış tutarı nedir?", today=TODAY)
    assert not any("saat" in c for c in sq.clarification), sq.clarification


def test_closing_verbs_are_not_undefined_terms(catalog, profiles):
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    for q in ("1 şubat 2026 tarihinde kaç adet satış gerçekleşmiştir?", "2026 ocak ayında satılan kitapların listesini hazırlar mısın"):
        sq = r.resolve(q, today=TODAY)
        assert not {"gerceklesmistir", "hazirlar"} & set(sq.unresolved), (q, sq.unresolved)


def test_a_request_verb_is_ignored_but_the_same_stem_in_an_account_name_is_not(catalog, profiles):
    """Tam set 2026-09-26: "hazırlar" dilbilgisi listesine eklenince kökü "hazır"ı da yuttu, "108 Diğer Hazır
    Değerler" hesabı düştü. İsteğin fiili soru ekinden (mısın/misiniz) tanınır, sözcük listesiyle değil."""
    r = SemanticResolver(catalog, TENANT, DS, profiles)
    sq = r.resolve("2026 ocak ayında satılan kitapların listesini hazırlar mısın", today=TODAY)
    assert "hazirlar" not in sq.unresolved, sq.unresolved
    from semantic_layer.normalize import STOPWORDS_S, stem
    assert stem("hazir") not in STOPWORDS_S and "hazir" not in STOPWORDS_S
