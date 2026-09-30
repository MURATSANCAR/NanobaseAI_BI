"""M21 Dijital pazarlama ve reklam: dışa aktarım dosyasının okunması (başlık, kolon sözlüğü, ondalık, tarih, özet satırı),
içe aktarma (dosya içi toplama, yeniden yüklemede son yükleme geçerli, geri alma), kampanya ↔ kitap eşleştirme (kod,
ad benzerliği, kapalı seçim eşiği), dönem göstergeleri (pazarlama verimi yalnız Logo verisi olan günlerde), bütçe
(ay × kanal, M15 onaylı plan satırları, ay sonu tahmini), öneri kuralları (eşiksiz kural kapalı), öneri durum makinesi,
brief kaydı, yetki kuralları ve uçlar.

Veriler yapaydır ve yalnız kuralları sınar; gerçek Logo/CRM kabulü test sunucusunda (`scripts/acceptance/M21/`).
"""

from __future__ import annotations

import base64
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from semantic_bridge import access as AC
from semantic_bridge import ads as A
from semantic_bridge import ads_sources as S
from semantic_bridge.marketing import core as MC
from semantic_layer.store.catalog_store import open_store

T = "t1"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    A._ready.discard(id(e))
    MC._ready.discard(id(e))
    A.ensure(e)
    MC.ensure(e)
    yield e
    A._ready.discard(id(e))
    MC._ready.discard(id(e))


def _st(**over):
    s = A.settings(lambda k: "")
    s.update(over)
    return s


def _acc(engine, platform="google", ad="Timaş Google Ads"):
    return A.create_account(engine, T, "ayse", {"platform": platform, "ad": ad})


def _row(day, campaign, spend, cid=None, **kw):
    return {"day": day, "campaign": campaign, "campaign_id": cid, "spend": spend, "impressions": kw.get("impr"),
            "clicks": kw.get("clicks"), "conversions": kw.get("conv"), "conv_value": kw.get("value"),
            "currency": kw.get("cur"), "status": kw.get("status")}


def _import(engine, acc, rows, name="rapor.csv"):
    m = {"day": "Gün", "campaign": "Kampanya", "spend": "Maliyet"}
    return A.commit_import(engine, T, "ayse", acc, name, "sha", rows, m, [], len(rows))


class Choice:
    def __init__(self, choice, index, p, margin=0.6, method="logprobs"):
        self.choice, self.index, self.probability, self.margin, self.method = choice, index, p, margin, method

    def confident(self, p, m=0.0, c=0.0):
        return self.probability is not None and self.probability >= p and self.margin >= m


class ChooseLlm:
    """Kapalı seçimde verilen sıradaki seçeneği verilen olasılıkla seçer."""

    def __init__(self, pick=0, p=0.9, margin=0.6):
        self.pick, self.p, self.margin, self.calls = pick, p, margin, []

    def choose(self, prompt, choices, **_):
        self.calls.append((prompt, choices))
        i = self.pick if self.pick >= 0 else len(choices) - 1
        return Choice(choices[i], i, self.p, self.margin)


# ------------------------------------------------------------------ dosya okuma


GOOGLE = (
    "Kampanya performans raporu\n"
    "1 Eylül 2026 - 2 Eylül 2026\n"
    "Gün\tKampanya\tKampanya kimliği\tKampanya türü\tGösterim\tTıklamalar\tMaliyet\tOrt. TBM\tTıklama oranı\tDönüşümler\tDönüşüm değeri\tPara birimi kodu\n"
    "2026-09-01\tArama | Kayıp Zamanın İzinde\t111\tArama\t1.000\t50\t125,50\t2,51\t5%\t2\t300,00\tTRY\n"
    "2026-09-02\tArama | Kayıp Zamanın İzinde\t111\tArama\t2.000\t40\t74,50\t1,86\t2%\t0\t0,00\tTRY\n"
    "2026-09-01\tPMax 9786050000000\t222\tPerformance Max\t500\t10\t1.200,00\t120,00\t2%\t1\t150,00\tTRY\n"
    "Toplam: Hesap\t\t\t\t3.500\t100\t1.400,00\t14,00\t3%\t3\t450,00\tTRY\n"
).encode("utf-16")

META = (
    '"Kampanya adı","Raporlama başlangıcı","Raporlama bitişi","Harcanan tutar (TRY)","Gösterimler","Bağlantı tıklamaları","Sonuçlar","Satın alma dönüşüm değeri","Sonuç başına maliyet"\n'
    '"","2026-09-01","2026-09-02","80.00","2000","30","1","100.00","80.00"\n'
    '"Instagram - Kayıp Zaman","2026-09-01","2026-09-01","40.00","1000","15","1","100.00","40.00"\n'
    '"Instagram - Kayıp Zaman","2026-09-02","2026-09-02","40.00","1000","15","","","--"\n'
).encode("utf-8")


