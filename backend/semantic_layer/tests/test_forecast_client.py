"""Ortak yapı taşı 6 (`semantic_bridge.forecast_client`): Baskı Öneri tahmin önbelleğini kantilleriyle okuyan tek istemci.
Kantil yoksa aralık uydurulmaz («aralık yok»). Bütçe ve stok bu istemciyi kullanır.

Saf işlevler; önbellek dosyası geçici klasörde yapay içerikle. Gerçek önbellek kabulü test sunucusunda.
"""

from __future__ import annotations

import json

from semantic_bridge import budget_sources as bsrc
from semantic_bridge import forecast_client as FC
from semantic_bridge import stock as S


def _snap(with_range=True):
    fc = {"K1": {"p50": [10, 20, 30] + [10] * 9, "p80": [12] * 12}, "K2": {"p50": [5] * 12}}
    if with_range:
        fc["K1"]["p10"] = [5, 10, 15] + [5] * 9
        fc["K1"]["p90"] = [20, 40, 60] + [20] * 9
    return {"updatedAt": 1.0, "data": {"forecastStart": "2026-09", "dataEnd": "2026-08-17", "horizon": 12, "forecasts": fc}}


def test_read_keeps_quantiles_and_p50_for_old_readers(tmp_path, monkeypatch):
    (tmp_path / FC.REPORT_FILE).write_text(json.dumps(_snap()))
    monkeypatch.setenv("MANAGEMENT_REPORT_CACHE_DIR", str(tmp_path))
    fc = bsrc.read_forecast()
    assert fc["start"] == "2026-09" and fc["p50"]["K2"] == [5.0] * 12
    assert fc["p10"]["K1"][:3] == [5.0, 10.0, 15.0] and "K2" not in fc["p10"]
    assert fc["kantiller"] == ["p10", "p50", "p80", "p90"] and FC.has_range(fc)
    (tmp_path / FC.REPORT_FILE).write_text("bozuk")
    assert bsrc.read_forecast() == {}


def test_window_band_and_honest_no_range():
    fc = FC.parse(_snap())
    w = FC.window(fc, "K1")
    assert w["aralik"] and w["g30"] == {"p10": 5, "p50": 10, "p90": 20, "aralik": True, "not": None}
    assert w["g90"]["p10"] == 30 and w["g90"]["p50"] == 60 and w["g90"]["p90"] == 120
    w2 = FC.window(fc, "K2")                                   # kantili olmayan kitap: yalnız p50
    assert w2["aralik"] is False and w2["not"] == FC.NO_RANGE and w2["g90"] == {"p10": None, "p50": 15, "p90": None,
                                                                                 "aralik": False, "not": FC.NO_RANGE}
    assert FC.window(fc, "YOK") is None
    fc_old = FC.parse(_snap(with_range=False))
    assert not FC.has_range(fc_old) and FC.window(fc_old, "K1")["aralik"] is False


def test_totals_offsets_and_weights():
    fc = FC.parse(_snap())
    assert FC.total(fc, "K1", "p50") == 150 and FC.total(fc, "K1", "p10") == 75 and FC.total(fc, "K2", "p10") is None
    assert FC.month_offset(fc, 2026, 9) == 0 and FC.month_offset(fc, 2026, 12) == 3 and FC.month_offset(fc, 2026, 8) == -1
    b = FC.band(fc, "K1", [0, 1], {0: 0.5, 1: 1.0})
    assert b["p50"] == 25 and b["p10"] == 12.5 and b["p90"] == 50


def test_stock_item_carries_range_next_to_p50():
    fc = FC.parse(_snap())
    assert S.forecast_window(fc, "K1") == {"baslangic": "2026-09", "g30": 10, "g60": 30, "g90": 60}
    assert S.forecast_range(fc, "K1")["g60"]["p90"] == 60
    assert S.forecast_range({"start": "2026-09", "p50": {"K1": [1, 2, 3]}}, "K1")["aralik"] is False
