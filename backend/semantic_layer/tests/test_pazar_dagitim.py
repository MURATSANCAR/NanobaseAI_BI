"""M39 Pazar — dağıtımcı katalogları: ayrıştırma, görüntü işleme (yalnız değişen satır, önceki stok, çıkış/giriş,
kaybolan ve geri gelen başlık, uzun aralık, eski tarih reddi, aynı görüntünün tekrarı), çıkış endeksi, kesintisiz dizi,
TİMAŞ markası (Logo barkod oranı), tam tur (gece görüntüleri; ikinci görüntüde endeks ve kalibrasyon), D&R alan
anlamları (servis belgesi), stok ekranı işaretleri, Pazar özeti.

Veriler yapaydır ve yalnız kuralları sınar; gerçek kaynakla kabul test sunucusunda
(docs/analiz/kitap-pazari-veri-kaynagi-API_URUN_DB-2026-09-29.md, günlük 2026-09-29).
"""

from __future__ import annotations

from datetime import date

import pytest
import sqlalchemy as sa

from semantic_bridge import pazar_dagitim as D
from semantic_layer.store.catalog_store import open_store

T = "t1"


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setenv("PAZAR_DAGITIM_ARALIK_GUN", "35")
    e = open_store("sqlite://").engine
    D._ready.discard(id(e))
    D.ensure(e)
    return e


def _b(barkod, stok, fiyat=100.0, marka="Rakip Yayınları", durum="Satışta", baski="1. Baskı", kategori="Edebiyat>Roman"):
    return {"barkod": barkod, "urun_ad": f"Kitap {barkod}", "yazar": "Yazar", "cevirmen": "", "marka": marka,
            "kategori": kategori, "sayfasayisi": "200", "kapak_turu": "Karton Kapak", "kagit_cinsi": "2. Hamur",
            "basimyili": "2024", "depo_stok": str(stok), "satis_fiyat": fiyat, "iskonto": "35", "stok_durum": durum,
            "baski_sayisi": baski}


def _apply(e, d, rows, **kw):
    return D.apply(e, T, "basari", d, D.parse(rows, "basari"), yontem=kw.pop("yontem", "elle"), **kw)


def _obs(e):
    with e.connect() as c:
        return {(r.barkod, r.tarih): r for r in c.execute(sa.select(D.OBS)).all()}


def test_parse_normalises_fields():
    x = D.basari_row(_b("978-605-0838954", 12, baski="3. Baskı "))
    assert x["barkod"] == "9786050838954" and x["stok"] == 12 and x["baski_no"] == 3
    assert x["ust_kategori"] == "Edebiyat" and x["sayfa"] == 200 and x["iskonto"] == 35.0
    assert D.basari_row(_b("abc", 1)) is None                          # barkodsuz satır atılır
    y = D.dr_row({"isbn": "9789754081299", "name": "Zindanda", "brand_name": "Nesil", "b2bstock": 6, "list_price": 15,
                  "dr_price": 12, "deleted": "1", "prefix_sale_status": "0", "sale_status_code": "4",
                  "bread_crumb": "Kitap|Edebiyat|Roman", "characteristic_value": "İnce Kapak"})
    assert y["stok"] == 6 and y["dr_fiyat"] == 12.0 and y["ust_kategori"] == "Edebiyat"
    assert y["durum"] == "Site: silinmiş · Prefix: Stokta yok" and y["site_stok"] is None
    z = D.dr_row({"isbn": "9786258618303", "b2bstock": 5333, "available_stock": 5336, "deleted": "0",
                  "sale_status_code": "0", "prefix_sale_status": "1", "list_price": 225, "dr_price": 157.5})
    assert (z["stok"], z["site_stok"], z["durum"]) == (5333, None, "Site: Satışa açık · Prefix: Satışa açık")  # 999 ve üstü
    z = D.dr_row({"isbn": "9786258618303", "b2bstock": 5, "available_stock": 4, "deleted": "0", "sale_status_code": "1",
                  "prefix_sale_status": "1"})
    assert z["site_stok"] == 4 and z["durum"].startswith("Site: Stokta yok")


def test_duplicate_barcode_keeps_higher_stock():
    items = D.parse([_b("9780000000001", 3), _b("9780000000001", 9)], "basari")
    assert items["9780000000001"]["stok"] == 9


