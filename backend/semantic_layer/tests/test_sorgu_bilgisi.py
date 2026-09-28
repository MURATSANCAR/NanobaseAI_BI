"""Sorgu bilgisi (ekrandaki her rakamın SQL'i ve hesabı): ortak sözleşme `provenance.py` ve üç örnek modül —
M46 bütçe, M45 finansal raporlar, M9 fiyatlama.

Her uç cevabı için denetlenen: (1) cevaptaki her rakam bir kaynağa bağlı (`uncovered_numbers` boş), (2) her kaynağın
SQL'i dolu ve çalıştırılabilir (yer tutucu kalmamış), (3) kökeni kayıtlı, (4) sır izi yok. Veriler yapaydır; gerçek
Logo/CRM'de kopyala-çalıştır kabulü `scripts/acceptance/sorgu-bilgisi/` ile test sunucusunda yapılır.
"""

from __future__ import annotations

import json
from datetime import date

import pytest
import sqlalchemy as sa

from semantic_bridge import budget as B
from semantic_bridge import budget_kaynak as BK
from semantic_bridge import finance as F
from semantic_bridge import finance_kaynak as FK
from semantic_bridge import provenance as P
from semantic_bridge.pricing import data as D
from semantic_bridge.pricing import kaynak as PK
from semantic_bridge.pricing import store as PS
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.test_budget import _approve, _seed as seed_budget
from semantic_layer.tests.test_finance import _seed as seed_finance, _seed_profit
from semantic_layer.tests.test_pricing_data import _fake_run

T = "t1"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    for mod in (B, F, PS):
        mod._ready.discard(id(e))
    B.ensure(e)
    F.ensure(e)
    PS.ensure(e)
    yield e
    for mod in (B, F, PS):
        mod._ready.discard(id(e))


def _check(out: dict, ignore=()) -> dict:
    """Ortak kabul: kapsanmamış rakam yok, her SQL dolu ve çalıştırılabilir, köken kayıtlı, sır izi yok."""
    k = out.get("kaynaklar")
    assert k and not k.get("error"), k
    assert P.uncovered_numbers(out, ignore) == []
    assert P.problems(out) == []
    assert k["sources"], "en az bir sorgu olmalı"
    for s in k["sources"].values():
        assert s["sql"].strip()
        assert P.placeholders_left(s["sql"]) == [], (s["id"], P.placeholders_left(s["sql"]))
        assert s["connection"] in ("logo", "crm", "portal")
    json.dumps(out, default=str)  # cevap JSON'a çevrilebilir
    return k


# ------------------------------------------------------------------ ortak yardımcı


def test_inline_params_positional_named_and_literals_untouched():
    sql = "SELECT '?' AS a, ':x' AS b -- ? :y\nFROM T WHERE A = ? AND B IN (?) AND C >= ? AND D = ?"
    out = P.inline_params(sql, [5, ["a", "b"], date(2026, 1, 1), "O'Neil"])
    assert out.endswith("A = 5 AND B IN (N'a', N'b') AND C >= '20260101' AND D = N'O''Neil'")
    assert "SELECT '?' AS a, ':x' AS b -- ? :y" in out
    assert P.inline_params("WHERE Y = :yil AND Z = :ad", {"yil": 2026, "ad": "Kitap"}) == "WHERE Y = 2026 AND Z = N'Kitap'"
    with pytest.raises(P.ProvenanceError):
        P.inline_params("A = ? AND B = ?", [1])
    with pytest.raises(P.ProvenanceError):
        P.inline_params("A = :eksik", {})


def test_placeholders_left_ignores_strings_comments_and_casts():
    assert P.placeholders_left("SELECT x::date, '{f}', N'?' FROM t -- :a ?") == []
    assert sorted(P.placeholders_left("SELECT * FROM LG_{f}_01 WHERE a = ? AND b = :yil")) == [":yil", "?", "{f}"]


