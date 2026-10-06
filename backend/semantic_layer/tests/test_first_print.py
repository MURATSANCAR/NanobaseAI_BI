"""M10 İlk baskı ve satış tahmini: hesap çekirdeği, rapor yardımcıları, karar/onay kaydı ve uçların yetki kuralı.

Sözleşme:
- Lansman, CRM ilk yayınıyla en çok 3 ay farklı ilk net satış ayıdır; 2015 başına yapışık ya da uzak olan emsal olmaz.
- Emsal yalnız kesimde ilk h ayı tamamen gözlenmiş lansmanlardan seçilir (geleceği görmez); CRM emsali ve aynı yazar
  puanı artırır, gerekçe ekranda görünür.
- İlk baskı önerisi yayınevinin kullandığı üst baskı adedine yuvarlanır.
- Karar iki ayrı kişinin (satış + üretim) onayıyla «onaylandı» olur; aynı kişi iki onayı veremez; açık karar varken
  aynı kitaba ikinci karar açılmaz; yalnız öneren ya da yönetici geri çeker.
"""

from __future__ import annotations

import math

import pytest

from semantic_bridge.management import ilk_baski as IB
from semantic_bridge.management import ilk_baski_api as API
from semantic_bridge.management import ilk_baski_model as M
from semantic_layer.store.catalog_store import open_store

T = "t1"


def _book(code, launch, *, author="A Yazar", series="", library="Roman", publisher="Timaş", emsal_price=100.0):
    return {"stok_kodu": code, "ad": f"Kitap {code}", "yayinevi": publisher, "kitaplik": library, "dizi": series,
            "yazar": author, "hedef_kitle": "Yetişkin", "tur": "roman", "sayfa": 200, "fiyat": emsal_price,
            "ilk_yayin": launch, "statu": "YS04 Aktif", "kart_durumu": 0}


def _sales(code, start, values, kanal="KITAPCI"):
    y, m = int(start[:4]), int(start[5:7])
    out = []
    for q in values:
        out.append({"stok_kodu": code, "yil": y, "ay": m, "kanal": kanal, "miktar": q, "net_tutar": q * 60.0,
                    "liste_tutar": q * 100.0})
        m += 1
        if m == 13:
            y, m = y + 1, 1
    return out


@pytest.fixture
def ds():
    books = [
        _book("15201.01.0001", "2022-01-10"), _book("15201.01.0002", "2022-06-01"), _book("15201.01.0003", "2023-02-01", author="B Yazar"),
        _book("15201.01.0004", "2023-03-01", author="C Yazar", library="Çocuk"),
        _book("15201.01.0010", "2010-01-01"),                     # 2015 öncesi: lansman gözlenmedi
        _book("15201.01.0011", "2020-01-01"),                     # CRM tarihinden çok sonra satış: başka baskının devamı
        _book("15201.01.0020", "2024-01-01"),                     # hedef
        _book("15201.01.0030", "2027-01-01"),                    # yayımlanacak
    ]
    sales = (_sales("15201.01.0001", "2022-01", [100] * 14) + _sales("15201.01.0002", "2022-06", [200] * 14)
             + _sales("15201.01.0003", "2023-02", [50] * 14) + _sales("15201.01.0004", "2023-03", [10] * 14)
             + _sales("15201.01.0010", "2015-01", [5] * 30) + _sales("15201.01.0011", "2022-01", [5] * 12)
             + _sales("15201.01.0020", "2024-01", [150] * 8))
    emsal = [{"stok_kodu": "15201.01.0020", "emsal_stok_kodu": "15201.01.0002"}]
    return M.build_dataset(books, emsal, sales, end=M.mi(2024, 8))


def test_launch_rules(ds):
    assert ds.books["15201.01.0001"].valid_launch and ds.books["15201.01.0001"].launch == M.mi(2022, 1)
    assert not ds.books["15201.01.0010"].valid_launch      # 2015 başından beri satıyor
    assert not ds.books["15201.01.0011"].valid_launch      # CRM ilk yayın 2020, ilk satış 2022
    assert ds.books["15201.01.0030"].launch == M.mi(2027, 1) and not ds.books["15201.01.0030"].valid_launch
    # son tam aydan sonraki satış kullanılmaz
    assert len(ds.outcomes["15201.01.0020"].months) == 8