def test_only_changed_rows_are_observed_with_previous_stock(engine):
    d1, d2 = date(2025, 1, 1), date(2025, 1, 15)
    r1 = _apply(engine, d1, [_b("9780000000001", 100), _b("9780000000002", 50)])
    assert r1["yeni"] == 2 and r1["degisen"] == 0
    r2 = _apply(engine, d2, [_b("9780000000001", 70), _b("9780000000002", 50), _b("9780000000003", 5)])
    assert (r2["degisen"], r2["yeni"]) == (1, 1)
    o = _obs(engine)
    a = o[("9780000000001", d2)]
    assert (a.onceki_stok, a.stok, a.cikis, a.giris) == (100, 70, 30, 0)
    assert ("9780000000002", d2) not in o                             # değişmeyen yazılmaz
    assert o[("9780000000003", d2)].ilk is True and o[("9780000000001", d1)].ilk is False
    with engine.connect() as c:
        son = dict(c.execute(sa.select(D.TITLES.c.barkod, D.TITLES.c.son_gorulme)).all())
    assert set(son.values()) == {d2}                                  # değişmeyen başlığın son görülmesi de kaydı


def test_price_change_is_observed_without_stock_movement(engine):
    _apply(engine, date(2025, 1, 1), [_b("9780000000001", 10, fiyat=100)])
    r = _apply(engine, date(2025, 1, 15), [_b("9780000000001", 10, fiyat=130)])
    a = _obs(engine)[("9780000000001", date(2025, 1, 15))]
    assert r["degisen"] == 1 and a.fiyat == 130.0 and a.cikis == 0 and a.giris == 0


def test_missing_then_returning_title_has_no_fake_movement(engine):
    b = "9780000000001"
    _apply(engine, date(2025, 1, 1), [_b(b, 100), _b("9780000000002", 1)])
    r = _apply(engine, date(2025, 1, 15), [_b("9780000000002", 1)])
    assert r["kaybolan"] == 1
    with engine.connect() as c:
        son = c.execute(sa.select(D.TITLES.c.son_gorulme).where(D.TITLES.c.barkod == b)).scalar()
    assert son == date(2025, 1, 1)                                    # düşen başlık kaydırılmaz
    r = _apply(engine, date(2025, 2, 1), [_b(b, 20), _b("9780000000002", 1)])
    a = _obs(engine)[(b, date(2025, 2, 1))]
    assert r["geriGelen"] == 1 and a.onceki_stok is None and a.cikis == 0


def test_long_gap_does_not_count_outflow(engine):
    _apply(engine, date(2026, 1, 1), [_b("9780000000001", 500)])
    r = _apply(engine, date(2026, 9, 25), [_b("9780000000001", 100)], yontem="gece")
    a = _obs(engine)[("9780000000001", date(2026, 9, 25))]
    assert r["cikisHesaplandi"] is False and a.onceki_stok == 500 and a.cikis == 0


def test_same_snapshot_twice_and_older_snapshot(engine):
    _apply(engine, date(2025, 2, 1), [_b("9780000000001", 1)])
    assert "skipped" in _apply(engine, date(2025, 2, 1), [_b("9780000000001", 2)])
    with pytest.raises(D.DagitimError):
        _apply(engine, date(2025, 1, 1), [_b("9780000000001", 2)])


def test_outflow_groups_and_stretch(engine):
    _apply(engine, date(2025, 1, 1), [_b("9780000000001", 100, marka="A"), _b("9780000000002", 50, marka="B")])
    _apply(engine, date(2025, 1, 15), [_b("9780000000001", 60, marka="A"), _b("9780000000002", 80, marka="B")])
    _apply(engine, date(2025, 2, 1), [_b("9780000000001", 40, marka="A"), _b("9780000000002", 30, marka="B")])
    by = {r["anahtar"]: r for r in D.outflow(engine, T, by="yayinevi")}
    assert (by["A"]["cikis"], by["B"]["cikis"], by["B"]["giris"]) == (60, 50, 30)
    ay = {r["anahtar"]: r["cikis"] for r in D.outflow(engine, T, by="ay")}
    assert ay == {"2025-01": 40, "2025-02": 70}
    _apply(engine, date(2025, 9, 1), [_b("9780000000001", 40, marka="A")], yontem="gece")
    _apply(engine, date(2025, 9, 2), [_b("9780000000001", 39, marka="A")], yontem="gece")
    assert D.stretch(engine, T) == (date(2025, 9, 1), date(2025, 9, 2))   # 212 günlük boşluk diziyi keser