def test_clean_sql_drops_tech_comment_lines_and_rejects_secrets():
    text = P.clean_sql("-- vLLM ile üretildi\n-- Faturalı satış satırları\nSELECT 1")
    assert text == "-- Faturalı satış satırları\nSELECT 1"
    for bad in ("SELECT 1 -- PWD=gizli", "Driver={ODBC Driver 18};Server=x", "SELECT 'x' -- password = 1",
                "SELECT k.new_name, k.new_apisifre FROM new_kargofirmasiBase k"):
        with pytest.raises(P.ProvenanceError):
            P.clean_sql(bad)


def test_record_adds_use_line_reads_only_database_name(tmp_path):
    conn = tmp_path / "logo.json"
    conn.write_text(json.dumps({"server": "10.0.0.5", "database": "TIGERDB", "username": "sa", "password": "S3cret!"}))
    db = P.connection_database(str(conn))
    assert db == "TIGERDB"
    k = P.Kaynaklar(data_end=date(2026, 8, 17))
    sid = k.sorgu("logo.x", "Deneme", "logo", "SELECT 1 FROM dbo.LG_411_01_STLINE WHERE DATE_ >= ?", params=[date(2026, 1, 1)],
                  database=db, rows=3, ms=1500, ran_at="2026-09-28T08:00:00")
    s = k.to_dict()["sources"][sid]
    assert s["sql"].startswith("USE [TIGERDB];\nSELECT 1") and "'20260101'" in s["sql"]
    assert s["stats"] == {"rows": 3, "dbMs": 1500, "ranAt": "2026-09-28T08:00:00"} and s["dataEnd"] == "2026-08-17"
    assert "S3cret" not in json.dumps(k.to_dict()) and "10.0.0.5" not in json.dumps(k.to_dict())
    with pytest.raises(P.ProvenanceError):
        k.sorgu("x", "x", "logo", "SELECT * FROM LG_{f}_ITEMS")
    with pytest.raises(P.ProvenanceError):
        k.hesap("y", "y", ["kayitsiz"])


def test_portal_sql_is_the_executed_statement_with_values(engine):
    stmt = B.month_sales_stmt(2026)
    text = P.portal_sql(stmt, engine)
    assert "semantic_budget_sales" in text and "2026" in text and "NOT LIKE '157%'" in text
    assert P.placeholders_left(text) == []
    from sqlalchemy.dialects import postgresql

    pg = P.portal_sql(stmt, postgresql.dialect())
    assert "'157%'" in pg and "%%" not in pg


def test_coverage_and_row_keys():
    k = P.Kaynaklar()
    a = k.sorgu("portal.a", "A", "portal", "SELECT 1")
    k.alanlar({"cards[]": k.hesap("hepsi", "x", [a]), "cards[]:net": k.hesap("net", "y", [a])})
    out = {"cards": [{"id": "net", "value": 1.0}], "year": 2026, "sirket": {"oran": 0.5}}
    P.ekle(out, k)
    assert P.uncovered_numbers(out, ["year"]) == ["sirket.oran"]
    bad = P.bagla({"x": 1}, lambda: (_ for _ in ()).throw(RuntimeError("bozuk")))
    assert bad["x"] == 1 and bad["kaynaklar"]["error"]


# ------------------------------------------------------------------ M46 bütçe


def _budget_meta(engine):
    for y, firm in ((2025, "211"), (2026, "411")):
        B.meta_set(engine, f"sales:{y}", {"rows": 40, "dbMs": 1800, "firm": firm})
        B.meta_set(engine, f"expense:{y}", {"rows": 24, "dbMs": 900, "firm": firm})