def test_google_export_header_mapping_and_numbers():
    table = S.read_table("rapor.csv", GOOGLE)
    h = S.find_header(table)
    assert h == 2
    m, src = S.suggest_mapping([str(x) for x in table[h]], None)
    assert src == "sozluk"
    assert m["day"] == "Gün" and m["campaign"] == "Kampanya" and m["campaign_id"] == "Kampanya kimliği"
    assert m["spend"] == "Maliyet" and m["clicks"] == "Tıklamalar" and m["impressions"] == "Gösterim"
    assert m["conversions"] == "Dönüşümler" and m["conv_value"] == "Dönüşüm değeri" and m["currency"] == "Para birimi kodu"
    assert "Ort. TBM" not in m.values() and "Tıklama oranı" not in m.values() and "Kampanya türü" not in m.values()
    res = S.apply_mapping(table, h, m, True)
    assert res["hataSayisi"] == 0 and res["ozetSatiri"] == 1 and res["ondalik"] == ","
    spends = [r["spend"] for r in res["rows"]]
    assert spends == [125.5, 74.5, 1200.0]
    assert res["rows"][0]["impressions"] == 1000 and res["rows"][0]["currency"] == "TRY"
    trial = S.trial(table, h, m, True)
    assert trial["toplam"] == {"TRY": 1400.0} and trial["kampanya"] == 2 and trial["bas"] == "2026-09-01"


def test_meta_export_summary_row_and_day_range():
    table = S.read_table("meta.csv", META)
    h = S.find_header(table)
    m, _ = S.suggest_mapping([str(x) for x in table[h]], None)
    assert m["campaign"] == "Kampanya adı" and m["day"] == "Raporlama başlangıcı" and m["day_end"] == "Raporlama bitişi"
    assert m["spend"] == "Harcanan tutar (TRY)" and m["clicks"] == "Bağlantı tıklamaları" and m["conversions"] == "Sonuçlar"
    assert m["conv_value"] == "Satın alma dönüşüm değeri" and "Sonuç başına maliyet" not in m.values()
    res = S.apply_mapping(table, h, m, True)
    assert res["ozetSatiri"] == 1 and res["hataSayisi"] == 0 and res["ondalik"] == "."
    assert [r["spend"] for r in res["rows"]] == [40.0, 40.0]
    assert res["rows"][1]["conversions"] is None and res["rows"][1]["conv_value"] is None


def test_non_daily_rows_and_bad_numbers_are_errors_not_skipped():
    csv_ = ("Kampanya adı,Raporlama başlangıcı,Raporlama bitişi,Harcanan tutar (TRY)\n"
            "K1,2026-09-01,2026-09-07,70.00\nK2,2026-09-01,2026-09-01,abc\nK3,bugün,,10\n").encode()
    table = S.read_table("x.csv", csv_)
    m, _ = S.suggest_mapping([str(x) for x in table[0]], None)
    res = S.apply_mapping(table, 0, m, True)
    assert res["hataSayisi"] == 3 and res["gunlukDegil"] == 1 and res["rows"] == []


def test_saved_mapping_wins_when_all_columns_present():
    headers = ["Date", "Campaign", "Cost", "Clicks"]
    saved = {"day": "Date", "campaign": "Campaign", "spend": "Cost"}
    assert S.suggest_mapping(headers, saved) == (saved, "kayitli")
    assert S.suggest_mapping(["Tarih", "Kampanya", "Maliyet"], saved)[1] == "sozluk"


@pytest.mark.parametrize("raw,day_first,want", [
    ("2026-09-01", True, date(2026, 9, 1)), ("2026-09-01 00:00:00", True, date(2026, 9, 1)), ("01.09.2026", True, date(2026, 9, 1)),
    ("02/09/2026", True, date(2026, 9, 2)), ("09/02/2026", False, date(2026, 9, 2)), ("Sep 1, 2026", True, date(2026, 9, 1)),
    ("1 Eyl 2026", True, date(2026, 9, 1)), ("1 Eylül 2026", True, date(2026, 9, 1)), ("20260901", True, date(2026, 9, 1)),
    (46266, True, date(2026, 9, 1)), ("", True, None), ("31.02.2026", True, None),
])
def test_parse_day(raw, day_first, want):
    assert S.parse_day(raw, day_first) == want


@pytest.mark.parametrize("raw,dec,want", [
    ("1.234,56", ",", 1234.56), ("1,234.56", ".", 1234.56), ("₺ 12,5", ",", 12.5), ("--", ",", None), ("(10,00)", ",", -10.0),
    (12, ",", 12.0), ("12.50 TRY", ".", 12.5),
])
def test_parse_num(raw, dec, want):
    v, ok = S.parse_num(raw, dec)
    assert ok and v == want


def test_empty_and_old_excel_files_are_refused():
    with pytest.raises(A.AdsError):
        S.read_table("x.csv", b"")
    with pytest.raises(A.AdsError):
        S.read_table("x.xls", b"\xd0\xcf\x11\xe0")


# ------------------------------------------------------------------ içe aktarma


def test_import_aggregates_duplicates_in_file_and_totals_match(engine):
    acc = _acc(engine)
    rows = [_row("2026-09-01", "K1", 10.0, "c1"), _row("2026-09-01", "K1", 5.25, "c1"), _row("2026-09-02", "K1", 4.0, "c1"),
            _row("2026-09-01", "K2", 7.0)]
    imp = _import(engine, acc, rows)
    assert imp["kampanyaGun"] == 3 and imp["kampanya"] == 2 and imp["toplamHarcama"] == 26.25
    with engine.connect() as c:
        total = c.execute(sa.select(sa.func.sum(A.DAILY.c.spend)).where(A.DAILY.c.import_id == imp["id"])).scalar()
    assert total == pytest.approx(26.25)
    assert imp["gecerliHarcama"] == pytest.approx(26.25) and imp["bas"] == "2026-09-01" and imp["bit"] == "2026-09-02"


