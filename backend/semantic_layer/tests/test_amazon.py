"""M41 Amazon ve yurtdışı (ilk sürüm: Logo + CRM, yalnız okuma): SQL tanımı, okuma (Logo ve CRM sahte koşucuyla),
konsinye kalan = faturalanmamış sevk − iade, yurtdışı karne (döviz, geçen yıl, aynı dönem), satılmış haklar (ülke adı,
taraf firmalar), parametre doğrulaması, listeleme taslağında denetim, pazar kartında iki göz, adla bulunan cariyi eşleme
listesine ekleme, çevrimdışı istemci ve yetki kuralları.

Veriler yapaydır ve yalnız hesap kurallarını sınar; gerçek Logo/CRM kabulü test sunucusunda (scripts/acceptance/M41).
"""
from __future__ import annotations

from datetime import date

import httpx
import pytest

from semantic_bridge import access as AC
from semantic_bridge import eticaret_sources as E
from semantic_bridge.channels import amazon as A
from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import platform_common as PC
from semantic_bridge.channels import platforms as P
from semantic_bridge.channels import sources as src
from semantic_bridge.channels import store as S
from semantic_bridge.channels.amazon_client import AmazonClient
from semantic_layer.store.catalog_store import open_store

TN = "t1"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    S._ready.discard(id(e))
    A._ready.discard(id(e))
    A.ensure(e)
    return e


def conf(values=None):
    values = values or {}
    return lambda k: values.get(k, "")


# ------------------------------------------------------------------ SQL


def test_sql_keeps_the_definitions():
    k = A.konsinye_sql("411", 2026, ["AMZ'1"])
    for must in ("S.INVOICEREF = 0", "S.BILLED = 0", "S.TRCODE IN (3, 8)", "S.CANCELLED = 0", "C.CODE IN (N'AMZ''1')",
                 "'2026-01-01'", "'2027-01-01'", "LG_411_01_STLINE"):
        assert must in k, must
    y = A.yurtdisi_sql("211", 2025, ["YURTDIŞI"])
    for must in ("S.INVOICEREF <> 0", "TRCODE IN (2,3,7,8,9)", "LG_211_01_INVOICE", "F.TRRATE", "C.SPECODE2 IN (N'YURTDIŞI')",
                 "'2025-01-01'", "'2026-01-01'"):
        assert must in y, must
    assert "TRCURR, 0) NOT IN (0, 160)" in A.doviz_sql("411", 2026)
    assert "new_SozlesmeTipi = 1" in A.crm_rights_sql("Timas_MSCRM.dbo.") and "new_yurticiyurtdisi" in A.crm_rights_sql("X.dbo.")
    assert "new_siparistipi = 14" in A.crm_orders_sql("X.dbo.", 14, "2025-01-01")
    assert "FROM X.dbo.new_ulkeBase" in A.crm_country_sql("X.dbo.", "new_ulke")
    assert "k.new_StokKodu = N'K''1'" in A.crm_book_sql("X.dbo.", "K'1")
    for sql in (k, y, A.yurtdisi_kitap_sql("411", 2026, ["X"]), A.doviz_sql("411", 2026), A.crm_rights_sql("X.dbo.")):
        assert "{" not in sql
    assert A.settings(conf({"AMAZON_ULKE_TABLOSU": "x; DROP"}))["ulkeTablosu"] == "new_ulke"


# ------------------------------------------------------------------ okuma


