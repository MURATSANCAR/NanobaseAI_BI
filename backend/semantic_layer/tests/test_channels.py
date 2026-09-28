"""M42 Platform ve kanallar: kapsam SQL'i, cari ↔ platform eşlemesi (ad adayı, Zeki AI kapalı küme, onay), karne toplamı
(platform = eşlenmiş carilerin toplamı), marj ve maliyetsiz satır, geçen yıl kıyasında yarım ay, M9 ile tamamlama, kitap ×
kanal matrisi, CRM bölge hedefi, iskonto simülasyonu, D2C güçlü kitaplar, panel dosyasında kişisel kolonun atlanması,
salt okunur platform istemcisi ve yetki kuralları.

Veriler yapaydır ve yalnız hesap kurallarını sınar; gerçek Logo/CRM kabulü test sunucusunda (scripts/acceptance/M42).
"""
from __future__ import annotations

import json
from datetime import date

import httpx
import pytest

from semantic_bridge import access as A
from semantic_bridge.channels import d2c as D
from semantic_bridge.channels import imports as I
from semantic_bridge.channels import mapping as M
from semantic_bridge.channels import platforms as P
from semantic_bridge.channels import refresh as RF
from semantic_bridge.channels import scorecard as SC
from semantic_bridge.channels import sources as src
from semantic_bridge.channels import store as S
from semantic_layer.store.catalog_store import open_store

T = "t1"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    S._ready.discard(id(e))
    S.ensure(e)
    return e


def _m(**kw):
    base = {k: 0.0 for k in src.METRICS}
    base.update(kw)
    return base