def test_budget_every_number_has_its_query(engine):
    seed_budget(engine)
    _budget_meta(engine)
    p = _approve(engine)
    B.evaluate_alerts(engine, T, 2026)

    out = B.tracking(engine, T, 2026, p["id"])
    k = _check(P.ekle(out, BK.for_tracking(engine, T, out, "TIGERDB")), BK.NOT_RAKAM)
    logo = k["sources"]["logo.satis.2026"]
    assert logo["sql"].startswith("USE [TIGERDB];") and "LG_411_01_STLINE" in logo["sql"]
    assert "'2026-01-01'" in logo["sql"] and "'2027-01-01'" in logo["sql"] and logo["stats"]["rows"] == 40
    assert "logo.satis.2026" in k["sources"]["portal.satis"]["origin"]
    assert "net" in k["formulas"]["gercek"]["text"].lower() and "LINENET" in k["formulas"]["gercek"]["text"]
    assert k["fields"]["sirket"] == "hesap:sirket"

    for build in (
        lambda: (lambda o: P.ekle(o, BK.for_plans(engine, T, 2026, o)))(B.list_plans(engine, T, 2026)),
        lambda: (lambda o: P.ekle(o, BK.for_books(engine, T, p["id"], o, None)))(B.books(engine, T, p["id"])),
        lambda: (lambda o: P.ekle(o, BK.for_program(engine, T, p["id"])))(B.program(engine, T, p["id"])),
        lambda: (lambda o: P.ekle(o, BK.for_departments(engine, T, p["id"], o, None)))(B.departments(engine, T, p["id"])),
        lambda: (lambda o: P.ekle(o, BK.for_compare(engine, T, 2026, o, None)))(B.compare(engine, T, 2026)),
        lambda: (lambda o: P.ekle(o, BK.for_deviations(engine, T, 2026)))(B.deviations(engine, T, 2026)),
    ):
        _check(build(), BK.NOT_RAKAM)


def test_budget_plan_list_has_row_keys_per_plan(engine):
    seed_budget(engine)
    _budget_meta(engine)
    items = B.generate(engine, T, "hazirlayan", {"year": 2026, "scenarios": ["muhafazakar", "temel"]})
    out = B.list_plans(engine, T, 2026)
    k = _check(P.ekle(out, BK.for_plans(engine, T, 2026, out)), BK.NOT_RAKAM)
    for it in items:
        ref = k["fields"][f"items[].totals:{it['id']}"]
        f = k["formulas"][ref[6:]]
        # satıra özel kayıt yalnız o planın sorgularını taşır, SQL'de plan kimliği değeriyle yazılı
        assert all(i.endswith(f":{it['id']}") for i in f["inputs"])
        assert it["id"] in k["sources"][f"portal.toplam.kitap:{it['id']}"]["sql"]


# ------------------------------------------------------------------ M45 finansal raporlar


def _finance_all(engine):
    seed_finance(engine)
    _seed_profit(engine)
    F.meta_set(engine, "position:2026", {"groups": {"100": 1_000.0, "102": 9_000.0}, "asof": "2026-08-17"})
    res = F.build_cash({"asof": date(2026, 8, 17), "position": {"100": 1_000, "102": 9_000},
                        "receivables": [(date(2026, 8, 20), 4_000, 3), (date(2026, 8, 1), 2_500, 1)],
                        "payables": [(date(2026, 8, 25), 20_000, 2)], "crm": [(date(2026, 8, 18), 500)],
                        "tax": [(date(2026, 8, 26), 1_200, "KDV")]})
    F.save_cash_run(engine, T, "cfo", res)
    seed_budget(engine)
    _budget_meta(engine)
    _approve(engine)