def test_reimport_replaces_day_and_moves_row_to_new_import(engine):
    acc = _acc(engine)
    first = _import(engine, acc, [_row("2026-09-01", "K1", 10.0, "c1"), _row("2026-09-02", "K1", 4.0, "c1")])
    second = _import(engine, acc, [_row("2026-09-02", "K1 yeni ad", 6.0, "c1")])
    camps = A.campaign_rows(engine, T)
    assert len(camps) == 1 and camps[0]["ad"] == "K1 yeni ad"            # aynı kimlik: ad güncellenir, kampanya bir
    assert A.import_row(engine, T, first["id"])["gecerliHarcama"] == pytest.approx(10.0)
    assert A.import_row(engine, T, second["id"])["gecerliHarcama"] == pytest.approx(6.0)
    out = A.delete_import(engine, T, second["id"])
    assert out["silinenKampanyaGun"] == 1
    assert A.import_row(engine, T, first["id"])["gecerliHarcama"] == pytest.approx(10.0)


def test_campaign_without_id_matches_by_folded_name(engine):
    acc = _acc(engine)
    _import(engine, acc, [_row("2026-09-01", "İnstagram  Kayıp", 1.0)])
    _import(engine, acc, [_row("2026-09-02", "instagram kayıp", 2.0)])
    assert len(A.campaign_rows(engine, T)) == 1


def test_two_currencies_for_same_campaign_day_is_refused(engine):
    acc = _acc(engine)
    with pytest.raises(A.AdsError):
        _import(engine, acc, [_row("2026-09-01", "K1", 1.0, cur="TRY"), _row("2026-09-01", "K1", 1.0, cur="USD")])


def test_account_validation_and_mapping(engine):
    with pytest.raises(A.AdsError):
        A.create_account(engine, T, "ayse", {"platform": "x", "ad": "a"})
    acc = _acc(engine)
    with pytest.raises(A.AdsError) as e:
        _acc(engine)
    assert e.value.status == 409
    with pytest.raises(A.AdsError):
        A.update_account(engine, T, acc["id"], {"eslem": {"day": "Gün"}})         # zorunlu alan eksik
    out = A.update_account(engine, T, acc["id"], {"eslem": {"day": "Gün", "campaign": "K", "spend": "M", "bilinmeyen": "x"}})
    assert out["eslem"] == {"day": "Gün", "campaign": "K", "spend": "M"}


# ------------------------------------------------------------------ kitap eşleştirme

BOOKS = [
    {"kitapId": "b1", "stokKodu": "15201.0001", "ad": "Kayıp Zamanın İzinde", "ean": "9786050000000", "yazar": "Yazar A"},
    {"kitapId": "b2", "stokKodu": "15201.0002", "ad": "Zamanın Ötesinde", "ean": "9786050000017", "yazar": "Yazar B"},
    {"kitapId": "b3", "stokKodu": "15201.0003", "ad": "Deniz", "ean": None, "yazar": "Yazar C"},
]


def test_code_or_barcode_in_name_is_a_certain_link():
    assert A.code_match("PMax 9786050000000", BOOKS)["stokKodu"] == "15201.0001"
    assert A.code_match("Arama 15201.0002 kampanya", BOOKS)["stokKodu"] == "15201.0002"
    assert A.code_match("Arama 15201.00021", BOOKS) is None


def test_candidates_ignore_platform_words():
    c = A.candidates("Google Arama | Kayıp Zamanın İzinde 2026", BOOKS, A.book_index(BOOKS))
    assert c[0]["stokKodu"] == "15201.0001" and c[0]["skor"] == 1.0
    assert A.candidates("Instagram Reels Kampanya", BOOKS) == []


def test_match_uses_closed_choice_threshold():
    idx = A.book_index(BOOKS)
    camp = {"ad": "Kayıp Zamanın İzinde - Arama", "platformAdi": "Google Ads"}
    ok = A.match_campaign(camp, BOOKS, idx, ChooseLlm(0, 0.92), _st())
    assert ok["book"]["stokKodu"] == "15201.0001" and ok["source"] == "zeki" and ok["probability"] == 0.92
    unsure = A.match_campaign(camp, BOOKS, idx, ChooseLlm(0, 0.55), _st())
    assert unsure["book"] is None and unsure["adaylar"]
    none = A.match_campaign(camp, BOOKS, idx, ChooseLlm(-1, 0.95), _st())      # «Hiçbiri»
    assert none["book"] is None
    rule = A.match_campaign(camp, BOOKS, idx, None, _st())                      # model yok: tek tam eşleşme
    assert rule["book"]["stokKodu"] == "15201.0001" and rule["source"] == "kural"
    code = A.match_campaign({"ad": "PMax 9786050000000"}, BOOKS, idx, ChooseLlm(), _st())
    assert code["source"] == "kod"


