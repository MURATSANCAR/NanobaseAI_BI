"""M47 Risk ve uyum: her rakamın sorgu bilgisi. Gösterge değerinin asıl SQL'i ölçümde çalışan metindir."""
from __future__ import annotations

from semantic_bridge import provenance as P
from semantic_bridge import risk as R
from semantic_bridge import risk_kaynak as K
from semantic_bridge import risk_sources as S
from semantic_layer.tests.test_risk import H24, NOW, TN, FakeRun, _env, _risk, _seed, engine  # noqa: F401 — fikstürler


def _check(out, ignore=K.NOT_RAKAM):
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out, ignore) == []
    assert P.problems(out) == []
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == []
    return k


def _measure_with_sql(engine):
    """Gerçek hesapçıyla ölç: çalışan SQL bağlamda kaydedilir, ölçüm kaydının yanına yazılır."""
    logo = FakeRun([("MAX(DATE_) AS son FROM dbo.LG_411_01_INVOICE", [{"son": "2026-08-17"}]),
                    ("CSCARD", [{"adet": 6, "tutar": 6326658.0}])])
    ctx = S.Context(logo_file=lambda: "", crm_file=lambda: "", crm_schema=lambda: "Timas_MSCRM.dbo")
    ctx._cache["logo"] = ctx._logged("logo", logo)
    ctx._cache["firm"] = ("411", 2026)
    res = S.measure(ctx, "karsiliksiz_cek")
    assert res["deger"] == 6 and len(res["sorgular"]) == 2 and all(q["conn"] == "logo" for q in res["sorgular"])
    R.record_measure(engine, TN, "karsiliksiz_cek", res, "sistem", NOW, H24)
    return res


def test_measure_keeps_executed_sql_out_of_evidence(engine):  # noqa: F811
    _seed(engine)
    res = _measure_with_sql(engine)
    g = next(x for x in R.indicators(engine, TN) if x["kod"] == "karsiliksiz_cek")
    assert "_sorgular" not in g["son"]["kanit"] and g["son"]["kanit"]["tutar"] == 6326658.0
    q = R.measure_queries(engine, TN)["karsiliksiz_cek"]["sorgular"]
    assert [x["sql"] for x in q] == [x["sql"] for x in res["sorgular"]]


def test_summary_indicators_and_detail(engine):  # noqa: F811
    r = _risk(engine, gostergeler=["karsiliksiz_cek"])
    R.add_action(engine, TN, "koordinator", r["id"], {"eylem": "Tahsilat", "sahip": "bt", "termin": "2026-09-20"})
    R.save_item(engine, TN, "hukuk", None, {"alan": "vergi", "madde": "KDV", "siklik": "aylik", "ilkSonGun": "2026-09-26"})
    _measure_with_sql(engine)
    ind = R.indicators(engine, TN, set(S.BY_CODE))
    out = R.summary(engine, TN, "koordinator", True, ind)
    k = _check(P.ekle(out, K.for_summary(engine, TN, out, "TIGERDB", "CRMDB", ind)))
    ref = k["fields"]["kirmiziGosterge[]:karsiliksiz_cek"][6:]
    meas = [i for i in k["formulas"][ref]["inputs"] if i.startswith("risk.olcum.")]
    assert any("LG_411_01_CSCARD" in k["sources"][m]["sql"] for m in meas)
    assert k["sources"][meas[0]]["sql"].startswith("USE [TIGERDB];")
    assert "risk.olcum.karsiliksiz_cek.1" in k["sources"]["risk.degerler"]["origin"]

    lst = R.list_risks(engine, TN, "koordinator", True)
    _check(P.ekle(lst, K.for_list(engine, TN)))
    det = R.risk_detail(engine, TN, r["id"])
    det["yazabilir"] = True
    k = _check(P.ekle(det, K.for_detail(engine, TN, r["id"], det, None, None)))
    assert "gostergeler[]:karsiliksiz_cek" in k["fields"] and r["id"] in k["sources"]["risk.risk"]["sql"]

    out = {"items": ind, "kutuphane": S.LIBRARY}
    _check(P.ekle(out, K.for_indicators(engine, TN, out, None, None)))
    vals = R.indicator_values(engine, TN, "karsiliksiz_cek")
    _check(P.ekle(vals, K.for_values(engine, TN, "karsiliksiz_cek", None, None)))


def test_compliance_policies_bcp_reports(engine):  # noqa: F811
    R.save_item(engine, TN, "hukuk", None, {"alan": "vergi", "madde": "KDV", "siklik": "aylik", "ilkSonGun": "2026-09-26"})
    items = R.compliance_items(engine, TN)
    _check(P.ekle(items, K.for_compliance(engine, TN, items)))
    cal = R.calendar(engine, TN, "2026-09")
    k = _check(P.ekle(cal, K.for_compliance(engine, TN, cal, cal["ay"])))
    assert "2026-09-30" in k["sources"]["risk.uyumAy"]["sql"]  # çalışan ifade: ayın son günü
    R.save_policy(engine, TN, "cfo", None, {"tur": "Yangın", "policeNo": "TR-12345678", "bit": "2026-11-15", "prim": 1200,
                                            "teminat": [{"ad": "Bina", "tutar": 5000000}]})
    pol = R.policies(engine, TN)
    _check(P.ekle(pol, K.for_manual(engine, TN, pol, "police")))
    R.save_bcp(engine, TN, "bt", None, {"surec": "Sipariş", "kritiklik": 5, "kabulKesintiSaat": 4, "sonrakiTatbikat": "2026-12-01"})
    b = R.bcp(engine, TN)
    _check(P.ekle(b, K.for_manual(engine, TN, b, "bcp")))
    rid = R.start_report(engine, TN, "koordinator", "2026-Ç3", {"sayilar": {"canli": 3}})
    R.finish_report(engine, rid, "Üç canlı risk var.", "kural", None)
    one = R.report(engine, TN, rid)
    k = _check(P.ekle(one, K.for_reports(engine, TN, one, rid)))
    assert k["fields"]["girdi"] == "hesap:brifing"
    lst = R.reports(engine, TN)
    _check(P.ekle(lst, K.for_reports(engine, TN, lst)))