def test_finance_every_number_has_its_query(engine):
    _finance_all(engine)
    ig = FK.NOT_RAKAM + ("status",)
    s = F.summary(engine, T, with_cash=True)
    k = _check(P.ekle(s, FK.for_summary(engine, T, s, "TIGERDB", "CRMDB")), ig)
    ids = {c["id"] for c in s["cards"]}
    assert {"net-satis", "brut-kar", "faaliyet", "nakit", "vadesi-gecmis", "butce"} <= ids
    for cid in ids:
        assert f"cards[]:{cid}" in k["fields"], cid
    net = k["sources"]["portal.fin.satisYbd"]
    assert "semantic_finance_sales_month" in net["sql"] and "logo.fin.satis.2026" in net["origin"]
    assert "LG_411_01_STLINE" in k["sources"]["logo.fin.satis.2026"]["sql"]
    assert k["sources"]["crm.nakit.tahsilat"]["sql"].startswith("USE [CRMDB];")

    pnl = F.pnl(engine, T, 2026, 7, "ay")
    k = _check(P.ekle(pnl, FK.for_pnl(engine, T, pnl, None)), ig)
    assert {"rows[].values.donem", "rows[].values.onceki", "rows[].values.gecenYil", "rows[].values.butce"} <= set(k["fields"])
    assert "LG_211_01" in k["sources"]["logo.fin.muhasebe.2025"]["sql"]  # geçen yıl kendi kopyasından

    for out, build in (
        (F.line_accounts(engine, T, "NET_SATIS", 2026, 7, "ay"), lambda o: FK.for_line_accounts(engine, T, o, 2026, 7, "ay", None)),
        (F.reconciliation(engine, T, 2026, 7, "ay"), lambda o: FK.for_reconciliation(engine, T, o, 2026, 7, "ay", None)),
        (F.account_map(engine, T, 2026), lambda o: FK.for_account_map(engine, T, o, None)),
        (F.profitability(engine, by="kitap", year=2026), lambda o: FK.for_profitability(engine, T, o, None, None)),
        (F.profitability(engine, by="cari", year=2026), lambda o: FK.for_profitability(engine, T, o, None, None)),
        (F.cash(engine, T), lambda o: FK.for_cash(engine, T, o, None, None)),
        (F.cash_history(engine, T), lambda o: FK.for_cash_history(engine, T, None)),
        (F.budget_view(engine, T, 2026), lambda o: FK.for_budget(engine, T, o, None)),
        (F.tax_list(engine, T, 2026), lambda o: FK.for_tax(engine, T, 2026)),
    ):
        _check(P.ekle(out, build(out)), ig)


def test_finance_entries_keep_the_live_sql(engine):
    seed_finance(engine)
    from semantic_bridge import finance_sources as src

    sql = src.entries_sql("411", "600.01.001", date(2026, 7, 1), date(2026, 8, 1), 0, 100)
    out = {"hesap": "600.01.001", "donem": "Temmuz 2026", "items": [{"borc": 0.0, "alacak": 10.0}], "total": 1, "page": 0,
           "pageSize": 100, "sql": sql}
    k = _check(P.ekle(out, FK.for_entries(engine, out, sql, None, 2026)), FK.NOT_RAKAM)
    assert k["sources"]["logo.fin.fisler"]["sql"] == P.clean_sql(sql)


# ------------------------------------------------------------------ M9 fiyatlama


@pytest.fixture
def snap():
    run, _ = _fake_run()
    return D.Builder(run).build()