def test_link_suggestion_approval_and_manual_link(engine):
    acc = _acc(engine)
    _import(engine, acc, [_row("2026-09-01", "Kayıp Zamanın İzinde", 1.0, "c1"), _row("2026-09-01", "PMax 9786050000000", 1.0, "c2")])
    camps = {c["platformKimlik"]: c for c in A.campaign_rows(engine, T)}
    A.save_link_suggestion(engine, camps["c1"]["id"], {"book": BOOKS[0], "source": "zeki", "probability": 0.9, "adaylar": []})
    A.save_link_suggestion(engine, camps["c2"]["id"], {"book": BOOKS[0], "source": "kod", "probability": 1.0, "adaylar": []})
    c1 = A.get_campaign(engine, T, camps["c1"]["id"])
    assert c1["bag"] == "oneri" and c1["stokKodu"] == "15201.0001"
    assert A.get_campaign(engine, T, camps["c2"]["id"])["bag"] == "onayli"       # kod eşleşmesi kesin
    by = {b["stokKodu"]: b for b in BOOKS}
    c1 = A.set_link(engine, T, "ayse", c1["id"], {"onayla": True}, by.get)
    assert c1["bag"] == "onayli" and c1["bagYapan"] == "ayse"
    # onaylı bağa model önerisi dokunmaz
    A.save_link_suggestion(engine, c1["id"], {"book": None, "adaylar": []})
    assert A.get_campaign(engine, T, c1["id"])["bag"] == "onayli"
    c1 = A.set_link(engine, T, "ayse", c1["id"], {"stokKodu": "15201.0003"}, by.get)
    assert c1["stokKodu"] == "15201.0003" and c1["bagKaynak"] == "elle"
    with pytest.raises(A.AdsError) as e:
        A.set_link(engine, T, "ayse", c1["id"], {"stokKodu": "YOK"}, by.get)
    assert e.value.status == 404
    c1 = A.set_link(engine, T, "ayse", c1["id"], {"kaldir": True}, by.get)
    assert c1["bag"] == "yok" and c1["stokKodu"] is None
    with pytest.raises(A.AdsError):
        A.set_link(engine, T, "ayse", c1["id"], {"onayla": True}, by.get)
    assert [c["id"] for c in A.unlinked_campaigns(engine, T)] == []               # denenmiş (link_json dolu)
    assert [c["id"] for c in A.unlinked_campaigns(engine, T, [c1["id"]])] == [c1["id"]]


# ------------------------------------------------------------------ göstergeler


def _link(engine, cid, code, name="Kitap"):
    A.set_link(engine, T, "ayse", cid, {"stokKodu": code}, lambda c: {"stokKodu": c, "ad": name, "kitapId": None})


def test_overview_efficiency_uses_only_days_with_logo_data(engine):
    acc = _acc(engine)
    _import(engine, acc, [
        {**_row("2026-08-16", "K1", 100.0, "c1"), "clicks": 10.0, "conv_value": 300.0},
        {**_row("2026-08-17", "K1", 100.0, "c1"), "clicks": 10.0, "conv_value": 100.0},
        {**_row("2026-08-18", "K1", 200.0, "c1"), "clicks": 20.0},                   # Logo verisi yok
        _row("2026-08-17", "K2", 50.0, "c2"),
        _row("2026-08-17", "K3", 99.0, "c3", cur="USD"),
    ])
    A.write_ecom(engine, T, date(2026, 8, 1), date(2026, 8, 17), [{"day": "2026-08-16", "ciro": 1000.0, "adet": 10},
                                                                   {"day": "2026-08-17", "ciro": 500.0, "adet": 5}])
    c1 = next(c for c in A.campaign_rows(engine, T) if c["platformKimlik"] == "c1")
    _link(engine, c1["id"], "B1", "Kitap Bir")
    A.write_book_sales(engine, T, date(2026, 8, 1), date(2026, 8, 17), ["B1"], [
        {"stok_kodu": "B1", "day": "2026-08-17", "eticaret_ciro": 120.0, "eticaret_adet": 3, "toplam_ciro": 400.0, "toplam_adet": 9}])
    A.write_stock(engine, T, [{"stok_kodu": "B1", "bakiye": 30.0, "gunluk": 3.0}], "2026-08-17")
    ov = A.overview(engine, T, date(2026, 8, 16), date(2026, 8, 18), "", date(2026, 8, 17))
    g = ov["gosterge"]
    assert g["harcama"] == 450.0 and ov["digerParaBirimi"] == {"USD": 99.0}
    assert g["eticaretCiro"] == 1500.0 and g["harcamaVeriIcinde"] == 250.0
    assert g["verim"] == pytest.approx(1500.0 / 250.0)
    assert g["tbm"] == pytest.approx(round(450.0 / 40.0, 2)) and g["platformRoas"] == pytest.approx(400.0 / 450.0)
    assert ov["verimDonemi"] == {"bas": "2026-08-16", "bit": "2026-08-17"}
    assert ov["bagsiz"]["harcama"] == 50.0 and ov["bagsiz"]["pay"] == pytest.approx(50.0 / 450.0)
    book = ov["kitaplar"][0]
    assert book["stokKodu"] == "B1" and book["harcama"] == 400.0 and book["harcamaVeriIcinde"] == 200.0
    assert book["satis"]["eticaretCiro"] == 120.0 and book["verim"] == pytest.approx(120.0 / 200.0)
    assert book["stok"]["gun"] == 10.0
    assert [x["gun"] for x in ov["gunluk"]] == ["2026-08-16", "2026-08-17", "2026-08-18"]
    assert ov["gunluk"][2]["eticaretCiro"] is None                                # veri yok ≠ sıfır satış


