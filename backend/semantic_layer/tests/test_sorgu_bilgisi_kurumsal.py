"""M32 Kurumsal satış ve B2B: her rakamın sorgu bilgisi. Portal SQL'i uçta çalışan ifade; tabloyu dolduran asıl Logo/CRM
SQL'i gece okumasında ÇALIŞAN metin (yıl kopyası LG_211 / LG_411, tarih penceresi ve kanal yerinde), okuma kaydında
(`semantic_corp_meta` «sorgular») saklanır ve köken olarak gösterilir. Bayi ayrıntısı anlık okunur: o istekte çalışan metin.

Veriler yapaydır; Logo ve CRM okuyucuları sahte `run` ile beslenir (gerçek kabul: scripts/acceptance/sorgu-bilgisi/kabul_kurumsal.py)."""
from __future__ import annotations

from datetime import date

import pytest

from semantic_bridge import corporate_sales as C
from semantic_bridge import corporate_sales_kaynak as K
from semantic_bridge import corporate_sales_sources as S
from semantic_bridge import provenance as P
from semantic_bridge.management.kaynak import is_template
from semantic_layer.tests.test_corporate_sales import ST, T, engine  # noqa: F401 — fikstür ve ayar

ST_LOGO = {**ST, "costSource": "logo"}
FIRMS = {2025: "211", 2026: "411"}
ALL_TAGS = {"donem", "veriSonu", "kurumCari", "kurumSatis", "crmKurum", "hacim", "stok", "fiyat", "bayiKitap", "maliyet",
            "crmKitap", "crmTema", "crmTemaAdlari", "bayiFatura", "bayiSatis", "crmB2b", "crmWeb"}


def _check(out, ignore=K.NOT_RAKAM):
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out, ignore) == []
    assert P.problems(out) == []
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == [] and not is_template(s["sql"]), s["id"]
        assert s["connection"] in ("logo", "crm", "portal")
    return k


# ---------------------------------------------------------------- sahte Logo ve CRM


def _logo(sql: str):
    if "L_CAPIPERIOD" in sql:
        return [{"FIRMNR": 211, "BEGDATE": date(2021, 1, 1), "ENDDATE": date(2025, 12, 31)},
                {"FIRMNR": 411, "BEGDATE": date(2026, 1, 1), "ENDDATE": date(2026, 12, 31)}]
    if "MAX(DATE_) AS son" in sql:
        return [{"son": date(2026, 8, 17)}]
    if "_CLCARD WHERE SPECODE2" in sql:
        return [{"ref": 10, "kod": "K001", "unvan": "Belediye", "il": "İstanbul", "kanal": "KURUM", "iskonto": 0, "pasif": 0}]
    if "ROW_NUMBER()" in sql:
        return [{"stok": "L1", "maliyet": 40.0, "gun": date(2026, 4, 1)}]
    if "AS onceki" in sql:
        return [{"stok": "L1", "son": 40, "onceki": 20}]
    if "AS bakiye" in sql:
        return [{"stok": "L1", "ad": "Liderlik 1", "bakiye": 500, "yil_adet": 900}]
    if "_PRCLIST" in sql:
        return [{"stok": "L1", "fiyat": 100.0, "liste": "SL1", "oncelik": 0, "kdv_dahil": 1, "cari_ozel": None, "cari": None,
                 "bas": date(2026, 1, 1)}]
    if "AS fatura, SUM(S.AMOUNT)" in sql:
        return [{"fatura": 1, "adet": 150, "brut": 1000.0, "net": 800.0}]
    if "WHERE C.CODE = N'" in sql:
        return [{"stok": "L1", "ad": "Liderlik 1", "adet": 12, "ciro": 600.0, "son": date(2026, 5, 1)}]
    kurum = "N'KURUM'" in sql
    new = "LG_411_" in sql
    if "_01_INVOICE AS I" in sql:
        if kurum:
            return [{"kod": "K001", "unvan": "Belediye", "kanal": "KURUM", "il": "İstanbul", "ref": 10, "yil": 2026, "ay": 3,
                     "fatura": 2, "son": date(2026, 3, 20)}] if new else []
        return [{"kod": "B1", "unvan": "Bayi", "kanal": "BAYI", "il": "Ankara", "ref": 20, "yil": 2026, "ay": 5, "fatura": 3,
                 "son": date(2026, 5, 10)}] if new else []
    if "AS ciro" in sql:
        if kurum:
            return ([{"kod": "K001", "yil": 2026, "ay": 3, "ciro": 1000.0, "adet": 10}] if new else
                    [{"kod": "K001", "yil": 2025, "ay": 3, "ciro": 800.0, "adet": 8},
                     {"kod": "K001", "yil": 2025, "ay": 10, "ciro": 500.0, "adet": 5}])
        return [{"kod": "B1", "yil": 2026, "ay": 5, "ciro": 900.0, "adet": 30}] if new else []
    raise AssertionError(sql)


