"""M9 Fiyatlama — dağıtımcı kataloğundan pazar fiyatı önerisi (`pricing/dagitim.py`): çeyrekler (emsal bandıyla aynı
doğrusal ara değer), TİMAŞ grubunun ve katalogdan düşen başlığın dışarıda kalması, sayfa ±%20 ve kapak daraltması (en
az `DAR_MIN` başlık kalmazsa uygulanmaz), son basım yılları, D&R satış/liste oranı (sitelerden silinmiş hariç), boş
küme, kategori çözümü (kendi kaydı → kitaplık adı → seçim) ve sorgu bilgisi.

Veriler yapaydır; gerçek katalogla kabul test sunucusunda (docs/analiz/kitap-pazari-veri-kaynagi-API_URUN_DB-2026-09-29.md).
"""

from __future__ import annotations

from datetime import date

import pytest
import sqlalchemy as sa

from semantic_bridge import pazar_dagitim as PD
from semantic_bridge import provenance as P
from semantic_bridge.pricing import dagitim as DG
from semantic_bridge.pricing import kaynak as K
from semantic_layer.store.catalog_store import open_store

T = "t1"
GUN = date(2026, 9, 25)


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    PD._ready.discard(id(e))
    PD.ensure(e)
    yield e
    PD._ready.discard(id(e))


def _bk(i: int) -> str:
    return f"978000000{i:04d}"


def _b(i, fiyat, sayfa=200, kategori="Edebiyat>Roman", kapak="Karton Kapak", yil=2026, marka="Rakip Yayınları"):
    return {"barkod": _bk(i), "urun_ad": f"Kitap {i}", "yazar": "Yazar", "cevirmen": "", "marka": marka,
            "kategori": kategori, "sayfasayisi": str(sayfa), "kapak_turu": kapak, "kagit_cinsi": "2. Hamur",
            "basimyili": str(yil), "depo_stok": "10", "satis_fiyat": fiyat, "iskonto": "35", "stok_durum": "Satışta",
            "baski_sayisi": "1. Baskı"}


def _dr(i, liste, satis, silinmis=False):
    return {"isbn": _bk(i), "name": f"Kitap {i}", "brand_name": "Rakip", "bread_crumb": "Kitap|Edebiyat|Roman",
            "characteristic_value": "Karton Kapak", "b2bstock": 5, "available_stock": 3, "list_price": liste,
            "dr_price": satis, "deleted": "1" if silinmis else "0", "prefix_sale_status": "1", "sale_status_code": "0"}


def _seed(e, basari, dr=(), gun=GUN, timas=()):
    PD.apply(e, T, "basari", gun, PD.parse(basari, "basari"), yontem="elle")
    if dr:
        PD.apply(e, T, "dr", gun, PD.parse(dr, "dr"), yontem="elle")
    if timas:
        with e.begin() as c:
            c.execute(PD.TITLES.update().where(PD.TITLES.c.barkod.in_([_bk(i) for i in timas])).values(timas=True))


def _roman(e, **kw):
    """5 roman (200 s., 100–180 ₺), 1 TİMAŞ romanı (999 ₺, sayılmaz)."""
    rows = [_b(i, 100 + 20 * i) for i in range(5)] + [_b(50, 999)]
    _seed(e, rows, timas=[50], **kw)


# ------------------------------------------------------------------ yüzdelik ve küme


def test_quartiles_exclude_timas_and_match_model(engine):
    _roman(engine)
    out = DG.suggest(engine, T, kategori="Edebiyat>Roman")
    t = out["tum"]
    assert (t["n"], t["p25"], t["median"], t["p75"]) == (5, 120.0, 140.0, 160.0)   # 999 ₺ TİMAŞ kitabı yok
    assert t["perPage"] == {"median": 0.7, "n": 5}
    assert out["kume"] == 5 and out["etiket"] == "Dağıtımcı kataloğundan (5 başlık, 25.09.2026)"
    assert out["kaynak"]["basari"] == "2026-09-25" and out["hazir"] is True


def test_upper_category_and_even_count_interpolates(engine):
    _seed(engine, [_b(0, 100), _b(1, 110), _b(2, 150, kategori="Edebiyat>Öykü"), _b(3, 200, kategori="Edebiyat>Şiir"),
                   _b(4, 90, kategori="Tarih>Osmanlı")])
    t = DG.suggest(engine, T, kategori="Edebiyat")["tum"]                  # üst kategori: 4 başlık
    assert t["n"] == 4 and t["median"] == 130.0 and t["p25"] == 107.5 and t["p75"] == 162.5