def test_timas_brand_by_logo_share(engine):
    rows = [_b(f"97860500000{i:02d}", 1, marka="Timaş Çocuk") for i in range(10)]
    rows += [_b(f"97899900000{i:02d}", 1, marka="Ötüken") for i in range(10)]
    logo = {f"97860500000{i:02d}": f"S{i}" for i in range(9)}           # %90 Logo'da
    logo["9789990000000"] = "TARCIN-1"                                  # başka yayınevinin tek satış kartı
    _apply(engine, date(2025, 1, 1), rows, logo=logo)
    out = D.mark_timas(engine, T)
    assert out["baslik"] == 10 and any("Timaş Çocuk" in m for m in out["markalar"])
    assert not any("Ötüken" in m for m in out["markalar"])


def test_run_all_nightly_snapshots_build_the_index(engine, monkeypatch):
    """Kaynak geçmiş tutmaz: ilk tur başlangıç görüntüsüdür, ikinci turda çıkış ve kalibrasyon oluşur. Aynı damgalı
    kaynak ikinci kez işlenmez."""
    state = {"t": "2026-09-25T11:04:20", "stok": 100}

    def run(sql: str):
        if "UNITBARCODE" in sql and "STLINE" not in sql:
            return [{"barkod": "9780000000001", "stok_kodu": "S1"}]
        if "STLINE" in sql:
            return [{"barkod": "9780000000001", "net": 60}]
        if "MAX(tarih)" in sql and "basari_list" in sql:
            return [{"t": state["t"], "n": 1, "bildirilen": 1}]
        if "basari_list" in sql:
            return [_b("9780000000001", state["stok"])]
        raise AssertionError(sql)

    monkeypatch.setenv("PAZAR_DAGITIM_KAYNAKLAR", "basari")
    monkeypatch.setenv("PAZAR_DAGITIM_TIMAS_MIN_BASLIK", "1")
    out = D.run_all(engine, T, run, {2026: "411"})
    assert out["basari"]["yeni"] == 1 and "kalibrasyon" not in out
    assert "skipped" in D.run_all(engine, T, run, {2026: "411"})["basari"]     # kaynak yenilenmedi
    state.update(t="2026-09-26T11:04:20", stok=70)
    out = D.run_all(engine, T, run, {2026: "411"})
    assert out["basari"]["degisen"] == 1
    kal = out["kalibrasyon"]
    assert (kal["eslesen"], kal["logoNet"], kal["cikis"]) == (1, 60, 30)
    st = D.status(engine, T)["kaynaklar"]["basari"]
    assert st["goruntu"] == 2 and st["logodaEslesen"] == 1 and st["sonGoruntuler"][-1]["eksik"] == 0


def test_stretch_keeps_previous_run_until_new_run_has_two_snapshots(engine):
    _apply(engine, date(2025, 12, 1), [_b("9780000000001", 10)])
    _apply(engine, date(2026, 1, 1), [_b("9780000000001", 5)])
    _apply(engine, date(2026, 9, 25), [_b("9780000000001", 4)], yontem="gece")
    assert D.stretch(engine, T) == (date(2025, 12, 1), date(2026, 1, 1))   # yeni dizi tek görüntü: önceki dizi
    _apply(engine, date(2026, 9, 26), [_b("9780000000001", 3)], yontem="gece")
    assert D.stretch(engine, T) == (date(2026, 9, 25), date(2026, 9, 26))


