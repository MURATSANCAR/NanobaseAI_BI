"""M17 Backlist: küme (M46 backlist segmenti, 157 hariç; plan yoksa CRM ilk yayın), bileşenler (son 12 / önceki 12 tam ay,
stok ve tükenme, marj, tahmin, hedef sapması), sıra yüzdeliği ve ağırlıklı endeks, süzgeçler (tavan yok), fırsat kartı,
gündem (özel gün, yazarın yeni kitabı, konu eşleşmesi onayı), kampanya etkisi (ay düzeyi), aktivasyon planı (çok kitaplı,
çekirdeğin onay akışı, revizyonda kitaplar kopyalanır), Zeki AI taslak denetimi, yetki kuralları ve uçlar.

Veriler yapaydır ve yalnız kuralları sınar; gerçek Logo/CRM kabulü test sunucusunda (`scripts/acceptance/m17/`).
"""

from __future__ import annotations

import math
from datetime import date, datetime, timezone

import pytest
import sqlalchemy as sa

from semantic_bridge import access as A
from semantic_bridge import budget as B
from semantic_bridge import budget_sources as bsrc
from semantic_bridge.marketing import backlist as BL
from semantic_bridge.marketing import backlist_api as BLA
from semantic_bridge.marketing import books as BK
from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import plans as P
from semantic_layer.store.catalog_store import open_store

T = "t1"
TODAY = date(2026, 10, 20)
END = date(2026, 8, 17)          # Logo veri sonu: son tam ay Temmuz 2026


def _reset(e):
    for mod in (C, B, BK, BL):
        mod._ready.discard(id(e))


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    _reset(e)
    B.ensure(e)
    BL.ensure(e)
    yield e
    _reset(e)


# ------------------------------------------------------------------ yapay veri


def adet(code: str, y: int, m: int) -> float:
    i = B.month_index(y, m)
    if code == "B1":
        if B.month_index(2024, 8) <= i <= B.month_index(2025, 7):
            return 10.0
        if B.month_index(2025, 8) <= i <= B.month_index(2026, 7):
            return 5.0
        if (y, m) == (2026, 8):
            return 99.0                                                # yarım ay: son 12'ye girmez
        if B.month_index(2022, 1) <= i < B.month_index(2024, 8):
            return 7.0
    if code == "B2" and B.month_index(2025, 8) <= i <= B.month_index(2026, 7):
        return 2.0
    if code == "N1" and y == 2026:
        return 50.0
    return 0.0


def year_rows(y: int) -> list[dict]:
    out = []
    for code in ("B1", "B2", "B3", "15700.1", "N1"):
        for m in range(1, 13):
            a = adet(code, y, m)
            if a:
                out.append({"year": y, "month": m, "stok_kodu": code, "adet": a, "ciro": a * 100, "maliyet": a * 40,
                            "maliyetli_ciro": a * 100})
    return out


def seed_budget(engine, *, plan=True, alert=True):
    B.meta_set(engine, "data_end", {"date": END.isoformat()})
    with engine.begin() as c:
        for y in (2025, 2026):
            rows = year_rows(y)
            if rows:
                c.execute(B.SALES.insert(), rows)
        now = datetime.now(timezone.utc)
        info = [("B1", "Uyuyan Kitap", "Yazar A", "2019-03-01"), ("B2", "Yükselen Kitap", "Yazar B", "2020-05-01"),
                ("B3", "Satmayan Kitap", "Yazar C", "2018-01-01"), ("15700.1", "Ajanda", None, "2019-01-01"),
                ("N1", "Yeni Kitap", "Yazar D", "2026-06-01"), ("X9", "Tarihsiz", None, None)]
        c.execute(B.BOOKINFO.insert(), [{"stok_kodu": k, "ad": a, "yazar": y, "yayinevi": "Timaş Yayınları", "kitaplik": "Roman",
                                         "ilk_yayin": d, "liste_fiyati": 100.0, "statu": None, "in_logo": True} for k, a, y, d in info])
        if plan:
            c.execute(B.PLANS.insert().values(id="P26", tenant_id=T, year=2026, scenario="temel", version=1, status="onayli",
                                              title="2026", params_json="{}", basis_json="{}", created_by="gm", created_at=now,
                                              decided_by="gm", decided_at=now))
            for code, seg, ad_, ciro in (("B1", "backlist", 120, 12000), ("B2", "backlist", 30, 3000), ("B3", "backlist", 10, 1000),
                                         ("15700.1", "backlist", 5, 500), ("N1", "yeni", 600, 60000)):
                c.execute(B.BOOKS.insert().values(plan_id="P26", stok_kodu=code, ad=code, segment=seg, adet=ad_, ciro=ciro,
                                                  marj=0.5, oneri_json="{}"))
        if plan and alert:
            c.execute(B.ALERTS.insert().values(id="al1", tenant_id=T, year=2026, plan_id="P26", kind="satis", scope="kitap",
                                               key="B1", label="Uyuyan Kitap", ratio=0.4, expected=7000, actual=2800, gap=4200,
                                               modules="M17", status="acik", first_at=now, last_at=now))
    for y in (2025, 2026):
        B.meta_set(engine, f"sales:{y}", {"rows": len(year_rows(y))})