def test_pricing_every_number_has_its_query(engine, snap):
    from semantic_bridge import pricing as PR

    ig = PK.NOT_RAKAM + ("offset", "limit", "dataEnd", "since", "until")
    src = {"sources": [{"id": s, "runs": len(v), "stats": snap["sources"].get(s)} for s, v in snap["sql"].items()],
           "copies": snap["copies"]}
    k = _check(P.ekle(src, PK.for_sources(snap, "TIGERDB", "CRMDB")), ig)
    # her Logo kopyası için çalışan metin ayrı kayıt; şablon değil
    runs = [s for s in k["sources"] if s.startswith("fiyatlama.logo_satis")]
    assert len(runs) == 2 and any("LG_411" in k["sources"][r]["sql"] for r in runs)
    assert f"sources[]:logo_satis" in k["fields"]

    measured = {"dataEnd": snap["dataEnd"], "asOf": snap["asOf"], "copies": snap["copies"], "channels": snap["channels"],
                "paper": snap["paper"], "distribution": snap["distribution"], "discount": D.weighted_discount(snap),
                "books": len(snap["books"]), "printedBooks": len(snap["prints"]), "printInvoices": 4, "warnings": []}
    ov = {"status": {"refreshing": False, "updatedAt": 1.0}, "measured": measured, "defaults": PS.get_defaults(engine, T),
          "counts": {}, "toApprove": 0}
    _check(P.ekle(ov, PK.for_overview(engine, T, snap, ov, None, None)), ig)

    det = D.book_detail(snap, "15201.01.1")
    det["suggested"] = D.suggested_inputs(snap, det["spec"], PS.get_defaults(engine, T))
    det["freelance"], det["quotes"] = {}, []
    det["analyses"] = PS.list_analyses(engine, T, book=det["book"]["id"])["items"]
    det["market"] = PS.market_list(engine, T, book=det["book"]["id"])["items"]
    _check(P.ekle(det, PK.for_book(engine, T, snap, det, None, None)), ig)

    sug = D.suggested_inputs(snap, {"pages": 200}, PS.get_defaults(engine, T))
    _check(P.ekle(sug, PK.for_suggest(engine, T, snap, None, None)), ig)
    comp = D.comparables(snap, 200, None)
    _check(P.ekle(comp, PK.for_comparables(snap, None, None)), ig + ("pages", "band"))
    calc = PR.calculate(snap, {"spec": {"pages": 200, "binding": "Amerikan Cilt"},
                               "inputs": {"printPerCopy": 20, "printSetup": 5000, "fixed": {"ceviri": 20000},
                                          "royaltyRate": 0.1, "vat": 0, "discount": 0.45, "variableRate": 0.02,
                                          "qtys": [1000, 3000], "targetMargin": 0.1, "chosenQty": 3000}})
    _check(P.ekle(calc, PK.for_calc(snap, None, None)), ig)
    _check(P.ekle(D.actuals(snap), PK.for_actuals(snap, None, None)), ig + ("sinceYear",))
    _check(P.ekle(D.backlist(snap), PK.for_backlist(snap, None, None)), ig)

    a = PS.create_analysis(engine, T, "fiyatci", {"title": "Deneme", "stage": "tahmini", "inputs": {}, "specs": {}})
    lst = PS.list_analyses(engine, T)
    _check(P.ekle(lst, PK.for_analyses(engine, T)), ig)
    one = PS.get_analysis(engine, T, a["id"])
    k = _check(P.ekle(one, PK.for_analysis(engine, T, a["id"])), ig + ("approvals", "history", "required"))
    assert a["id"] in k["sources"]["portal.fiyat.analiz"]["sql"]


# ------------------------------------------------------------------ örnek modüllerde kalan kalemler (Grup 2)


def test_budget_defaults_have_their_measurement_queries(engine):
    """Öneri sayfasının ön dolu kutuları: ölçülen fiyat ve gider artışı hangi satış/gider satırlarından."""
    seed_budget(engine)
    _budget_meta(engine)
    end = B.data_end(engine)
    out = {**B.default_params(engine, end.year + 1), "tahminVar": False, "tahminBaslangic": None}
    k = _check(P.ekle(out, BK.for_defaults(engine, end.year + 1, "TIGERDB")), BK.NOT_RAKAM)
    assert {"fiyat", "gider", "hacim", "esik", "uyariKapsam", "pencere"} <= set(k["fields"])
    fiyat = k["formulas"][k["fields"]["fiyat"][6:]]
    assert "portal.satis" in fiyat["inputs"] and "birim fiyat" in fiyat["text"]
    assert f"logo.satis.{end.year}" in k["sources"]["portal.satis"]["origin"]
    assert k["sources"][f"logo.satis.{end.year}"]["sql"].startswith("USE [TIGERDB];")


def test_budget_scenario_params_have_row_keys(engine):
    seed_budget(engine)
    _budget_meta(engine)
    items = B.generate(engine, T, "hazirlayan", {"year": 2026, "scenarios": ["temel"]})
    out = B.compare(engine, T, 2026)
    k = _check(P.ekle(out, BK.for_compare(engine, T, 2026, out, None)), BK.NOT_RAKAM)
    assert f"items[].params:{items[0]['id']}" in k["fields"]


