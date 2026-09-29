"""M39 dağıtımcı katalogları üç mevcut ekranda: kanal karnesi (kanalda bekleyen stok, Başarı sell-in'i, depodan çıkış),
kampanya adayları (D&R satış fiyatı ve «D&R zaten %X indirimde»), e-ticaret farkları («D&R fiyat farkı» türü).

Veriler yapaydır ve yalnız kuralları sınar; gerçek kaynakla kabul test sunucusunda (yan köprü, gerçek oturum).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
import sqlalchemy as sa

from semantic_bridge import eticaret as E
from semantic_bridge import kampanya as K
from semantic_bridge import pazar_dagitim as D
from semantic_bridge.channels import scorecard as SC
from semantic_bridge.channels import sources as csrc
from semantic_bridge.channels import store as S
from semantic_layer.store.catalog_store import open_store

T = "t1"
ALL = {"tsoft": True, "crm": True, "logo": True, "rights": True, "dr": True}
ST = E.settings_from(lambda key, default="": E.DEFAULTS.get(key, default))


@pytest.fixture
def engine(monkeypatch):
    monkeypatch.setenv("PAZAR_DAGITIM_ARALIK_GUN", "35")
    e = open_store("sqlite://").engine
    for mod in (D, E, S):
        mod._ready.discard(id(e))
        mod.ensure(e)
    return e


def _b(barkod, stok, marka="Timaş Yayınları", durum="Satışta"):
    return {"barkod": barkod, "urun_ad": f"Kitap {barkod}", "marka": marka, "kategori": "Edebiyat>Roman",
            "depo_stok": str(stok), "satis_fiyat": 200, "iskonto": "35", "stok_durum": durum, "baski_sayisi": "1. Baskı"}


def _r(isbn, b2b, site, liste=200.0, dr=160.0, deleted="0", sale="0", prefix="1"):
    return {"isbn": isbn, "name": f"Kitap {isbn}", "brand_name": "TİMAŞ YAYINLARI", "b2bstock": b2b, "available_stock": site,
            "list_price": liste, "dr_price": dr, "deleted": deleted, "sale_status_code": sale, "prefix_sale_status": prefix}


def _timas(engine, *barkodlar):
    with engine.begin() as c:
        c.execute(D.TITLES.update().where(D.TITLES.c.barkod.in_(barkodlar)).values(timas=True))


def _catalogs(engine, second=False):
    """Başarı: A, B TİMAŞ, R rakip; D&R: A (%20 indirimde, site stoğu 7), B (site yer tutucu 999), R rakip."""
    D.apply(engine, T, "basari", date(2026, 9, 25),
            D.parse([_b("9786050000011", 100), _b("9786050000028", 0), _b("9786259999999", 500, marka="Rakip")], "basari"),
            yontem="elle")
    D.apply(engine, T, "dr", date(2026, 9, 25),
            D.parse([_r("9786050000011", 40, 7), _r("9786050000028", 5, 999, dr=200.0),
                     _r("9786259999999", 900, 12, dr=100.0)], "dr"), yontem="elle")
    _timas(engine, "9786050000011", "9786050000028")
    D.store_pairs(engine, T, {("9786050000011", "K1"), ("9786050000028", "K2")})
    if second:
        D.apply(engine, T, "basari", date(2026, 9, 26),
                D.parse([_b("9786050000011", 70), _b("9786050000028", 0), _b("9786259999999", 400, marka="Rakip")],
                        "basari"), yontem="elle")


# ------------------------------------------------------------------ kanal stoğu (pazar_dagitim)


def test_channel_stock_counts_only_timas_titles_and_skips_placeholder_site_stock(engine):
    _catalogs(engine)
    ks = D.kanal_stok(engine, T)
    assert ks["basari"] == {"tarih": "2026-09-25", "baslik": 2, "stok": 100, "stokluBaslik": 1}   # rakibin 500'ü yok
    dr = ks["dr"]
    assert (dr["stok"], dr["baslik"], dr["stokluBaslik"]) == (45, 2, 2)
    assert (dr["siteStok"], dr["siteStokBilinen"]) == (7, 1)                                    # 999 yer tutucu sayılmaz
    assert ks["cikis"] is None and "iki günlük görüntü" in ks["cikisNot"] and "25.09.2026" in ks["cikisNot"]


def test_channel_stock_outflow_needs_two_snapshots_and_respects_the_period(engine):
    _catalogs(engine, second=True)
    ks = D.kanal_stok(engine, T, bas=date(2026, 1, 1), son=date(2026, 9, 30))
    assert ks["cikis"]["cikis"] == 30 and ks["cikis"]["bas"] == "2026-09-26"                    # rakibin 100'ü yok
    assert ks["basari"]["stok"] == 70
    empty = D.kanal_stok(engine, T, bas=date(2026, 1, 1), son=date(2026, 8, 31))
    assert empty["cikis"] is None and "Seçilen dönemde" in empty["cikisNot"]


def test_empty_catalog_gives_reasons_not_zeros(engine):
    ks = D.kanal_stok(engine, T)
    assert ks["basari"] is None and ks["dr"] is None and ks["cikisNot"] == "Başarı kataloğu henüz okunmadı."
    assert D.dr_fiyatlari(engine, T, codes=["K1"])["tarih"] is None


# ------------------------------------------------------------------ D&R fiyatı ve uyarı


def test_dr_prices_by_stock_code_and_ean_and_the_discount_warning(engine):
    _catalogs(engine)
    got = D.dr_fiyatlari(engine, T, codes=["K1", "YOK"], eans=["978-6259999999"])
    a = got["kod"]["K1"]
    assert (a["fiyat"], a["drFiyat"], a["indirim"], a["siteSatista"], a["katalogda"]) == (200.0, 160.0, 0.2, True, True)
    assert "YOK" not in got["kod"] and got["ean"]["9786259999999"]["indirim"] == 0.5 and got["tarih"] == "2026-09-25"
    assert D.dr_uyari(a) == "D&R zaten %20 indirimde"
    assert D.dr_uyari(got["kod"].get("K2")) is None                                            # indirim yok
    assert D.dr_uyari({**a, "siteSatista": False}) is None and D.dr_uyari({**a, "katalogda": False}) is None
    assert D.dr_uyari({**a, "indirim": 0.004}) is None                                          # yuvarlama kuruşu


def test_campaign_candidates_get_dr_price_and_warning(engine):
    _catalogs(engine)
    rows = [{"stok": "K1", "ean": "9786050000011"}, {"stok": "Z9", "ean": "9786259999999"}, {"stok": "Z8", "ean": None}]
    assert K.attach_dr(engine, T, rows) == "2026-09-25"
    assert rows[0]["dr"]["drFiyat"] == 160.0 and rows[0]["drUyari"] == "D&R zaten %20 indirimde"
    assert rows[1]["dr"]["indirim"] == 0.5                                                      # EAN ile eşleşti
    assert rows[2]["dr"] is None and rows[2]["drUyari"] is None


def test_campaign_candidates_survive_a_missing_catalog(engine, monkeypatch):
    rows = [{"stok": "K1", "ean": "9786050000011"}]
    monkeypatch.setattr(D, "dr_fiyatlari", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("tablo yok")))
    assert K.attach_dr(engine, T, rows) is None and rows[0]["dr"] is None


# ------------------------------------------------------------------ e-ticaret: D&R fiyat farkı


def _item(key="9786050000011", site=200.0, indirimli=None, crm=200.0, dr=None, aktif=True):
    return {"product_key": key, "stok_kodu": "K1", "ad": "Kitap", "ad_tsoft": "Kitap", "sitede": True, "tsoft_aktif": aktif,
            "crm_var": True, "crm_tsoftaktif": True, "crm_etkin": True, "stok_logo": 10.0, "stok_tsoft": 5.0,
            "fiyat_crm": crm, "fiyat_logo": crm, "fiyat_tsoft": site, "fiyat_tsoft_indirimli": indirimli, "eksik": [],
            "tsoft_urunleri": [{"id": "1", "aktif": aktif, "ad": "Kitap"}], "crm_kart_sayisi": 1, "logo_kayit": True,
            "logo_adet": 12.0, "logo_kesim_tarihi": "2026-09-25", "dr": dr}


def _dr(drf=160.0, liste=200.0, **kw):
    return {"barkod": "9786050000011", "fiyat": liste, "drFiyat": drf, "indirim": round(1 - drf / liste, 4) if drf else None,
            "durum": "Site: Satışa açık · Prefix: Satışa açık", "siteSatista": True, "stok": 5, "siteStok": 3,
            "timas": True, "katalogda": True, "son": "2026-09-25", **kw}


def _perakende(it, sources=ALL, st=ST):
    return [d for d in E.compute_diffs(it, st, sources) if d["tur"] == "perakende"]


def test_dr_cheaper_than_our_site_is_a_diff_with_the_dr_value():
    (d,) = _perakende(_item(dr=_dr()))
    assert "D&R'de 160,00 ₺" in d["aciklama"] or "D&R'de 160" in d["aciklama"]
    assert d["dr_deger"].startswith(E._money(160.0)) and "%20 indirim" in d["dr_deger"]
    assert _perakende(_item(indirimli=150.0, dr=_dr())) == []                  # sitede indirimli fiyat D&R'den düşük
    assert _perakende(_item(dr=_dr(), aktif=False)) == []                      # sitede satışta değil
    assert _perakende(_item(dr=_dr(siteSatista=False))) == []                  # D&R sitesinde satışta değil


def test_dr_list_price_differs_from_ours():
    (d,) = _perakende(_item(site=250.0, crm=250.0, dr=_dr(drf=250.0, liste=250.0 - 50)))
    assert "liste fiyatı" in d["aciklama"]
    assert _perakende(_item(site=200.0, dr=_dr(drf=200.0))) == []              # aynı liste, indirimsiz: fark yok


def test_dr_diff_only_for_timas_catalog_titles_and_readable_sources():
    assert _perakende(_item(dr=_dr(timas=False))) == []
    assert _perakende(_item(dr=_dr(katalogda=False))) == []
    assert _perakende(_item(dr=_dr()), sources={**ALL, "dr": False}) == []
    assert _perakende(_item(dr=_dr()), sources={**ALL, "crm": False}) == []     # liste esası okunamadı
    assert "perakende" in E.evaluated_kinds(ST, ALL)
    assert "perakende" not in E.evaluated_kinds(ST, {**ALL, "dr": False})


def test_dr_diff_is_stored_and_listed_with_its_value(engine):
    it = _item(dr=_dr())
    E.apply_run(engine, T, {it["product_key"]: it}, ST, ALL, datetime(2026, 9, 28, 3, 30, tzinfo=timezone.utc))
    lst = E.list_diffs(engine, T, tur="perakende")
    assert lst["total"] == 1 and lst["items"][0]["dr"].startswith(E._money(160.0))
    assert lst["turSayilari"]["perakende"] == 1
    csv_text = E.diffs_csv(E.all_diffs(engine, T)).decode("utf-8-sig")
    assert ";D&R;" in csv_text.splitlines()[0]


def test_old_diff_table_gets_the_new_column(monkeypatch):
    e = open_store("sqlite://").engine
    with e.begin() as c:
        c.execute(sa.text("CREATE TABLE semantic_eticaret_diffs (id VARCHAR(16) PRIMARY KEY, tenant_id VARCHAR(80))"))
    E._ready.discard(id(e))
    E.ensure(e)
    assert "dr_deger" in {c["name"] for c in sa.inspect(e).get_columns("semantic_eticaret_diffs")}


# ------------------------------------------------------------------ kanal karnesi


def _channels(engine, cari="12001.01.BA104"):
    for y in (2025, 2026):
        S.meta_set(engine, T, f"read:{y}", {"specodes": ["E-TICARET"], "codes": [], "kanalMapped": []})
        rows = [{"ay": m, **{k: 0.0 for k in csrc.METRICS}, "satis_adet": 100.0, "iade_adet": 10.0, "satis_ciro": 1000.0,
                 "iade_ciro": 100.0, "brut_satis": 1500.0, "iskonto": 500.0} for m in range(1, 13 if y == 2025 else 9)]
        S.meta_set(engine, T, f"dagitimci:{y}", {"cari": cari, "rows": rows})
    S.meta_set(engine, T, "data_end", {"date": "2026-08-17"})
    S.meta_set(engine, T, "dagitimci_kart", {"cari": cari, "unvan": "BAŞARI DAĞITIM", "bulundu": True})


def test_scorecard_shows_distributor_sell_in_next_to_waiting_stock(engine, monkeypatch):
    monkeypatch.setattr(csrc, "dagitimci_cari", lambda: "12001.01.BA104")
    _channels(engine)
    _catalogs(engine)
    card = SC.scorecard(engine, T, 2026, 8, dagitim=True)
    g = card["dagitimci"]
    b = g["basari"]
    assert b["satisOkundu"] and b["unvan"] == "BAŞARI DAĞITIM"
    assert b["kanalaSatis"]["netAdet"] == pytest.approx(90 * 8)                                 # Ocak–Ağustos
    assert b["gecenYil"]["netAdet"] == pytest.approx(90 * 7 + 90 * 17 / 31, abs=0.01)         # geçen yıl son ay gün payıyla (2 basamak)
    assert b["degisim"] == pytest.approx(720 / (630 + 90 * 17 / 31) - 1, abs=1e-4)  # yuvarlanmış adetten
    assert b["stok"]["stok"] == 100 and b["cikis"] is None and b["cikisNot"]
    assert g["dr"]["stok"]["stok"] == 45 and g["dr"]["kanalaSatis"] is None
    assert g["donem"] == {"bas": "2026-01-01", "son": "2026-08-17"}
    assert "dagitimci" not in SC.scorecard(engine, T, 2026, 8)                                 # D2C, rapor kurmaz
    assert all(p["platform"] != "basari" for p in card["platforms"])                           # platform toplamına girmez


def test_scorecard_distributor_block_when_cari_changed_or_catalog_missing(engine, monkeypatch):
    monkeypatch.setattr(csrc, "dagitimci_cari", lambda: "12001.01.YENI")
    _channels(engine)
    g = SC.scorecard(engine, T, 2026, 8, dagitim=True)["dagitimci"]
    assert g["basari"]["kanalaSatis"] is None and not g["basari"]["satisOkundu"] and g["basari"]["unvan"] is None
    assert g["basari"]["stok"] is None and g["dr"]["stok"] is None and g["hata"] is None


def test_distributor_sql_reuses_the_scorecard_query_for_one_cari():
    seen = []

    def run(sql):
        seen.append(sql)
        return [{"grup": "12001.01.BA104", "ay": 1, **{k: 1.0 for k in csrc.METRICS}}]

    rows = csrc.read_dagitimci(run, {2026: "411"}, 2026, "12001.01.BA104")
    assert rows == [{"ay": 1, **{k: 1.0 for k in csrc.METRICS}}]
    assert "C.CODE IN (N'12001.01.BA104')" in seen[0] and "INVOICEREF <> 0" in seen[0] and "E-TICARET" not in seen[0]


def test_dr_channel_detail_carries_waiting_stock(engine, monkeypatch):
    _channels(engine)
    _catalogs(engine)
    S.meta_set(engine, T, "read:2026", {"specodes": ["E-TICARET"], "codes": [], "kanalMapped": []})
    out = SC.channel(engine, T, "dr", 2026, 8)
    assert out["dagitimStok"]["dr"]["stok"] == 45 and out["dagitimStok"]["hata"] is None
    assert "dagitimStok" not in SC.channel(engine, T, "hepsiburada", 2026, 8)