class Choice:
    def __init__(self, choice, p):
        self.choice, self.probability, self.margin, self.method = choice, p, p - (1 - p), "logprobs"

    def confident(self, min_prob, min_margin=0.0, min_coverage=0.0):
        return self.probability >= min_prob and self.margin >= min_margin


class FakeLlm:
    def __init__(self, answer="İlgili", p=0.9, text="Uyuyan Kitap için şimdi tam zamanı. 2031 yılında da okunur."):
        self.answer, self.p, self.text, self.asked = answer, p, text, []

    def choose(self, prompt, choices):
        self.asked.append(prompt)
        return Choice(self.answer, self.p)

    def chat(self, messages, max_tokens=0):
        return self.text


DAYS = [{"id": "G1", "ad": "Öğretmenler Günü", "hafta1": None, "hafta2": None, "tarih": None},
        {"id": "G2", "ad": "Dünya Kitap Günü", "hafta1": None, "hafta2": None, "tarih": "2026-04-23"}]


class FakeSources(BL.Sources):
    def __init__(self, *, fail_past=False):
        super().__init__(lambda: "", lambda: None, lambda: "Timas_MSCRM.dbo")
        self.past_reads: list[int] = []
        self.fail_past = fail_past

    def sales(self, year):
        if self.fail_past:
            raise BL.SourceError("bağlantı yok")
        self.past_reads.append(year)
        return year_rows(year)

    def logo_sql(self, sql):
        assert "EOS_DEPO_STOK_KONTROL_211" in sql
        return [{"stok_kodu": "B1", "depo_stok": 100}, {"stok_kodu": "B2", "depo_stok": 0}, {"stok_kodu": "B3", "depo_stok": 50}]

    def crm(self, sql):
        if "new_ozelgunlerBase AS o" in sql:
            return DAYS
        if "new_new_kitap_new_ozelgunlerBase" in sql:
            return [{"gun_id": "G1", "stok_kodu": "B1"}, {"gun_id": "G1", "stok_kodu": "B3"}, {"gun_id": "G1", "stok_kodu": "N1"}]
        if "new_eserkatilimBase" in sql:
            return [{"yeni_stok": "Y1", "yeni_ad": "Yazarın Yeni Kitabı", "yeni_tarih": "2026-11-01", "yazar_id": "a", "yazar": "Yazar B",
                     "stok_kodu": "B2"}]
        if "new_kampanyaBase" in sql:
            return [{"id": "K1", "ad": "Kasım kampanyası", "tip": 1, "mecra": 2, "baslangic": "2025-11-01", "bitis": "2025-11-30",
                     "ek_iskonto": 5, "net_iskonto": 45, "planlanan_ciro": 10000, "gerceklesen_ciro": 8000, "stok_kodu": "B1"}]
        if "new_temaBase" in sql:
            return [{"stok_kodu": "B3", "kelime": "öğretmen ve okul", "kaynak": "tema"}]
        if "new_kitapBase AS k" in sql:
            return [{"stok_kodu": "B1", "kitap_id": "K-1", "hedef_kitle": "Çocuk", "yaslar": "8-10", "turler": "Roman",
                     "ekitap_stok": None, "ekitap_isbn": None, "satis_durumu": 1, "kapak": None},
                    {"stok_kodu": "B3", "kitap_id": "K-3", "hedef_kitle": "Yetişkin", "ekitap_stok": "E3", "ekitap_isbn": None}]
        raise AssertionError(sql[:80])


@pytest.fixture
def built(engine, monkeypatch):
    seed_budget(engine)
    monkeypatch.setattr(bsrc, "read_forecast", lambda: {"start": "2026-09", "updatedAt": 1.0,
                                                          "p50": {"B1": [10.0] * 24, "B2": [1.0] * 12}})
    src = FakeSources()
    meta = BL.build(engine, T, src, BL.settings(lambda k: ""), today=TODAY)
    return engine, meta, src


def rows(engine):
    with engine.connect() as c:
        return {r.stok_kodu: r for r in c.execute(sa.select(BL.ROWS)).all()}


# ------------------------------------------------------------------ saf hesaplar