def _seed(engine, end=date(2026, 8, 17)):
    """2025 tam yıl + 2026 Ocak–Ağustos (17'sinde biter). HB1/HB2 → Hepsiburada, KY → Kitapyurdu, XX eşlenmemiş,
    DG platform değil; site müşterileri INTERNET kanal koduyla D2C. Kanal karnesinde KITAPCI kıyas satırı."""
    cari, kanal, books = [], [], []
    for y, months in ((2025, range(1, 13)), (2026, range(1, 9))):
        for m in months:
            f = 1.0 if y == 2025 else 1.2
            cari += [
                {"yil": y, "ay": m, "grup": "HB1", **_m(satis_ciro=1000 * f, iade_ciro=100 * f, satis_adet=100, iade_adet=10,
                                                        brut_satis=1250 * f, iskonto=250 * f, maliyet=300, maliyetli_ciro=800,
                                                        maliyetsiz_satir=2, maliyetsiz_ciro=200 * f, iade_maliyet=30,
                                                        iade_maliyetli_ciro=80)},
                {"yil": y, "ay": m, "grup": "HB2", **_m(satis_ciro=500, satis_adet=50, brut_satis=600, iskonto=100,
                                                        maliyet=200, maliyetli_ciro=500)},
                {"yil": y, "ay": m, "grup": "KY", **_m(satis_ciro=2000, iade_ciro=400, satis_adet=200, iade_adet=40, brut_satis=2500,
                                                       iskonto=500, maliyet=800, maliyetli_ciro=2000)},
                {"yil": y, "ay": m, "grup": "XX", **_m(satis_ciro=300, satis_adet=30, brut_satis=300)},
                {"yil": y, "ay": m, "grup": "DG", **_m(satis_ciro=700, satis_adet=70, brut_satis=700)},
                {"yil": y, "ay": m, "grup": "#K:INTERNET", **_m(satis_ciro=400, satis_adet=40, brut_satis=400, maliyet=100,
                                                                maliyetli_ciro=400)},
            ]
            kanal += [
                {"yil": y, "ay": m, "kanal": "E-TICARET", **_m(satis_ciro=4500, iade_ciro=500, satis_adet=450, iade_adet=50, brut_satis=5350, iskonto=850)},
                {"yil": y, "ay": m, "kanal": "KITAPCI", **_m(satis_ciro=10000, iade_ciro=1000, satis_adet=1000, iade_adet=100,
                                                            brut_satis=14000, iskonto=4000, maliyet=5000, maliyetli_ciro=10000)},
            ]
            books += [
                {"yil": y, "ay": m, "grup": "HB1", "stok_kodu": "B1", "satis_adet": 60, "iade_adet": 10, "satis_ciro": 600, "iade_ciro": 100,
                 "maliyet": 180, "maliyetli_ciro": 480, "maliyetsiz_adet": 12, "maliyetsiz_ciro": 120},
                {"yil": y, "ay": m, "grup": "HB1", "stok_kodu": "B2", "satis_adet": 40, "iade_adet": 0, "satis_ciro": 400, "iade_ciro": 0,
                 "maliyet": 120, "maliyetli_ciro": 320, "maliyetsiz_adet": 8, "maliyetsiz_ciro": 80},
                {"yil": y, "ay": m, "grup": "KY", "stok_kodu": "B1", "satis_adet": 200, "iade_adet": 40, "satis_ciro": 2000, "iade_ciro": 400,
                 "maliyet": 800, "maliyetli_ciro": 2000, "maliyetsiz_adet": 0, "maliyetsiz_ciro": 0},
                {"yil": y, "ay": m, "grup": "#K:INTERNET", "stok_kodu": "B3", "satis_adet": 30, "iade_adet": 0, "satis_ciro": 300,
                 "iade_ciro": 0, "maliyet": 75, "maliyetli_ciro": 300, "maliyetsiz_adet": 0, "maliyetsiz_ciro": 0},
                {"yil": y, "ay": m, "grup": "#K:INTERNET", "stok_kodu": "B1", "satis_adet": 10, "iade_adet": 0, "satis_ciro": 100,
                 "iade_ciro": 0, "maliyet": 25, "maliyetli_ciro": 100, "maliyetsiz_adet": 0, "maliyetsiz_ciro": 0},
            ]
    for y in (2025, 2026):
        S.replace_year(engine, T, S.CARI_MONTHS, y, [r for r in cari if r["yil"] == y])
        S.replace_year(engine, T, S.KANAL_MONTHS, y, [r for r in kanal if r["yil"] == y])
        S.replace_year(engine, T, S.BOOK_MONTHS, y, [r for r in books if r["yil"] == y])
        S.meta_set(engine, T, f"read:{y}", {"specodes": ["E-TICARET", "INTERNET"], "codes": [], "kanalMapped": ["INTERNET"]})
    S.meta_set(engine, T, "data_end", {"date": end.isoformat()})
    S.upsert_books(engine, T, {"B1": "Birinci Kitap", "B2": "İkinci Kitap", "B3": "Üçüncü Kitap"})
    cards = [{"cari_kodu": c, "unvan": u, "kanal": "E-TICARET", "ref": i, "firma": "411"}
             for i, (c, u) in enumerate([("HB1", "D-MARKET ELEKTRONİK HİZ. A.Ş."), ("HB2", "HEPSİBURADA LOJİSTİK"),
                                         ("KY", "KİTAPYURDU DOĞRUDAN PAZ."), ("XX", "BİLİNMEYEN E-TİCARET LTD"),
                                         ("DG", "ÖRNEK KİTABEVİ E-TİCARET")], 1)]
    S.sync_accounts(engine, T, cards, {})
    for code, plat in (("HB1", "hepsiburada"), ("HB2", "hepsiburada"), ("KY", "kitapyurdu"), ("DG", "degil")):
        M.decide(engine, T, "ayse", code, {"platform": plat})
    M.set_kanal(engine, T, "ayse", "INTERNET", "timas.com.tr")


# ------------------------------------------------------------------ SQL


def test_scope_and_group_sql_quote_values_and_keep_the_sales_definition():
    sc = src.scope_sql(["E-TICARET"], ["120.01'X"])
    assert sc == "C.SPECODE2 IN (N'E-TICARET') OR C.CODE IN (N'120.01''X')"
    assert src.scope_sql([], []) == "1 = 0"
    g = src.grup_sql(["INTERNET"], ["HB1"])
    assert g.startswith("CASE WHEN C.CODE IN (N'HB1') THEN C.CODE WHEN C.SPECODE2 IN (N'INTERNET') THEN '#K:'")
    assert src.grup_sql([], ["HB1"]) == "C.CODE"
    sql = src.eticaret_cari_sql("411", 2026, sc, g)
    for must in ("INVOICEREF <> 0", "S.CANCELLED = 0", "TRCODE IN (2,3,7,8,9)", "S.LINETYPE = 2", "ISNULL(S.OUTCOST, 0) > 0",
                 "'2026-01-01'", "'2027-01-01'", "LG_411_01_STLINE", "LG_411_CLCARD"):
        assert must in sql, must
    assert "{" not in sql and "{" not in src.cari_kitap_sql("211", 2025, sc) and "{" not in src.kanal_karne_sql("411", 2026)
    assert "new_logicalref IN (N'5', N'7')" in src.crm_cari_sql("Timas_MSCRM.dbo", ["5", "7"])
    assert "new_yil = 100000000" in src.crm_hedef_sql("Timas_MSCRM.dbo", 100000000)