def test_forecast_uses_only_fully_observed_launches_and_explains(ds):
    t = ds.books["15201.01.0020"]
    cut = t.launch - IB.GAP
    pool = M.pool_for(ds, cut, 6)
    assert "15201.01.0020" not in pool and "15201.01.0004" in pool and set(pool) <= set(ds.outcomes)
    for c in pool:
        assert ds.books[c].launch + 5 <= cut
    fc = M.forecast(ds, t, t.launch, cut, 6, pool=pool)
    by = {a["code"]: a for a in fc.analogs}
    assert "CRM emsali" in by["15201.01.0002"]["reasons"] and "aynı yazar" in by["15201.01.0002"]["reasons"]
    assert by["15201.01.0002"]["score"] > by["15201.01.0004"]["score"]
    # A2'nin (CRM emsali + aynı yazar) ağırlığı baskın: baz tahmin A2'nin 6 ayına (1.200) yakın
    assert 600 <= fc.base <= 1200


def test_revise_scales_actual_with_analog_growth(ds):
    t = ds.books["15201.01.0020"]
    fc = M.forecast(ds, t, t.launch, t.launch - IB.GAP, 6)
    # emsallerin hepsi düz satıyor: 1 ayda 150 → 6 ayda 900
    assert M.revise(ds, fc, [150.0], 6) == pytest.approx(900, rel=0.01)
    assert M.revise(ds, fc, [], 6) == fc.base


def test_weighted_quantile_and_norm():
    assert M.wquantile([1, 2, 3], [1, 1, 1], 0.5) == 2
    assert M.wquantile([1, 10], [9, 1], 0.5) < 5
    assert M.norm("İSTANBUL Şiir") == "istanbul siir"
    assert M.parts("Ali Veli, Ayşe Fatma & Can") == frozenset({"ali veli", "ayse fatma", "can"})
    assert M.channel_label("KITAPCI") == "Kitapçı" and M.channel_label("YENI KANAL") == "Yeni Kanal"


def test_print_steps_and_rounding():
    rows = [{"baski_sayisi": 1, "son_baski_adet": a} for a in [3000] * 5 + [5000] * 3 + [1234] * 2]
    rows += [{"baski_sayisi": 2, "son_baski_adet": 7000}] * 5  # ikinci baskı: ilk baskı kararı değil
    steps = IB.print_steps(rows)
    assert steps == [3000, 5000]
    assert IB.round_print(2100, steps) == 3000
    assert IB.round_print(5001, steps) == 6000
    assert IB.round_print(700, []) == 1000


def test_engine_full_and_serialization_roundtrip(ds):
    eng = IB.Engine(ds, None, {}, [500, 1000, 2000], M.PARAMS)
    eng.calib = {"6": {"hepsi": {"0.1": 0.5, "0.2": 0.7, "0.5": 1.0, "0.8": 1.4, "0.9": 2.0},
                       "ratios": {"hepsi": [0.5, 0.8, 1.0, 1.2, 2.0]}},
                 "12": {"hepsi": {"0.1": 0.5, "0.2": 0.7, "0.5": 1.0, "0.8": 1.4, "0.9": 2.0}}}
    out = eng.full(ds.books["15201.01.0030"], M.mi(2027, 1))
    h6 = out["horizons"]["6"]
    units = [s["units"] for s in h6["scenarios"]]
    assert units == sorted(units) and h6["band"]["low"] <= units[0] and h6["band"]["high"] >= units[-1]
    assert h6["curve"][-1]["base"] == pytest.approx(units[1], abs=1)
    assert out["recommendation"]["units"] in (500, 1000, 2000) or out["recommendation"]["units"] % 1000 == 0
    assert out["recommendation"]["units"] >= units[1]
    # ciro: fiyat × emsallerin net/liste oranı (0,6)
    assert h6["scenarios"][1]["revenue"] == pytest.approx(units[1] * 100 * 0.6, rel=0.01)
    assert h6["channels"][0]["channel"] == "Kitapçı"
    again = IB.engine_from(IB.serialize(eng))
    assert again.full(ds.books["15201.01.0030"], M.mi(2027, 1))["horizons"]["6"]["scenarios"] == h6["scenarios"]


def test_upcoming_list_excludes_closed_and_sold(ds):
    from datetime import date
    ds.books["15201.01.0030"].status = "YS01 İptal Edilmiş"
    assert [b.code for b, _ in IB.upcoming_books(ds, date(2024, 9, 1))] == []
    ds.books["15201.01.0030"].status = "YS04 Aktif"
    got = IB.upcoming_books(ds, date(2024, 9, 1))
    assert [(b.code, L) for b, L in got] == [("15201.01.0030", M.mi(2027, 1))]


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    API._ready.discard(id(e))
    API.ensure(e)
    return e