LOGO = {
    "cariler": [{"cari_kodu": "AMZ1", "unvan": "AMAZON TURKEY PERAKENDE", "kanal": "E-TICARET", "ref": 5, "ulke": "TÜRKİYE"},
                {"cari_kodu": "AMZ2", "unvan": "AMAZON SELLER CENTRAL", "kanal": "", "ref": 6, "ulke": None}],
    "konsinye": [{"cari": "AMZ1", "stok_kodu": "K1", "sevk": 100, "iade": 20, "sevk_tutar": 5000, "ilk": "2026-02-01", "son": "2026-07-01"},
                 {"cari": "AMZ1", "stok_kodu": "K2", "sevk": 10, "iade": 0, "sevk_tutar": 400, "ilk": "2026-03-01", "son": "2026-03-01"}],
    2026: [{"cari": "Y1", "unvan": "Buch GmbH", "ulke": "ALMANYA", "doviz": 20, "ay": 1, "satis_ciro": 1000, "iade_ciro": 100,
            "satis_adet": 10, "iade_adet": 1, "doviz_net": 30, "fatura": 2},
           {"cari": "Y2", "unvan": "NL BV", "ulke": "HOLLANDA", "doviz": 0, "ay": 2, "satis_ciro": 500, "iade_ciro": 0,
            "satis_adet": 5, "iade_adet": 0, "doviz_net": 0, "fatura": 1}],
    2025: [{"cari": "Y1", "unvan": "Buch GmbH", "ulke": "ALMANYA", "doviz": 20, "ay": 1, "satis_ciro": 800, "iade_ciro": 0,
            "satis_adet": 8, "iade_adet": 0, "doviz_net": 25, "fatura": 1},
           {"cari": "Y1", "unvan": "Buch GmbH", "ulke": "ALMANYA", "doviz": 20, "ay": 11, "satis_ciro": 200, "iade_ciro": 0,
            "satis_adet": 2, "iade_adet": 0, "doviz_net": 6, "fatura": 1}],
    "kitap2026": [{"ulke": "ALMANYA", "stok_kodu": "K1", "satis_adet": 10, "iade_adet": 1, "satis_ciro": 1000, "iade_ciro": 100}],
}
CRM = {
    "siparis": [{"yil": 2026, "sayi": 7}, {"yil": 2025, "sayi": 3}],
    "ulke": [{"id": "GUID-DE", "ad": "Almanya"}],
    "haklar": [{"id": "S1", "no": "TS-1", "bas": "2020-01-01", "bit": None, "durum": 1, "ulke": "guid-de", "stok_kodu": "K1",
                "kitap": "Kitap K1", "firma": "Verlag A", "yon": 2},
               {"id": "S1", "no": "TS-1", "bas": "2020-01-01", "bit": None, "durum": 1, "ulke": "guid-de", "stok_kodu": "K1",
                "kitap": "Kitap K1", "firma": "Agentur B", "yon": 2},
               {"id": "S2", "no": "TS-2", "bas": None, "bit": None, "durum": 1, "ulke": None, "stok_kodu": "K3", "kitap": "Kitap K3",
                "firma": None, "yon": None}],
}


def fake_logo(sql):
    if "DEFINITION_ LIKE" in sql:
        return LOGO["cariler"]
    if "S.BILLED = 0" in sql:
        return LOGO["konsinye"] if "'2026-01-01'" in sql and "N'AMZ1'" in sql else []
    if "COUNT(*) AS toplam" in sql:
        return [{"toplam": 5, "satis": 3, "satis_tl": 1200}] if "'2026-01-01'" in sql else [{"toplam": 1, "satis": 1, "satis_tl": 10}]
    if "doviz_net" in sql:
        return LOGO[2026] if ">= '2026-01-01'" in sql else LOGO[2025]   # 2025 sorgusunun üst sınırı da 2026-01-01
    if "C.COUNTRY AS ulke, I.CODE" in sql:
        return LOGO["kitap2026"] if ">= '2026-01-01'" in sql else []
    raise AssertionError("beklenmeyen Logo sorgusu: " + sql[:80])


def fake_crm(sql):
    if "new_siparistipi" in sql:
        return CRM["siparis"]
    if "new_ulkeBase" in sql:
        return CRM["ulke"]
    if "new_SozlesmeTipi = 1" in sql:
        return CRM["haklar"]
    raise AssertionError("beklenmeyen CRM sorgusu: " + sql[:80])


def _read(engine, monkeypatch):
    monkeypatch.setattr(src, "runner", lambda path: fake_logo if path == "logo.json" else fake_crm)
    monkeypatch.setattr(src, "firms_by_year", lambda run: {2025: "211", 2026: "411"})
    monkeypatch.setattr(src, "read_item_names", lambda run, firm, codes: {c: f"Kitap {c}" for c in codes})
    monkeypatch.setattr(E, "read_data_end", lambda run, firms: date(2026, 8, 17))
    S.sync_accounts(engine, TN, [{"cari_kodu": "AMZ1", "unvan": "AMAZON TURKEY", "kanal": "E-TICARET", "ref": 5, "firma": "411"}], {})
    M.decide(engine, TN, "ayse", "AMZ1", {"platform": "amazon"})
    return A.refresh(engine, TN, "logo.json", "crm.json", "Timas_MSCRM.dbo", conf())