def test_filled_logo_sql_has_no_live_text_outside_the_query():
    """Yorum satırında anılan çok satırlı yer tutucu (ölçü kolonları) yerine konunca ilk satırından sonrası yorum dışında
    kalıyordu: kanal karnesi SQL Server'da «Incorrect syntax near ','» ile düştü (2026-09-28 kabul). SELECT'ten önce
    yalnız yorum satırı olmalı."""
    sc = src.scope_sql(["E-TICARET"], ["HB1"])
    g = src.grup_sql(["INTERNET"], ["HB1"])
    for sql in (src.kanal_karne_sql("411", 2026), src.eticaret_cari_sql("411", 2026, sc, g),
                src.cari_kitap_sql("411", 2026, sc, g), src.cari_liste_sql("411", sc)):
        head = sql[:sql.index("SELECT")]
        assert all(not ln.strip() or ln.lstrip().startswith("--") for ln in head.splitlines()), head


def test_target_labels_prefer_the_year_label():
    rows = [{"alan": "new_yil", "kod": 100000000, "ad": "2026"}, {"alan": "new_yil", "kod": 3, "ad": "2025"},
            {"alan": "new_bolge", "kod": 8, "ad": "HEPSİBURADA"}, {"alan": "new_yil", "kod": 3, "ad": "Diğer"}]
    out = src.read_target_labels(lambda sql: rows, "x")
    assert out["years"] == {"100000000": "2026", "3": "2025"} and out["regions"] == {"8": "HEPSİBURADA"}


# ------------------------------------------------------------------ eşleme


def test_name_candidate_uses_platform_name_and_operator_but_not_ambiguity():
    h = M.DEFAULT_HINTS
    assert M.name_candidate({"unvan": "D-MARKET ELEKTRONİK"}, h) == "hepsiburada"
    assert M.name_candidate({"unvan": "KİTAPYURDU DOĞRUDAN"}, h) == "kitapyurdu"
    assert M.name_candidate({"unvan": "X LTD", "crmAd": "D&R Kültür"}, h) == "dr"
    assert M.name_candidate({"unvan": "AMAZON VE TRENDYOL ORTAK"}, h) is None     # iki platform: modele kalır
    assert M.name_candidate({"unvan": "DRAMA KİTABEVİ"}, h) is None               # «dr» sözcük değil


class FakeChoice:
    def __init__(self, choice, p, margin):
        self.choice, self.probability, self.margin, self.method = choice, p, margin, "logprobs"
        self.probs = {choice: p} if choice else {}

    def confident(self, min_prob, min_margin=0.0):
        return self.probability is not None and self.probability >= min_prob and self.margin >= min_margin


class FakeLlm:
    def __init__(self, answers):
        self.answers, self.prompts = answers, []

    def choose(self, prompt, labels):
        self.prompts.append((prompt, labels))
        return self.answers.pop(0)


def _st(**kw):
    s = M.settings(lambda k: "")
    s.update(kw)
    return s