def test_windows_use_last_full_month():
    w = BL.windows(date(2026, 8, 17))
    assert BL.ym(w["lastFull"]) == "2026-07" and BL.ym(w["son12"]) == "2025-08" and BL.ym(w["onceki12"]) == "2024-08"
    assert BL.ym(w["seri"]) == "2023-08"
    assert BL.ym(BL.windows(date(2026, 7, 31))["lastFull"]) == "2026-07"


def test_percentiles_are_mid_rank_and_keep_blanks():
    p = BL.percentiles({"a": 1.0, "b": 2.0, "c": 2.0, "d": None, "e": math.inf})
    assert p["d"] is None and p["a"] == 12.5 and p["b"] == p["c"] == 50.0 and p["e"] == 87.5


def test_index_skips_missing_components_and_follows_weights():
    pct = {"egilim": 90.0, "stok": 10.0, "marj": None, "tahmin": 50.0, "sapma": None}
    assert BL.index_of(pct, BL.DEFAULT_WEIGHTS) == 50.0
    assert BL.index_of(pct, BL.parse_weights("egilim:3,stok:1,tahmin:0")) == 70.0
    assert BL.index_of({k: None for k in BL.KEYS}, BL.DEFAULT_WEIGHTS) is None


def test_weight_parsing():
    assert BL.parse_weights("") == BL.DEFAULT_WEIGHTS
    w = BL.parse_weights("egilim:2,bilinmeyen:5,stok:0,5")
    assert w["egilim"] == 2 and w["stok"] == 0 and w["marj"] == 1
    for bad in ("egilim:-1", "egilim:x", "egilim:0,stok:0,marj:0,tahmin:0,sapma:0"):
        with pytest.raises(C.MarketingError):
            BL.parse_weights(bad)


def test_runout_and_change():
    assert BL.tukenme(100, 60) == 20.0 and BL.tukenme(0, 60) == 0.0 and BL.tukenme(None, 10) is None
    assert BL.tukenme(50, 0) is None                                    # sonsuz: satış yok
    assert BL.change(60, 120) == -0.5 and BL.change(24, 0) is None


def test_backlist_materials_are_core_kinds():
    for k in BL.MATERIALS:
        assert k in C.MATERIALS_KINDS and C.MATERIALS_KINDS[k][1] is None
    assert set(BL.MATERIAL_PROMPTS) == set(BL.MATERIALS)


# ------------------------------------------------------------------ gece hesabı


def test_set_is_m46_backlist_segment_without_trade_items(built):
    engine, meta, _ = built
    r = rows(engine)
    assert set(r) == {"B1", "B2", "B3"}                                 # 157 ve yeni kitap yok
    assert meta["kume"]["kaynak"] == "m46" and meta["kume"]["sayi"] == 3 and meta["kume"]["haric157"] == 1
    assert meta["sonTamAy"] == "2026-07" and meta["veriSonu"] == END.isoformat()


def test_components_from_sales_stock_forecast_and_targets(built):
    engine, _, _ = built
    b1 = rows(engine)["B1"]
    assert b1.adet_son12 == 60 and b1.adet_onceki12 == 120 and b1.degisim == -0.5   # Ağustos 2026 (yarım ay) dışarıda
    assert b1.ciro_son12 == 6000 and b1.marj == pytest.approx(0.6)
    assert b1.stok == 100 and b1.tukenme_ay == 20 and b1.tahmin12_p50 == 120
    assert b1.sapma_acik and b1.sapma_acik_tutar == 4200 and b1.m46_durum in ("sapma", "izle", "iyi")
    assert b1.hedef_kitle == "Çocuk" and b1.kume == "m46"
    b2, b3 = rows(engine)["B2"], rows(engine)["B3"]
    assert b2.degisim is None and b2.stok == 0 and b2.tukenme_ay == 0
    assert b3.stok == 50 and b3.tukenme_ay is None and b3.tahmin12_p50 is None


def test_past_years_come_from_logo_once_then_from_cache(built):
    engine, meta, src = built
    assert sorted(src.past_reads) == [2022, 2023, 2024]                 # 2025–2026 M46 önbelleğinden
    assert meta["yillar"] == {"2022": "logo", "2023": "logo", "2024": "logo", "2025": "m46", "2026": "m46"}
    src2 = FakeSources()
    BL.build(engine, T, src2, BL.settings(lambda k: ""), today=TODAY)
    assert src2.past_reads == []                                        # haftalık tazeleme dışında Logo'ya gidilmez
    BL.build(engine, T, src2, BL.settings(lambda k: ""), refresh_past=True, today=TODAY)
    assert sorted(src2.past_reads) == [2022, 2023, 2024]


