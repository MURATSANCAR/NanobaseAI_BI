"""DYK Kurul: her rakamın sorgu bilgisi. Göstergenin asıl SQL'i ölçüm anında kaynak modülde çalışan sorgudur; değer satırıyla
saklanır (`_sorgu`), ekrana giden ayrıntıya girmez. Paket derlenirken çalışan sorgular içerikle dondurulur.

Veriler test_kurul / test_risk tohumlarıyla kurulur; Logo ve CRM okuyucuları sahte çalıştırıcıyla beslenir.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

from semantic_bridge import kurul as K
from semantic_bridge import kurul_kaynak as KK
from semantic_bridge import kurul_sources as S
from semantic_bridge import provenance as P
from semantic_bridge import risk as R
from semantic_layer.tests import test_risk as TR
from semantic_layer.tests.test_kurul import NOW, TN, _env, _meeting, engine, fake_pdf, ok  # noqa: F401 — fikstürler
from semantic_layer.tests.test_sorgu_bilgisi_risk import _measure_with_sql

DAY = date(2026, 9, 28)


def _check(out, ignore=KK.NOT_RAKAM):
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out, ignore) == []
    assert P.problems(out) == []
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == []
        assert s["connection"] in ("logo", "crm", "portal")
        assert s["id"].startswith("kurul.")
    return k


def _ctx(engine, **kw):
    return S.Ctx(engine=engine, tenant=TN, conf=lambda k, d="": d, today=DAY, **kw)


def _risk_measured(engine, monkeypatch):
    """M47: risk kaydı + Logo'dan (sahte) ölçülen gösterge; kurul sağlayıcısı zinciri ölçümle saklar."""
    R._ready.discard(id(engine))
    R.ensure(engine)
    monkeypatch.setattr(R, "today", lambda: DAY)
    TR._risk(engine, gostergeler=["karsiliksiz_cek"])
    _measure_with_sql(engine)
    ctx = _ctx(engine)
    res = S.m47(ctx)
    assert res["risk_kritik"]["durum"] == "ok" and res["risk_kirmizi_gosterge"]["durum"] == "ok"
    for kod in ("risk_kritik", "risk_kirmizi_gosterge", "risk_geciken_aksiyon"):
        rec = res[kod]["_sorgu"]
        assert rec["saglayici"] == "m47" and not rec.get("hata") and rec["sources"], rec
    return ctx, res


def _crm_run(calls):
    def run(sql):
        calls.append(sql)
        if "yaklasan" in sql:
            return {"records": [{"toplam": 40, "yururlukte": 31, "yenilemede": 2, "yaklasan": 5, "ort_telif": 10.5,
                                 "telif_dolu": 20}], "dbMs": 12, "computedAt": "2026-09-28T06:30:05+03:00"}
        return {"records": [], "dbMs": 3}
    return run


def test_measure_keeps_chain_out_of_screen_and_panel_shows_origin(engine, monkeypatch):  # noqa: F811
    ctx, res = _risk_measured(engine, monkeypatch)
    calls: list[str] = []
    crm = S.m6(_ctx(engine, crm=lambda: ("Timas_MSCRM.dbo", _crm_run(calls))))
    assert crm["sozlesme_bitecek"]["deger"] == 5.0
    sq = crm["sozlesme_bitecek"]["_sorgu"]
    (src,) = sq["sources"].values()
    assert src["connection"] == "crm" and src["sql"].startswith("USE [Timas_MSCRM];") and "new_sozlesmeBase" in src["sql"]
    assert src["stats"]["rows"] == 1 and src["stats"]["dbMs"] == 12
    K.record(engine, TN, "2026-09", {**res, **crm, "butce_satis": ok(70.0, renk="kirmizi")}, NOW)

    p = K.panel(engine, TN, "2026-09")
    assert "_sorgu" not in json.dumps(p, default=str)                  # ölçüm zinciri ekrana giden ayrıntıda yok
    out = {**p, "olcumSuruyor": False}
    k = _check(P.ekle(out, KK.for_panel(engine, TN, out)))
    # risk göstergesinin kökeni: ölçümde Logo'da çalışan metin (firma kopyası yerinde)
    logo = [sid for sid, s in k["sources"].items() if "LG_411_01_CSCARD" in s["sql"]]
    assert logo and all(sid.startswith("kurul.m47.2026-09.") for sid in logo)
    assert set(logo) <= set(k["sources"]["kurul.deger.risk_kirmizi_gosterge"]["origin"])
    ref = k["fields"]["bolumler[].gostergeler[]:risk_kirmizi_gosterge"]
    assert ref.startswith("hesap:") and "kurul.deger.risk_kirmizi_gosterge" in k["formulas"][ref[6:]]["inputs"]
    val = k["sources"]["kurul.deger.risk_kirmizi_gosterge"]
    assert val["sql"] == k["sources"]["kurul.degerler"]["sql"] and "'risk_kirmizi_gosterge'" in val["description"]
    # CRM sayacı: çalışan metin, veritabanı adıyla
    crm_src = [s for s in k["sources"].values() if s["connection"] == "crm"]
    assert crm_src and crm_src[0]["id"].startswith("kurul.m6.2026-09.")
    # zinciri olmayan (kayıt tutulmadan ölçülmüş) değer: açıklama söyler, rakam yine bağlı
    assert "tutulmadan önce" in k["sources"]["kurul.deger.butce_satis"]["description"]
    assert "kritik[]:butce_satis" in k["fields"] and "sayilar" in k["fields"] and "olcum" in k["fields"]
    # gri gösterge: sayı yok, hesap «kaynak yok» der
    gray = k["formulas"][k["fields"]["bolumler[].gostergeler[]:stok_riski"][6:]]
    assert "sayı ve renk yazılmaz" in gray["text"]