def test_propose_saves_name_and_confident_model_candidates_only(engine):
    S.sync_accounts(engine, T, [{"cari_kodu": c, "unvan": u, "kanal": "E-TICARET", "ref": None, "firma": "411"}
                                for c, u in (("A", "D-MARKET A.Ş."), ("B", "ÖZGÜN TİC."), ("C", "BAŞKA TİC."))], {})
    llm = FakeLlm([FakeChoice("Trendyol", 0.93, 0.8), FakeChoice("Amazon", 0.55, 0.1)])
    out = M.propose(engine, T, llm, _st())
    assert out == {"ad": 1, "zeki": 1, "eminDegil": 1, "kalan": 0, "atlandi": None}
    acc = {a["cariKodu"]: a for a in S.accounts(engine, T)}
    assert (acc["A"]["platform"], acc["A"]["durum"], acc["A"]["yontem"]) == ("hepsiburada", "aday", "ad")
    assert (acc["B"]["platform"], acc["B"]["durum"], acc["B"]["olasilik"]) == ("trendyol", "aday", 0.93)
    assert acc["C"]["platform"] is None and acc["C"]["durum"] == "bekliyor" and acc["C"]["aday"]["emin"] is False
    # Kapalı küme: platform listesi + «Platform değil»; istemde işletmeci unvanı var.
    prompt, labels = llm.prompts[0]
    assert "Platform değil" in labels and "Hepsiburada" in labels and "D-MARKET" in prompt
    # Sorulan cari ikinci turda yeniden sorulmaz; model yoksa kalan sayılır.
    assert M.propose(engine, T, None, _st())["kalan"] == 0


def test_decide_approves_changes_and_removes_mapping(engine):
    S.sync_accounts(engine, T, [{"cari_kodu": "A", "unvan": "D-MARKET", "kanal": "E-TICARET", "ref": 1, "firma": "411"}], {})
    M.propose(engine, T, None, _st())
    out, diff = M.decide(engine, T, "ayse", "A", {})
    assert out["durum"] == "onayli" and out["platform"] == "hepsiburada" and out["yontem"] == "ad" and out["onaylayan"] == "ayse"
    out, diff = M.decide(engine, T, "ali", "A", {"platform": "degil", "not": "B2B sitesi"})
    assert out["platform"] == "degil" and out["yontem"] == "elle" and diff["once"]["platform"] == "hepsiburada"
    out, _ = M.decide(engine, T, "ali", "A", {"platform": None, "onay": False})
    assert out["durum"] == "bekliyor" and out["platform"] is None
    with pytest.raises(M.MappingError):
        M.decide(engine, T, "ali", "A", {"platform": "yok-boyle"})
    with pytest.raises(M.MappingError):
        M.decide(engine, T, "ali", "YOK", {})
    # Kart yeniden okununca eşleme korunur.
    M.decide(engine, T, "ali", "A", {"platform": "trendyol"})
    S.sync_accounts(engine, T, [{"cari_kodu": "A", "unvan": "YENİ UNVAN", "kanal": "E-TICARET", "ref": 1, "firma": "411"}], {})
    a = S.account_get(engine, T, "A")
    assert a["platform"] == "trendyol" and a["durum"] == "onayli" and a["unvan"] == "YENİ UNVAN"


def test_scope_grows_when_a_cari_outside_the_read_scope_is_mapped(engine):
    _seed(engine)
    st = _st()
    assert RF.missing_scope(engine, T, st, [2026]) == []
    S.sync_accounts(engine, T, [{"cari_kodu": "Z9", "unvan": "AMAZON TURKEY", "kanal": "YURTDISI", "ref": 9, "firma": "411"}], {})
    M.decide(engine, T, "ayse", "Z9", {"platform": "amazon"})
    assert RF.missing_scope(engine, T, st, [2025, 2026]) == [2025, 2026]
    sc = RF.scope(engine, T, st)
    assert "Z9" in sc["codes"] and "DG" not in sc["codes"] and "INTERNET" in sc["specodes"]


# ------------------------------------------------------------------ karne