def test_refresh_reads_logo_and_crm(engine, monkeypatch):
    out = _read(engine, monkeypatch)
    assert out["years"] == [2025, 2026] and out["konsinyeYillari"] == [2026] and out["cariler"] == ["AMZ1"]
    assert out["doviz"]["2026"] == {"toplam": 5, "satis": 3, "satisTl": 1200.0} and out["crmError"] is None
    crm = S.meta_get(engine, TN, "amazon:crm")
    assert crm["siparis"] == {"2026": 7, "2025": 3} and crm["haklar"] == 2 and crm["tip"] == 14
    assert S.book_names(engine, TN, ["K1"]) == {"K1": "Kitap K1"}


def test_consignment_is_unbilled_shipment_minus_unbilled_return(engine, monkeypatch):
    _read(engine, monkeypatch)
    out = A.consignment(engine, TN, billed={"K1": 50.0})
    k1, k2 = out["items"]
    assert (k1["stokKodu"], k1["sevk"], k1["iade"], k1["kalan"], k1["faturalanan"]) == ("K1", 100, 20, 80, 50.0)
    assert (k2["stokKodu"], k2["kalan"], k2["faturalanan"]) == ("K2", 10, None)
    assert out["toplam"] == {"sevk": 110, "iade": 20, "kalan": 90, "sevkTutar": 5400.0, "kitap": 2}
    assert out["cariler"][0]["cari"] == "AMZ1" and out["faturalananBagli"] is True
    assert A.consignment(engine, TN, q="K2")["total"] == 1


def test_international_by_country_currency_and_same_period(engine, monkeypatch):
    _read(engine, monkeypatch)
    out = A.international(engine, TN)
    assert out["yil"] == 2026 and out["sonAy"] == 2
    de = next(x for x in out["ulkeler"] if x["ulke"] == "ALMANYA")
    assert (de["netCiro"], de["gecenYil"], de["gecenYilAyniDonem"], de["cari"]) == (900.0, 1000.0, 800.0, 1)
    y1 = next(x for x in out["items"] if x["cari"] == "Y1")
    assert (y1["doviz"], y1["dovizNet"], y1["gecenYil"], y1["netAdet"]) == ("EUR", 30.0, 1000.0, 9.0)
    assert out["dovizToplam"] == {"EUR": 30.0} and out["toplam"]["netCiro"] == 1400.0
    assert A.international(engine, TN, ulke="HOLLANDA")["toplam"]["netCiro"] == 500.0
    with pytest.raises(A.AmazonError):
        A.international(engine, TN, yil=2019)
    books = A.intl_books(engine, TN)
    assert books["items"][0]["stokKodu"] == "K1" and books["items"][0]["netAdet"] == 9


def test_rights_join_country_names_and_parties(engine, monkeypatch):
    _read(engine, monkeypatch)
    out = A.rights(engine, TN)
    k1 = next(x for x in out["items"] if x["stokKodu"] == "K1")
    assert k1["ulkeler"] == ["Almanya"] and k1["firmalar"] == ["Agentur B", "Verlag A"] and k1["yurtdisiNetAdet"] == 9
    assert len(k1["sozlesmeler"]) == 1 and k1["sozlesmeler"][0]["yurtdisiTaraf"] is True
    k3 = next(x for x in out["items"] if x["stokKodu"] == "K3")
    assert k3["ulkeler"] == [] and k3["yurtdisiNetAdet"] == 0.0
    assert out["ulkeler"] == {"Almanya": 1} and out["sozlesme"] == 2


def test_views_need_a_read_first(engine):
    with pytest.raises(A.AmazonError) as e:
        A.consignment(engine, TN)
    assert e.value.status == 409
    assert A.overview(engine, TN, {"eslendi": False})["okundu"] is False


def test_name_candidates_and_adding_to_the_mapping(engine, monkeypatch):
    _read(engine, monkeypatch)
    cands = S.meta_get(engine, TN, "amazon:cariler")["items"]
    view = {x["cariKodu"]: x["durum"] for x in PC.candidates_view(engine, TN, "amazon", cands)}
    assert view == {"AMZ1": "onayli", "AMZ2": "listede-yok"}
    out = PC.add_to_mapping(engine, TN, "amazon", next(c for c in cands if c["cari_kodu"] == "AMZ2"), "M41")
    assert out["durum"] == "aday" and out["platform"] == "amazon" and out["onaylayan"] is None     # onay insanda
    assert "AMZ2" not in PC.approved_codes(engine, TN, "amazon")


# ------------------------------------------------------------------ parametre, taslak, pazar kartı