def test_missing_trend_year_fails_and_keeps_old_snapshot(engine, monkeypatch):
    seed_budget(engine)
    monkeypatch.setattr(bsrc, "read_forecast", lambda: {})
    with pytest.raises(BL.SourceError):
        BL.build(engine, T, FakeSources(fail_past=True), BL.settings(lambda k: ""), today=TODAY)   # 2024 eğilim için şart
    assert rows(engine) == {}


def test_series_is_36_full_months(built):
    engine, _, _ = built
    with engine.connect() as c:
        s = {r.yil_ay: r.net_adet for r in c.execute(sa.select(BL.SERIES).where(BL.SERIES.c.stok_kodu == "B1")).all()}
    assert min(s) == "2023-08" and max(s) == "2026-07" and len(s) == 36 and "2026-08" not in s
    d = BL.detail(engine, T, "B1", BL.settings(lambda k: ""), BL.DEFAULT_WEIGHTS, today=TODAY)
    assert len(d["seri"]) == 36 and d["seri"][-1] == {"ay": "2026-07", "adet": 5.0, "ciro": 500.0}


def test_campaign_effect_before_during_after(built):
    engine, meta, _ = built
    e = BL.effects(engine, T)
    k = e["items"][0]
    u = k["urunler"][0]
    assert (u["once3"], u["kampanya"], u["sonra2"], u["kapsam"]) == (15.0, 5.0, 10.0, "tam")
    assert u["backlist"] and k["aylikDegisim"] == pytest.approx(0.0)
    assert "Nedensellik" in e["not"] and meta["kampanya"] == 1


def test_crm_matches_special_day_and_new_author_book(built):
    engine, meta, _ = built
    assert meta["eslesme"] == {"ozel-gun": 2, "yazar-yeni": 1}          # N1 kümede değil, alınmaz
    ag = BL.agenda(engine, T, 8, today=TODAY)
    g = ag["gunler"][0]
    assert g["ad"] == "Öğretmenler Günü" and g["baslangic"] == "2026-11-24" and g["kalanGun"] == 35
    assert {b["stokKodu"] for b in g["kitaplar"]} == {"B1", "B3"} and g["stokta"] == 2 and g["aktivasyonsuz"] == 2
    assert next(b for b in g["kitaplar"] if b["stokKodu"] == "B1")["gecenYilAyAdet"] == 5.0   # Kasım 2025
    assert ag["yazarlar"][0]["stokKodu"] == "Y1" and ag["yazarlar"][0]["kitaplar"][0]["stokKodu"] == "B2"


def test_fallback_set_from_crm_first_publication(engine, monkeypatch):
    seed_budget(engine, plan=False)
    monkeypatch.setattr(bsrc, "read_forecast", lambda: {})
    meta = BL.build(engine, T, FakeSources(), BL.settings(lambda k: ""), today=TODAY)
    assert set(rows(engine)) == {"B1", "B2", "B3"}                      # N1 genç, X9 tarihsiz, 157 hariç
    assert meta["kume"]["kaynak"] == "crm" and meta["kume"]["ilkYayinYok"] == 1
    assert rows(engine)["B1"].m46_durum is None and any("onaylı bütçe planı yok" in n for n in meta["notlar"])


# ------------------------------------------------------------------ liste


def test_list_has_no_cap_filters_and_priority_order(built):
    engine, _, _ = built
    out = BL.list_rows(engine, T, weights=BL.DEFAULT_WEIGHTS, today=TODAY)
    assert out["total"] == out["hepsi"] == 3 and out["items"][0]["stokKodu"] == "B1"   # açık sapma üstte
    assert out["kpi"] == {"sapmaAcik": 1, "stokta": 2, "yakinGun": 2, "planli": 0}
    assert {x["stokKodu"] for x in BL.list_rows(engine, T, weights=BL.DEFAULT_WEIGHTS, stokta=True, today=TODAY)["items"]} == {"B1", "B3"}
    assert [x["stokKodu"] for x in BL.list_rows(engine, T, weights=BL.DEFAULT_WEIGHTS, m46="acik", today=TODAY)["items"]] == ["B1"]
    assert [x["stokKodu"] for x in BL.list_rows(engine, T, weights=BL.DEFAULT_WEIGHTS, ozel_gun="g1", today=TODAY)["items"]] == ["B1", "B3"]
    assert BL.list_rows(engine, T, weights=BL.DEFAULT_WEIGHTS, q="yükselen", today=TODAY)["total"] == 1
    small = BL.list_rows(engine, T, weights=BL.DEFAULT_WEIGHTS, page_size=2, page=1, today=TODAY)
    assert small["total"] == 3 and len(small["items"]) == 1