def test_overview_without_logo_data_has_no_efficiency(engine):
    acc = _acc(engine)
    _import(engine, acc, [_row("2026-09-20", "K1", 10.0)])
    ov = A.overview(engine, T, date(2026, 9, 20), date(2026, 9, 21), "", date(2026, 8, 17))
    assert ov["verimDonemi"] is None and ov["gosterge"]["verim"] is None and ov["gosterge"]["eticaretCiro"] is None
    with pytest.raises(A.AdsError):
        A.overview(engine, T, date(2026, 9, 21), date(2026, 9, 20), "", None)


def test_overview_channel_filter(engine):
    g, m = _acc(engine, "google", "G"), _acc(engine, "meta", "M")
    _import(engine, g, [_row("2026-09-01", "KG", 10.0)])
    _import(engine, m, [_row("2026-09-01", "KM", 30.0)])
    ov = A.overview(engine, T, date(2026, 9, 1), date(2026, 9, 1), "", None)
    assert [c["kanal"] for c in ov["kanallar"]] == ["meta", "google"] and ov["kanallar"][0]["pay"] == pytest.approx(0.75)
    assert A.overview(engine, T, date(2026, 9, 1), date(2026, 9, 1), "google", None)["gosterge"]["harcama"] == 10.0


# ------------------------------------------------------------------ bütçe


def test_spread_by_days():
    s = A.spread(3050.0, "2026-10-01", "2026-11-30", None)
    assert s["2026-10"] == pytest.approx(3050 * 31 / 61) and s["2026-11"] == pytest.approx(3050 * 30 / 61)
    assert A.spread(100.0, None, None, "2026-12-15") == {"2026-12": 100.0}
    assert A.spread(100.0, None, None, None) == {}


def test_budget_plan_actual_projection_and_m15_lines(engine):
    acc = _acc(engine)
    _import(engine, acc, [_row("2026-09-01", "K1", 300.0), _row("2026-09-10", "K1", 300.0)])
    assert A.put_budget(engine, T, "ayse", [{"ay": "2026-09", "kanal": "google", "plan": 1000}, {"ay": "2026-10", "kanal": "meta", "plan": 500}]) == 2
    with pytest.raises(A.AdsError):
        A.put_budget(engine, T, "ayse", [{"ay": "2026-13", "kanal": "google", "plan": 1}])
    with pytest.raises(A.AdsError):
        A.put_budget(engine, T, "ayse", [{"ay": "2026-09", "kanal": "google", "plan": -1}])
    pid = MC.create_plan(engine, T, "ayse", kind="yeni", baslik="Plan", stok_kodu="B1", yayin_tarihi="2026-11-01", yayin_kaynagi="elle")
    MC.replace_lines(engine, T, "ayse", pid, [{"kanal": "dijital", "tutar": 3050, "baslangic": "2026-10-01", "bitis": "2026-11-30"},
                                              {"kanal": "basin", "tutar": 999, "baslangic": "2026-10-01", "bitis": "2026-10-31"}])
    draft = A.budget(engine, T, 2026, _st(), None, date(2026, 9, 15))
    assert draft["m15"]["satirlar"] == []                                         # onaysız plan sayılmaz
    with engine.begin() as c:
        c.execute(MC.PLANS.update().where(MC.PLANS.c.id == pid).values(durum="onayli"))
    b = A.budget(engine, T, 2026, _st(), [{"tutar": 600.0, "baslangic": "2026-09-01", "bitis": "2026-09-30"}], date(2026, 9, 15))
    cell = next(x for x in b["hucreler"] if x["ay"] == "2026-09" and x["kanal"] == "google")
    assert cell["plan"] == 1000 and cell["harcama"] == 600.0 and cell["kalan"] == 400.0
    assert cell["tahmin"] == pytest.approx(600.0 / 15 * 30) and cell["asim"] is True
    assert [ln["kanal"] for ln in b["m15"]["satirlar"]] == ["dijital"]
    assert b["m15"]["satirlar"][0]["aylar"]["2026-10"] == pytest.approx(3050 * 31 / 61, abs=0.01)
    assert b["crm"] == [{"ay": "2026-09", "tutar": 600.0}]
    assert b["toplam"]["plan"] == 1500 and b["toplam"]["harcama"] == 600.0
    assert A.m15_by_book(engine, T, ["B1"], {"dijital", "sosyal-medya"}) == {"B1": {"planlar": [pid], "tutar": 3050.0}}
    assert A.put_budget(engine, T, "ayse", [{"ay": "2026-10", "kanal": "meta", "plan": None}]) == 1   # boş = sil


# ------------------------------------------------------------------ öneri kuralları


def _setup_rules(engine, ref):
    acc = _acc(engine)
    d = lambda n: (ref - timedelta(days=n)).isoformat()  # noqa: E731
    _import(engine, acc, [
        {**_row(d(1), "Stok biten", 50.0, "c1"), "conversions": 0.0},
        {**_row(d(1), "Satış dışı", 20.0, "c2"), "conversions": 1.0},
        {**_row(d(2), "Yüksek", 500.0, "c3"), "conv_value": 5000.0, "conversions": 5.0},
        {**_row(d(2), "Düşük", 500.0, "c4"), "conv_value": 500.0, "conversions": 1.0},
    ])
    camps = {c["platformKimlik"]: c for c in A.campaign_rows(engine, T)}
    _link(engine, camps["c1"]["id"], "B1", "Biten Kitap")
    _link(engine, camps["c2"]["id"], "B2", "Kalkan Kitap")
    A.write_stock(engine, T, [{"stok_kodu": "B1", "bakiye": 20.0, "gunluk": 5.0}, {"stok_kodu": "B2", "bakiye": 500.0, "gunluk": 1.0}],
                  ref.isoformat())
    return acc, camps