def test_decision_needs_two_different_approvers(engine):
    with pytest.raises(API.DecisionError, match="sıfırdan büyük"):
        API.create_decision(engine, T, "ali", {"title": "K", "units": 0})
    d = API.create_decision(engine, T, "ali", {"code": "X1", "title": "Kitap", "units": 3000, "scenario": "oneri",
                                               "recommended": 3000, "launch": "2026-10"})
    assert d["status"] == "bekliyor"
    with pytest.raises(API.DecisionError) as e:
        API.create_decision(engine, T, "veli", {"code": "X1", "title": "Kitap", "units": 5000})
    assert e.value.status == 409
    d = API.approve(engine, T, "ali", d["id"], "satis")
    assert d["approvals"]["satis"]["by"] == "ali" and d["status"] == "bekliyor"
    with pytest.raises(API.DecisionError, match="iki ayrı kişiden"):
        API.approve(engine, T, "ALI", d["id"], "uretim")
    with pytest.raises(API.DecisionError):
        API.approve(engine, T, "veli", d["id"], "satis")  # zaten verilmiş
    d = API.approve(engine, T, "veli", d["id"], "uretim")
    assert d["status"] == "onaylandi"
    with pytest.raises(API.DecisionError):
        API.withdraw(engine, T, "ali", False, d["id"])  # onaylanmış karar geri çekilmez
    assert [x["id"] for x in API.list_decisions(engine, T, status="onaylandi")] == [d["id"]]


def test_withdraw_only_by_proposer_or_admin(engine):
    d = API.create_decision(engine, T, "ali", {"code": "X2", "title": "Kitap 2", "units": 2000})
    with pytest.raises(API.DecisionError) as e:
        API.withdraw(engine, T, "veli", False, d["id"])
    assert e.value.status == 403
    assert API.withdraw(engine, T, "yonetici", True, d["id"])["status"] == "geri_cekildi"
    # geri çekilen karardan sonra aynı kitaba yeni karar açılabilir
    assert API.create_decision(engine, T, "veli", {"code": "X2", "title": "Kitap 2", "units": 2500})["status"] == "bekliyor"


def test_first_print_routes_have_page_and_feature_rules():
    from semantic_bridge import access
    assert access.rule_for("/api/v1/management/first-print/summary") == frozenset({access.page("ilk-baski")})
    assert access.rule_for("/api/v1/management/reports") == frozenset({access.page("yonetim-raporlari"), access.page("baski-oneri")})
    assert access.features_for("POST", "/api/v1/management/first-print/decisions") == ["ozellik:ilk-baski.karar"]
    assert access.features_for("POST", "/api/v1/management/first-print/forecast") == []
    assert access.features_for("GET", "/api/v1/management/first-print/decisions") == []
    keys = {f["key"]: f for f in access.catalog()["features"]}
    assert keys["ozellik:ilk-baski.onay"].get("explicit") is True
    assert "ozellik:ilk-baski.karar" in keys


def test_non_book_codes_are_not_analogs():
    books = [_book("15205.01.0001", "2022-01-01"), _book("15201.01.0001", "2022-01-01")]
    sales = _sales("15205.01.0001", "2022-01", [100] * 8) + _sales("15201.01.0001", "2022-01", [100] * 8)
    ds = M.build_dataset(books, [], sales, end=M.mi(2022, 12))
    assert list(ds.outcomes) == ["15201.01.0001"]  # set kodu (15205) emsal havuzuna girmez


def test_market_factor_neutral_without_level(ds):
    assert M.market_factor(ds, M.mi(2022, 1), M.mi(2030, 1), 6, None) == 1.0
    assert not math.isnan(M.market_factor(ds, M.mi(2022, 1), M.mi(2022, 6), 6, None))


