"""Dijital baskı maliyet formu: «AŞIKLARIN HALLERİ-TBK DİJİTAL-05102026.xlsx» Excel'inin kendi sonuçlarıyla."""
from __future__ import annotations

import pytest

from semantic_bridge.pricing import form as F


def _inputs(**over):
    base = {
        "baski": "dijital", "yayinevi": "SUFİ KİTAP", "kitap": "AŞIKLARIN HALLERİ", "simdikiFiyat": 180, "fiyat": None,
        "ozelIskonto": None, "matbaaAyar": None, "sayfa": 208, "adet": 200, "ebat": "13X21",
        "dijital": {"icKagit": " 1/1- 60gr KİTAP KAĞIDI", "renkliSayfa": None, "renkliKagit": " 4/4- 115gr KUŞE-KALİTELİ",
                    "kapakKagit": "BRİSTOL", "kapakGr": 230, "pay": 25,
                    "ekler": {"ayracAtma": False, "ayracRenk": None, "gofre": False, "kulakli": False, "kapakRenk": None,
                              "selofan": False, "lokalLak": False}},
        "diger": {}, "telif": 7, "dolayli": 40,
    }
    base.update(over)
    return base


def test_excel_form_matches_to_the_kurus():
    out = F.compute(_inputs(), F.default_tariff())
    s = out["summary"]
    assert s["matbaaToplam"] == pytest.approx(8840, abs=0.01)       # J19
    assert s["digerToplam"] == pytest.approx(3245, abs=0.01)        # J29 = kapak 725 + telif 2520
    assert s["dolayli"] == pytest.approx(4834, abs=0.01)            # J33
    assert s["genelToplam"] == pytest.approx(16919, abs=0.01)       # J34
    assert s["birimMaliyet"] == pytest.approx(84.595, abs=1e-6)     # J38
    assert s["iskonto"] == 40                                       # I5 (dijital Excel'in yayınevi listesi)
    assert s["satisFiyati"] == pytest.approx(108, abs=1e-6)         # J5
    assert s["karAdet"] == pytest.approx(23.405, abs=1e-6)          # J40
    assert s["toplamKar"] == pytest.approx(4681, abs=0.01)          # J41
    assert s["karYuzde"] == pytest.approx(0.27667119806135115, abs=1e-6)
    assert s["matbaaAdet"] == pytest.approx(47.825, abs=1e-6)       # D33
    assert s["telifAdet"] == pytest.approx(12.6, abs=1e-6)          # D34
    assert s["kagitAdet"] == 0


def test_digital_publisher_discount_differs_from_offset():
    # Ofset listesinde Mavi Kirpi %60, dijital Excel'de %45.
    s = F.compute(_inputs(yayinevi="MAVİ KİRPİ KİTAP"), F.default_tariff())["summary"]
    assert s["iskonto"] == 45


def test_missing_price_asks_for_manual_unit():
    with pytest.raises(F.FormError, match="elle"):
        F.compute(_inputs(ebat="16X24"), F.default_tariff())  # 16X24 kapak fiyatı tabloda boş
    inp = _inputs(ebat="16X24")
    inp["dijital"] = {**inp["dijital"], "kapakBirim": 4}
    s = F.compute(inp, F.default_tariff())["summary"]
    assert s["matbaaToplam"] == pytest.approx(208 * 0.23 * 1.25 * 200, abs=0.01)


def test_color_pages_need_a_price():
    inp = _inputs()
    inp["dijital"] = {**inp["dijital"], "renkliSayfa": 16}
    with pytest.raises(F.FormError):
        F.compute(inp, F.default_tariff())
    inp["dijital"]["renkliBirim"] = 1.2
    out = F.compute(inp, F.default_tariff())
    keys = {ln["key"]: ln["total"] for ln in out["lines"]}
    assert keys["renkliBaski"] == pytest.approx(16 * 1.2 * 1.25 * 200)
    assert keys["icBaski"] == pytest.approx(192 * 0.17 * 1.25 * 200)


def test_extras_and_lak():
    inp = _inputs(adet=6000)
    inp["dijital"] = {**inp["dijital"], "ekler": {"ayracAtma": True, "ayracRenk": 2, "gofre": True, "kulakli": True,
                                                  "kapakRenk": 4, "selofan": True, "lokalLak": True}}
    keys = {ln["key"]: ln["total"] for ln in F.compute(inp, F.default_tariff())["lines"]}
    f10 = (6000 + 600) / 8
    assert keys["ayracAtma"] == pytest.approx((6000 + 170) * 0.06)
    assert keys["ayracBaski"] == pytest.approx(2 * 95)  # f10 = 825 ≤ 3000
    assert keys["gofre"] == pytest.approx(6 * 200 + 400)  # f10 × 2 > 1000
    assert keys["kulakli"] == pytest.approx(6 * 200)
    assert keys["selofan"] == pytest.approx(max(250, f10 * 70 * 100 * 0.9 / 10000))
    assert keys["lokalLak"] == pytest.approx(3200 * 1.25)


def test_blank_inputs_carry_digital_defaults_and_analysis_runs():
    t = F.default_tariff()
    b = F.blank_inputs(t)
    assert b["baski"] == "ofset" and b["dijital"]["kapakKagit"] == "BRİSTOL"
    a = F.to_analysis(_inputs(), t)
    assert a["printService"] > 0 and a["paperPerCopy"] == 0


def test_overhead_default_follows_publisher():
    t = F.default_tariff()
    inp = _inputs(yayinevi="TİMAŞ İNANÇ")
    inp.pop("dolayli")
    assert F.compute(inp, t)["summary"]["dolayliOran"] == 70
    inp["yayinevi"] = "Sufi Kitap"
    assert F.compute(inp, t)["summary"]["dolayliOran"] == 40
    inp["yayinevi"] = "Timaş Akademi"  # listede yok → genel dijital oran
    assert F.compute(inp, t)["summary"]["dolayliOran"] == 40
    inp["dolayli"] = 55  # elle girilen her zaman geçerli
    assert F.compute(inp, t)["summary"]["dolayliOran"] == 55