def test_dropped_titles_are_not_counted(engine):
    _roman(engine)
    later = [_b(i, 100 + 20 * i) for i in range(4)] + [_b(50, 999)]       # 4 numara ikinci görüntüde yok
    PD.apply(engine, T, "basari", date(2026, 9, 26), PD.parse(later, "basari"), yontem="elle")
    t = DG.suggest(engine, T, kategori="Edebiyat>Roman")["tum"]
    assert t["n"] == 4 and t["median"] == 130.0


# ------------------------------------------------------------------ süzgeçler


def test_page_band_narrows_only_when_enough_titles(engine):
    rows = [_b(i, 100, sayfa=200) for i in range(5)] + [_b(10 + i, 300, sayfa=400) for i in range(5)]
    _seed(engine, rows)
    dar = DG.suggest(engine, T, kategori="Edebiyat>Roman", pages=210)
    assert dar["suzgec"]["sayfaUygulandi"] and dar["suzgec"]["sayfaAralik"] == [168, 252]
    assert dar["tum"]["n"] == 5 and dar["tum"]["median"] == 100.0
    bos = DG.suggest(engine, T, kategori="Edebiyat>Roman", pages=300)      # 240–360 aralığında başlık yok
    assert not bos["suzgec"]["sayfaUygulandi"] and bos["tum"]["n"] == 10
    assert "sayfa süzgeci uygulanmadı" in bos["suzgec"]["notlar"][0]


def test_binding_class_narrows(engine):
    rows = [_b(i, 100, kapak="Karton Kapak") for i in range(5)] + [_b(10 + i, 250, kapak="Ciltli") for i in range(5)]
    _seed(engine, rows)
    sert = DG.suggest(engine, T, kategori="Edebiyat>Roman", kapak="Sert Kapak")
    assert sert["suzgec"]["kapakUygulandi"] and sert["tum"]["median"] == 250.0
    karton = DG.suggest(engine, T, kategori="Edebiyat>Roman", kapak="Amerikan Cilt")
    assert karton["suzgec"]["kapakSinifi"] == "karton" and karton["tum"]["median"] == 100.0
    bilinmez = DG.suggest(engine, T, kategori="Edebiyat>Roman", kapak="Kutulu")
    assert not bilinmez["suzgec"]["kapakUygulandi"] and bilinmez["tum"]["n"] == 10


def test_binding_classes():
    assert DG.kapak_sinifi("Flexi Kapak Cilt") == "fleksi"
    assert DG.kapak_sinifi("Amerikan Cilt") == DG.kapak_sinifi("KARTON KAPAK") == DG.kapak_sinifi("İnce Kapak") == "karton"
    assert DG.kapak_sinifi("Sert Kapak") == DG.kapak_sinifi("Ciltli") == "sert"
    assert DG.kapak_sinifi("Tel Dikiş") == "tel"
    assert DG.kapak_sinifi("Ciltsiz") == "karton"
    assert DG.kapak_sinifi(None) is None and DG.kapak_sinifi("Kutulu") is None


def test_recent_print_years_filter(engine):
    rows = [_b(0, 100, yil=2026), _b(1, 120, yil=2025), _b(2, 300, yil=2019), _b(3, 320, yil=2018)]
    _seed(engine, rows)
    out = DG.suggest(engine, T, kategori="Edebiyat>Roman")
    assert out["sonYillar"]["yillar"] == [2026, 2025]
    assert out["sonYillar"]["n"] == 2 and out["sonYillar"]["median"] == 110.0
    assert out["tum"]["n"] == 4 and out["tum"]["median"] == 210.0


def test_dr_ratio_skips_deleted_and_missing(engine):
    _seed(engine, [_b(i, 200) for i in range(4)],
          dr=[_dr(0, 200, 160), _dr(1, 200, 180), _dr(2, 200, 100, silinmis=True)])   # 3: D&R'de yok
    d = DG.suggest(engine, T, kategori="Edebiyat>Roman")["tum"]["dr"]
    assert d == {"ratioMedian": 0.85, "n": 2}


# ------------------------------------------------------------------ boş küme


def test_empty_category_and_no_snapshot(engine):
    none = DG.suggest(engine, T, kategori="Edebiyat>Roman")
    assert none["hazir"] is False and none["tum"] is None and "henüz okunmadı" in none["mesaj"]
    assert DG.categories(engine, T) == {"tarih": None, "items": [], "not": DG.NOT}
    _roman(engine)
    bos = DG.suggest(engine, T, kategori="Felsefe")
    t = bos["tum"]
    assert t["n"] == 0 and t["median"] is None and t["p25"] is None and t["perPage"]["median"] is None
    assert bos["mesaj"] and bos["sonYillar"]["n"] == 0