def test_platform_total_is_the_sum_of_its_mapped_caris(engine):
    _seed(engine)
    card = SC.scorecard(engine, T, 2026, 7)
    by = {x["platform"]: x for x in card["platforms"]}
    hb = by["hepsiburada"]["donem"]
    # HB1 (1.200 − 120) + HB2 500, 7 ay
    assert hb["netCiro"] == pytest.approx(7 * (1200 - 120 + 500))
    assert by["hepsiburada"]["grupSayisi"] == 2
    assert by[M.UNMAPPED]["donem"]["netCiro"] == pytest.approx(7 * 300)
    assert "degil" not in by and card["platformDisi"]["donem"]["netCiro"] == pytest.approx(7 * 700)
    assert by["timas.com.tr"]["donem"]["netCiro"] == pytest.approx(7 * 400)
    # İade ve iskonto oranı, marj (maliyetli satırlar), maliyetsiz satır ayrıca
    ky = by["kitapyurdu"]["donem"]
    assert ky["iadeOrani"] == pytest.approx(0.2) and ky["iskontoOrani"] == pytest.approx(0.2) and ky["marj"] == pytest.approx(0.6)
    assert hb["maliyetsizSatir"] == 14 and hb["maliyetsizCiro"] == pytest.approx(7 * 240)
    assert hb["iadeSonrasiMarj"] == pytest.approx(((1300 - 80) - (500 - 30)) / (1300 - 80))
    # Temmuz tam ay: geçen yıl da 7 tam ay
    assert by["kitapyurdu"]["degisim"] == pytest.approx(0.0)
    # e-ticaret toplamı platform dışını içermez; şirket toplamı kanal karnesinden
    assert card["toplam"]["eticaret"]["netCiro"] == pytest.approx(7 * (1580 + 1600 + 300 + 400))
    assert card["toplam"]["sirket"]["netCiro"] == pytest.approx(7 * (4000 + 9000))
    assert [k["kanal"] for k in card["kanallar"]] == ["KITAPCI", "E-TICARET"]


def test_partial_last_month_is_compared_with_the_same_share_of_last_year(engine):
    _seed(engine)
    card = SC.scorecard(engine, T, 2026)
    p = card["period"]
    assert p["ay"] == 8 and p["kismiAy"] and p["gunPayi"] == pytest.approx(17 / 31, abs=1e-4)
    ky = next(x for x in card["platforms"] if x["platform"] == "kitapyurdu")
    assert ky["gecenYil"]["netCiro"] == pytest.approx(1600 * (7 + 17 / 31), abs=0.05)   # gün payı 4 hanede yuvarlanır
    assert ky["donem"]["netCiro"] == pytest.approx(1600 * 8)


def test_missing_year_and_future_year_are_explained(engine):
    _seed(engine)
    with pytest.raises(SC.ChannelError) as e:
        SC.scorecard(engine, T, 2027)
    assert "henüz veri yok" in str(e.value)
    with pytest.raises(SC.ChannelError) as e:
        SC.scorecard(engine, T, 2024)
    assert e.value.status == 409


def test_redact_removes_margin_everywhere():
    obj = {"donem": {"netCiro": 1, "marj": 0.3, "maliyet": 5, "m9": {"marj": 0.2}}, "items": [{"brutKar": 1, "ad": "x"}]}
    assert SC.redact(obj) == {"donem": {"netCiro": 1}, "items": [{"ad": "x"}]}


def test_channel_detail_fills_uncosted_lines_with_m9_unit_cost(engine):
    _seed(engine)
    calls = []

    def unit_costs(codes):
        calls.append(list(codes))
        return {"B1": {"maliyet": 3.0, "kaynak": "onayli-analiz"}, "B2": {"maliyet": None, "kaynak": "yok"}}

    ch = SC.channel(engine, T, "hepsiburada", 2026, 7, unit_costs)
    m9 = ch["donem"]["m9"]
    assert calls == [["B1", "B2"]]
    assert m9["tamamlananCiro"] == pytest.approx(7 * 120) and m9["tamamlananMaliyet"] == pytest.approx(7 * 12 * 3)
    assert m9["bilinmeyenKitap"] == 1 and m9["bilinmeyenCiro"] == pytest.approx(7 * 80)
    assert [c["grup"] for c in ch["cariler"]] == ["HB1", "HB2"]
    assert ch["aylik"][7]["buYil"] is None and ch["aylik"][6]["buYil"]["netCiro"] == pytest.approx(1580)