def test_weights_change_the_order_and_components_stay_visible(built):
    engine, _, _ = built
    by_stock = BL.list_rows(engine, T, weights=BL.parse_weights("egilim:0,stok:1,marj:0,tahmin:0,sapma:0"), sirala="endeks",
                            today=TODAY)["items"]
    assert by_stock[0]["stokKodu"] == "B3"                              # satış yok + stok var = en uzun tükenme
    by_fc = BL.list_rows(engine, T, weights=BL.parse_weights("egilim:0,stok:0,marj:0,tahmin:1,sapma:0"), sirala="endeks",
                         today=TODAY)["items"]
    assert by_fc[0]["stokKodu"] == "B1"
    x = by_fc[0]
    assert set(x["bilesen"]) == set(BL.KEYS) and x["bilesen"]["egilim"]["ham"] == 0.5 and x["satisYok"] is False


def test_money_is_hidden_without_budget_right(built):
    engine, _, _ = built
    d = BL.detail(engine, T, "B1", BL.settings(lambda k: ""), BL.DEFAULT_WEIGHTS, today=TODAY)
    h = BLA.hide_money(d)
    assert h["ciroSon12"] is None and h["marj"] is None and h["m46"]["hedefCiro"] is None and h["seri"][0]["ciro"] is None
    assert h["bilesen"]["marj"]["yuzdelik"] == d["bilesen"]["marj"]["yuzdelik"] and h["adetSon12"] == 60
    assert h["kampanyalar"][0]["gerceklesenCiro"] is None


def test_card_actions_are_rules_with_reasons(built):
    engine, _, _ = built
    d = BL.detail(engine, T, "B1", BL.settings(lambda k: ""), BL.DEFAULT_WEIGHTS, today=TODAY)
    names = [a["eylem"] for a in d["eylemler"]]
    assert names[0] == "Öncelikli aktivasyon" and "Özel gün kampanyası: Öğretmenler Günü" in names
    assert "Okul / kütüphane toplu alım teklifi" in names and "Dijital format adayı" in names
    b2 = BL.detail(engine, T, "B2", BL.settings(lambda k: ""), BL.DEFAULT_WEIGHTS, today=TODAY)
    assert b2["eylemler"][0]["eylem"] == "Fırsat değil: stok yok"
    with pytest.raises(C.MarketingError):
        BL.detail(engine, T, "N1", BL.settings(lambda k: ""), BL.DEFAULT_WEIGHTS, today=TODAY)


# ------------------------------------------------------------------ konu eşleşmesi


def test_topic_candidates_and_model_decision(built):
    engine, _, _ = built
    llm = FakeLlm("İlgili", 0.9)
    mkt = P.settings(lambda k: "")
    out = BL.match_topics(engine, T, FakeSources(), llm, BL.settings(lambda k: ""), mkt, today=TODAY)
    assert out["aday"] == 0                                             # B3 zaten CRM'de Öğretmenler Günü'ne bağlı
    with engine.begin() as c:
        c.execute(BL.MATCHES.delete().where(BL.MATCHES.c.tur == "ozel-gun"))
    out = BL.match_topics(engine, T, FakeSources(), llm, BL.settings(lambda k: ""), mkt, today=TODAY)
    assert out == {"aday": 1, "ilgili": 1, "belirsiz": 0, "ilgisiz": 0} and "Öğretmenler Günü" in llm.asked[0]
    again = BL.match_topics(engine, T, FakeSources(), llm, BL.settings(lambda k: ""), mkt, today=TODAY)
    assert again["aday"] == 0                                           # sorulan bir daha sorulmaz
    konu = BL.agenda(engine, T, 8, today=TODAY)["konular"][0]
    assert konu["onay"] == "bekliyor" and konu["skor"] == 0.9
    m = BL.decide_match(engine, T, "ayse", konu["id"], "kabul")
    assert m["onay"] == "kabul" and m["onaylayan"] == "ayse"
    with pytest.raises(C.MarketingError):
        BL.decide_match(engine, T, "ayse", konu["id"], "belki")


def test_unsure_model_goes_to_review_and_crm_links_are_not_decided_here(built):
    engine, _, _ = built
    with engine.begin() as c:
        c.execute(BL.MATCHES.delete().where(BL.MATCHES.c.tur == "ozel-gun", BL.MATCHES.c.stok_kodu == "B3"))
    out = BL.match_topics(engine, T, FakeSources(), FakeLlm("İlgisiz", 0.55), BL.settings(lambda k: ""), P.settings(lambda k: ""),
                          today=TODAY)
    assert out["belirsiz"] == 1                                         # eşik altı «İlgisiz» → onaya düşer
    crm_row = next(m for m in BL.agenda(engine, T, 8, today=TODAY)["gunler"][0]["kitaplar"])
    with engine.connect() as c:
        mid = c.execute(sa.select(BL.MATCHES.c.id).where(BL.MATCHES.c.tur == "ozel-gun")).scalar()
    with pytest.raises(C.MarketingError) as e:
        BL.decide_match(engine, T, "ayse", mid, "red")
    assert e.value.status == 409 and crm_row