def test_indicator_detail_series_each_period_its_own_chain(engine, monkeypatch):  # noqa: F811
    _ctx0, res = _risk_measured(engine, monkeypatch)
    K.record(engine, TN, "2026-08", {"risk_kritik": ok(1.0)}, NOW - timedelta(days=30))
    K.record(engine, TN, "2026-09", res, NOW)
    d = K.indicator_detail(engine, TN, "risk_kritik")
    k = _check(P.ekle(d, KK.for_indicator(engine, TN, "risk_kritik", d)))
    assert {"seri[]:2026-08", "seri[]:2026-09", "gosterge", "seri", "gosterge.esikSari"} <= set(k["fields"])
    cur = k["formulas"][k["fields"]["gosterge"][6:]]
    assert any(i.startswith("hesap:kurul.m47.2026-09.") for i in cur["inputs"])
    assert "LIMIT" in k["sources"]["kurul.seri.2026-09"]["sql"].upper()          # seri tavanı açıklamada ve SQL'de


def test_capture_records_the_executed_statement(engine):  # noqa: F811
    stmt = K.values_stmt(TN, "2026-09")
    with KK.capture(engine) as cap:
        with engine.connect() as c:
            c.execute(stmt).all()
    assert [it["sql"] for it in cap.sqls()] == [P.portal_sql(stmt, engine)]
    assert cap.items[0]["dbMs"] is not None
    with engine.connect() as c:                                               # yakalama bitince kayıt yok
        c.execute(stmt).all()
    assert len(cap.items) == 1


def test_system_status_chain_is_captured(engine):  # noqa: F811
    from semantic_bridge import it_ops as I

    I.ensure(engine)
    I.record_check(engine, TN, "logo", True, data_end=datetime(2026, 8, 16, 21, 0, tzinfo=timezone.utc))
    res = S.m48(_ctx(engine))
    assert res["logo_veri_gecikmesi"]["deger"] == 42.0
    rec = res["logo_veri_gecikmesi"]["_sorgu"]
    assert not rec.get("hata") and all("'logo'" in s["sql"] for s in rec["sources"].values())
    K.record(engine, TN, "2026-09", res, NOW)
    p = {**K.panel(engine, TN, "2026-09"), "olcumSuruyor": False}
    k = _check(P.ekle(p, KK.for_panel(engine, TN, p)))
    assert any(sid.startswith("kurul.m48.2026-09.") for sid in k["sources"]["kurul.deger.logo_veri_gecikmesi"]["origin"])