def test_books_returns_and_matrix(engine):
    _seed(engine)
    b = SC.books(engine, T, "hepsiburada", 2026, 7, sort="iadeAdet")
    assert [x["stokKodu"] for x in b["items"]] == ["B1", "B2"] and b["items"][0]["iadeOrani"] == pytest.approx(10 / 60)
    assert SC.books(engine, T, "hepsiburada", 2026, 7, q="ikinci")["total"] == 1
    r = SC.returns(engine, T, "kitapyurdu", 2026, 2, months=3)
    # Aralık 2025, Ocak, Şubat 2026 → 3 ay × 40
    assert r["aralik"]["bas"] == "2025-12" and r["items"][0]["iadeAdet"] == pytest.approx(120)
    mx = SC.matrix(engine, T, 2026, 7)
    assert [c["platform"] for c in mx["columns"]] == ["kitapyurdu", "hepsiburada", "timas.com.tr"]
    b1 = next(x for x in mx["items"] if x["stokKodu"] == "B1")
    assert b1["kanallar"]["kitapyurdu"] == {"alim": 1400, "iade": 280, "net": 1120}
    assert b1["toplam"] == pytest.approx(7 * (160 + 50 + 10))
    assert SC.matrix(engine, T, 2026, 7, sort="timas.com.tr")["items"][0]["stokKodu"] == "B3"
    assert SC.matrix(engine, T, 2026, 7, size=1)["total"] == 3


def test_crm_region_target_is_prorated_to_the_data_end(engine):
    _seed(engine)
    S.replace_year(engine, T, S.TARGETS, 2026, [{"yil": 2026, "bolge": "8", "bolge_ad": "HEPSİBURADA", "satir": 3, "toplam": 1200,
                                                  "aylar_json": json.dumps([100.0] * 12)}])
    assert SC.targets_by_platform(engine, T, SC.period(engine, T, 2026, None)) == {}   # bölge eşlenmeden hedef yok
    M.set_region(engine, T, "ayse", "8", "hepsiburada")
    t = SC.targets(engine, T, 2026)["crm"]["hepsiburada"]
    assert t["beklenen"] == pytest.approx(100 * (7 + 17 / 31), abs=0.01) and t["gerceklesen"] == pytest.approx(8 * 140)
    assert t["aylik"][8]["gercek"] is None and t["bolgeler"] == ["HEPSİBURADA"]


def test_m46_target_is_split_by_last_years_channel_share(engine):
    from semantic_bridge import budget as B

    _seed(engine)
    B._ready.discard(id(engine))
    B.ensure(engine)
    with engine.begin() as c:
        c.execute(B.SALES.insert(), [{"year": 2025, "month": m, "stok_kodu": "B1", "adet": 540, "ciro": 1, "maliyet": 0,
                                      "maliyetli_ciro": 0} for m in range(1, 13)])
    plan = {"plan": {"id": "p"}, "items": [{"stokKodu": "B1", "hedef": {"adet": 12000, "ciro": 120000},
                                             "aylik": [{"ay": m, "adet": 1000} for m in range(1, 13)]}]}
    out = SC.targets(engine, T, 2026, lambda y: plan)["m46"]["platformlar"]
    # 2025: Kitapyurdu B1 net 160/ay, şirket 540/ay → pay 160/540
    assert out["kitapyurdu"]["hedefAdet"] == pytest.approx(12000 * 160 / 540, abs=0.01)
    assert out["kitapyurdu"]["gerceklesenAdet"] == pytest.approx(8 * 160)


def test_discount_simulation_and_breakeven(engine):
    _seed(engine)
    s = SC.simulate(engine, T, {"platform": "kitapyurdu", "yil": 2026, "ay": 7, "iskontoPuan": 2})
    B, N, Nc, C = 7 * 2500, 7 * 2000, 7 * 2000, 7 * 800
    assert s["sonra"]["netSatis"] == pytest.approx(N - B * 0.02)
    assert s["sonra"]["brutKar"] == pytest.approx(Nc - B * 0.02 - C)
    assert s["fark"]["brutKar"] == pytest.approx(-B * 0.02)
    assert s["basabasHacim"] == pytest.approx((Nc - C) / (Nc - B * 0.02 - C) - 1)
    assert s["once"]["iskontoOrani"] == pytest.approx(0.2) and s["sonra"]["iskontoOrani"] == pytest.approx(0.22)
    with pytest.raises(SC.ChannelError):
        SC.simulate(engine, T, {"platform": "kitapyurdu", "iskontoPuan": "x"})
    assert "Kitapyurdu" in SC.facts_text(s)


# ------------------------------------------------------------------ D2C