def test_finance_remaining_fields(engine):
    """Gelir tablosu «bütçeden fark», vergi kalan günü, nakit bandı, eşleme grup sayısı kendi hesaplarıyla."""
    _finance_all(engine)
    ig = FK.NOT_RAKAM + ("status",)
    pnl = F.pnl(engine, T, 2026, 7, "ay")
    k = _check(P.ekle(pnl, FK.for_pnl(engine, T, pnl, None)), ig)
    fark = k["formulas"][k["fields"]["rows[].values.fark"][6:]]
    assert "dönem − bütçe" in fark["text"] and set(fark["inputs"]) == {k["fields"]["rows[].values.donem"],
                                                                         k["fields"]["rows[].values.butce"]}

    tax = F.tax_list(engine, T, 2026)
    k = _check(P.ekle(tax, FK.for_tax(engine, T, 2026)), ig)
    assert k["fields"]["items[].kalanGun"] == k["fields"]["geciken[]"] == "hesap:vergiGun"

    cash = F.cash(engine, T)
    cash["bant"] = {"var": True, "gecmisHafta": 104, "haftalar": [{"hafta": 1, "kesin": 10.0,
                                                                   "kapanis": {"kotu": -5.0, "orta": 3.0, "iyi": 9.0}}],
                    "enKotuAcik": {"hafta": 1, "kapanis": -5.0},
                    "sorgular": [{"year": 2026, "firm": "411", "from": "2024-08-19", "to": "2026-08-17", "rows": 480,
                                  "dbMs": 900, "at": "2026-09-28T07:00:00"}]}
    k = _check(P.ekle(cash, FK.for_cash(engine, T, cash, "TIGERDB", None)), ig)
    band = k["sources"]["logo.nakit.bant.2026"]
    assert "LG_411_01_EMFLINE" in band["sql"] and "'20240819'" in band["sql"] and band["stats"]["rows"] == 480
    assert "logo.nakit.bant.2026" in k["formulas"]["bant"]["inputs"]

    amap = F.account_map(engine, T, 2026)
    k = _check(P.ekle(amap, FK.for_account_map(engine, T, amap, None)), ig)
    assert k["fields"]["gruplar"] == "hesap:gruplar" and "items[].esleme" in k["fields"] and "suggest" in k["fields"]


def test_pricing_remaining_fields(engine, snap):
    ig = PK.NOT_RAKAM + ("offset", "limit", "dataEnd", "since", "until")
    k = _check(P.ekle(D.actuals(snap), PK.for_actuals(snap, None, None)), ig + ("sinceYear",))
    assert k["fields"]["gosterilen"] == "hesap:gosterilen"
    k = _check(P.ekle(D.backlist(snap), PK.for_backlist(snap, None, None)), ig)
    assert k["fields"]["secim"] == "hesap:secim"

    det = D.book_detail(snap, "15201.01.1")
    det["suggested"] = D.suggested_inputs(snap, det["spec"], PS.get_defaults(engine, T))
    det["freelance"], det["quotes"] = {"items": [], "byKey": {}}, []
    det["analyses"], det["market"] = [], []
    k = _check(P.ekle(det, PK.for_book(engine, T, snap, det, None, None)), ig)
    # girdi kutuları (NumField «i») bu anahtarlarla çözülür
    for key in ("printService", "paper", "printSetup", "royaltyRate", "vat", "discount", "variableRate", "sellThrough",
                "targetMargin", "advance"):
        assert f"suggested.{key}" in k["fields"], key
    ins = k["formulas"]["teklifler"]["inputs"]
    if [p for p in det["crmPrints"] if p.get("id")]:
        assert "portal.fiyat.teklifler" in ins and "semantic_" in k["sources"]["portal.fiyat.teklifler"]["sql"]
    if (det.get("book") or {}).get("id"):
        assert "portal.fiyat.serbest" in k["formulas"]["serbest"]["inputs"]