def test_rules_stock_off_sale_and_defaults_keep_money_rules_off(engine):
    ref = date(2026, 9, 20)
    _, camps = _setup_rules(engine, ref)
    books = {"B2": {"durum": "YS05 Artık bizim değil", "satisDisi": True}}
    cands = A.evaluate(engine, T, _st(), ref, crm_books=books)
    kinds = {(x["kind"], x.get("campaign_id")) for x in cands}
    assert ("stok", camps["c1"]["id"]) in kinds                                  # 20 / 5 = 4 gün < 14
    assert ("satis-disi", camps["c2"]["id"]) in kinds
    assert ("stok", camps["c2"]["id"]) not in kinds                              # 500 gün
    assert not any(x["kind"] in ("durdur", "kaydir") for x in cands)             # eşik girilmedi: kapalı


def test_rules_stop_and_shift_when_thresholds_are_set(engine):
    ref = date(2026, 9, 20)
    _, camps = _setup_rules(engine, ref)
    s = _st(stopMinSpend=40.0, shiftMinSpend=100.0)
    cands = A.evaluate(engine, T, s, ref)
    stop = [x for x in cands if x["kind"] == "durdur"]
    assert [x["campaign_id"] for x in stop] == [camps["c1"]["id"]]               # 50 TL, sıfır dönüşüm
    shift = [x for x in cands if x["kind"] == "kaydir"]
    assert len(shift) == 1 and shift[0]["payload"]["kaynak"] == camps["c4"]["id"] and shift[0]["payload"]["hedef"] == camps["c3"]["id"]
    assert shift[0]["payload"]["tutar"] == pytest.approx(500.0 * 0.20)


def test_rules_no_data_and_budget_projection(engine):
    ref = date(2026, 9, 20)
    acc = _acc(engine)
    _import(engine, acc, [_row("2026-09-15", "K1", 1000.0)])
    A.put_budget(engine, T, "ayse", [{"ay": "2026-09", "kanal": "google", "plan": 1200}])
    cands = A.evaluate(engine, T, _st(), ref)
    nod = [x for x in cands if x["kind"] == "veri-yok"]
    assert len(nod) == 1 and nod[0]["payload"]["gun"] == 5
    bud = [x for x in cands if x["kind"] == "butce"]
    assert len(bud) == 1 and bud[0]["payload"]["tahmin"] == pytest.approx(1000.0 / 20 * 30)
    assert not [x for x in A.evaluate(engine, T, _st(overspendPct=100.0), ref) if x["kind"] == "butce"]


def test_suggestions_dedupe_close_and_decide(engine):
    ref = date(2026, 9, 20)
    _, camps = _setup_rules(engine, ref)
    s = _st(stopMinSpend=40.0)
    first = A.store_suggestions(engine, T, A.evaluate(engine, T, s, ref), s)
    again = A.store_suggestions(engine, T, A.evaluate(engine, T, s, ref), s)
    assert first["yeni"] and again["yeni"] == []                                  # açık öneri tekrar yazılmaz
    items = {x["tur"]: x for x in A.list_suggestions(engine, T, "acik")}
    stop, stock = items["durdur"], items["stok"]
    assert stop["onayGerekir"] and not stock["onayGerekir"]
    with pytest.raises(A.AdsError):
        A.decide(engine, T, "ayse", stop["id"], "uygulandi")                      # önce onay
    with pytest.raises(A.AdsError):
        A.decide(engine, T, "mudur", stop["id"], "reddet")                        # gerekçe zorunlu
    assert A.decide(engine, T, "mudur", stop["id"], "onayla")["durum"] == "onaylandi"
    done = A.decide(engine, T, "ayse", stop["id"], "uygulandi")
    assert done["durum"] == "uygulandi" and done["uygulayan"] == "ayse" and done["karar"] == "mudur"
    with pytest.raises(A.AdsError):
        A.decide(engine, T, "ayse", stock["id"], "onayla")                        # uyarı onay istemez
    # stok geldi: koşulu kalkan uyarı kendiliğinden kapanır
    A.write_stock(engine, T, [{"stok_kodu": "B1", "bakiye": 9999.0, "gunluk": 1.0}], ref.isoformat())
    out = A.store_suggestions(engine, T, A.evaluate(engine, T, s, ref), s)
    assert out["kapanan"] >= 1
    assert A.get_suggestion(engine, T, stock["id"])["durum"] == "gecersiz"
    # sistemin kapattığı uyarı koşul geri gelince yeniden çıkar; insanın karar verdiği öneri bekleme süresince çıkmaz
    A.write_stock(engine, T, [{"stok_kodu": "B1", "bakiye": 0.0, "gunluk": 1.0}], ref.isoformat())
    again = A.store_suggestions(engine, T, A.evaluate(engine, T, s, ref), s)
    turs = [A.get_suggestion(engine, T, i)["tur"] for i in again["yeni"]]
    assert "stok" in turs and "durdur" not in turs


# ------------------------------------------------------------------ brief


