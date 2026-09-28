"""M36 Dijital yayın: her rakamın sorgu bilgisi. Portal SQL'i uçta çalışan ifade; tabloyu dolduran asıl CRM/Logo SQL'i
gece okumasında ÇALIŞAN metin (firma kopyası, pencere, şema yerinde), okuma kaydında saklanır ve köken olarak gösterilir."""
from __future__ import annotations

from datetime import date

from semantic_bridge import dijital as D
from semantic_bridge import dijital_kaynak as K
from semantic_bridge import dijital_sources as src
from semantic_bridge import provenance as P
from semantic_bridge.management.kaynak import is_template
from semantic_layer.tests.test_dijital import CSV, ST, T, _seed, contract, engine  # noqa: F401 — fikstür ve tohumlar


def _check(out, ignore=K.NOT_RAKAM):
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out, ignore) == []
    assert P.problems(out) == []
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == [] and not is_template(s["sql"])
        assert s["connection"] in ("logo", "crm", "portal")
    return k


# ---------------------------------------------------------------- gece okuması: çalışan SQL saklanır


def _crm(sql: str):
    if "StringMap" in sql:
        return []
    if "new_sozlesmetarafiBase" in sql:
        return [{"contract_id": "C1", "person": "Yazar A", "company": None}]
    if "AS yururlukte" in sql:
        return [{"yururlukte": 3, "ekitap": 2, "sesli": 1, "iletim": 2, "notlu": 1}]
    if "new_new_sozlesme_new_kitapBase" in sql:
        return [{"book_id": "a1", "id": "c1", "name": "S-1", "kind": 5, "status": 100000000, "ends": None, "open_ended": 1,
                 "terminated": None, "internet": 1, "ebook": 1, "zbook": 0, "audiobook": 0, "public_domain": 0, "rights_note": None}]
    if "new_UretimBase" in sql or "new_kitapgecmisiBase" in sql:
        return []
    if "new_kitapBase" in sql:
        return [{"id": "a1", "ad": "Kitap A", "stok_kodu": "TMS-A", "isbn": None, "ean": None, "e_isbn": None, "ekitap_barkod": None,
                 "ekitap_stok_kodu": "E-A", "epub": 0, "tip": 1, "yayin_durumu": None, "hedef_kitle": None, "yazar": "Yazar A",
                 "turler": None, "basili_fiyat": 120.0, "ilk_yayin": None},
                {"id": "b1", "ad": "Kitap B", "stok_kodu": "TMS-B", "isbn": None, "ean": None, "e_isbn": None, "ekitap_barkod": None,
                 "ekitap_stok_kodu": None, "epub": 0, "tip": 1, "yayin_durumu": None, "hedef_kitle": None, "yazar": "Yazar B",
                 "turler": None, "basili_fiyat": 90.0, "ilk_yayin": None}]
    raise AssertionError(sql)


def _logo(sql: str):
    if "L_CAPIPERIOD" in sql:
        return [{"FIRMNR": 211, "BEGDATE": date(2025, 1, 1), "ENDDATE": date(2025, 12, 31)},
                {"FIRMNR": 411, "BEGDATE": date(2026, 1, 1), "ENDDATE": date(2026, 12, 31)}]
    if "MAX(DATE_)" in sql:
        return [{"son": date(2026, 8, 17)}]
    if "LG_411_01_STLINE" in sql:
        return [{"stok_kodu": "TMS-A", "yil": 2026, "ay": 3, "adet": 5000, "ciro": 250000.0},
                {"stok_kodu": "E-A", "yil": 2026, "ay": 4, "adet": 12, "ciro": 600.0}]
    if "LG_211_01_STLINE" in sql:
        return [{"stok_kodu": "TMS-B", "yil": 2025, "ay": 11, "adet": 40, "ciro": 2000.0}]
    raise AssertionError(sql)


def _refresh(e, logo=_logo):
    r = D.Refresher(lambda: e, lambda: T, lambda: _crm, lambda: logo, None, None, lambda: ST)
    return r.run()


