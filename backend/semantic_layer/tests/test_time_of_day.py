"""2026-09-28: "20.08.2026 03:00 ile 21.08.2026 03:00 arasındaki toplam net sipariş tutarı" — saat K3'ten beri geri
soruluyordu, çünkü saati taşıyan kolon beyan edilmemişti. Logo belgenin saatini tarihin yanında tamsayı tutar
(TIME_/FTIME = saat*2^24 + dakika*2^16 + saniye*2^8); `equivalences.yml` → `time_of_day` beyanıyla aralığın iki uç
günü saatle kırpılır. Tek bir saat ("03:00'te") hâlâ geri sorulur: "arası" değil "anı" sorar."""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

from semantic_layer.conventions import TIME_ENCODINGS, Conventions
from semantic_layer.runtime.compiler import DeterministicCompiler
from semantic_layer.runtime.resolver import SemanticResolver
from semantic_layer.runtime.temporal import parse_temporal
from semantic_layer.tests.conftest import DS, TENANT
from semantic_layer.tests.test_runtime import catalog  # noqa: F401

TODAY = date(2026, 9, 28)


def test_logo_packed_time():
    assert TIME_ENCODINGS["logo_packed"](11, 20, 0) == 185860096        # .155'te gözlenen FTIME
    assert TIME_ENCODINGS["logo_packed"](3, 0, 0) == 3 * 16777216


def _conv(profiles):
    conv = Conventions.from_profiles(profiles)
    conv.times_of_day = {"INVOICE": {"column": "TIME_", "encoding": "logo_packed", "reason": "test"}}
    return conv


def test_a_span_between_two_times_is_not_asked_when_the_time_is_declared(catalog, profiles):
    r = SemanticResolver(catalog, TENANT, DS, profiles, conventions=_conv(profiles))
    sq = r.resolve("14.08.2026 03:00:00 ve 15.08.2026 03:00:00 arasındaki toplam satış tutarı nedir?", today=TODAY)
    assert not any("saat" in c for c in sq.clarification), sq.clarification
    assert any("saatle birlikte" in e and "INVOICE.TIME_" in e for e in sq.explanation), sq.explanation
    sq = r.resolve("14.08.2026 03:00 toplam satış tutarı nedir?", today=TODAY)          # a single time: asked
    assert any("saat" in c for c in sq.clarification), sq.clarification


def test_the_edge_days_are_trimmed_by_time(profiles):
    comp = DeterministicCompiler.__new__(DeterministicCompiler)
    comp.conventions = _conv(profiles)
    slot = parse_temporal("14.08.2026 03:00 ve 15.08.2026 03:30 arasındaki satış", TODAY)[0][0]
    plan = SimpleNamespace(entity="INVOICE", date_column="DATE_")
    d = SimpleNamespace(q=lambda c: c)
    explain = []
    out = comp._time_of_day_bounds(plan, "I", slot, d, explain)
    assert out == [f"(I.DATE_ >= '2026-08-15' OR I.TIME_ >= {3 * 16777216})",
                   f"(I.DATE_ < '2026-08-15' OR I.TIME_ < {3 * 16777216 + 30 * 65536})"], out
    plan = SimpleNamespace(entity="STLINE", date_column="DATE_")          # not declared: nothing added
    assert comp._time_of_day_bounds(plan, "S", slot, d, []) == []