def test_brief_lifecycle(engine):
    b = A.create_brief(engine, T, "ayse", {"stokKodu": "B1", "ad": "Kitap", "kitapId": "k1"}, "yetişkin okur")
    assert b["durum"] == "hazirlaniyor"
    with pytest.raises(A.AdsError):
        A.update_brief(engine, T, "ayse", b["id"], {"metin": "x"})
    A.finish_brief(engine, b["id"], "Hedef kitle: …", {"dusenSayisi": 0})
    b = A.update_brief(engine, T, "ayse", b["id"], {"metin": "Düzeltilmiş", "onayla": True})
    assert b["durum"] == "onayli" and b["onaylayan"] == "ayse" and b["metin"] == "Düzeltilmiş"
    b2 = A.create_brief(engine, T, "ayse", {"stokKodu": "B1", "ad": "Kitap"}, None)
    assert A.fail_stale_briefs(engine) == 1 and A.get_brief(engine, T, b2["id"])["durum"] == "hata"
    assert len(A.list_briefs(engine, T, "B1")) == 2


def test_manual_brief_opens_empty_draft(engine):
    b = A.create_brief(engine, T, "ayse", {"stokKodu": "B2", "ad": "Kitap", "kitapId": "k2"}, "lansman", manual=True)
    assert b["durum"] == "taslak" and b["metin"] is None and b["istek"] == "lansman" and b["denetim"] is None
    with pytest.raises(A.AdsError):
        A.update_brief(engine, T, "ayse", b["id"], {"onayla": True})           # boş brief onaylanmaz
    b = A.update_brief(engine, T, "ayse", b["id"], {"metin": "Hedef kitle: yetişkin okur"})
    assert b["durum"] == "taslak" and b["metin"] == "Hedef kitle: yetişkin okur"
    b = A.update_brief(engine, T, "ayse", b["id"], {"onayla": True})
    assert b["durum"] == "onayli" and b["onaylayan"] == "ayse"
    assert A.fail_stale_briefs(engine) == 0                                    # elle açılan taslak kuyrukta beklemez


# ------------------------------------------------------------------ ayarlar ve yetki


def test_settings_defaults():
    s = _st()
    assert s["ecomChannels"] == ["E-TICARET"] and s["stockDays"] == 14 and s["stopMinSpend"] is None and s["shiftMinSpend"] is None
    assert s["m15Channels"]["google"] == "dijital" and s["m15Channels"]["meta"] == "sosyal-medya"
    t = A.settings(lambda k: {"ADS_ECOM_CHANNELS": "e-ticaret, internet", "ADS_STOP_MIN_SPEND": "250", "ADS_DATE_ORDER": "ay-gun"}.get(k, ""))
    assert t["ecomChannels"] == ["E-TICARET", "INTERNET"] and t["stopMinSpend"] == 250.0 and t["dayFirst"] is False


def test_access_rules_for_ads():
    page = frozenset({AC.page("reklam")})
    assert AC.rule_for("/api/v1/ads/overview") == page and AC.rule_for("/api/v1/ads/run-due") == AC.SYSTEM
    f = AC.features_for
    w = "ozellik:reklam.duzenle"
    assert f("POST", "/api/v1/ads/imports") == [w] and f("POST", "/api/v1/ads/imports/preview") == [w]
    assert f("DELETE", "/api/v1/ads/imports/abc") == [w] and f("PATCH", "/api/v1/ads/campaigns/c1") == [w]
    assert f("POST", "/api/v1/ads/campaigns/c1/match") == [w] and f("PUT", "/api/v1/ads/budget") == [w]
    assert f("POST", "/api/v1/ads/briefs") == [w] and f("POST", "/api/v1/ads/accounts") == [w] and f("POST", "/api/v1/ads/refresh") == [w]
    assert f("GET", "/api/v1/ads/campaigns") == [] and f("GET", "/api/v1/ads/budget") == []
    assert f("POST", "/api/v1/ads/suggestions/s1/decide") == []                  # ucun içinde (açıkça verilen onay)
    assert f("POST", "/api/v1/ads/run-due") == [] and f("POST", "/api/v1/ads/report/summary") == []
    assert f("GET", "/api/v1/ads/report/export.pdf") == ["ozellik:veri.disa-aktar"]
    assert f("GET", "/api/v1/ads/report/export.xlsx") == ["ozellik:veri.disa-aktar"]
    assert "ozellik:reklam.onay" in AC.explicit_keys() and w not in AC.explicit_keys()
    assert {"sayfa:reklam", w, "ozellik:reklam.onay"} <= AC.all_keys()


def test_tables_are_created(engine):
    names = set(sa.inspect(engine).get_table_names())
    assert {"semantic_ads_accounts", "semantic_ads_campaigns", "semantic_ads_daily", "semantic_ads_imports", "semantic_ads_budget",
            "semantic_ads_suggestions", "semantic_ads_briefs", "semantic_ads_ecom_daily", "semantic_ads_ecom_book", "semantic_ads_stock",
            "semantic_ads_meta"} <= names


# ------------------------------------------------------------------ uçlar


def _app(monkeypatch, store, settings):
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
    A._ready.discard(id(store.engine))
    MC._ready.discard(id(store.engine))
    app = create_app(Runtime(settings, store=store, llm=FakeLlm([""])))
    jobs = []
    monkeypatch.setattr(app.state.ads["pool"], "submit", lambda fn, *a, **kw: jobs.append((fn.__name__, a)))
    monkeypatch.setattr(app.state.ads["crm"], "books", lambda off, fresh=False: [{**b, "durum": None, "satisDisi": False} for b in BOOKS])
    return app, TestClient(app), jobs