def test_stats_of_nothing():
    assert DG.stats([]) == {"n": 0, "p25": None, "median": None, "p75": None, "perPage": {"median": None, "n": 0},
                            "dr": {"ratioMedian": None, "n": 0}}


# ------------------------------------------------------------------ kategori çözümü


def test_category_from_own_record_then_library_then_choice(engine):
    _seed(engine, [_b(i, 100 + 20 * i) for i in range(5)] + [_b(60, 90, kategori="Tarih>Osmanlı", sayfa=320, kapak="Ciltli")])
    PD.store_pairs(engine, T, {(_bk(60), "15201.01.9"), (_bk(61), "15201.01.9")})
    own = DG.suggest(engine, T, code="15201.01.9", library="Roman")
    assert own["kategori"]["yol"] == "kendi" and own["kategori"]["secili"] == "Tarih>Osmanlı"
    assert own["suzgec"]["sayfa"] == 320 and own["suzgec"]["kapak"] == "Ciltli"   # künye yoksa kendi kaydından

    ad = DG.suggest(engine, T, code="15201.01.1", library="ROMAN")
    assert ad["kategori"]["yol"] == "ad" and ad["kategori"]["secili"] == "Edebiyat>Roman"
    yok = DG.suggest(engine, T, code="15201.01.1", library="Mutfak")
    assert yok["kategori"]["yol"] == "yok" and yok["tum"] is None
    sec = DG.suggest(engine, T, code="15201.01.9", kategori="Edebiyat")
    assert sec["kategori"]["yol"] == "secim" and sec["kategori"]["secili"] == "Edebiyat"


def test_match_categories_folds_case_and_punctuation():
    cats = [{"kategori": "Edebiyat>Roman", "ust": "Edebiyat", "alt": "Roman", "n": 10},
            {"kategori": "Çocuk Kitapları", "ust": "Çocuk Kitapları", "alt": None, "n": 40},
            {"kategori": "Edebiyat>Türk Romanı", "ust": "Edebiyat", "alt": "Türk Romanı", "n": 3},
            {"kategori": "Edebiyat", "ust": "Edebiyat", "alt": None, "n": 13}]
    got = DG.match_categories("roman", cats)
    assert [c["kategori"] for c in got] == ["Edebiyat>Roman", "Edebiyat>Türk Romanı"]
    assert DG.match_categories("ÇOCUK  KİTAPLARI", cats)[0]["kategori"] == "Çocuk Kitapları"
    assert DG.match_categories("", cats) == [] and DG.match_categories("Din", cats) == []


def test_category_list_has_upper_rows(engine):
    _seed(engine, [_b(0, 100), _b(1, 100, kategori="Edebiyat>Şiir"), _b(2, 100, kategori="Tarih>Osmanlı"), _b(3, 0)])
    items = DG.categories(engine, T)["items"]
    edebiyat = next(x for x in items if x["kategori"] == "Edebiyat")
    assert edebiyat["alt"] is None and edebiyat["n"] == 2                  # fiyatı 0 olan sayılmaz
    assert {"kategori": "Edebiyat>Şiir", "ust": "Edebiyat", "alt": "Şiir", "n": 1} in items


# ------------------------------------------------------------------ sorgu bilgisi


def _check(out):
    k = out.get("kaynaklar")
    assert k and not k.get("error"), k
    assert P.uncovered_numbers(out) == []
    assert P.problems(out) == []
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == []
    return k


def test_every_number_has_its_query(engine):
    _roman(engine, dr=[_dr(0, 200, 160)])
    PD.store_pairs(engine, T, {(_bk(50), "15201.01.5")})
    out = DG.suggest(engine, T, code="15201.01.5", pages=200, kapak="Amerikan Cilt")
    k = _check(P.ekle(out, K.for_distributor(engine, T, out)))
    assert "semantic_pazar_dagitim_titles" in k["sources"]["portal.fiyat.dagitim"]["sql"]
    assert "portal.fiyat.dagitimKendi" in k["formulas"]["dagitim.kategori"]["inputs"]
    assert k["fields"]["tum"] == "hesap:dagitim"
    cats = DG.categories(engine, T)
    _check(P.ekle(cats, K.for_distributor_categories(engine, T, cats)))
    # görüntü yokken de sorgu bilgisi kurulur
    e2 = open_store("sqlite://").engine
    PD._ready.discard(id(e2))
    empty = DG.suggest(e2, T, code="x")
    P.ekle(empty, K.for_distributor(e2, T, empty))
    assert not empty["kaynaklar"].get("error") and P.uncovered_numbers(empty) == []
    PD._ready.discard(id(e2))