def test_meetings_actions_catalog_packages_job(engine):  # noqa: F811
    m = _meeting(engine)
    K.set_agenda(engine, TN, m["id"], [{"baslik": "Bütçe", "tur": "karar", "sureDk": 20}])
    K.add_decision(engine, TN, "sekreter", m["id"], {"metin": "Plan onaylandı", "aksiyonlar": [
        {"eylem": "Revizyonu işle", "sahip": "cfo", "termin": "2026-09-20"}]})
    out = K.list_meetings(engine, TN)
    k = _check(P.ekle(out, KK.for_meetings(engine, TN, out)))
    assert out["siradaki"]["kalanGun"] == 8 and "siradaki" in k["fields"]
    mt = K.meeting(engine, TN, m["id"])
    k = _check(P.ekle(mt, KK.for_meeting(engine, TN, m["id"], mt)))
    assert m["id"] in k["sources"]["kurul.kararAksiyon"]["sql"]
    for durum, sahip in (("acik", None), ("geciken", "cfo"), ("hepsi", None)):
        a = K.list_actions(engine, TN, durum=durum, sahip=sahip)
        _check(P.ekle(a, KK.for_actions(engine, TN, a, durum, sahip)))
    K.record(engine, TN, "2026-09", {"butce_satis": ok(70.0, renk="kirmizi")}, NOW)
    sug = {"items": K.agenda_suggestions(engine, TN, m["id"])}
    k = _check(P.ekle(sug, KK.for_agenda_suggest(engine, TN, m["id"], sug)))
    assert {"items[]:aksiyon", "items[]:butce_satis"} <= set(k["fields"])
    assert next(i for i in sug["items"] if i["neden"] == "gosterge")["kod"] == "butce_satis"
    cat = {"items": K.indicators(engine, TN)}
    _check(P.ekle(cat, KK.for_indicators(engine, TN, cat)))
    with engine.begin() as c:
        c.execute(K.JOBS.insert().values(id="j1", tenant_id=TN, tur="tutanak", durum="bitti", baslatan="s",
                                         sonuc_json=K._dump({"oneriler": [], "dusenler": ["45 bayi"]}), baslangic=NOW))
    j = K.job(engine, TN, "j1")
    k = _check(P.ekle(j, KK.for_job(engine, TN, "j1", j)))
    assert k["fields"]["sonuc.dusenler"] == "hesap:kurul.isSonuc"


def test_package_freezes_its_query_record(engine, monkeypatch):  # noqa: F811
    ctx, res = _risk_measured(engine, monkeypatch)
    K.record(engine, TN, "2026-09", {**res, "butce_satis": ok(70.0, renk="kirmizi")}, NOW)
    m = _meeting(engine)
    content = K.build_content(engine, TN, m["id"], risk=None, risk_numbers=S.risk_numbers(ctx), market=None)
    content[K.QUERY_KEY] = KK.for_compile(engine, TN, content, risk_ctx=ctx)
    pkg = K.compile_package(engine, TN, "sekreter", m["id"], content)
    assert K.QUERY_KEY not in pkg["icerik"]                                   # ekrana giden içerikte yok
    k = _check(P.ekle(pkg, KK.for_package(engine, TN, pkg["id"], pkg)))
    assert {"icerik.gostergeler[].gostergeler[]:risk_kritik", "icerik.sayilar", "icerik.eksikYorum", "icerik.aksiyonOzeti",
            "icerik.risk.sayilar", "ozetMetin"} <= set(k["fields"])
    assert pkg["id"] in k["sources"]["kurul.paket"]["sql"]
    row = k["formulas"][k["fields"]["icerik.gostergeler[].gostergeler[]:risk_kritik"][6:]]
    assert row["inputs"][0] == "kurul.paket"
    assert any("LG_411_01_CSCARD" in s["sql"] for s in k["sources"].values())
    # dondurma kaydı değiştirmez; kaynak değer sonradan değişse de derleme anının zinciri kalır
    K.freeze_package(engine, TN, "gm", pkg["id"], fake_pdf)
    K.record(engine, TN, "2026-09", {"risk_kritik": ok(9.0)}, NOW + timedelta(hours=2))
    again = K.package(engine, TN, pkg["id"])
    k2 = _check(P.ekle(again, KK.for_package(engine, TN, pkg["id"], again)))
    assert set(k2["sources"]) == set(k["sources"])
    # kayıt tutulmadan derlenmiş sürüm: rakamlar paket kaydına bağlı, açıklama söyler
    old = K.compile_package(engine, TN, "sekreter", m["id"], K.build_content(engine, TN, m["id"], risk=None, risk_numbers=None,
                                                                             market=None))
    k3 = _check(P.ekle(old, KK.for_package(engine, TN, old["id"], old)))
    assert "tutulmadan önce" in k3["formulas"]["kurul.paket.icerik"]["text"]
    lst = K.list_packages(engine, TN)
    _check(P.ekle(lst, KK.for_packages(engine, TN, lst)))


def test_not_rakam_holds_no_measure():
    assert not any(x.split(".")[-1] in ("deger", "hedef", "onceki", "kalanGun", "kararSayisi", "total", "geciken")
                   for x in KK.NOT_RAKAM)
