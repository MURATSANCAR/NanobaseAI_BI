"""Zeki AI öneri 4–8: fark ayrıştırma («Neden?»), «ne değişti», beklenen aralık + eşik önerisi, olasılıklı nakit bandı,
destek taslağında sipariş/kargo/fatura olguları.

Veriler yapaydır; hesap kurallarını ve «rakamı model üretmez» denetimini sınar. Gerçek Logo ile karşılaştırma test
sunucusunda (`scripts/acceptance/zeki-fark/`).
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from semantic_bridge import access as ACC
from semantic_bridge import alerts as A
from semantic_bridge import board as BD
from semantic_bridge import finance as F
from semantic_bridge import forecast_client as FC
from semantic_bridge import reports as R
from semantic_bridge import result_diff as RD
from semantic_bridge import support as S
from semantic_bridge import variance as V
from semantic_layer.store.catalog_store import open_store

T, D = "t1", "logo"

NET = "SUM(CASE WHEN STLINE.TRCODE IN (7, 8, 9) THEN STLINE.LINENET ELSE -STLINE.LINENET END)"


def _sq(**kw):
    slots = [
        {"term": "net ciro", "semanticType": "METRIC",
         "mapping": {"entity": "STLINE", "formula": NET, "extra": {"conditions": ["STLINE.INVOICEREF NOT IN (0)"]}}},
        {"term": "iptal olmayan", "semanticType": "DEFAULT_FILTER",
         "mapping": {"entity": "STLINE", "column": "CANCELLED", "operator": "IN", "values": ["0"]}},
    ]
    q = {"slots": slots + kw.pop("extra_slots", []), "temporal": [{"start": "2026-01-01", "end": "2026-10-01"}]}
    q.update(kw)
    return q


# ================================================================================ ölçü katalogdan


def test_measure_comes_from_catalog_formula_conditions_and_default_scope():
    m, why = V.measure_of(_sq())
    assert why is None and m.formul == NET and m.birim == "₺"
    assert m.kosullar == ["STLINE.INVOICEREF NOT IN (0)", "STLINE.CANCELLED IN (0)"]
    assert V.hint(_sq()) == {"ok": True, "olcu": "net ciro", "birim": "₺", "bas": "2026-01-01", "bit": "2026-10-01"}


def test_value_filter_on_customer_card_is_carried_and_joins_the_card():
    kanal = {"term": "toptan", "semanticType": "DIMENSION_VALUE",
             "mapping": {"entity": "CLCARD", "column": "SPECODE2", "operator": "IN", "values": ["TOPTAN", "O'NEIL"]}}
    m, _ = V.measure_of(_sq(extra_slots=[kanal]))
    assert "CLCARD.SPECODE2 IN (N'TOPTAN', N'O''NEIL')" in m.kosullar and m.tablolar == {"CLCARD"}
    sql = V.dim_sql(m, "kitap", date(2026, 1, 1), date(2026, 10, 1))
    assert "LEFT JOIN CLCARD AS CLCARD" in sql and "LEFT JOIN ITEMS AS ITEMS" in sql
    assert "STLINE.DATE_ >= '20260101'" in sql and "STLINE.DATE_ < '20261001'" in sql
    assert "LG_" not in sql, "yıl kopyaları köprünün fiziksel yeniden yazımında çözülür"


@pytest.mark.parametrize("formula,expect", [
    ("SUM(STLINE.LINENET) / NULLIF(SUM(STLINE.AMOUNT), 0)", "toplanabilir"),
    ("COUNT(DISTINCT STLINE.CLIENTREF)", "toplanabilir"),
    ("AVG(STLINE.PRICE)", "toplanabilir"),
])
def test_non_additive_measures_are_refused_with_a_reason(formula, expect):
    q = _sq()
    q["slots"][0]["mapping"]["formula"] = formula
    m, why = V.measure_of(q)
    assert m is None and expect in why


def test_other_tables_missing_period_and_two_measures_are_refused():
    q = _sq(extra_slots=[{"term": "sipariş", "semanticType": "DIMENSION_VALUE",
                          "mapping": {"entity": "ORFLINE", "column": "STATUS", "operator": "=", "values": ["1"]}}])
    assert V.measure_of(q)[0] is None
    q = _sq(temporal=[])
    assert V.hint(q)["ok"] is False and "dönem" in V.hint(q)["neden"]
    q = _sq(extra_slots=[dict(_sq()["slots"][0], term="iade")])
    assert "birden çok ölçü" in V.measure_of(q)[1]
    q = _sq()
    q["slots"][0]["mapping"]["formula"] = "SUM(STLINE.LINENET); DROP TABLE X"
    assert V.measure_of(q)[0] is None


# ================================================================================ ayrıştırma


def _runner(calls):
    cur = {"kanal": [{"anahtar": "Toptan", "ad": "Toptan", "deger": 100, "son": "2026-09-17"},
                     {"anahtar": "Perakende", "ad": "Perakende", "deger": 50, "son": "2026-09-10"}]}
    prev = {"kanal": [{"anahtar": "Toptan", "ad": "Toptan", "deger": 60},
                      {"anahtar": "Perakende", "ad": "Perakende", "deger": 70},
                      {"anahtar": "Diğer", "ad": "Diğer", "deger": 10}]}

    def run(sql, period):
        calls.append((sql, period))
        return cur["kanal"] if period[0].year == 2026 else prev["kanal"]
    return run


def test_decomposition_clips_the_comparison_to_the_data_end_and_ranks_contributions():
    calls = []
    res = V.for_question(_runner(calls), _sq(), boyutlar=["kanal"])
    assert res["kirpildi"] is True and res["veriSonu"] == "2026-09-17"
    assert res["donem"]["bit"] == "2026-09-18"
    assert res["karsi"]["bas"] == "2025-01-01" and res["karsi"]["bit"] == "2025-09-18"
    assert calls[1][1] == (date(2025, 1, 1), date(2025, 9, 18)), "karşı dönem kendi tarihleriyle sorulur"
    assert res["toplam"] == {"simdi": 150.0, "onceki": 140.0, "fark": 10.0, "oran": round(10 / 140, 4)}
    items = res["boyutlar"][0]["kalemler"]
    assert [(i["anahtar"], i["fark"]) for i in items] == [("Toptan", 40.0), ("Perakende", -20.0), ("Diğer", -10.0)]
    assert items[0]["pay"] == 4.0 and items[0]["yon"] == "artis" and items[2]["kayip"] is True
    assert [s["sql"] for s in res["kaynak"]["sql"]] == [c[0] for c in calls], "çalıştırılan her SQL cevapta"


def test_previous_period_window_for_whole_months_and_days():
    assert V.compare_window(date(2026, 7, 1), date(2026, 10, 1), "onceki-donem") == (date(2026, 4, 1), date(2026, 7, 1))
    assert V.compare_window(date(2026, 9, 10), date(2026, 9, 20), "onceki-donem") == (date(2026, 8, 31), date(2026, 9, 10))
    assert V.compare_window(date(2024, 2, 29), date(2024, 3, 1), "gecen-yil") == (date(2023, 2, 28), date(2023, 3, 1))
    with pytest.raises(V.VarianceError):
        V.compare_window(date(2026, 1, 1), date(2026, 2, 1), "yarin")


def test_explanation_numbers_must_come_from_facts():
    res = V.for_question(_runner([]), _sq(), boyutlar=["kanal"])
    ok = V.explain(res, llm=lambda messages: "Artışı en çok Toptan kanalı sürükledi. Perakende geriledi.")
    assert ok["kaynak"] == "zeki"
    bad = V.explain(res, llm=lambda messages: "Toptan kanalında 999 adet kampanya etkisi var. Başka bir şey yok.")
    assert bad["kaynak"] == "kural" and bad["neden"].startswith("olgu-disi-sayi")
    assert "40 ₺" in bad["metin"] and "Toptan" in bad["metin"]
    assert V.explain(res)["neden"] == "model-yok"


# ================================================================================ beklenen aralık ve eşik önerisi


def test_seasonal_range_uses_year_over_year_ratio_median_and_mad():
    lags = {k: (110.0 if k % 2 else 90.0) for k in range(1, 13)}
    lags.update({k: 100.0 for k in range(13, 25)})
    rng = V.expected_range(150.0, lags, k=2.0)
    assert rng["yontem"] == "mevsimsel" and rng["nokta"] == 12
    assert rng["merkez"] == pytest.approx(90.0 * 1.0)          # taban = geçen yılın aynı penceresi (gecikme 12 = 90)
    assert rng["alt"] < rng["merkez"] < rng["ust"] and rng["disinda"] is True and rng["yon"] == "ust"


def test_range_falls_back_to_median_and_refuses_short_history():
    rng = V.expected_range(100.0, {k: 100.0 + k for k in range(1, 13)})
    assert rng["yontem"] == "medyan" and rng["disinda"] is False
    assert V.expected_range(100.0, {k: 1.0 for k in range(1, 6)}) is None, "kısa geçmişte aralık uydurulmaz"


def test_window_lags_sum_the_same_window_back_in_time():
    daily = {date(2024, 1, 1) + timedelta(days=i): 1.0 for i in range(0, 1000)}
    cur, lags = V.window_lags(daily, date(2026, 3, 1), date(2026, 4, 1))
    assert cur == 31 and lags[1] == 28 and lags[12] == 31 and lags[24] == 31
    assert 25 not in lags


def test_threshold_suggestion_follows_the_condition():
    rng = {"ok": True, "alt": 80.0, "ust": 120.0, "merkez": 100.0, "yontem": "medyan", "nokta": 12}
    assert V.suggest_threshold(rng, "gt")["esik"] == 120.0
    assert V.suggest_threshold(rng, "lte")["esik"] == 80.0
    assert V.suggest_threshold(rng, "gt")["etiket"] == "Kurala göre öneri"
    assert V.suggest_threshold({"ok": False}, "gt") is None


def test_measure_range_reads_history_once_and_clips_to_data_end():
    seen = []

    def run(sql, period):
        seen.append(period)
        start = period[0]
        out = []
        d = start
        while d < date(2026, 9, 18):
            out.append({"gun": d.isoformat(), "deger": 10.0})
            d += timedelta(days=1)
        return out

    rng = V.measure_range(run, _sq(temporal=[{"start": "2026-09-01", "end": "2026-10-01"}]))
    assert len(seen) == 1 and seen[0][0] == date(2024, 9, 1)
    assert rng["ok"] is True and rng["kirpildi"] is True and rng["deger"] == 170.0
    assert "gün gün" in rng["kaynak"]["sql"][0]["sql"]


# ================================================================================ uyarılar


@pytest.fixture
def aengine():
    e = open_store("sqlite://").engine
    A._ready.discard(id(e))
    A.ensure(e)
    return e


def _answer(v):
    return lambda rule: {"records": [{"deger": v}], "sql": "SELECT 1"}


def test_anomaly_rule_uses_expected_range_and_notification_carries_reason(aengine):
    r = A.create_rule(aengine, T, D, {"title": "Aylık ciro", "question": "bu ay net ciro", "condition": "olagandisi",
                                      "threshold": "", "recipients": ["cfo@example.com"]})
    assert r["threshold"] == 2
    calls = {"expect": 0, "reason": 0}
    got = []

    def expect(rule):
        calls["expect"] += 1
        return {"ok": True, "alt": 80.0, "ust": 120.0, "merkez": 100.0, "yontem": "mevsimsel", "nokta": 12}

    def reason(rule):
        calls["reason"] += 1
        return {"ok": True, "olcu": {"ad": "net ciro", "birim": "₺"}, "donem": {"etiket": "01.09.2026–17.09.2026"},
                "karsi": {"ad": "geçen yılın aynı dönemi", "etiket": "01.09.2025–17.09.2025"},
                "anlatim": {"metin": "Artışı Toptan sürükledi.", "kaynak": "zeki"},
                "boyutlar": [{"ad": "Kanal", "kalemler": [{"ad": "Toptan", "fark": 40.0}]}]}

    def notify(rule, value):
        got.append(A.render(rule, value)[1])
        return "sent"

    t0 = datetime(2026, 9, 11, 9, tzinfo=timezone.utc)
    A.check(aengine, T, D, _answer(150), notify, now=t0, expect=expect, reason=reason)
    A.check(aengine, T, D, _answer(150), notify, now=t0 + timedelta(minutes=15), expect=expect, reason=reason)
    assert calls == {"expect": 1, "reason": 1}, "aralık günde bir hesaplanır; neden yalnız bildirimde"
    rule = A.get_rule(aengine, T, D, r["id"])
    assert rule["state"] == "triggered" and rule["expected"]["alt"] == 80.0
    text = got[0]
    assert "beklenenin dışına çıktı" in text and "Beklenen aralık: 80 – 120" in text
    assert "Neden (Zeki AI yorumu):" in text and "Toptan +40 ₺" in text
    A.check(aengine, T, D, _answer(100), notify, now=t0 + timedelta(minutes=30), expect=expect, reason=reason)
    assert A.get_rule(aengine, T, D, r["id"])["state"] == "ok"


def test_anomaly_rule_without_range_is_an_error_not_a_guess(aengine):
    r = A.create_rule(aengine, T, D, {"title": "X", "question": "q", "condition": "olagandisi", "threshold": 2,
                                      "recipients": []})
    A.check(aengine, T, D, _answer(1), lambda rule, v: "sent",
            expect=lambda rule: {"ok": False, "neden": "Beklenen aralık için en az 12 geçmiş pencere gerekir."})
    rule = A.get_rule(aengine, T, D, r["id"])
    assert rule["state"] == "error" and "12 geçmiş" in rule["last_error"]
    with pytest.raises(A.AlertError):
        A.create_rule(aengine, T, D, {"title": "X", "question": "q", "condition": "olagandisi", "threshold": 9, "recipients": []})


def test_threshold_rule_mentions_out_of_range_value(aengine):
    rule = {"title": "İade", "condition": "gt", "threshold": 100, "question": "iade",
            "_aralik": {"ok": True, "alt": 10.0, "ust": 90.0, "yontem": "medyan"}, "_disinda": True}
    text = A.render(rule, 150.0)[1]
    assert "Koşul: değer > 100" in text and "(değer beklenenin dışında)" in text and "son 12 ayın" in text


# ================================================================================ «ne değişti»


PREV = {"columns": [{"name": "kanal"}, {"name": "net"}], "records": [{"kanal": "A", "net": 100}, {"kanal": "B", "net": 50}]}
CUR = {"columns": [{"name": "kanal"}, {"name": "net"}], "records": [{"kanal": "A", "net": 130}, {"kanal": "C", "net": 20}]}


def test_result_diff_matches_rows_by_key_and_counts_new_and_gone():
    d = RD.diff(PREV, CUR)
    assert d["anahtar"] == ["kanal"] and d["olcu"] == "net" and d["degisti"] is True
    assert d["toplamlar"][0] == {"kolon": "net", "onceki": 150.0, "simdi": 150.0, "fark": 0.0, "oran": 0.0}
    assert [(c["satir"], c["fark"]) for c in d["enBuyuk"]] == [("B", -50.0), ("A", 30.0), ("C", 20.0)]
    assert d["yeni"] == ["C"] and d["dusen"] == ["B"]
    assert RD.diff(None, CUR) == {"ilk": True, "satir": 2}
    assert RD.bullets(RD.diff(CUR, CUR)) == ["Önceki sonuca göre değişiklik yok."]


def test_kpi_single_row_compares_the_number():
    d = RD.diff({"columns": ["net"], "records": [{"net": 100}]}, {"columns": ["net"], "records": [{"net": 125}]})
    assert d["toplamlar"][0]["oran"] == 0.25 and d["anahtar"] == []
    assert "net toplamı 100 → 125 (%25 artış)." in RD.bullets(d)


def test_change_note_uses_model_only_when_numbers_check():
    d = RD.diff(PREV, CUR)
    good = RD.explain(d, "Kanal cirosu", llm=lambda m: "B kanalı listeden düştü. C kanalı yeni geldi.")
    assert good["kaynak"] == "zeki" and good["maddeler"] == ["B kanalı listeden düştü.", "C kanalı yeni geldi."]
    bad = RD.explain(d, "Kanal cirosu", llm=lambda m: "Toplam 777 arttı. Başka yok.")
    assert bad["kaynak"] == "kural" and bad["maddeler"] == RD.bullets(d)
    first = RD.explain(RD.diff(None, CUR), "x", llm=lambda m: 1 / 0)
    assert first["kaynak"] == "kural", "ilk koşuda model çağrılmaz"


@pytest.fixture
def bengine():
    e = open_store("sqlite://").engine
    BD._ready.discard(id(e))
    BD.ensure(e)
    return e


def test_board_card_keeps_the_difference_and_explains_once(bengine):
    BD.save_cards(bengine, T, D, "ali", [{"id": "c1", "sql": "SELECT 1", "title": "Kanal cirosu", "question": "kanal cirosu"}])
    BD._store_result(bengine, "c1", PREV, auto=False)
    first = BD.list_cards(bengine, T, D, "ali")[0]["result"]["fark"]
    assert first["ilk"] is True
    BD._store_result(bengine, "c1", CUR, auto=False)
    fark = BD.list_cards(bengine, T, D, "ali")[0]["result"]["fark"]
    assert fark["degisti"] is True and fark["kaynak"] == "kural" and fark["maddeler"]
    BD._store_result(bengine, "c1", CUR, auto=True)
    assert BD.list_cards(bengine, T, D, "ali")[0]["result"]["fark"]["degisenSatir"] == 3, "aynı sonuç son değişimi ezmez"
    n = []

    def explain(d, title):
        n.append(title)
        return {"maddeler": ["B düştü."], "kaynak": "zeki", "neden": None}

    assert BD.change_note(bengine, T, D, "ali", "c1", explain)["kaynak"] == "zeki"
    assert BD.change_note(bengine, T, D, "ali", "c1", explain)["maddeler"] == ["B düştü."]
    assert n == ["Kanal cirosu"], "anlatım bir kez üretilir, saklanır"
    assert BD.change_note(bengine, T, D, "veli", "c1", explain) is None, "başkasının kartı okunmaz"


def test_report_mail_carries_what_changed(tmp_path, monkeypatch):
    monkeypatch.setattr(R, "REPORT_DIR", tmp_path)
    assert R.change_of("r1", "Kanal", CUR["columns"], CUR["records"], None)["ilk"] is True
    R.save_snapshot("r1", PREV["columns"], PREV["records"], datetime(2026, 9, 1, tzinfo=timezone.utc))
    ch = R.change_of("r1", "Kanal", CUR["columns"], CUR["records"], None)
    assert ch["degisti"] is True and ch["kaynak"] == "kural"
    path = tmp_path / "r.xlsx"
    path.write_bytes(b"x")
    rep = {"title": "Kanal", "question": "kanal cirosu", "when": "Her gün", "recipients": []}
    msg = R.compose_mail(rep, path, [{"name": "kanal"}, {"name": "net", "type": "float"}], CUR["records"],
                         datetime(2026, 9, 2, tzinfo=timezone.utc), change=ch)
    text = msg.get_body(("plain",)).get_content()
    html = msg.get_body(("html",)).get_content()
    assert "Ne değişti · önceki rapora göre:" in text and "Listeden düşen 1 satır: B." in text
    assert "Ne değişti" in html
    zeki = dict(ch, kaynak="zeki")
    assert "Zeki AI yorumu" in R.compose_mail(rep, path, [], [], datetime(2026, 9, 2, tzinfo=timezone.utc), change=zeki).get_body(("plain",)).get_content()


# ================================================================================ olasılıklı nakit bandı


def _cash():
    return F.build_cash({"asof": date(2026, 8, 17), "position": {"100": 0, "102": 1_000},
                         "receivables": [(date(2026, 8, 20), 4_000, 3)],
                         "tax": [(date(2026, 8, 20), 300.0, "KDV")]})


def _daily(weeks=60):
    return {date(2026, 8, 17) - timedelta(days=7 * k): (1_000.0, 800.0) for k in range(1, weeks + 1)}


def _fc(series, h):
    assert set(series) == {"tahsilat", "odeme"} and len(series["tahsilat"]) == 60 and h == 13
    return {"tahsilat": {"p10": [500.0] * h, "p50": [1_000.0] * h, "p90": [1_500.0] * h},
            "odeme": {"p10": [600.0] * h, "p50": [800.0] * h, "p90": [1_000.0] * h}}


def test_cash_band_keeps_scheduled_items_and_draws_the_worst_ten_percent_line():
    band = F.build_band(_cash(), _daily(), _fc)
    assert band["var"] is True and band["etiket"] == "tahmin" and band["gecmisHafta"] == 60
    w0, w1 = band["haftalar"][0], band["haftalar"][1]
    assert w0["kesin"] == -300.0, "vergi vadesi kuraldan (eksi)"
    assert w0["kapanis"] == {"kotu": 200.0, "orta": 900.0, "iyi": 1_600.0}
    assert w1["kapanis"]["kotu"] == -300.0
    assert band["enKotuAcik"]["hafta"] == 2
    assert band["yerineGecen"] == ["alacak"] and "vergi" in band["kesinKalemler"]


def test_cash_band_is_not_invented_without_history_or_quantiles():
    assert F.build_band(_cash(), _daily(10), _fc)["var"] is False

    def down(series, h):
        raise RuntimeError("servis yok")
    out = F.build_band(_cash(), _daily(), down)
    assert out["var"] is False and "Tahmin servisine" in out["neden"]
    no_q = F.build_band(_cash(), _daily(), lambda s, h: {"tahsilat": {"p50": [1.0] * h}, "odeme": {"p50": [1.0] * h}})
    assert no_q["var"] is False


def test_weekly_flows_start_at_monday_and_skip_before_data():
    tah, od, first = F.weekly_flows({date(2026, 8, 10): (5.0, 2.0), date(2026, 8, 11): (1.0, 0.0)}, date(2026, 8, 17), 104)
    assert first == date(2026, 8, 10) and tah == [6.0] and od == [2.0]


def test_cash_flow_history_sql_reads_bank_lines_against_customer_and_supplier():
    from semantic_bridge import finance_sources as FS

    sql = FS.cash_flows_daily_sql("411", date(2026, 1, 1), date(2026, 8, 17))
    assert "LG_411_01_EMFLINE" in sql and "'120'" in sql and "'320'" in sql and "IN ('100', '102')" in sql
    assert "F.TRCODE <> 1" in sql and "L.DATE_ < '20260817'" in sql


def test_forecast_series_reads_p10_p50_p90_and_refuses_missing():
    rows = [[-1.0, 0, 0, 0, 5.0, 0, 0, 0, 9.0]] * 3
    out = FC.forecast_series({"tahsilat": [1.0] * 30}, 3, post=lambda p: {"results": [{"id": "tahsilat", "quantiles": rows}]},
                             ready=lambda: None)
    assert out["tahsilat"] == {"p10": [0.0] * 3, "p50": [5.0] * 3, "p90": [9.0] * 3}
    with pytest.raises(RuntimeError):
        FC.forecast_series({"odeme": [1.0]}, 3, post=lambda p: {"results": []}, ready=lambda: None)


# ================================================================================ bütçe sapmasının nedeni


def test_budget_expense_deviation_is_split_by_month():
    from semantic_bridge import budget as B

    e = open_store("sqlite://").engine
    B._ready.discard(id(e))
    B.ensure(e)
    now = datetime(2026, 4, 1, tzinfo=timezone.utc)
    with e.begin() as c:
        c.execute(B.PLANS.insert().values(id="p1", tenant_id=T, year=2026, scenario="temel", version=1, status="onayli",
                                          title="2026", params_json="{}", basis_json="{}", created_by="cfo", created_at=now))
        c.execute(B.DEPTS.insert().values(plan_id="p1", merkez_kodu="B01", hesap="760", merkez_adi="Pazarlama",
                                          hesap_adi="Pazarlama gid.", aylar_json=json.dumps([100.0] * 12), oneri_json="{}"))
        for m, v in ((1, 90.0), (2, 150.0), (3, 120.0)):
            c.execute(B.EXPENSES.insert().values(year=2026, month=m, merkez_kodu="B01", hesap="760", tutar=v))
        c.execute(B.ALERTS.insert().values(id="a1", tenant_id=T, year=2026, plan_id="p1", kind="gider", scope="merkez",
                                           key="B01|760", label="Pazarlama · Pazarlama gid.", expected=300.0, actual=360.0,
                                           gap=60.0, status="acik", first_at=now, last_at=now))
    B.meta_set(e, "data_end", {"date": "2026-03-31"})
    res = V.budget_reason(e, T, "a1")
    months = res["boyutlar"][0]
    assert months["id"] == "ay" and [(i["ad"], i["fark"]) for i in months["kalemler"]] == [("Şubat", 50.0), ("Mart", 20.0), ("Ocak", -10.0)]
    assert res["toplam"]["fark"] == 60.0
    assert "Şubat" in V.explain(res)["metin"]
    with pytest.raises(V.VarianceError):
        V.budget_reason(e, T, "yok")


# ================================================================================ destek taslağı


def test_draft_facts_add_order_amount_cargo_state_and_last_invoice():
    ctx = {"orders": [{"id": "o1", "no": "TS-9", "kdvliTutar": 500, "takipNo": "T9", "acik": False}],
           "cargo": [{"orderIds": ["o1"], "takipNo": "T9", "firma": "Aras", "teslimTarihi": "05.09.2026", "varisSube": "Kadıköy"}],
           "invoices": [{"no": "İ1", "iade": True, "tarih": "2026-09-12", "tutar": 50},
                        {"no": "F9", "iade": False, "tarih": "2026-09-10", "tutar": 1234.5}]}
    f = S.facts_from_context(ctx)
    assert f["siparis_tutari"] == "500,00 TL" and f["kargo_durumu"] == "teslim edildi" and f["kargo_varis_subesi"] == "Kadıköy"
    assert f["son_fatura_no"] == "F9" and f["son_fatura_tarihi"] == "10.09.2026" and f["son_fatura_tutari"] == "1.234,50 TL"
    assert set(f) <= set(S.FACT_KEYS)
    raw = ("Merhaba, son faturanız {son_fatura_no} numaralı ve {son_fatura_tutari} tutarındadır. "
           "Size 250 TL indirim tanımladık. Kargonuz {kargo_durumu}.")
    out = S.fill_draft(raw, f, "faturam nerede", "")
    assert "F9" in out["text"] and "1.234,50 TL" in out["text"] and "teslim edildi" in out["text"]
    assert "250" not in out["text"] and out["dropped"] == 1, "uydurma sayı taşıyan cümle düşer"


def test_cargo_state_is_read_from_fields_only():
    assert S.cargo_state({"iadeDurumu": "Göndericiye iade"}) == "Göndericiye iade"
    assert S.cargo_state({"irsTarihi": "01.09.2026"}) == "kargoya verildi"
    assert S.cargo_state({}) is None


# ================================================================================ yetki


def test_fark_endpoints_are_open_to_overview_board_and_alerts_pages():
    rule = ACC.rule_for("/api/v1/fark/ayristir")
    assert {ACC.page("genel-bakis"), ACC.page("panolar"), ACC.page("uyarilar")} <= set(rule)
    assert ACC.page("butce") in ACC.rule_for("/api/v1/budget/deviations/a1/neden")
    assert ACC.page("finansal-raporlar") in ACC.rule_for("/api/v1/finance/budget/deviations/a1/neden")