def test_summary_category_share_and_timas_rank(engine, monkeypatch):
    monkeypatch.setenv("PAZAR_DAGITIM_TIMAS_MIN_BASLIK", "1")
    t1 = [_b("9786050000001", 100, marka="Timaş Çocuk", kategori="Çocuk Kitapları>Hikaye"),
          _b("9789990000001", 300, marka="Rakip", kategori="Çocuk Kitapları>Hikaye"),
          _b("9789990000002", 50, marka="Rakip", kategori="Edebiyat>Roman")]
    _apply(engine, date(2025, 1, 1), t1, logo={"9786050000001": "S1"})
    t2 = [_b("9786050000001", 70, marka="Timaş Çocuk", kategori="Çocuk Kitapları>Hikaye"),
          _b("9789990000001", 210, marka="Rakip", kategori="Çocuk Kitapları>Hikaye"),
          _b("9789990000002", 40, marka="Rakip", kategori="Edebiyat>Roman")]
    _apply(engine, date(2025, 1, 15), t2, logo={"9786050000001": "S1"})
    D.mark_timas(engine, T)
    s = D.summary(engine, T)
    cocuk = next(k for k in s["kategoriler"] if k["kategori"] == "Çocuk Kitapları")
    assert (cocuk["cikis"], cocuk["timasCikis"], cocuk["timasPay"]) == (120, 30, 25.0)
    assert s["toplam"] == 130 and s["timasToplam"] == 30
    assert [(y["yayinevi"], y["sira"], y["timas"]) for y in s["yayinevleri"]] == [("Rakip", 1, False), ("Timaş Çocuk", 2, True)]
    assert s["aylar"] == [{"ay": "2025-01", "cikis": 130, "timasCikis": 30}]


def test_attach_stock_marks_distributor_gaps(engine, monkeypatch):
    monkeypatch.setenv("PAZAR_DAGITIM_TIMAS_MIN_BASLIK", "1")
    rows = [_b("9786050000001", 0, marka="Timaş Çocuk", durum="Baskısı Yok"),
            _b("9786050000002", 0, marka="Timaş Çocuk", durum="Satışta"),
            _b("9786050000003", 40, marka="Timaş Çocuk", durum="Satışta")]
    logo = {"9786050000001": "S1", "9786050000002": "S2", "9786050000003": "S3"}
    _apply(engine, date(2025, 1, 1), rows, logo=logo)
    D.mark_timas(engine, T)
    D.store_pairs(engine, T, {(b, k) for b, k in logo.items()} | {("9786050000001", "S1B")})   # aynı barkod iki kartta
    items = [{"stokKodu": "S1", "bakiye": 500.0}, {"stokKodu": "S1B", "bakiye": 3.0}, {"stokKodu": "S2", "bakiye": 20.0}, {"stokKodu": "S3", "bakiye": 5.0},
             {"stokKodu": "S9", "bakiye": 1.0}]
    oz = D.attach_stock(engine, T, items)
    by = {i["stokKodu"]: i["dagitim"] for i in items}
    assert by["S1"]["isaret"] == "baskisi_yok" and by["S1"]["basari"]["durumTarihi"] == "2025-01-01"
    assert by["S1B"]["isaret"] == "baskisi_yok"
    assert by["S2"]["isaret"] == "tukendi" and by["S3"]["isaret"] is None and by["S9"] is None
    assert oz["isaretler"] == {"baskisi_yok": 2, "tukendi": 1}


def test_attach_stock_no_flag_for_non_timas_brand(engine):
    rows = [_b("9789750000001", 0, marka="Ötüken", durum="Baskısı Yok")] + \
           [_b(f"97897500000{i:02d}", 1, marka="Ötüken") for i in range(2, 12)]
    _apply(engine, date(2025, 1, 1), rows, logo={"9789750000001": "TARCIN-1"})
    D.mark_timas(engine, T)
    D.store_pairs(engine, T, {("9789750000001", "TARCIN-1")})
    items = [{"stokKodu": "TARCIN-1", "bakiye": 40.0}]
    D.attach_stock(engine, T, items)
    assert items[0]["dagitim"]["basari"]["durum"] == "Baskısı Yok" and items[0]["dagitim"]["isaret"] is None


def test_freshness_reports_source_date_and_staleness(engine, monkeypatch):
    monkeypatch.setenv("PAZAR_DAGITIM_BAYAT_GUN", "2")
    _apply(engine, date(2026, 9, 25), [_b("9780000000001", 1)])
    f = D.freshness(engine, T, today=date(2026, 9, 29))
    assert f["basari"] == {"ad": "Başarı Dağıtım kataloğu", "tarih": "2026-09-25", "yasGun": 4, "bayat": True}
    assert f["dr"]["tarih"] is None and f["dr"]["bayat"] is False
    assert D.freshness(engine, T, today=date(2026, 9, 26))["basari"]["bayat"] is False