def test_no_model_skips_topics(built):
    engine, _, _ = built
    assert "atlandi" in BL.match_topics(engine, T, FakeSources(), None, BL.settings(lambda k: ""), P.settings(lambda k: ""))


# ------------------------------------------------------------------ aktivasyon planı


class FakeCrm:
    def spend(self, since, fresh=False):
        return [{"id": "s1", "tip": 4, "tipAdi": None, "tutar": 750.0, "stokKodu": "B1"},
                {"id": "s2", "tip": 6, "tipAdi": None, "tutar": 250.0, "stokKodu": "B1"}]

    def book(self, stok, fresh=False):
        return {"ad": "Uyuyan Kitap" if stok == "B1" else "Satmayan Kitap", "yazar": "Yazar A", "yayinevi": "Timaş Yayınları",
                "kitaplik": "Roman", "hedefKitle": "Çocuk", "turler": "Roman",
                "metinler": {"new_ozet": "Bir çocuğun okul yolunda başlayan büyük macerası."}}

    def email_of(self, user):
        return None


def _mkt(**over):
    s = P.settings(lambda k: "")
    s.update(over)
    return s


def test_activation_plan_is_multi_book_with_anchor_budget_and_tasks(built):
    engine, _, _ = built
    pid = BL.create_activation(engine, T, "ayse", FakeCrm(), _mkt(rate=0.1), BL.settings(lambda k: ""),
                               {"kitaplar": [{"stokKodu": "B1"}, {"stokKodu": "B3", "rol": "set"}]}, today=TODAY)
    plan = C.plan_full(engine, T, pid)
    assert plan["kind"] == "backlist" and plan["stokKodu"] is None and plan["yayinTarihi"] == "2026-11-24"
    assert "Öğretmenler Günü" in plan["baslik"] and plan["hedef"]["kitap"] == 2 and plan["hedef"]["sapmaAcik"] == 1
    assert plan["butceCerceve"] == pytest.approx(1300.0) and plan["butceToplam"] == pytest.approx(1300.0)  # %10 × (12000 + 1000)
    assert {ln["kanal"] for ln in plan["lines"]} == {"sosyal-medya", "satis-kampanyasi"}
    assert any(t["materyalTur"] == "yeniden-kesfet" for t in plan["tasks"]) and any(t["kaynak"] == "ozel-gun" for t in plan["tasks"])
    bks = BK.of(engine, pid)
    assert [(b["stokKodu"], b["rol"]) for b in bks] == [("B1", "ana"), ("B3", "set")] and "Uyku endeksi" in bks[0]["gerekce"]
    assert BK.by_codes(engine, T, ["B1"])["B1"][0]["id"] == pid
    assert BL.list_rows(engine, T, weights=BL.DEFAULT_WEIGHTS, plan="yok", today=TODAY)["total"] == 1
    with pytest.raises(C.MarketingError):
        BL.create_activation(engine, T, "ayse", FakeCrm(), _mkt(), BL.settings(lambda k: ""), {"kitaplar": [{"stokKodu": "N1"}]})


def test_plan_books_follow_approval_revision_and_delete(built):
    engine, _, _ = built
    pid = BL.create_activation(engine, T, "ayse", FakeCrm(), _mkt(rate=0.1), BL.settings(lambda k: ""),
                               {"kitaplar": [{"stokKodu": "B1"}], "baslangic": "2026-12-01"}, today=TODAY)
    assert C.plan_full(engine, T, pid)["stokKodu"] == "B1"             # tek kitap: plan kitabıyla görünür
    C.submit(engine, T, "ayse", pid)
    with pytest.raises(C.MarketingError):
        BK.put(engine, T, "ayse", pid, [{"stokKodu": "B3"}])            # onaydaki planın kitabı değişmez
    C.decide(engine, T, "mudur", pid, True, None, level="pazarlama", threshold=None)
    new = C.revise(engine, T, "ayse", pid, "özel gün eklendi")["id"]
    assert [b["stokKodu"] for b in BK.of(engine, new)] == ["B1"]        # revizyon kitapları kopyalar
    BK.put(engine, T, "ayse", new, [{"stokKodu": "B1"}, {"stokKodu": "B3", "rol": "capraz"}])
    assert C.plan_full(engine, T, new)["stokKodu"] is None
    C.delete_plan(engine, T, new)
    with engine.connect() as c:
        left = c.execute(sa.select(BK.PLAN_BOOKS.c.stok_kodu).where(BK.PLAN_BOOKS.c.plan_id == new)).all()
    assert left == [] and [b["stokKodu"] for b in BK.of(engine, pid)] == ["B1"]


