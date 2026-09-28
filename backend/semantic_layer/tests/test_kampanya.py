"""M35 E-ticaret kampanya yönetimi: indirim simülasyonu (net gelir, telif esası, marj), kontroller (maliyet, asgari fiyat,
son 30 gün en düşük fiyat, stok/tükenme, hak), onay akışı (hazırlayan onaylayamaz), tarih geçişleri, aday kuralları, sonuç
dönemleri, Zeki AI metin denetimi, maliyet sağlayıcısı bağı, yetki kuralları ve yazma yasağı.

Veriler yapaydır ve yalnız hesap kurallarını sınar; gerçek Logo/CRM kabulü test sunucusunda (`scripts/acceptance/M35/`).
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

from semantic_bridge import access as A
from semantic_bridge import kampanya as K
from semantic_bridge import kampanya_sources as src
from semantic_layer.store.catalog_store import open_store

T = "t1"
ST = K.settings_from(lambda key, default="": K.DEFAULTS.get(key, default))
BRIDGE = Path(K.__file__).parent
REF = date(2026, 10, 1)
UP = (1.0, "öğrenim kaydı yetersiz; artış varsayılmadı")


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    K._ready.discard(id(e))
    K.ensure(e)
    return e


@pytest.fixture(autouse=True)
def _no_provider():
    K.register_cost_provider(None)
    yield
    K.register_cost_provider(None)


def book(**kw):
    b = {"stok": "K1", "ad": "Kitap 1", "ean": "9786050000001", "listeCrm": 100.0, "listeLogo": None, "kdv": 0.0, "stokAdet": 1000.0,
         "gunlukHiz": 2.0, "maliyetYil": 3000.0, "maliyetliAdet": 100.0, "maliyetsizSatir": 0, "marjYili": 2026, "asgariFiyat": None,
         "sozlesmeler": [], "hak": "var", "durumBayragi": None, "sezonlar": [], "yazar": "Yazar A", "crmTip": 1,
         "adetSon": 180.0, "adetOnceki": 400.0}
    b.update(kw)
    return b


CAMP = {"kanal": "site", "kanalKesinti": None, "beklenenArtis": None, "baslangic": "2026-10-10", "bitis": "2026-10-20"}


def kod(out, code):
    return [k for k in json.loads(out["kontroller_json"]) if k["kod"] == code]


# ------------------------------------------------------------------ simülasyon


def test_net_revenue_cost_and_margin_before_and_after():
    cost = {"maliyet": 30.0, "kaynak": "Logo gerçekleşen maliyet (2026)"}
    out = K.simulate_item(book(kdv=10.0), {"indirim": 0.3}, {**CAMP, "kanalKesinti": 0.1, "kanal": "pazar_yeri"}, ST, cost, None,
                          REF, REF, UP)
    assert out["kampanya_fiyati"] == 70.0 and out["indirim_orani"] == pytest.approx(0.3)
    assert out["net_once"] == pytest.approx(100 / 1.1 * 0.9, abs=1e-3)
    assert out["net_sonra"] == pytest.approx(70 / 1.1 * 0.9, abs=1e-3)
    assert out["marj_sonra"] == pytest.approx(70 / 1.1 * 0.9 - 30, abs=1e-3)
    assert out["marj_orani_sonra"] == pytest.approx((70 / 1.1 * 0.9 - 30) / (70 / 1.1 * 0.9), abs=1e-3)
    assert not out["maliyet_eksik"]


def test_fixed_price_sets_the_discount():
    out = K.simulate_item(book(), {"kampanyaFiyati": 75.0}, CAMP, ST, {"maliyet": 30.0, "kaynak": "x"}, None, REF, REF, UP)
    assert out["kampanya_fiyati"] == 75.0 and out["indirim_orani"] == pytest.approx(0.25)


def test_missing_cost_means_margin_cannot_be_computed():
    out = K.simulate_item(book(), {"indirim": 0.2}, CAMP, ST, {"maliyet": None, "kaynak": "Maliyet bilinmiyor"}, None, REF, REF, UP)
    assert out["marj_once"] is None and out["marj_sonra"] is None and out["maliyet_eksik"]
    assert kod(out, "maliyet")[0]["seviye"] == "kirmizi"


@pytest.mark.parametrize("hesaplama,tur,once,sonra", [
    (2, None, 10.0, 10.0),          # perakende (liste) fiyatından: indirim telife yansımaz
    (1, None, 10.0, 7.0),           # toptan satış fiyatı: birim net gelirden
    (3, None, 10.0, 7.0),           # perakende oranlı: kampanya perakende fiyatından
    (None, 1, 10.0, 10.0),          # tip boş, telif türü brüt → liste
    (None, 2, 10.0, 7.0),           # tip boş, net
])
def test_royalty_basis_follows_the_contract(hesaplama, tur, once, sonra):
    ks = [{"odeme": 2, "oran": 10.0, "hesaplama": hesaplama, "tur": tur, "asgari": None}]
    out = K.simulate_item(book(sozlesmeler=ks), {"indirim": 0.3}, CAMP, ST, {"maliyet": 30.0, "kaynak": "x"}, None, REF, REF, UP)
    assert out["telif_once"] == pytest.approx(once) and out["telif_sonra"] == pytest.approx(sonra)
    assert out["marj_sonra"] == pytest.approx(70 - 30 - sonra)
    if hesaplama == 2:
        assert kod(out, "telif")[0]["seviye"] == "bilgi"


def test_print_based_royalty_does_not_change_with_price_and_missing_rate_blocks_margin():
    ks = [{"odeme": 1, "oran": 12.0, "hesaplama": 2, "tur": None, "asgari": None}]
    out = K.simulate_item(book(sozlesmeler=ks), {"indirim": 0.3}, CAMP, ST, {"maliyet": 30.0, "kaynak": "x"}, None, REF, REF, UP)
    assert out["telif_once"] == 0 and out["telif_sonra"] == 0
    ks = [{"odeme": 2, "oran": None, "hesaplama": 1, "tur": None, "asgari": None}]
    out = K.simulate_item(book(sozlesmeler=ks), {"indirim": 0.3}, CAMP, ST, {"maliyet": 30.0, "kaynak": "x"}, None, REF, REF, UP)
    assert out["telif_once"] is None and out["marj_sonra"] is None
    assert kod(out, "telif")[0]["seviye"] == "sari"


def test_contract_floor_price_is_red_below_and_info_for_dealers():
    b = book(asgariFiyat=80.0, sozlesmeler=[{"odeme": 3, "oran": None, "hesaplama": None, "tur": None, "asgari": 80.0}])
    out = K.simulate_item(b, {"indirim": 0.3}, CAMP, ST, {"maliyet": 30.0, "kaynak": "x"}, None, REF, REF, UP)
    assert kod(out, "asgari")[0]["seviye"] == "kirmizi"
    ok = K.simulate_item(b, {"indirim": 0.1}, CAMP, ST, {"maliyet": 30.0, "kaynak": "x"}, None, REF, REF, UP)
    assert not kod(ok, "asgari")
    dealer = K.simulate_item(b, {"indirim": 0.3}, {**CAMP, "kanal": "bayi"}, ST, {"maliyet": 30.0, "kaynak": "x"}, None, REF, REF, UP)
    assert kod(dealer, "asgari")[0]["seviye"] == "bilgi"
    none = K.simulate_item(book(sozlesmeler=[{"odeme": 3}]), {"indirim": 0.3}, CAMP, ST, {"maliyet": 30.0, "kaynak": "x"}, None, REF, REF, UP)
    assert "asgari fiyat yok" in kod(none, "asgari")[0]["mesaj"]


def test_thirty_day_lowest_price_rule_on_site():
    cost = {"maliyet": 30.0, "kaynak": "x"}
    missing = K.simulate_item(book(), {"indirim": 0.3}, CAMP, ST, cost, None, REF, REF, UP)
    assert kod(missing, "fiyat-30")[0]["seviye"] == "sari"
    floor = {"min": 70.0, "gun": 30, "son": 100.0, "sonGun": "2026-09-30"}
    red = K.simulate_item(book(), {"indirim": 0.3}, CAMP, ST, cost, floor, REF, REF, UP)      # 70 ≥ 70: indirim değil
    assert kod(red, "fiyat-30")[0]["seviye"] == "kirmizi"
    floor = {"min": 90.0, "gun": 30, "son": 100.0, "sonGun": "2026-09-30"}
    warn = K.simulate_item(book(), {"indirim": 0.3}, CAMP, ST, cost, floor, REF, REF, UP)    # liste 100 > 90
    assert [k["seviye"] for k in kod(warn, "fiyat-30")] == ["sari"]
    other = K.simulate_item(book(), {"indirim": 0.3}, {**CAMP, "kanal": "pazar_yeri"}, ST, cost, None, REF, REF, UP)
    assert kod(other, "fiyat-30")[0]["seviye"] == "bilgi"


def test_stockout_before_end_is_flagged_and_uplift_used():
    b = book(stokAdet=30.0, gunlukHiz=2.0)
    out = K.simulate_item(b, {"indirim": 0.3}, {**CAMP, "beklenenArtis": 3.0}, ST, {"maliyet": 30.0, "kaynak": "x"}, None, REF,
                          date(2026, 9, 30), UP)
    # veri sonu 30.09 → 10.10 başlangıç: 10 gün × 2 = 20 satılır, 10 kalır; kampanyada 6/gün → 1,7 gün
    assert out["tukenme_tahmini"] == "2026-10-11"
    assert kod(out, "stok")[0]["seviye"] == "sari"
    zero = K.simulate_item(book(stokAdet=0.0), {"indirim": 0.3}, CAMP, ST, {"maliyet": 30.0, "kaynak": "x"}, None, REF, REF, UP)
    assert kod(zero, "stok")[0]["seviye"] == "kirmizi"


def test_rights_and_status_flags():
    cost = {"maliyet": 30.0, "kaynak": "x"}
    assert kod(K.simulate_item(book(hak="yok"), {"indirim": 0.1}, CAMP, ST, cost, None, REF, REF, UP), "hak")[0]["seviye"] == "kirmizi"
    assert kod(K.simulate_item(book(hak="eksik"), {"indirim": 0.1}, CAMP, ST, cost, None, REF, REF, UP), "hak")[0]["seviye"] == "sari"
    assert kod(K.simulate_item(book(durumBayragi="cekildi"), {"indirim": 0.1}, CAMP, ST, cost, None, REF, REF, UP), "hak")


def test_ratio_accepts_percent_and_fraction():
    assert K.ratio("30", "x") == 0.3 and K.ratio(0.25, "x") == 0.25 and K.ratio("1", "x") == 0.01 and K.ratio(None, "x") is None
    with pytest.raises(K.KampanyaError):
        K.ratio(96, "x")


# ------------------------------------------------------------------ kayıt ve onay akışı


def _seed_books(engine):
    now = datetime.now(timezone.utc)
    rows = [
        dict(stok_kodu="K1", ad="Kitap 1", ean="9786050000001", crm_tip=1, liste_crm=100.0, kdv=0.0, stok=1000.0, adet_son=30.0,
             adet_onceki=300.0, gunluk_hiz=0.33, maliyet_yil=3000.0, maliyetli_adet=100.0, marj_yili=2026, hak="var",
             in_logo=True, in_crm=True, asof=now, sezon_json=json.dumps(["ogretmenler-gunu"])),
        dict(stok_kodu="K2", ad="Kitap 2", ean="9786050000002", crm_tip=1, liste_crm=80.0, kdv=0.0, stok=50.0, adet_son=300.0,
             adet_onceki=280.0, gunluk_hiz=3.3, maliyet_yil=None, maliyetli_adet=None, hak="var", in_logo=True, in_crm=True, asof=now),
        dict(stok_kodu="K3", ad="Kitap 3", ean="9786050000003", crm_tip=1, liste_crm=60.0, kdv=0.0, stok=900.0, adet_son=0.0,
             adet_onceki=0.0, gunluk_hiz=0.0, hak="yok", in_logo=True, in_crm=True, asof=now),
        dict(stok_kodu="S1", ad="Set", ean=None, crm_tip=4, liste_crm=200.0, kdv=0.0, stok=900.0, adet_son=0.0, adet_onceki=10.0,
             gunluk_hiz=0.0, in_logo=True, in_crm=True, asof=now),
    ]
    with engine.begin() as c:
        for r in rows:                      # satırların kolonları farklı: tek tek
            c.execute(K.BOOKS.insert().values(**r))


def _camp(engine, user="ayse", **kw):
    body = {"ad": "Öğretmenler Günü", "kanal": "site", "baslangic": "2026-11-17", "bitis": "2026-11-24", "varsayilanIndirim": 25}
    body.update(kw)
    return K.create_campaign(engine, T, user, body)


def test_create_add_submit_and_two_eyes(engine):
    _seed_books(engine)
    c = _camp(engine)
    assert c["id"].startswith(f"KM-{K.today().year}-") and c["durum"] == "taslak" and c["varsayilanIndirim"] == 0.25
    out, missing = K.add_items(engine, ST, T, c["id"], [{"stok": "K1"}, {"stok": "K2", "kampanyaFiyati": 60}, {"stok": "YOK"}])
    assert missing == ["YOK"]
    items = {i["stok"]: i for i in out["kitaplar"]}
    assert items["K1"]["indirim"] == pytest.approx(0.25) and items["K1"]["kampanyaFiyati"] == 75.0
    assert items["K2"]["kampanyaFiyati"] == 60.0 and items["K2"]["maliyetEksik"]      # maliyetsiz: marj hesaplanamaz
    assert items["K1"]["marjSonra"] == pytest.approx(75 - 30)
    # toplu indirim sabit fiyatı ezmez mi? Ezer: toplu indirim bütün kitaplara uygulanır.
    out = K.simulate(engine, ST, T, c["id"], bulk=0.2)
    assert {i["stok"]: i["kampanyaFiyati"] for i in out["kitaplar"]} == {"K1": 80.0, "K2": 64.0}
    sub = K.submit(engine, ST, T, "ayse", c["id"])
    assert sub["durum"] == "onay_bekliyor" and sub["gonderen"] == "ayse"
    with pytest.raises(K.KampanyaError) as e:
        K.decide(engine, T, "ayse", c["id"], True, None)
    assert e.value.status == 409
    with pytest.raises(K.KampanyaError):
        K.decide(engine, T, "mehmet", c["id"], False, "")                               # geri göndermede gerekçe şart
    with pytest.raises(K.KampanyaError):
        K.update_item(engine, ST, T, c["id"], "K1", {"indirim": 10})                    # onaydaki kampanya değişmez
    ok = K.decide(engine, T, "mehmet", c["id"], True, "Uygun")
    assert ok["durum"] == "onaylandi" and ok["onaylayan"] == "mehmet"
    with pytest.raises(K.KampanyaError):
        K.simulate(engine, ST, T, c["id"])                                              # onaylı hesap değişmez
    K.simulate(engine, ST, T, c["id"], stock_only=True)                                 # yalnız stok tazelenir


def test_reject_returns_to_draft_and_withdraw(engine):
    _seed_books(engine)
    c = _camp(engine)
    K.add_items(engine, ST, T, c["id"], [{"stok": "K1"}])
    K.submit(engine, ST, T, "ayse", c["id"])
    back = K.decide(engine, T, "mehmet", c["id"], False, "Marj düşük")
    assert back["durum"] == "taslak" and back["onayNotu"] == "Marj düşük"
    K.submit(engine, ST, T, "ayse", c["id"])
    assert K.withdraw(engine, T, "ayse", c["id"])["durum"] == "taslak"
    with pytest.raises(K.KampanyaError):
        K.delete_campaign(engine, T, c["id"])                                           # bir kez gönderilen silinmez, iptal edilir
    assert K.cancel_campaign(engine, T, "ayse", c["id"], "Platform vazgeçti")["durum"] == "iptal"


def test_submit_needs_books_and_prices(engine):
    _seed_books(engine)
    c = _camp(engine, varsayilanIndirim=None)
    with pytest.raises(K.KampanyaError):
        K.submit(engine, ST, T, "ayse", c["id"])
    K.add_items(engine, ST, T, c["id"], [{"stok": "K1"}])
    with pytest.raises(K.KampanyaError, match="kampanya fiyatı"):
        K.submit(engine, ST, T, "ayse", c["id"])


def test_head_validation(engine):
    with pytest.raises(K.KampanyaError):
        K.create_campaign(engine, T, "a", {"ad": "x", "kanal": "tv", "baslangic": "2026-10-01", "bitis": "2026-10-02"})
    with pytest.raises(K.KampanyaError):
        K.create_campaign(engine, T, "a", {"ad": "x", "kanal": "site", "baslangic": "2026-10-05", "bitis": "2026-10-02"})


def test_date_transitions(engine):
    _seed_books(engine)
    c = _camp(engine, baslangic="2026-10-01", bitis="2026-10-05")
    K.add_items(engine, ST, T, c["id"], [{"stok": "K1"}])
    K.submit(engine, ST, T, "ayse", c["id"])
    K.decide(engine, T, "mehmet", c["id"], True, None)
    assert K.advance(engine, T, date(2026, 9, 30)) == []
    assert K.advance(engine, T, date(2026, 10, 2))[0]["durum"] == "yurutuluyor"
    assert K.advance(engine, T, date(2026, 10, 6))[0]["durum"] == "bitti"


def test_copy_edit_after_approval_but_not_the_calculation(engine):
    _seed_books(engine)
    c = _camp(engine)
    K.add_items(engine, ST, T, c["id"], [{"stok": "K1"}])
    K.submit(engine, ST, T, "ayse", c["id"])
    K.decide(engine, T, "mehmet", c["id"], True, None)
    out, info = K.update_campaign(engine, T, "ayse", c["id"], {"metin": {"secili": {"baslik": "Öğretmenlerimize"}}})
    assert out["metin"]["secili"]["baslik"] == "Öğretmenlerimize"
    with pytest.raises(K.KampanyaError):
        K.update_campaign(engine, T, "ayse", c["id"], {"kanalKesinti": 10})
    with pytest.raises(K.KampanyaError):
        K.update_campaign(engine, T, "ayse", c["id"], {"metin": {"secili": {"banner": "x" * 41}}})
    out, _ = K.update_campaign(engine, T, "ayse", c["id"], {"kurulumNotu": "Panelde kuruldu"})
    assert out["kurulduBy"] == "ayse"


# ------------------------------------------------------------------ adaylar


def test_candidates_signals_and_conditions(engine, monkeypatch):
    _seed_books(engine)
    monkeypatch.setattr(K, "_special_days", lambda e, t, a, b: [{"gunKey": "ogretmenler-gunu", "ad": "Öğretmenler Günü"}])
    got = K.candidates(engine, ST, T, rules="stok,dusus,sezon,hak", ref=REF)
    codes = [x["stok"] for x in got["items"]]
    assert "K1" in codes                     # stok 100 ay, satış %90 düştü, sezon bağı
    assert "K2" not in codes                 # stok az, satış yükseliyor
    assert "K3" not in codes                 # hak yok
    assert "S1" not in codes                 # set kartı aday değil
    k1 = got["items"][0]
    assert k1["stok"] == "K1" and "Öğretmenler Günü" in k1["gerekce"] and k1["gerekce"][0].isupper()
    only_cost = K.candidates(engine, ST, T, rules="stok,maliyet", ref=REF)
    assert [x["stok"] for x in only_cost["items"]] == ["K1"]    # K3 maliyetsiz, K2 sinyalsiz


def test_candidates_exclude_books_already_in_the_campaign(engine, monkeypatch):
    _seed_books(engine)
    monkeypatch.setattr(K, "_special_days", lambda e, t, a, b: [])
    c = _camp(engine)
    K.add_items(engine, ST, T, c["id"], [{"stok": "K1"}])
    assert "K1" not in [x["stok"] for x in K.candidates(engine, ST, T, cid=c["id"], rules="stok", ref=REF)["items"]]


# ------------------------------------------------------------------ maliyet sağlayıcısı


def test_cost_provider_first_then_logo_fallback():
    from decimal import Decimal

    books = {"A": book(stok="A", maliyetYil=None, maliyetliAdet=None), "B": book(stok="B")}
    K.register_cost_provider(lambda codes: {"A": {"maliyet": Decimal("12.5"), "kaynak": "onayli-analiz", "asama": "kesin", "tarih": "2026-09-01"},
                                            "B": {"maliyet": None, "kaynak": "yok"}})
    got = K.costs_for(ST, books)
    assert got["A"]["maliyet"] == 12.5 and got["A"]["kaynak"].startswith("Onaylı fiyat analizi")
    assert got["B"]["maliyet"] == 30.0 and "Logo gerçekleşen" in got["B"]["kaynak"]
    only = K.costs_for({**ST, "costSource": "m9"}, books)
    assert only["B"]["maliyet"] is None
    assert all(v["maliyet"] is None for v in K.costs_for({**ST, "costSource": "yok"}, books).values())


# ------------------------------------------------------------------ fiyat kaydı ve sonuç


def test_price_floor_uses_sale_price_and_counts_days(engine):
    now = datetime.now(timezone.utc)
    with engine.begin() as c:
        for i, (p, s_) in enumerate([(100.0, None), (100.0, 85.0), (100.0, None)]):
            c.execute(K.SNAPS.insert().values(tarih=(date(2026, 10, 1) + timedelta(days=i)).isoformat(), product_key="E1", kaynak="tsoft",
                                              fiyat=p, indirimli=s_, asof=now))
    got = K.price_floor(engine, ["E1"], date(2026, 10, 10), 30)
    assert got["E1"]["min"] == 85.0 and got["E1"]["gun"] == 3 and got["E1"]["son"] == 100.0
    assert K.price_floor(engine, ["E1"], date(2026, 10, 2), 30)["E1"]["gun"] == 1     # başlangıç günü hariç


def test_result_windows_and_summary(engine):
    _seed_books(engine)
    c = _camp(engine, baslangic="2026-10-11", bitis="2026-10-20")
    K.add_items(engine, ST, T, c["id"], [{"stok": "K1"}])
    wins = K.windows(date(2026, 10, 11), date(2026, 10, 20), 14)
    assert wins["once"] == (date(2026, 10, 1), date(2026, 10, 10)) and wins["sonra"] == (date(2026, 10, 21), date(2026, 11, 3))
    rows = [{"stok": "K1", "gun": date(2026, 10, 5), "adet": 10.0, "iade": 0.0, "tutar": 500.0, "maliyet": 300.0, "maliyetliTutar": 500.0},
            {"stok": "K1", "gun": date(2026, 10, 12), "adet": 40.0, "iade": 4.0, "tutar": 1500.0, "maliyet": 1200.0, "maliyetliTutar": 1500.0},
            {"stok": "K1", "gun": date(2026, 12, 1), "adet": 99.0, "iade": 0.0, "tutar": 1.0, "maliyet": 0.0, "maliyetliTutar": 0.0}]
    assert K.store_results(engine, c["id"], rows, wins, date(2026, 10, 25), "logo") == 2        # pencere dışı satır yazılmaz
    with engine.begin() as cn:
        cn.execute(K.CAMPAIGNS.update().where(K.CAMPAIGNS.c.id == c["id"]).values(durum="bitti"))
    r = K.results(engine, ST, T, c["id"])
    assert r["donemler"]["once"]["gun"] == 10 and r["donemler"]["kampanya"]["gun"] == 10 and r["donemler"]["sonra"]["gun"] == 5
    assert r["donemler"]["once"]["gunlukAdet"] == 1.0 and r["donemler"]["kampanya"]["gunlukAdet"] == 4.0
    assert r["degisim"]["satis"] == 4.0 and r["donemler"]["kampanya"]["iadeOrani"] == 0.1
    assert r["donemler"]["kampanya"]["marjOrani"] == pytest.approx(0.2)
    assert any("bütün kanallardan" in n for n in r["notlar"])
    lr = K.add_learning(engine, ST, T, "ayse", c["id"], {"ozet": "İndirim satışı dört kat artırdı."})
    got = K.learnings(engine, T, kanal="site")["items"][0]
    assert got["id"] == lr["id"] and got["satisDegisimi"] == 4.0 and got["indirim"] == pytest.approx(0.25)
    assert K.uplift_for(engine, T, "site", {**ST, "learnMinN": 1}) == (4.0, "aynı kanaldaki 1 kampanyanın öğrenim kaydı (ortanca)")
    assert K.uplift_for(engine, T, "site", ST)[0] == 1.0
    with pytest.raises(K.KampanyaError):
        K.delete_learning(engine, T, "mehmet", lr["id"], False)


def test_overlaps_same_channel_and_platform():
    camps = [{"id": "A", "ad": "A", "kanal": "site", "platform": None, "baslangic": "2026-10-01", "bitis": "2026-10-10"},
             {"id": "B", "ad": "B", "kanal": "site", "platform": None, "baslangic": "2026-10-05", "bitis": "2026-10-12"},
             {"id": "C", "ad": "C", "kanal": "bayi", "platform": None, "baslangic": "2026-10-05", "bitis": "2026-10-12"}]
    days = [{"id": "g", "tur": "ozel_gun", "ad": "Gün", "baslangic": "2026-10-11", "bitis": "2026-10-11"}]
    out = K.overlaps(camps, days)
    assert [x for x in out if x["tur"] == "kampanya"] == [{"tur": "kampanya", "a": "A", "b": "B", "mesaj": out[0]["mesaj"]}]
    assert {x["a"] for x in out if x["tur"] == "denk"} == {"B", "C"}


# ------------------------------------------------------------------ Zeki AI


def test_copy_variants_are_guarded_and_limited():
    raw = "- Öğretmenlerimize özel kitaplar\n- %30 indirimle Kitap 1\n- 5 kat daha çok satan kitaplar\n- " + "x" * 70
    got, dropped = K.parse_variants(raw, 60, ["Kitap 1", "Öğretmenler Günü"], ["%30", "30"])
    assert got == ["Öğretmenlerimize özel kitaplar", "%30 indirimle Kitap 1"]
    assert dropped == 2


class _Choice:
    def __init__(self, choice, p):
        self.choice, self.probability = choice, p

    def confident(self, min_prob, min_margin=0.0):
        return self.probability is not None and self.probability >= min_prob


class _Llm:
    def __init__(self, choice, p=0.9):
        self._c = _Choice(choice, p)

    def choose(self, prompt, choices):
        assert self._c.choice in choices
        return self._c


def test_crm_campaign_type_rules_then_model(engine):
    camps = [{"id": "a" * 8 + "-0000-0000-0000-000000000001", "ad": "Yaz iskontosu", "netIskonto": 5.0},
             {"id": "a" * 8 + "-0000-0000-0000-000000000002", "ad": "Kasım vade", "vadeli": True},
             {"id": "a" * 8 + "-0000-0000-0000-000000000003", "ad": "Okul stant kampanyası"},
             {"id": "a" * 8 + "-0000-0000-0000-000000000004", "ad": "Bahar özel", "aciklama": "hediye kitap"}]
    out = K.classify_crm(engine, ST, _Llm("Hediye ürün kampanyası"), camps, 60)
    assert out == {"kural": 3, "model": 1, "belirsiz": 0, "kalan": 0}
    types = K.crm_types(engine, [c["id"] for c in camps])
    assert [types[c["id"]]["tur"] for c in camps] == ["iskonto", "vade", "stant", "hediye"]
    more = [{"id": "a" * 8 + "-0000-0000-0000-000000000005", "ad": "Belirsiz"}]
    assert K.classify_crm(engine, ST, _Llm("Diğer", 0.4), more, 60)["belirsiz"] == 1


# ------------------------------------------------------------------ kaynak ve güvenlik


def test_sql_guards_and_values_join():
    with pytest.raises(src.SourceError):
        src.daily_sql("411", ["A'; DROP TABLE x --"], date(2026, 1, 1), date(2026, 2, 1))
    with pytest.raises(src.SourceError):
        src.prefix("Timas;DROP.dbo")
    with pytest.raises(src.SourceError):
        src.monthly_sql("41", date(2026, 1, 1), date(2026, 2, 1))
    sql = src.daily_sql("411", ["K1", "K2"], date(2026, 1, 1), date(2026, 2, 1), ["120.01"])
    assert "JOIN (VALUES (N'K1'), (N'K2')) AS K(kod)" in sql and "LG_411_CLCARD" in sql and " IN (N'" not in sql
    m = src.margin_sql("411", date(2026, 1, 1), date(2027, 1, 1))
    assert "S.TRCODE IN (7,8,9)" in m and "S.INVOICEREF <> 0" in m and "OUTCOST = 0" in m
    assert src.money_text("1.250,50 TL") == 1250.5 and src.money_text("45") == 45.0 and src.money_text("") is None
    assert K.parse_kanal_cari("site:120.01.001, 120.01.002;tv:1;bayi:") == {"site": ["120.01.001", "120.01.002"]}


def test_year_spans_split_by_firm():
    firms = {2025: "211", 2026: "411"}
    spans = src.year_spans(firms, date(2025, 12, 20), date(2026, 1, 10))
    assert spans == [("211", date(2025, 12, 20), date(2026, 1, 1)), ("411", date(2026, 1, 1), date(2026, 1, 10))]


def test_no_write_to_crm_logo_or_tsoft():
    body = (BRIDGE / "kampanya_sources.py").read_text(encoding="utf-8")
    sql = re.findall(r'"""(.*?)"""|"([^"\n]*(?:SELECT|FROM)[^"\n]*)"', body, re.S)
    blob = " ".join(a + b for a, b in sql).upper()
    for kw in ("INSERT ", "UPDATE ", "DELETE ", "MERGE ", "EXEC ", "DROP "):
        assert kw not in blob
    for f in ("kampanya.py", "kampanya_api.py", "kampanya_sources.py"):
        text = (BRIDGE / f).read_text(encoding="utf-8")
        assert "seo_geo.connections" not in text and "seo_geo import connections" not in text
        assert "import httpx" not in text and "requests." not in text


def test_request_is_imported_at_module_level():
    text = (BRIDGE / "kampanya_api.py").read_text(encoding="utf-8")
    assert re.search(r"^from fastapi import .*\bRequest\b", text, re.M)


def test_no_technology_names_on_screen_texts():
    banned = re.compile(r"qwen|vllm|temporal|timesfm|ollama|openai|gpt|claude|llama", re.I)
    for f in ("kampanya.py", "kampanya_api.py"):
        strings = re.findall(r'"([^"\n]{12,})"', (BRIDGE / f).read_text(encoding="utf-8"))
        assert not [s for s in strings if banned.search(s)], f


# ------------------------------------------------------------------ yetki


def test_access_rules_for_campaigns():
    f = A.features_for
    D = "ozellik:kampanya.duzenle"
    assert A.rule_for("/api/v1/kampanya/overview") == frozenset({A.page("kampanya")})
    assert A.rule_for("/api/v1/kampanya/run-due") == A.SYSTEM
    assert f("POST", "/api/v1/kampanya/campaigns") == [D]
    assert f("PATCH", "/api/v1/kampanya/campaigns/KM-2026-0001") == [D]
    assert f("POST", "/api/v1/kampanya/campaigns/KM-2026-0001/items") == [D]
    assert f("PATCH", "/api/v1/kampanya/campaigns/KM-2026-0001/items/AB/12") == [D]
    assert f("POST", "/api/v1/kampanya/campaigns/KM-2026-0001/submit") == [D]
    assert f("POST", "/api/v1/kampanya/campaigns/KM-2026-0001/learnings") == [D]
    assert f("DELETE", "/api/v1/kampanya/calendar/KT-2026-0001") == [D]
    assert f("POST", "/api/v1/kampanya/campaigns/KM-2026-0001/decision") == []          # açıkça verilen onay ucun içinde
    assert f("POST", "/api/v1/kampanya/campaigns/KM-2026-0001/copy") == ["ozellik:kampanya.metin-uret"]
    assert f("POST", "/api/v1/kampanya/campaigns/KM-2026-0001/summary") == ["ozellik:kampanya.metin-uret"]
    assert f("GET", "/api/v1/kampanya/campaigns/KM-2026-0001/export.xlsx") == ["ozellik:veri.disa-aktar"]
    assert f("GET", "/api/v1/kampanya/candidates") == []
    assert f("POST", "/api/v1/kampanya/run-due") == []
    assert "ozellik:kampanya.onay" in A.explicit_keys()
    assert {"ozellik:kampanya.duzenle", "ozellik:kampanya.metin-uret"} <= A.all_keys() - A.explicit_keys()


def test_catalog_and_settings():
    cat = json.loads((BRIDGE / "access_catalog.json").read_text(encoding="utf-8"))
    assert any(p["key"] == "sayfa:kampanya" and p["area"] == "dijital" for p in cat["pages"])
    from semantic_bridge import admin

    keys = {s["key"] for s in admin.SPEC}
    assert set(K.DEFAULTS) <= keys
    assert any(g["id"] == "kampanya" for g in admin.GROUPS)


def test_tables_have_their_own_prefix():
    assert all(t.startswith("semantic_kampanya_") for t in K._md.tables)