def _crm(sql: str):
    if "new_siparisBase" in sql:
        return [{"kod": "B1", "ref": "20", "siparis": 4, "son": date(2026, 8, 1)}]
    if "new_webuserBase" in sql:
        return [{"kod": "B1", "ref": "20", "kullanici": 2}]
    if "new_new_kitap_new_temaBase" in sql:
        return [{"stok": "L1", "tema": "Liderlik ve yönetim"}]
    if "SELECT new_name AS tema" in sql:
        return [{"tema": "Liderlik ve yönetim"}]
    if "powerbikitap" in sql:
        return [{"stok": "L1", "yazar": "Yazar", "liste_fiyati": 110.0}]
    if "new_kitap k" in sql:
        return [{"stok": "L1", "ad": "Liderlik 1", "yayinevi": "Timaş", "kitaplik": "İş dünyası", "turler": None, "yaslar": None,
                 "hedef": 3, "yas_min": None, "yas_max": None, "ilk_yayin": None, "crm_fiyat": 110.0, "ozet": None}]
    if "new_KurumunTemsilcisi" in sql:
        return [{"id": "A1", "unvan": "Belediye", "kod": "K001", "ref": "10", "rol": 2, "kanal": 100000007, "temsilci": "Ali",
                 "temsilci_hesap": "TIMAS\\ali", "sahip": None, "sahip_hesap": None, "iys": 1, "eposta_yok": 0}]
    raise AssertionError(sql)


def _refresh(e, monkeypatch, logo=_logo, st=ST_LOGO):
    monkeypatch.setattr(S, "runner", lambda path: {"logo": logo, "crm": _crm}[path])
    r = C.Refresher(lambda: e, lambda: T, lambda: "logo", lambda: "crm", lambda: "Timas_MSCRM.dbo", lambda: st)
    return r.run()


# ---------------------------------------------------------------- okuma: çalışan SQL saklanır


def test_refresh_keeps_the_executed_sql_with_the_year_copy(engine, monkeypatch):  # noqa: F811
    assert _refresh(engine, monkeypatch)["ok"]
    items = C.meta_get(engine, "sorgular")["items"]
    assert ALL_TAGS <= {q["tag"] for q in items}
    assert all(q["rows"] is not None and q["dbMs"] is not None and q["at"] for q in items)
    assert not any(is_template(q["sql"]) for q in items)
    sales = [q["sql"] for q in items if q["tag"] == "kurumSatis"]
    assert any("LG_211_01_STLINE" in s for s in sales) and any("LG_411_01_STLINE" in s for s in sales)
    assert all("N'KURUM'" in s for s in sales)
    assert all("N'BAYI'" in q["sql"] for q in items if q["tag"] in ("bayiFatura", "bayiSatis"))


def test_failed_refresh_keeps_earlier_queries_for_steps_that_did_not_run(engine, monkeypatch):  # noqa: F811
    assert _refresh(engine, monkeypatch)["ok"]

    def broken(sql: str):
        if "AS bakiye" in sql:
            raise S.SourceError("stok okunamadı")
        return _logo(sql)

    assert not _refresh(engine, monkeypatch, logo=broken)["ok"]
    tags = {q["tag"] for q in C.meta_get(engine, "sorgular")["items"]}
    assert {"kurumSatis", "stok", "fiyat", "bayiFatura", "crmB2b"} <= tags
    assert C.merge_queries([{"tag": "a", "sql": "yeni"}], {"items": [{"tag": "a", "sql": "eski"}, {"tag": "b", "sql": "x"}]}) == [
        {"tag": "a", "sql": "yeni"}, {"tag": "b", "sql": "x"}]