def test_params_are_validated(engine):
    out, diff = A.set_params(engine, TN, "fin", "de", {"ad": "Almanya", "ulkeler": ["ALMANYA"], "kdvOrani": "0,07",
                                                      "komisyonOrani": 0.15, "kargoBirim": "45"})
    assert (out["pazar"], out["kdvOrani"], out["komisyonOrani"], out["kargoBirim"]) == ("DE", 0.07, 0.15, 45.0)
    assert diff["once"] is None and A.params(engine, TN)[0]["ulkeler"] == ["ALMANYA"]
    for bad in ({"ad": "X", "kdvOrani": 7}, {"ad": "", "kdvOrani": 0.1}, {"ad": "X", "kargoBirim": "-3"}):
        with pytest.raises(A.AmazonError):
            A.set_params(engine, TN, "fin", "de", bad)
    with pytest.raises(A.AmazonError):
        A.set_params(engine, TN, "fin", "!!", {"ad": "X"})


class Llm:
    def __init__(self, text):
        self.text, self.prompts = text, []

    def chat(self, messages, **kw):
        self.prompts.append(messages[-1]["content"])
        return self.text


def test_listing_draft_is_checked_and_never_sent(engine):
    card = {"ad": "Kitap K1", "yazar": "Yazar Bir", "arka_kapak": "Bir aile romanı."}
    llm = Llm('Tabii: {"baslik": "Das Buch", "aciklama": "Ein Familienroman. Das meistverkaufte Buch, en çok satan eser.",'
              ' "anahtar_kelimeler": ["roman", "familie"]}')
    out = A.create_draft(engine, TN, "ayse", llm, card, {"stokKodu": "K1", "pazar": "de", "dil": "Almanca", "tur": "listeleme"})
    assert out["pazar"] == "DE" and out["metin"]["aciklama"] == "Ein Familienroman." and out["metin"]["baslik"] == "Das Buch"
    assert len(out["dusen"]) == 1 and out["dusen"][0]["neden"] == "kanitsiz-iddia" and out["durum"] == "taslak"
    assert "Kitap K1" in llm.prompts[0] and "Almanca" in llm.prompts[0]
    used = A.set_draft_state(engine, TN, "ali", out["id"], "kullanildi")
    assert used["durum"] == "kullanildi" and used["guncelleyen"] == "ali"
    with pytest.raises(A.AmazonError):
        A.set_draft_state(engine, TN, "ali", out["id"], "gonderildi")
    with pytest.raises(A.AmazonError):
        A.create_draft(engine, TN, "ayse", None, card, {"stokKodu": "K1", "pazar": "DE", "dil": "Almanca"})
    with pytest.raises(A.AmazonError):
        A.create_draft(engine, TN, "ayse", llm, card, {"stokKodu": "K1", "pazar": "DE", "dil": "Almanca", "tur": "yayinla"})
    assert A.drafts(engine, TN, stok="K1")["total"] == 1


def test_market_card_indicators_and_two_eyes(engine, monkeypatch):
    _read(engine, monkeypatch)
    A.set_params(engine, TN, "fin", "DE", {"ad": "Almanya", "ulkeler": ["ALMANYA"]})
    card = A.create_card(engine, TN, "ali", Llm("Diaspora talebi güçlü görünüyor.\n3 kitap satıyor."), {"pazar": "de", "ulkeler": ["ALMANYA"]})
    g = card["gostergeler"]
    assert g["yillar"]["2026"] == {"netCiro": 900.0, "netAdet": 9.0} and g["yillar"]["2025"]["netCiro"] == 1000.0
    assert g["cariSayisi"] == 1 and g["hakSatilanKitap"] == 1 and g["parametre"]["pazar"] == "DE"
    assert g["kitaplar"][0] == {"stokKodu": "K1", "ad": "Kitap K1", "netAdet": 9.0}
    assert card["gerekce"] == "Diaspora talebi güçlü görünüyor." and card["karar"] is None
    with pytest.raises(A.AmazonError) as e:
        A.decide_card(engine, TN, "ali", card["id"], "girilsin", None)
    assert e.value.status == 403
    with pytest.raises(A.AmazonError):
        A.decide_card(engine, TN, "veli", card["id"], "bekle", None)        # gerekçe gerekli
    done = A.decide_card(engine, TN, "veli", card["id"], "girilsin", None)
    assert done["karar"] == "girilsin" and done["kararVeren"] == "veli"
    with pytest.raises(A.AmazonError) as e:
        A.decide_card(engine, TN, "zeynep", card["id"], "girilmesin", "x")
    assert e.value.status == 409
    with pytest.raises(A.AmazonError):
        A.create_card(engine, TN, "ali", None, {"pazar": "DE", "ulkeler": []})