def test_refresh_keeps_the_executed_sql_and_the_overview_cites_it(engine):  # noqa: F811
    assert _refresh(engine)["ok"]
    items = D.meta_get(engine, T, "sorgular")["items"]
    tags = {q["tag"] for q in items}
    assert {"logo.donem", "logo.verisonu", "logo.satis.211.2025-09-01", "logo.satis.411.2026-01-01", "crm.kitaplar",
            "crm.sozlesmeler", "crm.sozlesmeSayilari"} <= tags
    assert all(q["rows"] is not None and q["dbMs"] is not None and q["at"] for q in items)

    out = D.overview(engine, T, ST)
    k = _check(P.ekle(out, K.for_overview(engine, T, ST, out, "TIGERDB", "CRMDB")))
    logo = k["sources"]["dijital.okuma.logo.satis.411.2026-01-01"]
    assert logo["sql"].startswith("USE [TIGERDB];") and "LG_411_01_STLINE" in logo["sql"] and "'2026-08-18'" in logo["sql"]
    assert logo["stats"]["rows"] == 2 and "firma 411" in logo["period"]
    assert "dijital.okuma.logo.satis.211.2025-09-01" in k["sources"]["dijital.kpi.hakRiski"]["origin"]
    counts = k["sources"]["dijital.okuma.crm.sozlesmeSayilari"]
    assert counts["sql"].startswith("USE [CRMDB];") and "new_iletimhakki" in counts["sql"] and "new_EKitap" in counts["sql"]
    assert "new_SozlesmeTipi = 5" in counts["sql"]
    assert counts["id"] in k["sources"]["dijital.sozlesmeSayilari"]["origin"]
    assert k["fields"]["kpi.dijitalde"] == "hesap:kpi.dijitalde" and k["fields"]["kart.hakRiski"] == "hesap:kart.hakRiski"
    assert out["kpi"]["dijitalde"] == 1 and out["sozlesme"]["iletim"] == 2

    s = D.sales(engine, T)
    k = _check(P.ekle(s, K.for_sales(engine, T, s, logo_db="TIGERDB")))
    assert s["logoEkitap"] == [{"donem": "2026-04", "adet": 12.0, "ciro": 600.0}]
    assert any("LG_411_01_STLINE" in k["sources"][o]["sql"] for o in k["sources"]["dijital.logoOkuma"]["origin"])


def test_a_failed_logo_read_keeps_the_previous_logo_queries(engine):  # noqa: F811
    _refresh(engine)

    def down(sql):
        raise src.SourceError("Veritabanına şu an ulaşılamıyor.")

    info = _refresh(engine, down)
    assert info["ok"] and any("Logo okunamadı" in n for n in info["notlar"])
    items = D.meta_get(engine, T, "sorgular")["items"]
    assert any(q["tag"] == "logo.satis.411.2026-01-01" for q in items)      # 12 ay kolonları da bir önceki okumadan
    assert any(q["tag"] == "crm.kitaplar" for q in items)


def test_query_tags():
    assert src.query_tag(src.sales_sql("411", date(2026, 1, 1), date(2026, 8, 18))) == "logo.satis.411.2026-01-01"
    assert src.query_tag("SELECT MAX(DATE_) AS son FROM dbo.LG_411_01_STLINE WHERE 1=1") == "logo.verisonu"
    assert src.query_tag(src.contract_counts_sql("Timas_MSCRM.dbo.")) == "crm.sozlesmeSayilari"
    assert src.query_tag(src.books_sql("Timas_MSCRM.dbo.")) == "crm.kitaplar"


# ---------------------------------------------------------------- ekranlar