# ---------------------------------------------------------------- uçlar


def test_summary_cites_the_logo_sql_that_filled_the_sales_table(engine, monkeypatch):  # noqa: F811
    _refresh(engine, monkeypatch)
    out = C.summary(engine, T, "ali", True, ST_LOGO)
    k = _check(P.ekle(out, K.for_summary(engine, T, ST_LOGO, out, "TIGERDB", "CRMDB")))
    src = k["sources"]["kurumsal.kurumCiroDonem"]
    logo = [k["sources"][o] for o in src["origin"]]
    assert logo and all(s["connection"] == "logo" for s in logo)
    assert any("LG_411_01_STLINE" in s["sql"] and s["sql"].startswith("USE [TIGERDB];") for s in logo)
    assert k["fields"]["kurumCiroBuyume"].startswith("hesap:")
    assert "kurumsal.okuma.crmKurum.1" in k["sources"]["kurumsal.kurumSayisi"]["origin"]
    assert k["sources"]["kurumsal.okuma.crmKurum.1"]["sql"].startswith("USE [CRMDB];")


def test_summary_without_a_logged_read_says_so_and_invents_nothing(engine):  # noqa: F811
    C.meta_set(engine, "data_end", {"date": "2026-08-17"})
    out = C.summary(engine, T, "ali", True, ST)
    k = _check(P.ekle(out, K.for_summary(engine, T, ST, out, None, None)))
    assert k["sources"]["kurumsal.kurumCiroDonem"]["origin"] == []
    assert "ilk okumada" in k["sources"]["kurumsal.kurumCiroDonem"]["description"]


def test_meta_accounts_account_books_themes(engine, monkeypatch):  # noqa: F811
    _refresh(engine, monkeypatch)
    meta = {"settings": {x: ST_LOGO[x] for x in ("discountApprovalPct", "marginMinPct", "silentDays", "reminderLeadDays")},
            "volume": C.meta_get(engine, "volume"), "volumeTiers": ST_LOGO["volumeTiers"], "vocabulary": C.vocabulary(engine, ST_LOGO),
            "status": {"running": False, "startedAt": 1.0, "last": C.meta_get(engine, "refresh")}}
    k = _check(P.ekle(meta, K.for_meta(engine, ST_LOGO, meta, "TIGERDB", "CRMDB")))
    assert any(o.startswith("kurumsal.okuma.hacim.") for o in k["sources"]["kurumsal.hacimGecmisi"]["origin"])
    assert "vocabularyCount" in k["fields"]

    lst = C.list_accounts(engine, T)
    assert lst["items"] and lst["items"][0]["buYil"] == pytest.approx(1000.0)
    _check(P.ekle(lst, K.for_accounts(engine, T, lst, logo_db="TIGERDB", crm_db="CRMDB")))
    acc = C.account_detail(engine, T, "K001")
    assert acc["gecenYil"] == pytest.approx(1300.0) and acc["yillar"]
    k = _check(P.ekle(acc, K.for_account(engine, T, "K001", acc, "TIGERDB", "CRMDB")))
    assert "buyume" in k["fields"] and "enCokAy" in k["fields"]

    books = C.find_books(engine, "Lider")
    assert books["items"][0]["fiyat"] == 100.0
    _check(P.ekle(books, K.for_books(engine, "Lider", 0, books, "TIGERDB", "CRMDB")))
    th = C.list_themes(engine, ST_LOGO, durum="onayli")
    assert th["total"] == 1
    k = _check(P.ekle(th, K.for_themes(engine, ST_LOGO, th, durum="onayli", logo_db="TIGERDB", crm_db="CRMDB")))
    assert any(o.startswith("kurumsal.okuma.crmTema.") for o in k["sources"]["kurumsal.temaSayilari"]["origin"])