def _star_ds(n_prior: int, prior_sales: list[int]):
    """Yıldız yazar: editörün emsal gösterdiği aynı dizideki kitaplar düşük satar, yazarın önceki kitapları yüksek
    (Babası Kılıklı / Mert Arık durumu)."""
    books, sales = [], []
    for i in range(20):  # yazarın olmadığı, aynı dizide düşük satan çocuk kitapları
        code = f"15201.01.1{i:03d}"
        books.append(_book(code, f"2022-{i % 12 + 1:02d}-01", author=f"Başka {i}", library="Çocuk", series="Yeni Dizi"))
        sales += _sales(code, f"2022-{i % 12 + 1:02d}", [100] * 14)
    for i in range(n_prior):
        code = f"15201.01.2{i:03d}"
        start = f"2023-{i + 1:02d}"
        books.append(_book(code, start + "-01", author="Yıldız Yazar", library="Edebiyat"))
        sales += _sales(code, start, [prior_sales[i] // 6] * 12)
    books.append(_book("15201.01.3000", "2027-01-01", author="Yıldız Yazar", library="Çocuk", series="Yeni Dizi"))
    books.append(_book("15201.01.3001", "2027-01-01", author="Yeni Yazar", library="Çocuk", series="Yeni Dizi"))
    emsal = [{"stok_kodu": "15201.01.3000", "emsal_stok_kodu": f"15201.01.1{i:03d}"} for i in range(8)]
    return M.build_dataset(books, emsal, sales, end=M.mi(2024, 12))


def _engine(ds):
    eng = IB.Engine(ds, None, {}, [1000, 5000, 10000, 100000], M.PARAMS)
    eng.calib = {h: {"hepsi": {"0.1": 0.5, "0.2": 0.7, "0.5": 1.0, "0.8": 1.4, "0.9": 2.0},
                     "ratios": {"hepsi": [0.5, 0.8, 1.0, 1.2, 2.0]}} for h in ("6", "12")}
    return eng


def test_author_history_pulls_consistent_bestseller_to_its_level():
    ds = _star_ds(8, [120000, 110000, 130000, 125000, 100000, 140000, 115000, 120000])
    eng = _engine(ds)
    t = ds.books["15201.01.3000"]
    fc6, fc12 = eng.raw(t, M.mi(2025, 1), ds.end, 6), eng.raw(t, M.mi(2025, 1), ds.end, 12)
    assert fc6.author["count"] == 8 and fc6.author["weight"] > 0.7
    assert fc6.emsal_base < 1000 and fc6.base > 40000           # emsaller tutturamıyor, yazar düzeyi baskın
    # çarpan yalnız ilk 6 aydan: 12 ay aynı oranla büyür, 6 aydan küçük kalamaz
    assert fc12.base / fc12.emsal_base == pytest.approx(fc6.base / fc6.emsal_base)
    assert fc12.base >= fc6.base
    out = eng.full(t, M.mi(2025, 1))
    assert out["author"]["count"] == 8 and out["author"]["books"][0]["launch"] >= out["author"]["books"][-1]["launch"]
    assert sum(b["weight"] for b in out["author"]["books"]) == pytest.approx(1, abs=0.01)
    assert any("Yazarın daha önce çıkmış 8 kitabı" in r for r in out["reasons"])
    assert out["horizons"]["6"]["emsalBase"] < out["horizons"]["6"]["raw"]


def test_author_history_weak_when_single_or_scattered_and_absent_for_new_author():
    one = _star_ds(1, [120000])
    eng = _engine(one)
    fc = eng.raw(one.books["15201.01.3000"], M.mi(2025, 1), one.end, 6)
    assert fc.author["count"] == 1 and fc.author["weight"] < 0.5
    scattered = _star_ds(4, [500, 120000, 2000, 90000])
    fc_s = _engine(scattered).raw(scattered.books["15201.01.3000"], M.mi(2025, 1), scattered.end, 6)
    consistent = _star_ds(4, [100000, 120000, 110000, 90000])
    fc_c = _engine(consistent).raw(consistent.books["15201.01.3000"], M.mi(2025, 1), consistent.end, 6)
    assert fc_s.author["weight"] < fc_c.author["weight"]
    new = _engine(one).full(one.books["15201.01.3001"], M.mi(2025, 1))
    assert new["author"] is None and any("tahmin yalnız emsallerden" in r for r in new["reasons"])


def test_author_history_never_sees_the_future():
    ds = _star_ds(8, [120000] * 8)
    eng = _engine(ds)
    t = ds.books["15201.01.3000"]
    # kesim 2023-05: yazarın ilk kitabı 2023-01'de çıktı, hiçbirinin ilk 6 ayı dolmamış
    assert eng.raw(t, M.mi(2023, 7), M.mi(2023, 5), 6).author is None
    # kesim 2023-06: yalnız 2023-01 kitabının 6 ayı dolmuş
    assert eng.raw(t, M.mi(2023, 8), M.mi(2023, 6), 6).author["count"] == 1
    eng.author = None  # kapalı: baz yalnız emsallerden
    fc = eng.raw(t, M.mi(2025, 1), ds.end, 6)
    assert fc.author is None and fc.base == fc.emsal_base