# ------------------------------------------------------------------ istemci ve yetki


def test_offline_amazon_client_never_writes_or_connects():
    def boom(request):
        raise AssertionError("ağ çağrısı")

    c = AmazonClient(lambda k: "x", transport=httpx.MockTransport(boom))
    for method, path in (("PUT", "listings/2021-08-01/items/S/SKU"), ("PATCH", "listings/2021-08-01/items/S/SKU"),
                         ("POST", "feeds/2021-06-30/feeds"), ("POST", "orders/v0/orders"), ("DELETE", "orders/v0/orders")):
        with pytest.raises(P.ReadOnlyViolation):
            c.request(method, path)
    with pytest.raises(P.PlatformError):
        c.get("fba/inventory/v1/summaries")


def test_access_rules_for_amazon_endpoints():
    r = AC.rule_for
    assert r("/api/v1/channels/amazon/consignment") == {"sayfa:amazon-konsinye"}
    assert r("/api/v1/channels/amazon/international/books") == {"sayfa:amazon-yurtdisi"}
    assert r("/api/v1/channels/amazon/market-cards/x/decision") == {"sayfa:amazon-yurtdisi"}
    assert r("/api/v1/channels/amazon/drafts/x") == {"sayfa:amazon-taslaklar"}
    assert r("/api/v1/channels/amazon/overview") == {"sayfa:amazon"}
    assert r("/api/v1/channels/amazon/run-due") == AC.SYSTEM
    f = AC.features_for
    assert f("POST", "/api/v1/channels/amazon/drafts") == ["ozellik:amazon.taslak"]
    assert f("PUT", "/api/v1/channels/amazon/drafts/x") == ["ozellik:amazon.taslak"]
    assert f("POST", "/api/v1/channels/amazon/market-cards") == ["ozellik:amazon.taslak"]
    assert f("POST", "/api/v1/channels/amazon/market-cards/x/decision") == []       # açıkça verilen, ucun içinde
    assert f("PUT", "/api/v1/channels/amazon/params/DE") == []                      # açıkça verilen, ucun içinde
    assert f("POST", "/api/v1/channels/amazon/cariler/ekle") == ["ozellik:kanal.eslesme"]
    assert {"ozellik:amazon.parametre", "ozellik:amazon.pazar-karar"} <= AC.explicit_keys()


def test_api_gates(monkeypatch, store, settings):
    from fastapi.testclient import TestClient

    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm

    users = {"timas_session=a": "ayse", "timas_session=z": "zekiai"}
    monkeypatch.setattr(board_mod, "_fetch_user", lambda cookie: users.get(cookie))
    monkeypatch.setattr(board_mod, "_fetch_session", lambda cookie: {"username": users.get(cookie), "displayName": "x"})
    monkeypatch.setattr(admin_mod, "admins", lambda: ["zekiai"])
    monkeypatch.delenv("SEMANTIC_CALLER_TOKEN", raising=False)
    monkeypatch.delenv("SEMANTIC_ADMIN_TOKEN", raising=False)
    AC._ready.clear()
    AC.invalidate()
    S._ready.discard(id(store.engine))   # ortak store fixture'ı: eski bir motorun id'si yeniden kullanılmış olabilir
    A._ready.discard(id(store.engine))
    client = TestClient(create_app(Runtime(settings, store=store, llm=FakeLlm([""]))))
    a, z = {"cookie": "timas_session=a"}, {"cookie": "timas_session=z"}
    meta = client.get("/api/v1/channels/amazon/meta", headers=a).json()
    assert meta["api"]["bagli"] is False and meta["me"]["canParam"] is False and meta["me"]["canDecide"] is False
    assert client.get("/api/v1/channels/amazon/overview", headers=a).json()["okundu"] is False
    assert client.get("/api/v1/channels/amazon/consignment", headers=a).status_code == 409
    assert client.put("/api/v1/channels/amazon/params/DE", json={"ad": "Almanya"}, headers=a).status_code == 403
    ok = client.put("/api/v1/channels/amazon/params/DE", json={"ad": "Almanya", "kdvOrani": 0.07}, headers=z)
    assert ok.status_code == 200 and ok.json()["pazar"] == "DE"
    assert client.post("/api/v1/channels/amazon/drafts", json={}, headers=z).status_code == 400
    assert client.post("/api/v1/channels/amazon/run-due", headers=a).status_code == 403