def test_catalog_opportunities_risks_pending_platforms(engine):  # noqa: F811
    p = _seed(engine, sales={"A": {"adet": 5000, "ciro": 1}})
    D.set_listing(engine, T, "ayse", "B", p["id"], {"durum": "yayinda", "tarih": "2026-09-01", "fiyat": "49,90"})

    lst = D.list_titles(engine, T, ST, durum="", page=0)
    k = _check(P.ekle(lst, K.for_titles(engine, T, ST, lst)))
    assert "LIMIT 50" in k["sources"]["dijital.katalog"]["sql"].upper() and "t1" in k["sources"]["dijital.katalogToplam"]["sql"]
    assert k["sources"]["dijital.katalog"]["origin"] == []                  # bu tohumda okuma kaydı yok
    assert "ilk okumada" in k["sources"]["dijital.katalog"]["description"]
    lst = D.list_titles(engine, T, ST, platform=p["id"])
    k = _check(P.ekle(lst, K.for_titles(engine, T, ST, lst, platform=p["id"])))
    assert "'B'" in k["sources"]["dijital.katalogToplam"]["sql"] and lst["total"] == 1   # çalışan ifade: platformdaki kitap

    opp = D.opportunities(engine, T, tur="ekitap")
    k = _check(P.ekle(opp, K.for_opportunities(engine, T, ST, opp)))
    assert "≥ 1000" in k["formulas"]["ayar"]["text"] and k["fields"]["esik"] == "hesap:esik"

    risk = D.rights_risks(engine, T)
    k = _check(P.ekle(risk, K.for_rights_risks(engine, T, ST, risk)))
    assert [r["kitapId"] for r in risk["risk"]] == ["B"]
    assert "dijital.kpi.hakRiski" in k["formulas"]["kpi.hakRiski"]["inputs"]      # rozet = gösterge sayımı
    assert "hesap:kpi.hakRiski" in k["formulas"]["sayac.risk"]["inputs"]

    pend = D.crm_pending(engine, T, "hepsi")
    _check(P.ekle(pend, K.for_pending(engine, T, ST, "hepsi", pend)))
    plats = D.list_platforms(engine, T)
    _check(P.ekle(plats, K.for_platforms(engine, T, plats)))


def test_title_detail_import_and_sales(engine):  # noqa: F811
    p = _seed(engine, contracts={"A": [contract("A", note="Yalnız basılı")], "B": [contract("B", ebook=0)], "C": [contract("C")]})
    D.set_price(engine, T, "fin", "A", {"fiyat": "59,90", "gerekce": "Basılının %60'ı"})
    D.set_listing(engine, T, "ayse", "A", p["id"], {"durum": "yuklendi", "fiyat": "3,99"})
    imp = D.create_import(engine, T, "fin", p["id"], "2026-08", "rapor.csv", CSV)
    k = _check(P.ekle(imp, K.for_import(engine, T, imp["id"], imp)))
    assert "rapor.csv" in k["formulas"]["sayac"]["text"] and imp["id"] in k["sources"]["dijital.rapor"]["sql"]
    done = D.commit_import(engine, T, "fin", imp["id"], {"kurlar": {"USD": "34,20"}})
    _check(P.ekle(done, K.for_import(engine, T, imp["id"], done)))
    lst = D.list_imports(engine, T)
    _check(P.ekle(lst, K.for_imports(engine, T, lst)))

    t = D.get_title(engine, T, "A", with_sales=True)
    k = _check(P.ekle(t, K.for_title(engine, T, "A", t)))
    assert t["satis"]["platform"] and k["fields"]["satis.platform"] == "hesap:kitapSatis"
    assert k["fields"]["oran"] == "hesap:oran" and "'A'" in k["sources"]["dijital.kitap"]["sql"]
    t = D.get_title(engine, T, "B", with_sales=False)
    _check(P.ekle(t, K.for_title(engine, T, "B", t)))

    for donem, platform in (("", 0), ("2026", p["id"]), ("2026-08", 0)):
        s = D.sales(engine, T, donem=donem, platform=platform)
        k = _check(P.ekle(s, K.for_sales(engine, T, s, donem=donem, platform=platform)))
        assert "rapor.csv" in k["formulas"]["satis"]["text"] and "Kitap Platformu 2026-08" in k["formulas"]["satis"]["text"]
        assert {"toplam.net", "toplam.adet", "sayac.kitap", "sayac.eslesmeyen", "toplam.logoAdet", "kart.adet"} <= set(k["fields"])
    assert s["aylik"][0]["netTl"] > 0


def test_meta_settings_and_status():
    out = {"ayarlar": {"oppMinQty": ST["oppMinQty"], "audioMinQty": ST["audioMinQty"], "audioGenres": [], "matchMinProb": 0.6,
                       "importMaxMb": 40},
           "okuma": {"ok": True, "sure": 3.4, "kitap": 12, "yazilan": {"yeni": 1}, "running": True, "since": 1759000000.0},
           "me": {"admin": True}}
    from semantic_layer.store.catalog_store import open_store

    e = open_store("sqlite://").engine
    D._ready.discard(id(e))
    D.ensure(e)
    k = _check(P.ekle(out, K.for_meta(e, T, ST, out)))
    assert "semantic_settings" in k["sources"]["dijital.ayarlar"]["sql"] and "DIJITAL_OPP_MIN_QTY" in k["sources"]["dijital.ayarlar"]["sql"]