def test_endpoints_import_link_and_explicit_approval(monkeypatch, store, settings):
    app, client, jobs = _app(monkeypatch, store, settings)
    a, z = {"cookie": "timas_session=a"}, {"cookie": "timas_session=z"}
    acc = client.post("/api/v1/ads/accounts", json={"platform": "google", "ad": "Timaş Google"}, headers=a)
    assert acc.status_code == 201, acc.text
    content = base64.b64encode(GOOGLE).decode()
    pv = client.post("/api/v1/ads/imports/preview", json={"dosyaAdi": "g.csv", "icerik": content, "hesapId": acc.json()["id"]}, headers=a)
    assert pv.status_code == 200, pv.text
    body = pv.json()
    assert body["eksik"] == [] and body["deneme"]["toplam"] == {"TRY": 1400.0} and body["baslikSatiri"] == 3
    imp = client.post("/api/v1/ads/imports", json={"dosyaAdi": "g.csv", "icerik": content, "hesapId": acc.json()["id"],
                                                   "eslem": body["eslem"], "baslikSatiri": body["baslikSatiri"]}, headers=a)
    assert imp.status_code == 201, imp.text
    assert imp.json()["toplamHarcama"] == pytest.approx(1400.0) and [j[0] for j in jobs] == ["after_import"]
    bad = client.post("/api/v1/ads/imports", json={"dosyaAdi": "g.csv", "icerik": base64.b64encode(
        "Gün\tKampanya\tMaliyet\nhatalı\tK\t1\n".encode("utf-16")).decode(), "hesapId": acc.json()["id"],
        "eslem": {"day": "Gün", "campaign": "Kampanya", "spend": "Maliyet"}}, headers=a)
    assert bad.status_code == 400 and bad.json()["detail"]["hataSayisi"] == 1
    camps = client.get("/api/v1/ads/campaigns?frm=2026-09-01&to=2026-09-02", headers=a).json()
    assert camps["total"] == 2 and camps["items"][0]["harcama"] == 1200.0
    cid = camps["items"][0]["id"]
    linked = client.patch(f"/api/v1/ads/campaigns/{cid}", json={"stokKodu": "15201.0001"}, headers=a)
    assert linked.status_code == 200 and linked.json()["bag"] == "onayli"
    assert client.get("/api/v1/ads/books?q=kayip", headers=a).json()["items"][0]["stokKodu"] == "15201.0001"
    ov = client.get("/api/v1/ads/overview?frm=2026-09-01&to=2026-09-02", headers=a)
    assert ov.status_code == 200 and ov.json()["gosterge"]["harcama"] == 1400.0 and ov.json()["verimDonemi"] is None
    # onay isteyen öneri: açıkça verilen yetki olmadan onaylanamaz
    engine = store.engine
    with engine.begin() as c:
        c.execute(A.SUGGESTIONS.insert().values(id="s1", tenant_id=settings.tenant_id, kind="durdur", dedupe_key="durdur:x",
                                                campaign_id=cid, reason="deneme", status="yeni", created_at=A.now()))
    assert client.post("/api/v1/ads/suggestions/s1/decide", json={"karar": "onayla"}, headers=a).status_code == 403
    ok = client.post("/api/v1/ads/suggestions/s1/decide", json={"karar": "onayla"}, headers=z)
    assert ok.status_code == 200 and ok.json()["durum"] == "onaylandi"
    assert client.post("/api/v1/ads/suggestions/s1/decide", json={"karar": "uygulandi"}, headers=a).json()["durum"] == "uygulandi"
    assert client.post("/api/v1/ads/run-due", headers=a).status_code == 403     # kişi zamanlayıcıyı tetikleyemez
    me = client.get("/api/v1/ads/meta", headers=a).json()["me"]
    assert me["canEdit"] and not me["canApprove"]
    put = client.put("/api/v1/ads/budget", json={"items": [{"ay": "2026-09", "kanal": "google", "plan": 2000}]}, headers=a)
    assert put.status_code == 200 and put.json()["degisen"] == 1
    xl = client.get("/api/v1/ads/report/export.xlsx?frm=2026-09-01&to=2026-09-02", headers=a)
    assert xl.status_code == 200 and xl.content[:2] == b"PK"


def test_manual_brief_endpoint_skips_model(monkeypatch, store, settings):
    _, client, jobs = _app(monkeypatch, store, settings)
    a = {"cookie": "timas_session=a"}
    r = client.post("/api/v1/ads/briefs", json={"stokKodu": "15201.0001", "not": "lansman ayı", "elle": True}, headers=a)
    assert r.status_code == 201, r.text
    b = r.json()
    assert b["durum"] == "taslak" and b["metin"] is None and b["kitapAdi"] == "Kayıp Zamanın İzinde" and jobs == []
    assert client.patch(f"/api/v1/ads/briefs/{b['id']}", json={"onayla": True}, headers=a).status_code == 400
    saved = client.patch(f"/api/v1/ads/briefs/{b['id']}", json={"metin": "Ana mesaj: …", "onayla": True}, headers=a)
    assert saved.status_code == 200 and saved.json()["durum"] == "onayli"
    ai = client.post("/api/v1/ads/briefs", json={"stokKodu": "15201.0002"}, headers=a)
    assert ai.status_code == 201 and ai.json()["durum"] == "hazirlaniyor" and [j[0] for j in jobs] == ["brief_job"]