def test_d2c_strong_books_by_share_index(engine):
    _seed(engine)
    st = _st(d2cMinAdet=20, d2cIndex=1.5)
    out = D.overview(engine, T, st, 2026, 7)
    assert out["eslendi"] and out["site"]["bagli"] is False
    # D2C: B3 210, B1 70; pazar yeri: B1 (50+160)×7, B2 280 → genel D2C payı 280/(280+1750)
    assert [r["stokKodu"] for r in out["kitaplar"]] == ["B3"]
    assert out["genelD2cPay"] == pytest.approx(280 / (280 + 7 * 250))
    sug = D.suggest_set(engine, T, "ayse", st, [], None, 2026, 7)
    assert sug["tur"] == "d2c-set" and sug["durum"] == "taslak" and sug["payload"]["kitaplar"][0]["stokKodu"] == "B3"


def test_d2c_without_mapping_says_so(engine):
    _seed(engine)
    M.set_kanal(engine, T, "ayse", "INTERNET", None)
    out = D.overview(engine, T, _st(), 2026, 7)
    assert out["eslendi"] is False and out["kitaplar"] == [] and "eşlenmedi" in out["not"]


# ------------------------------------------------------------------ panel dosyası


def test_import_keeps_only_whitelisted_columns_and_matches_barcodes(engine):
    _seed(engine)
    S.replace_all(engine, T, S.BARCODES, [{"barkod": "9786050000001", "stok_kodu": "B1"}])
    csv_text = ("Rapor tarihi;28.09.2026\n\nBarkod;Ürün Adı;Müşteri Adı Soyadı;Teslimat Adresi;Satış Adedi;Satış Tutarı;Stok\n"
                "9786050000001;Birinci Kitap;Ayşe Yılmaz;İstanbul;5;500,50;12\n"
                "0000000000000;Bilinmeyen;Ali Veli;Ankara;2;100;0\n;boş satır;;;;;\n")
    out = I.store_import(engine, T, "ayse", "hepsiburada", "rapor.csv", csv_text.encode("utf-8"), "2026-07-01", "2026-07-31")
    assert out["satir"] == 2 and out["eslesen"] == 1
    assert set(out["kolonlar"]["kisiselOlabilir"]) == {"Müşteri Adı Soyadı", "Teslimat Adresi"}
    rows = I.get(engine, T, out["id"], with_rows=True)["rows"]
    assert rows[0]["tutar"] == pytest.approx(500.5) and rows[0]["kanalStok"] == 12
    assert not any("Ayşe" in json.dumps(r, ensure_ascii=False) or "İstanbul" in json.dumps(r, ensure_ascii=False) for r in rows)
    st = I.sell_through(engine, T, out["id"], SC.sell_in_books(engine, T, "hepsiburada", SC.months_between("2026-07-01", "2026-07-31")))
    assert st["items"][0]["kanalaSatis"] == 50 and st["items"][0]["oran"] == pytest.approx(0.1) and st["eslesmeyen"] == 1
    with pytest.raises(I.ImportError_):
        I.store_import(engine, T, "ayse", "hepsiburada", "x.csv", b"a;b\n1;2\n")
    with pytest.raises(I.ImportError_):
        I.store_import(engine, T, "ayse", "degil", "x.csv", csv_text.encode())
    I.delete(engine, T, out["id"])
    assert I.list_imports(engine, T) == []


# ------------------------------------------------------------------ salt okunur istemci


class Demo(P.ReadOnlyClient):
    platform = "trendyol"
    BASE_DEFAULT = "https://ornek.invalid"
    CONF_KEYS = {"anahtar": "X_KEY"}
    ALLOWED = (("GET", r"products"), ("GET", r"orders/\d+"))


def test_read_only_client_refuses_writes_before_the_network():
    def boom(request):  # ağa çıkılırsa test kırılır
        raise AssertionError(f"ağ çağrısı: {request.method} {request.url}")

    c = Demo(lambda k: "gizli", transport=httpx.MockTransport(boom))
    for method, path in (("POST", "products"), ("PUT", "products"), ("DELETE", "orders/1"), ("GET", "products/update"),
                         ("PATCH", "orders/5")):
        with pytest.raises(P.ReadOnlyViolation):
            c.request(method, path)
    ok = Demo(lambda k: "gizli", transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"n": 1})))
    assert ok.get("orders/12") == {"n": 1}
    with pytest.raises(P.PlatformError):
        Demo(lambda k: "", transport=httpx.MockTransport(boom)).get("products")