def test_packages_have_a_row_record_per_alternative_and_cost_origin(engine, monkeypatch):  # noqa: F811
    _refresh(engine, monkeypatch)
    out = C.suggest_packages(engine, ST_LOGO, {"temalar": ["Liderlik ve yönetim"], "kisi": 10, "kitapSayisi": 1, "butce": 5000})
    assert out["alternatifler"]
    k = _check(P.ekle(out, K.for_packages(engine, T, ST_LOGO, out, "TIGERDB", "CRMDB")))
    assert "alternatifler[]:1" in k["fields"]
    assert any(o.startswith("kurumsal.okuma.maliyet.") for o in k["sources"]["kurumsal.maliyetLogo"]["origin"])
    S.register_cost_provider(None)
    k = _check(P.ekle(out, K.for_packages(engine, T, ST, out, None, None)))    # M9 yolu: onaylı analizler
    assert "kurumsal.maliyetM9" in k["sources"]


def test_opportunities_quotes_approvals_reminders(engine, monkeypatch):  # noqa: F811
    _refresh(engine, monkeypatch)
    o = C.create_opportunity(engine, T, "ali", {"accountRef": "K001", "ad": "Yılsonu paketi", "deger": 5000,
                                               "kararTarihi": "2026-10-01"})
    q = C.create_quote(engine, ST_LOGO, T, "ali", True, o["id"], {"kalemler": [{"stok": "L1", "adet": 20, "indirim": 35}]})
    C.submit_quote(engine, ST_LOGO, T, "ali", True, q["id"])
    lost = C.create_opportunity(engine, T, "ali", {"kurum": "X", "ad": "Y", "deger": 100})
    C.update_opportunity(engine, T, "ali", True, lost["id"], {"asama": "kaybedildi", "kayipSinif": "fiyat"})

    lst = C.list_opportunities(engine, T, "ali", True, True)
    k = _check(P.ekle(lst, K.for_opportunities(engine, T, lst)))
    assert "kalanGun" in k["fields"]
    ps = C.pipeline_summary(engine, T, "ali", True)
    _check(P.ekle(ps, K.for_pipeline_summary(engine, T, ps)))
    opp = C.opportunity(engine, T, "ali", True, True, o["id"])
    k = _check(P.ekle(opp, K.for_opportunity(engine, T, ST_LOGO, o["id"], opp, "TIGERDB", "CRMDB")))
    assert "teklifler[].taslak" in k["fields"]
    one = C.quote(engine, T, "ali", True, True, q["id"])
    _check(P.ekle(one, K.for_quote(engine, T, ST_LOGO, q["id"], one, "TIGERDB", "CRMDB")))
    ap = {"items": C.approval_queue(engine, T)}
    assert ap["items"]
    _check(P.ekle(ap, K.for_approvals(engine, T, ap)))
    rem = C.list_reminders(engine, T, ST_LOGO, ay="2026-10")
    k = _check(P.ekle(rem, K.for_reminders(engine, T, ST_LOGO, rem)))
    assert k["sources"]["kurumsal.hatirlatmalar"]["origin"] == ["kurumsal.hatirlatmaKaynagi.2026-10"]


def test_dealers_highlights_and_live_dealer_detail(engine, monkeypatch):  # noqa: F811
    _refresh(engine, monkeypatch)
    d = C.dealer_rows(engine, gun=60)
    assert d["items"] and d["items"][0]["b2bSiparis"] == 4
    k = _check(P.ekle(d, K.for_dealers(engine, ST_LOGO, d, "TIGERDB", "CRMDB")))
    origin = k["sources"]["kurumsal.bayiler"]["origin"]
    assert {o.split(".")[2] for o in origin} >= {"bayiFatura", "bayiSatis", "crmB2b", "crmWeb"}
    h = C.highlights(engine, ST_LOGO)
    assert h["total"] == 1
    _check(P.ekle(h, K.for_highlights(engine, ST_LOGO, h, "TIGERDB", "CRMDB")))

    ran: list[dict] = []
    x = C.dealer_detail(engine, C.logged(_logo, "logo", ran, {"p": "bayiAyrinti"}), FIRMS, "B1")
    assert ran and all("WHERE C.CODE = N'B1'" in q["sql"] for q in ran)
    k = _check(P.ekle(x, K.for_dealer(engine, ST_LOGO, "B1", x, ran, "TIGERDB", "CRMDB")))
    live = [s for sid, s in k["sources"].items() if sid.startswith("kurumsal.bayiAyrinti.")]
    assert {("LG_211_" in s["sql"], "LG_411_" in s["sql"]) for s in live} == {(True, False), (False, True)}
    assert all(s["sql"].startswith("USE [TIGERDB];") for s in live)