def test_book_list_validation():
    with pytest.raises(C.MarketingError):
        BK.clean([])
    with pytest.raises(C.MarketingError):
        BK.clean([{"stokKodu": "B1", "rol": "patron"}])
    assert [x["stok_kodu"] for x in BK.clean(["B1", {"stokKodu": "B1"}, {"stokKodu": "B2"}])] == ["B1", "B2"]


def test_draft_drops_numbers_and_quotes_not_in_sources(built):
    engine, _, _ = built
    pid = BL.create_activation(engine, T, "ayse", FakeCrm(), _mkt(), BL.settings(lambda k: ""),
                               {"kitaplar": [{"stokKodu": "B1"}]}, today=TODAY)
    plan = C.plan_full(engine, T, pid)
    bks = BK.of(engine, pid)
    rows_ = BL.rows_by_code(engine, T, ["B1"])
    llm = FakeLlm(text="Uyuyan Kitap şimdi okunmalı. «Bu cümle kitapta yok» dedi yazar. 2031 yılında da okunur. "
                       "24 Kasım için hazır.")
    metin, dog = BL.draft(llm, plan, bks, rows_, {"B1": FakeCrm().book("B1")}, [], "yeniden-kesfet", P.settings(lambda k: ""))
    assert "Uyuyan Kitap şimdi okunmalı." in metin and "24 Kasım" in metin
    assert dog["dusenSayisi"] == 2 and {d["neden"] for d in dog["dusen"]} == {"alinti-bulunamadi", "kaynaksiz-rakam"}
    with pytest.raises(C.MarketingError):
        BL.draft(llm, plan, bks, rows_, {}, [], "foy", P.settings(lambda k: ""))


def test_notifications_texts(built):
    engine, _, _ = built
    st = BL.settings(lambda k: "")
    text = BL.digest_month(engine, T, {**st, "digestMin": 0}, "https://x/timas/pazarlama/backlist")
    assert "Backlist'te 3 kitap" in text and "açık sapma uyarısı olan: 1" in text and "https://x" in text
    due = BL.remind_days(engine, T, {**st, "remindWeeks": 6}, today=TODAY)
    assert [d["ad"] for d in due] == ["Öğretmenler Günü"] and due[0]["aktivasyonsuz"] == 2
    assert BL.first_workday(date(2026, 11, 2)) and not BL.first_workday(date(2026, 11, 3))   # 1 Kasım 2026 pazar


# ------------------------------------------------------------------ yetki ve uçlar


def test_access_rules_for_backlist():
    page = frozenset({A.page("pazarlama-backlist")})
    assert A.rule_for("/api/v1/marketing/backlist") == page and A.rule_for("/api/v1/marketing/backlist/agenda") == page
    assert A.rule_for("/api/v1/marketing/backlist/run-due") == A.SYSTEM
    assert A.page("pazarlama-backlist") in A.rule_for("/api/v1/marketing/plans/MP-2026-0001")
    assert A.page("pazarlama-backlist") in A.rule_for("/api/v1/budget/targets")
    assert A.page("pazarlama-backlist") in A.rule_for("/api/v1/budget/deviations")
    f = A.features_for
    w = "ozellik:pazarlama.plan-yaz"
    assert f("POST", "/api/v1/marketing/backlist/plans") == [w]
    assert f("PUT", "/api/v1/marketing/backlist/plans/MP-2026-0001/books") == [w]
    assert f("POST", "/api/v1/marketing/backlist/plans/MP-2026-0001/materials") == [w]
    assert f("POST", "/api/v1/marketing/backlist/matches/abc/decide") == [w]
    assert f("PUT", "/api/v1/marketing/backlist/weights") == ["ozellik:pazarlama.backlist-ayar"]
    assert f("GET", "/api/v1/marketing/backlist/export.csv") == ["ozellik:veri.disa-aktar"]
    assert f("GET", "/api/v1/marketing/backlist") == [] and f("GET", "/api/v1/marketing/backlist/B1") == []
    assert {"sayfa:pazarlama-backlist", "ozellik:pazarlama.backlist-ayar"} <= A.all_keys()
    assert "ozellik:pazarlama.backlist-ayar" in A.explicit_keys()      # ekip ayarı rolde tek tek verilir


