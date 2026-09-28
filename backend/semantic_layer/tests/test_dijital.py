"""M36 Dijital yayın ve e-kitap: hak kararı (e-kitap / sesli, telif kararı ve notun değişmesi), fırsat kuralı ve puanı,
yeni baskı tespiti, kitap satırlarının yazılması (kullanıcı kolonları korunur), CRM'e işlenecekler, platform durumu,
satış raporu yükleme (kolon tanıma, kişisel veri atılır, hiçbir satır atılmaz, kurallı eşleme, Zeki AI önerisi, kur,
çift dönem), uyarılar, yetki kuralları, yazma yasağı.

Veriler yapaydır ve yalnız kuralları sınar; gerçek CRM/Logo kabulü test sunucusunda (`scripts/acceptance/M36/`,
günlük 2026-09-28 M36).
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from semantic_bridge import access as A
from semantic_bridge import dijital as D
from semantic_bridge import dijital_sources as src
from semantic_bridge import contracts as C
from semantic_bridge import royalty as RY
from semantic_layer.store.catalog_store import open_store

T = "t1"
ST = D.settings_from(lambda key, default="": D.DEFAULTS.get(key, default))
BRIDGE = Path(D.__file__).parent
TODAY = date(2026, 9, 28)


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    D._ready.discard(id(e))
    RY._ready.discard(id(e))     # hak notu sınıflaması telifin tablosunda (ortak)
    C._ready.discard(id(e))
    D.ensure(e)
    return e


def contract(cid="C1", ebook=1, audio=0, note=None, status=100000000, parties=("Yazar A",), ends=None, public=0):
    return {"id": cid, "name": cid, "status": status, "ends": ends, "open_ended": 1 if ends is None else 0, "terminated": None,
            "internet": 1, "ebook": ebook, "zbook": 0, "audiobook": audio, "public_domain": public, "rights_note": note,
            "parties": list(parties)}


# ------------------------------------------------------------------ hak kararı


def test_rights_follow_every_live_contract_and_never_trust_a_note():
    assert D.rights_for([contract()], TODAY, "ekitap")[0] == "var"
    kind, why, _ = D.rights_for([contract(), contract("C2", ebook=0, parties=("Çevirmen B",))], TODAY, "ekitap")
    assert kind == "eksik" and "Çevirmen B" in why
    assert D.rights_for([contract(note="Özel maddeler var")], TODAY, "ekitap")[0] == "incele"   # not → asla kendiliğinden var
    assert D.rights_for([contract(audio=0)], TODAY, "sesli")[0] == "eksik"                        # e-kitap ve sesli ayrı hak
    assert D.rights_for([], TODAY, "ekitap")[0] == "yok"
    assert D.rights_for([contract(status=0)], TODAY, "ekitap")[0] == "yok"                        # yürürlükte değil
    assert D.rights_for([contract(status=0, public=1)], TODAY, "ekitap")[0] == "koruma_disi"
    assert D.rights_for([contract(ends=TODAY - timedelta(days=1))], TODAY, "ekitap")[0] == "yok"  # süresi dolmuş


def test_rights_decision_resolves_review_until_the_note_changes():
    note = "Yalnız Türkiye'de dijital satış"
    dec = {("C1", "ekitap"): {"karar": "kismi", "gerekce": "Bölge kısıtı", "not_ozeti": D.note_hash(note)}}
    kind, why, noted = D.rights_for([contract(note=note)], TODAY, "ekitap", dec)
    assert kind == "kismi" and "Bölge kısıtı" in why and noted
    assert D.rights_for([contract(note=note)], TODAY, "sesli", dec)[0] == "eksik"                # biçim ayrı karar ister
    assert D.rights_for([contract(note=note + " ve Kıbrıs")], TODAY, "ekitap", dec)[0] == "incele"  # not değişti → yeniden sor
    dec[("C1", "ekitap")]["karar"] = "uygun_degil"
    assert D.rights_for([contract(note=note)], TODAY, "ekitap", dec)[0] == "yok"


def test_non_book_and_set_rules_come_from_the_seo_filter():
    rows = D.build_titles(_crm([_book("K1", tip=7, tip_adi="Pazarlama Materyalleri")], {}), ST, TODAY, decisions={}, live={},
                          last_listing={}, sales12={}, studio={}, history={})
    assert rows[0]["hak_ekitap"] == "kitap_degil"


# ------------------------------------------------------------------ katalog kurulumu


def _book(kid, *, ad=None, tip=1, tip_adi="Kitap", stok=None, estok=None, eisbn=None, isbn=None, ys="YS04 Aktif", hk="Yetişkin",
          turler="Roman", epub=0):
    return {"kitap_id": kid, "ad": ad or f"Kitap {kid}", "stok_kodu": stok or kid, "isbn": isbn, "ean": isbn, "e_isbn": eisbn,
            "ekitap_barkod": None, "ekitap_stok_kodu": estok, "epub_crm": epub, "tip": tip, "tip_adi": tip_adi,
            "yayin_durumu": ys, "hedef_kitle": hk, "yazar": "Yazar A", "turler": turler, "basili_fiyat": 100.0, "ilk_yayin": None}


def _crm(books, contracts, production=None):
    return {"books": books, "contracts": contracts, "counts": {}, "production": production or {}}


def _titles(books, contracts, sales, *, studio=None, history=None, live=None, last=None, st=ST):
    rows = D.build_titles(_crm(books, contracts), st, TODAY, decisions={}, live=live or {}, last_listing=last or {},
                          sales12=sales, studio=studio if studio is not None else {}, history=history if history is not None else {})
    D.score(rows, st)
    return {r["kitap_id"]: r for r in rows}


def test_opportunity_needs_right_no_ebook_enough_print_sales_and_an_active_status():
    books = [_book("A"), _book("B", estok="E-B"), _book("C"), _book("D", ys="YS11 Satıştan Çekildi"), _book("E"),
             _book("F", tip=8, tip_adi="Ekitap")]
    contracts = {k: [contract(k)] for k in "ABCDEF"}
    contracts["E"] = [contract("E", note="özel madde")]
    sales = {"A": {"adet": 5000, "ciro": 1}, "B": {"adet": 9000, "ciro": 1}, "C": {"adet": 999, "ciro": 1},
             "D": {"adet": 8000, "ciro": 1}, "E": {"adet": 7000, "ciro": 1}, "F": {"adet": 7000, "ciro": 1}}
    t = _titles(books, contracts, sales)
    assert t["A"]["firsat_puani"] is not None and "5.000 adet" in t["A"]["firsat_gerekcesi"]
    assert t["B"]["firsat_puani"] is None and t["B"]["ekitap_var"]          # e-kitap stok kodu var
    assert t["C"]["firsat_puani"] is None                                      # eşik altı (1000)
    assert t["D"]["firsat_puani"] is None                                      # satıştan çekilmiş
    assert t["E"]["firsat_puani"] is None and t["E"]["hak_ekitap"] == "incele"  # hak notu: önerilmez
    assert t["F"]["firsat_puani"] is None                                      # kitap tipi değil
    assert t["B"]["firsat_puani"] is None and t["A"]["firsat_puani"] <= 100


def test_platform_listing_counts_as_digital_version_and_audio_needs_its_own_card():
    books = [_book("A"), _book("S", ad="Kitap A", tip=9, tip_adi="SesliKitap")]
    t = _titles(books, {"A": [contract("A", audio=1)]}, {"A": {"adet": 5000, "ciro": 1}}, live={"A": {"ekitap"}})
    assert t["A"]["ekitap_var"] and t["A"]["firsat_puani"] is None
    assert t["A"]["sesli_var"] and t["A"]["sesli_firsat_puani"] is None       # aynı adlı SesliKitap kartı
    t = _titles([_book("A")], {"A": [contract("A", audio=1)]}, {"A": {"adet": 5000, "ciro": 1}})
    assert t["A"]["sesli_firsat_puani"] is not None
    only_child = {**ST, "audioGenres": ["masal", "cocuk"]}
    t = _titles([_book("A")], {"A": [contract("A", audio=1)]}, {"A": {"adet": 5000, "ciro": 1}}, st=only_child)
    assert t["A"]["sesli_firsat_puani"] is None                                 # yetişkin roman tür süzgecine takılır


def test_edition_change_after_the_last_digital_update_only():
    h = [{"tarih": "2026-01-01", "baski": 3, "kapak": "k1.jpg"}, {"tarih": "2026-08-01", "baski": 4, "kapak": "k1.jpg"},
         {"tarih": "2026-09-01", "baski": 4, "kapak": "k2.jpg"}]
    since = TODAY - timedelta(days=90)
    assert D.edition_change(h, since, None) == ("2026-09-01", "kapak değişti")
    assert D.edition_change(h[:2], since, None) == ("2026-08-01", "yeni baskı")
    assert D.edition_change(h, since, "2026-09-10") is None                     # dijital sürüm sonradan güncellendi
    assert D.edition_change(h[:2], TODAY - timedelta(days=30), None) is None    # pencere dışı


def test_write_titles_keeps_user_columns_and_drops_inactive_books(engine):
    t = _titles([_book("A"), _book("B")], {}, {})
    D.write_titles(engine, T, list(t.values()))
    D.set_price(engine, T, "fin", "A", {"fiyat": "59,90", "gerekce": "Basılının %60'ı"})
    t = _titles([_book("A", ad="Yeni ad")], {}, {})
    res = D.write_titles(engine, T, list(t.values()))
    assert res == {"yeni": 0, "guncellenen": 1, "silinen": 1}
    got = D.get_title(engine, T, "A", with_sales=False)
    assert got["ad"] == "Yeni ad" and got["dijitalFiyat"] == 59.9 and got["fiyatOnaylayan"] == "fin"


def test_missing_source_keeps_the_previous_reading(engine):
    t = _titles([_book("A")], {}, {"A": {"adet": 1500, "ciro": 10}})
    D.write_titles(engine, T, list(t.values()))
    rows = D.build_titles(_crm([_book("A")], {}), ST, TODAY, decisions={}, live={}, last_listing={}, sales12=None, studio={}, history={})
    D.merge_previous(rows, D.previous(engine, T), ["sales"])
    assert rows[0]["basili_12ay_adet"] == 1500


def test_crm_pending_lists_what_the_crm_should_record(engine):
    studio = {"A": {"is": "j1", "durum": "hazir", "denetim": "OK", "e_isbn": "978-605-000-000-1"}}
    t = _titles([_book("A"), _book("B")], {}, {}, studio=studio, live={"B": {"ekitap"}})
    want = D.pending_from(list(t.values()), {"B": {"ekitap"}})
    assert {(k, a) for k, a, _, _ in want} == {("A", "new_ekitapisbn"), ("A", "new_EPubDurumu"), ("B", "new_EKitapStokKodu")}
    D.write_titles(engine, T, list(t.values()))
    assert D.write_pending(engine, T, want)["eklenen"] == 3
    assert D.write_pending(engine, T, {w for w in want if w[0] == "B"}) == {"eklenen": 0, "kapanan": 2}
    assert len(D.crm_pending(engine, T)["items"]) == 1


def test_studio_state_summary():
    assert src.studio_state({"status": "done", "stale": False, "check": {"status": "WARN"}, "result": {"eisbn": "9786050000001"}}) == \
        {"durum": "hazir", "denetim": "WARN", "e_isbn": "9786050000001"}
    assert src.studio_state({"status": "done", "stale": True})["durum"] == "eski"
    assert src.studio_state({"status": "none"})["durum"] == "is_var"


def test_window_is_twelve_calendar_months_ending_with_the_data_end():
    assert src.window12(date(2026, 8, 17)) == (date(2025, 9, 1), date(2026, 8, 18))
    assert src.window12(date(2026, 12, 31)) == (date(2026, 1, 1), date(2027, 1, 1))


# ------------------------------------------------------------------ platform ve risk


def _seed(engine, books=None, contracts=None, sales=None):
    books = books or [_book("A", isbn="9786050000011", eisbn="9786050000028"), _book("B", ad="Sessiz Deniz", stok="TMS-B"),
                      _book("C", ad="Kırmızı Kedi Masalları", stok="TMS-C")]
    contracts = contracts if contracts is not None else {"A": [contract("A")], "B": [contract("B", ebook=0)], "C": [contract("C")]}
    t = _titles(books, contracts, sales or {})
    D.write_titles(engine, T, list(t.values()))
    return D.create_platform(engine, T, "ayse", {"ad": "Kitap Platformu", "tur": "ekitap", "dagitim": "dogrudan", "paraBirimi": "USD",
                                                 "raporGunu": 20})


def test_listing_on_a_book_without_right_warns_and_enters_the_risk_list(engine):
    p = _seed(engine)
    out = D.set_listing(engine, T, "ayse", "B", p["id"], {"durum": "yayinda", "tarih": "2026-09-01"})
    assert out["uyari"] and out["ekitapVar"]
    risks = D.rights_risks(engine, T)
    assert [r["kitapId"] for r in risks["risk"]] == ["B"] and risks["risk"][0]["riskBicim"] == ["ekitap"]
    with pytest.raises(D.DigitalError):
        D.set_listing(engine, T, "ayse", "A", p["id"], {"durum": "satista"})
    with pytest.raises(D.DigitalError):
        D.create_platform(engine, T, "ayse", {"ad": "kitap platformu"})          # aynı ad


def test_rights_decision_needs_a_noted_contract_and_recomputes(engine):
    _seed(engine, contracts={"A": [contract("A", note="Özel madde")], "B": [contract("B")], "C": [contract("C")]})
    with pytest.raises(D.DigitalError):
        D.decide_rights(engine, T, "telif", {"kitapId": "B", "sozlesmeId": "B", "bicim": "ekitap", "karar": "uygun", "gerekce": "x"})
    with pytest.raises(D.DigitalError):
        D.decide_rights(engine, T, "telif", {"kitapId": "A", "sozlesmeId": "A", "bicim": "ekitap", "karar": "uygun", "gerekce": ""})
    out = D.decide_rights(engine, T, "telif", {"kitapId": "A", "sozlesmeId": "A", "bicim": "ekitap", "karar": "uygun", "gerekce": "Okundu"})
    assert out["hakEkitap"] == "var" and out["hakSesli"] == "eksik" and out["kararlar"][0]["yazan"] == "telif"


def test_overview_counts(engine):
    _seed(engine, sales={"A": {"adet": 5000, "ciro": 1}})
    k = D.overview(engine, T, ST)["kpi"]
    assert k["kitap"] == 3 and k["firsat"] == 1 and k["hakliDijitalYok"] == 2 and k["hakRiski"] == 0


# ------------------------------------------------------------------ rapor yükleme


CSV = ("Platform Satış Raporu\n"
       "Başlık;Yazar;ISBN;Adet;Net Tutar;Para Birimi;Müşteri E-posta\n"
       "Kitap A;Yazar A;978-605-000-002-8;10;25,50;USD;okur@ornek.com\n"
       ";;;;;;\n"
       "Sessiz Deniz (e-kitap);Yazar A;;3;7,00;USD;x@y.z\n"
       "Bilinmeyen Kitap;Kimse;;1;1,00;USD;\n"
       "Toplam;;;14;33,50;;\n").encode("utf-8")


def test_import_drops_personal_columns_keeps_every_row_and_matches_by_rule(engine):
    p = _seed(engine)
    imp = D.create_import(engine, T, "fin", p["id"], "2026-08", "rapor.csv", CSV)
    assert imp["atilanKolonlar"] == ["Müşteri E-posta"] and "okur@ornek.com" not in json.dumps(imp, ensure_ascii=False)
    assert imp["satir"] == 4 and imp["bosSatir"] == 1 and imp["ozetSatir"] == 1              # boş satır yazılmaz, toplam işaretli
    assert imp["eslesen"] == 1 and imp["eslesmeyen"] == 2
    first = imp["satirlar"][0]
    assert first["kitapId"] == "A" and first["anahtar"] == "e-ISBN" and first["net"] == 25.5 and first["paraBirimi"] == "USD"
    assert imp["toplamlar"]["USD"]["net"] == pytest.approx(33.5)                              # özet satırı toplama girmez


def test_ai_suggestion_is_only_a_proposal_and_strong_ones_need_a_click(engine):
    p = _seed(engine)
    imp = D.create_import(engine, T, "fin", p["id"], "2026-08", "rapor.csv", CSV)

    class Llm:
        def choose(self, prompt, choices):
            pick = next((c for c in choices if c.startswith("Sessiz Deniz")), choices[-1])
            return SimpleNamespace(choice=pick, probability=0.9 if pick != "Hiçbiri" else 0.8, probs={pick: 0.9})

    res = D.suggest_matches(engine, T, imp["id"], Llm(), ST)
    assert res["modelSorulan"] >= 1
    imp = D.get_import(engine, T, imp["id"])
    row = next(r for r in imp["satirlar"] if (r["baslik"] or "").startswith("Sessiz"))
    assert row["kitapId"] is None and row["olasilik"] == 0.9 and row["adaylar"][0]["oneri"]
    imp = D.accept_strong(engine, T, imp["id"], ST)
    row = next(r for r in imp["satirlar"] if (r["baslik"] or "").startswith("Sessiz"))
    assert row["kitapId"] == "B" and row["eslesme"] == "zeki"


def test_commit_needs_rates_and_refuses_a_double_period(engine):
    p = _seed(engine)
    imp = D.create_import(engine, T, "fin", p["id"], "2026-08", "rapor.csv", CSV)
    with pytest.raises(D.DigitalError) as e:
        D.commit_import(engine, T, "fin", imp["id"], {})
    assert "USD" in str(e.value)
    done = D.commit_import(engine, T, "fin", imp["id"], {"kurlar": {"USD": "34,20"}})
    assert done["durum"] == "onaylandi" and done["kurlar"]["USD"] == 34.2
    s = D.sales(engine, T)
    assert s["aylik"][0]["netTl"] == pytest.approx(33.5 * 34.2) and len(s["eslesmeyen"]) == 2   # eşleşmeyen atılmaz
    second = D.create_import(engine, T, "fin", p["id"], "2026-08", "rapor2.csv", CSV)
    with pytest.raises(D.DigitalError) as e:
        D.commit_import(engine, T, "fin", second["id"], {"kurlar": {"USD": 34.2}})
    assert e.value.status == 409
    assert D.delete_import(engine, T, second["id"]) == {"id": second["id"], "silindi": True}
    assert D.delete_import(engine, T, imp["id"]) == {"id": imp["id"], "iptal": True}
    assert D.sales(engine, T)["aylik"] == []


def test_remap_only_in_preview_and_personal_columns_cannot_come_back(engine):
    p = _seed(engine)
    imp = D.create_import(engine, T, "fin", p["id"], "2026-08", "rapor.csv", CSV)
    with pytest.raises(D.DigitalError):
        D.remap_import(engine, T, imp["id"], {"kimlik": 6})                                    # atılan kişisel kolon
    out = D.remap_import(engine, T, imp["id"], {"kimlik": None})
    assert out["eslesen"] == 0


def test_number_parsing_and_header_detection():
    assert D.parse_number("1.234,56") == 1234.56 and D.parse_number("1,234.56") == 1234.56
    assert D.parse_number("12,5") == 12.5 and D.parse_number("1.234") == 1234 and D.parse_number("(3,00)") == -3
    assert D.parse_number("") is None and D.parse_number("abc") is None
    det = D.detect_columns([["Rapor"], ["Title", "Author", "ASIN", "Net Units", "Royalty", "Currency", "Buyer"]])
    assert det["header_row"] == 1 and det["mapping"]["baslik"] == 0 and det["mapping"]["kimlik"] == 2
    assert det["mapping"]["adet"] == 3 and det["mapping"]["net"] == 4 and det["personal"] == [6]
    with pytest.raises(D.DigitalError):
        D.detect_columns([["a", "b"], ["1", "2"]])


def test_rule_match_is_ambiguous_when_a_key_points_to_two_books():
    idx = {"keys": {"ISBN": {"9786050000011": {"A", "B"}}, "stok kodu": {"TMS-C": {"C"}}}, "tokens": {}, "books": {}}
    assert D.rule_match("978-605-000-001-1", idx) == (None, None)
    assert D.rule_match("tms-c", idx) == ("C", "stok kodu")


# ------------------------------------------------------------------ Zeki AI hak notu ön okuması


def test_note_reads_are_cached_by_note_text(engine):
    _seed(engine, contracts={"A": [contract("A", note="Yalnız basılı")], "B": [contract("B")], "C": [contract("C")]})
    calls = []

    class Llm:
        def choose(self, prompt, choices):
            calls.append((prompt, choices))
            return SimpleNamespace(choice="Format kısıtı", probability=0.9, margin=0.8, method="logprobs", probs=None)

    assert D.read_notes(engine, T, Llm(), 60)["okunan"] == 1
    assert D.read_notes(engine, T, Llm(), 60)["okunan"] == 0 and len(calls) == 1
    assert D.read_notes(engine, T, None, 60)["model"] is False
    assert calls[0][1] == list(RY.NOTE_CLASSES.values())          # telifle aynı kapalı küme (tek soru)
    rd = D.note_reads(engine, T)["A"]
    assert rd["sonuc"] == "kisitliyor" and rd["sinif"] == "format" and rd["ozet"] == D.note_hash("Yalnız basılı")
    title = D.get_title(engine, T, "A", with_sales=False)
    assert title["sozlesmeler"][0]["notOkuma"]["sonuc"] == "kisitliyor"
    assert title["sozlesmeler"][0]["notOkuma"]["sinifAdi"] == "Format kısıtı"


# ------------------------------------------------------------------ uyarılar


def test_alerts_once_per_key(engine):
    p = _seed(engine)
    D.set_listing(engine, T, "ayse", "B", p["id"], {"durum": "yayinda"})
    items = D.due_alerts(engine, T, ST, date(2026, 9, 28))
    kinds = {i["kime"] for i in items}
    assert "telif" in kinds and "finans" in kinds                               # Ağustos raporu 20 Eylül'de bekleniyordu
    D.mark_sent(engine, T, [i["key"] for i in items])
    assert D.due_alerts(engine, T, ST, date(2026, 9, 28)) == []
    assert "platformlara" in D.alert_text(items, "")


# ------------------------------------------------------------------ yetki ve kurallar


def test_feature_rules_for_digital():
    f = A.features_for
    assert f("PUT", "/api/v1/dijital/titles/ABC/listings/3") == ["ozellik:dijital.durum-yaz"]
    assert f("POST", "/api/v1/dijital/platforms") == ["ozellik:dijital.durum-yaz"]
    assert f("PATCH", "/api/v1/dijital/platforms/3") == ["ozellik:dijital.durum-yaz"]
    assert f("POST", "/api/v1/dijital/refresh") == ["ozellik:dijital.durum-yaz"]
    assert f("POST", "/api/v1/dijital/imports") == ["ozellik:dijital.rapor-yukle"]
    assert f("POST", "/api/v1/dijital/imports/DR-2026-0001/commit") == ["ozellik:dijital.rapor-yukle"]
    assert f("DELETE", "/api/v1/dijital/imports/DR-2026-0001") == ["ozellik:dijital.rapor-yukle"]
    assert f("POST", "/api/v1/dijital/rights-decisions") == []                  # açıkça verilen, ucun içinde
    assert f("PUT", "/api/v1/dijital/titles/ABC/price") == []                    # açıkça verilen, ucun içinde
    assert f("POST", "/api/v1/dijital/run-due") == []
    assert f("GET", "/api/v1/dijital/opportunities/export.csv") == ["ozellik:veri.disa-aktar"]
    assert f("GET", "/api/v1/dijital/sales/export.csv") == ["ozellik:veri.disa-aktar"]
    yayin, satis = A.page("dijital-yayin"), A.page("dijital-satis")
    assert A.rule_for("/api/v1/dijital/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/dijital/titles") == frozenset({yayin})
    assert A.rule_for("/api/v1/dijital/imports/DR-2026-0001") == frozenset({satis})
    assert A.rule_for("/api/v1/dijital/sales") == frozenset({satis})
    assert A.rule_for("/api/v1/dijital/overview") == frozenset({yayin, satis})
    assert {"ozellik:dijital.hak-karari", "ozellik:dijital.fiyat-onay"} <= A.explicit_keys()
    assert {"ozellik:dijital.durum-yaz", "ozellik:dijital.rapor-yukle"} <= A.all_keys() - A.explicit_keys()


def test_catalog_pages_and_sales_page_is_explicit():
    cat = json.loads((BRIDGE / "access_catalog.json").read_text(encoding="utf-8"))
    pages = {p["key"]: p for p in cat["pages"]}
    assert pages["sayfa:dijital-yayin"]["area"] == "dijital"
    assert pages["sayfa:dijital-satis"].get("explicit") is True


def test_settings_are_on_the_admin_screen():
    from semantic_bridge import admin as admin_mod

    keys = {s["key"] for s in admin_mod.SPEC if s.get("group") == "dijital"}
    assert set(k for k in D.DEFAULTS if k.startswith("DIJITAL_")) <= keys
    assert any(g["id"] == "dijital" for g in admin_mod.GROUPS)


def test_no_write_to_crm_logo_tsoft_or_platforms():
    text = "".join((BRIDGE / f).read_text(encoding="utf-8") for f in ("dijital_sources.py", "dijital.py", "dijital_api.py"))
    blob = " ".join(re.findall(r'"([^"\n]*(?:SELECT|FROM)[^"\n]*)"', (BRIDGE / "dijital_sources.py").read_text(encoding="utf-8"))
                    + re.findall(r'"""(.*?)"""', (BRIDGE / "dijital_sources.py").read_text(encoding="utf-8"), re.S)).upper()
    for kw in ("INSERT ", "UPDATE ", "DELETE ", "MERGE ", "EXEC ", "DROP "):
        assert kw not in blob.replace("YALNIZ OKUMA", "")
    assert "seo_geo.connections" not in text and "httpx" not in text and "requests" not in text


def test_no_technology_names_on_screen_texts():
    banned = re.compile(r"qwen|vllm|temporal|timesfm|ollama|openai|gpt|claude|llama|epubcheck", re.I)
    for f in ("dijital.py", "dijital_api.py", "dijital_sources.py"):
        strings = re.findall(r'"([^"\n]{12,})"', (BRIDGE / f).read_text(encoding="utf-8"))
        assert not [s for s in strings if banned.search(s)], f


def test_request_is_imported_at_module_level():
    body = (BRIDGE / "dijital_api.py").read_text(encoding="utf-8")
    assert re.search(r"^from fastapi import .*\bRequest\b", body, re.M)


def test_tables_have_the_module_prefix():
    assert all(t.startswith("semantic_dijital_") for t in D._md.tables)


def test_rights_provider_hook_for_m54():
    src.register_rights_provider(lambda ids, bicim: {i.lower(): ("var", "hak haritası") for i in ids})
    try:
        assert src.external_rights(["abc"], "ekitap") == {"ABC": ("var", "hak haritası")}
    finally:
        src.register_rights_provider(None)
    assert src.external_rights(["abc"], "ekitap") is None