# ------------------------------------------------------------------ yetki


def test_access_rules_for_channel_endpoints():
    assert A.rule_for("/api/v1/channels/scorecard") == {"sayfa:kanallar"}
    assert A.rule_for("/api/v1/channels/channel/hepsiburada/books") == {"sayfa:kanallar"}
    assert A.rule_for("/api/v1/channels/matrix") == {"sayfa:kanal-matris"}
    assert A.rule_for("/api/v1/channels/d2c/suggest") == {"sayfa:kanal-d2c"}
    assert A.rule_for("/api/v1/channels/accounts/HB1") == {"sayfa:kanal-eslesme"}
    assert A.rule_for("/api/v1/channels/meta") == {"sayfa:kanallar", "sayfa:kanal-matris", "sayfa:kanal-d2c", "sayfa:kanal-eslesme"}
    assert A.rule_for("/api/v1/channels/run-due") == A.SYSTEM
    f = A.features_for
    assert f("PUT", "/api/v1/channels/accounts/HB1") == ["ozellik:kanal.eslesme"]
    assert f("GET", "/api/v1/channels/accounts") == []
    assert f("POST", "/api/v1/channels/imports") == ["ozellik:kanal.yukle"]
    assert f("POST", "/api/v1/channels/suggestions") == ["ozellik:kanal.oneri-yaz"]
    assert f("POST", "/api/v1/channels/suggestions/x/decision") == []          # açıkça verilen, ucun içinde
    assert f("POST", "/api/v1/channels/simulate") == []                         # açıkça verilen, ucun içinde
    assert f("GET", "/api/v1/channels/export/karne.xlsx") == ["ozellik:veri.disa-aktar"]
    assert {"ozellik:kanal.marj", "ozellik:kanal.oneri-karar"} <= A.explicit_keys()


def _api(monkeypatch, store, settings):
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
    A._ready.clear()
    A.invalidate()
    app = create_app(Runtime(settings, store=store, llm=FakeLlm([""])))
    return TestClient(app)


def test_api_redacts_margin_and_enforces_two_eyes(monkeypatch, store, settings):
    client = _api(monkeypatch, store, settings)
    S.ensure(store.engine)
    _seed(store.engine)
    a, z = {"cookie": "timas_session=a"}, {"cookie": "timas_session=z"}
    meta = client.get("/api/v1/channels/meta", headers=a).json()
    assert meta["me"]["canMargin"] is False and meta["me"]["canMap"] is True and meta["defaultYear"] == 2026
    plain = client.get("/api/v1/channels/scorecard?yil=2026&ay=7", headers=a).json()
    assert "marj" not in plain["platforms"][0]["donem"] and "netCiro" in plain["platforms"][0]["donem"]
    full = client.get("/api/v1/channels/scorecard?yil=2026&ay=7", headers=z).json()
    assert "marj" in full["platforms"][0]["donem"]
    assert client.post("/api/v1/channels/simulate", json={"platform": "kitapyurdu", "iskontoPuan": 1}, headers=a).status_code == 403
    sim = client.post("/api/v1/channels/suggestions", json={"platform": "kitapyurdu", "yil": 2026, "ay": 7, "iskontoPuan": 1}, headers=z)
    assert sim.status_code == 201
    sid = sim.json()["id"]
    assert client.post(f"/api/v1/channels/suggestions/{sid}/decision", json={"karar": "onayli"}, headers=z).status_code == 403
    assert client.post(f"/api/v1/channels/suggestions/{sid}/decision", json={"karar": "onayli"}, headers=a).status_code == 403
    assert client.get("/api/v1/channels/scorecard?yil=2024", headers=a).status_code == 409
    put = client.put("/api/v1/channels/accounts/XX", json={"platform": "diger"}, headers=a)
    assert put.status_code == 200 and put.json()["durum"] == "onayli"
    x = client.get("/api/v1/channels/export/karne.xlsx?yil=2026&ay=7", headers=a)
    assert x.status_code == 200 and x.content[:2] == b"PK"
    assert client.post("/api/v1/channels/run-due", headers=a).status_code == 403