def _app(monkeypatch, store, settings):
    from fastapi.testclient import TestClient

    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm as Llm

    users = {"timas_session=a": "ayse", "timas_session=z": "zekiai"}
    monkeypatch.setattr(board_mod, "_fetch_user", lambda cookie: users.get(cookie))
    monkeypatch.setattr(board_mod, "_fetch_session", lambda cookie: {"username": users.get(cookie), "displayName": "x"})
    monkeypatch.setattr(admin_mod, "admins", lambda: ["zekiai"])
    monkeypatch.delenv("SEMANTIC_CALLER_TOKEN", raising=False)
    monkeypatch.delenv("SEMANTIC_ADMIN_TOKEN", raising=False)
    A._ready.clear()
    A.invalidate()
    _reset(store.engine)
    app = create_app(Runtime(settings, store=store, llm=Llm([""])))
    return app, TestClient(app)


def test_endpoints_list_card_plan_and_scheduler_gate(monkeypatch, store, settings):
    app, client = _app(monkeypatch, store, settings)
    engine = store.engine
    B.ensure(engine)
    BL.ensure(engine)
    seed_budget(engine)
    monkeypatch.setattr(bsrc, "read_forecast", lambda: {})
    monkeypatch.setattr(C, "today", lambda: TODAY)
    BL.build(engine, T, FakeSources(), BL.settings(lambda k: ""), today=TODAY)
    crm = app.state.marketing["crm"]
    fake = FakeCrm()
    for name in ("spend", "book", "email_of"):
        monkeypatch.setattr(crm, name, getattr(fake, name))
    a = {"cookie": "timas_session=a"}

    meta = client.get("/api/v1/marketing/backlist/meta", headers=a)
    assert meta.status_code == 200, meta.text
    assert meta.json()["me"]["canWrite"] and [c["key"] for c in meta.json()["components"]] == BL.KEYS
    lst = client.get("/api/v1/marketing/backlist?agirlik=egilim:1,stok:1,marj:1,tahmin:1,sapma:1", headers=a).json()
    assert lst["total"] == lst["hepsi"] == 3 and lst["items"][0]["stokKodu"] == "B1"
    assert client.get("/api/v1/marketing/backlist?agirlik=egilim:-1", headers=a).status_code == 400
    card = client.get("/api/v1/marketing/backlist/B1", headers=a)
    assert card.status_code == 200 and len(card.json()["seri"]) == 36
    assert client.get("/api/v1/marketing/backlist/agenda", headers=a).json()["gunler"][0]["ad"] == "Öğretmenler Günü"
    assert client.get("/api/v1/marketing/backlist/effects", headers=a).json()["total"] == 1
    assert client.get("/api/v1/marketing/backlist/export.csv", headers=a).status_code == 200

    made = client.post("/api/v1/marketing/backlist/plans", json={"kitaplar": [{"stokKodu": "B1"}, {"stokKodu": "B3"}]}, headers=a)
    assert made.status_code == 201, made.text
    pid = made.json()["id"]
    assert client.get(f"/api/v1/marketing/plans/{pid}", headers=a).json()["kind"] == "backlist"   # çekirdeğin plan ekranı
    assert client.post(f"/api/v1/marketing/plans/{pid}/suggest", json={}, headers=a).status_code == 409
    assert client.post(f"/api/v1/marketing/plans/{pid}/materials", json={"tur": "toplu-alim-mektubu"}, headers=a).status_code == 409
    mat = client.post(f"/api/v1/marketing/backlist/plans/{pid}/materials", json={"tur": "e-bulten-bolum", "metin": "Elle yazıldı."},
                      headers=a)
    assert mat.status_code == 201 and mat.json()["material"]["tur"] == "e-bulten-bolum"
    assert client.get("/api/v1/marketing/backlist/activations", headers=a).json()["items"][0]["kitaplar"][1]["stokKodu"] == "B3"
    assert client.put("/api/v1/marketing/backlist/weights", json={"agirlik": "egilim:2"}, headers=a).status_code == 403
    z = {"cookie": "timas_session=z"}
    assert client.put("/api/v1/marketing/backlist/weights", json={"agirlik": "egilim:2"}, headers=z).json()["teamWeights"]["egilim"] == 2
    assert client.post("/api/v1/marketing/backlist/run-due", headers=a).status_code == 403    # kişi zamanlayıcıyı tetikleyemez


def test_tables_are_created(engine):
    names = set(sa.inspect(engine).get_table_names())
    assert {"semantic_mkt_backlist", "semantic_mkt_backlist_series", "semantic_mkt_backlist_sales", "semantic_mkt_campaign_effect",
            "semantic_mkt_matches", "semantic_mkt_plan_books"} <= names
    assert BK.PLAN_BOOKS in C.PLAN_TABLES
