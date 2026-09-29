"""Sorgu bilgisi · M52 Tedarik ve baskı: her ucun cevabındaki her rakam bir kaynağa bağlı, SQL çalışmış metin.

Logo/CRM sahte çalıştırıcıyla okunur ama SQL'ler gerçek dosyalardan gerçek doldurmayla kurulur (`fill` + `Recorder`);
uçlar kaydı `kaynaklar` olarak döndürür. Denetlenen: kaynaksız rakam yok, kayıt tutarlı, SQL'de yer tutucu yok,
`/sources` artık şablon değil çalışan metni veriyor. Gerçek Logo/CRM kabulü: `scripts/acceptance/sorgu-bilgisi/g3_supply.py`.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from semantic_bridge import provenance as P
from semantic_bridge import supply as S
from semantic_bridge import supply_kaynak as K
from semantic_bridge import supply_sources as src
from semantic_bridge import supply_store as store
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.test_supply import card, gid

T = "t1"
Y = datetime.now(S.TZ).year
ALL = {"ozellik:tedarik.borc", "ozellik:tedarik.maliyet", "ozellik:tedarik.kapasite", "ozellik:tedarik.oneri-karar",
       "ozellik:tedarik.eslesme"}


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    store._ready.discard(id(e))
    store.ensure(e)
    return e


def _rows(sid: str) -> list[dict]:
    today = date.today()
    return {
        "logo_tedarikci_cari": [{"ref": 1, "kod": "320.01", "unvan": "A Matbaa Ltd", "ozel_kod": "MATBAALAR", "bakiye": 1000.0},
                                {"ref": 2, "kod": "320.02", "unvan": "Kağıtçı AŞ", "ozel_kod": "KAĞITÇILAR", "bakiye": 500.0}],
        "logo_tedarikci_vade": [{"ref": 1, "satir": 1, "vade": date(today.year, 1, 15), "tutar": 800.0, "kumulatif": 800.0,
                                 "fatura_no": "F1", "fatura_tarihi": date(today.year, 1, 1)},
                                {"ref": 1, "satir": 2, "vade": today, "tutar": 200.0, "kumulatif": 1000.0,
                                 "fatura_no": "F2", "fatura_tarihi": today}],
        "logo_cari_ozel_kod": [{"ozel_kod": "MATBAALAR", "cari": 1}, {"ozel_kod": "KAĞITÇILAR", "cari": 1}],
        "logo_baski_faturasi": [{"fatura_ref": 9, "satir_ref": 91, "tarih": date(today.year, 1, 20), "no": "BF1",
                                 "cari_kod": "320.01", "cari": "A Matbaa Ltd", "stok": "S1", "adet": 700, "tutar": 7000.0}],
        "logo_alis_fatura": [{"cari_kod": "320.01", "yil": today.year, "ay": 1, "tur": 4, "fatura": 1, "tutar": 8400.0,
                              "kdv": 1400.0}],
        "logo_uretim_giris": [{"yil": today.year, "ay": 1, "adet": 700, "fis": 1}],
        "logo_kagit_alis_satir": [{"tarih": date(today.year, 1, 5), "cari_kod": "320.02", "malzeme_kod": "K1",
                                   "malzeme": "1. hamur 80 gr", "birim": "KG", "miktar": 1000, "tutar": 30000}],
        "logo_tedarikci_faturalar": [{"tarih": date(today.year, 1, 20), "no": "BF1", "tur": 4, "tutar": 8400.0, "kdv": 1400.0,
                                      "aciklama": "Baskı"}],
        "logo_tedarikci_faturalar_tumu": [{"cari_kod": "320.01", "tarih": date(today.year, 1, 20), "no": "BF1", "tur": 4,
                                           "tutar": 8400.0, "kdv": 1400.0, "aciklama": "Baskı"}],
    }.get(sid, [])


class FakeRun:
    """Sahte bağlantı: dönem tablosu + `fill()` ile kurulmuş kaynaklar (hangi kaynak olduğu doldurmadan bilinir)."""

    def __call__(self, sql: str) -> list[dict]:
        if "L_CAPIPERIOD" in sql:
            return [{"FIRMNR": 211, "BEGDATE": date(2021, 1, 1), "ENDDATE": date(Y - 1, 12, 31)},
                    {"FIRMNR": 411, "BEGDATE": date(Y, 1, 1), "ENDDATE": date(Y, 12, 31)}]
        last = getattr(src._filled, "last", None)
        if last and last[2] == sql:
            return _rows(last[0])
        return []


def _production(cards):
    peek = {"since": f"{Y - 1}-01-01", "cards": [{"id": c["id"]} for c in cards], "at": 1_000_000.0, "crmMs": 30}
    return SimpleNamespace(
        cards=lambda e, t, fresh=False, now=None: (cards, {"since": f"{Y - 1}-01-01", "cards": [], "warnings": []}),
        source=SimpleNamespace(snapshot=lambda fresh=False: {"options": {"new_matbaa": {1: "A Matbaa"}}},
                               peek=lambda: peek, _schema=lambda: "Timas_MSCRM.dbo"))


def _client(engine, monkeypatch, perms: set[str]):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from semantic_bridge import supply_api

    monkeypatch.setattr(src, "runner", lambda path: FakeRun())

    def auth(request):
        return engine, T, "ayse", "Ayşe"

    cards = [card(1, qty=700, baski=f"{Y}-12-31", code="S1"),
             card(2, qty=500, baski=f"{Y}-11-30", printer="A Matbaa", stage="matbaada", code="S2"),
             card(3, qty=900, stage="tamam", depo=f"{Y}-01-10", bdone=f"{Y}-01-05", code="S3")]
    app = FastAPI()
    supply_api.register(app, {
        "auth": auth, "can": lambda u, k: k in perms, "is_admin": lambda u: False, "audit": lambda *a, **k: None,
        "conf": lambda k, d="": d or ("Timas_MSCRM.dbo" if k == "CRM_SCHEMA" else ""), "fresh": lambda: False,
        "require_caller": lambda r: None, "runtime": lambda: (engine, T), "production": _production(cards),
        "logo_file": lambda: "", "crm_file": lambda: "", "llm": lambda p: None, "send_mail": None,
    })
    return TestClient(app)


def _check(out: dict) -> dict:
    k = out.get("kaynaklar")
    assert k and not k.get("error"), k
    assert P.uncovered_numbers(out, K.NOT_RAKAM) == []
    assert P.problems(out) == []
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == [], (s["id"], P.placeholders_left(s["sql"]))
    json.dumps(out, default=str)
    return k


@pytest.mark.parametrize("perms", [set(), ALL])
def test_every_supply_endpoint_has_no_unsourced_number(engine, monkeypatch, perms):
    c = _client(engine, monkeypatch, perms)
    store.add_capacity(engine, T, "ayse", "Ayşe", {"matbaa": "A Matbaa", "kapasiteAdet": "5000"}, ["A Matbaa"])
    paths = ["/overview", "/load", "/paper", "/suppliers", "/suppliers/320.01", "/unbilled", "/incoming?aylar=6",
             "/suggestions", "/capacity"]
    if perms:
        paths += ["/payments?gun=30", "/cost-trend?kirilim=cilt"]
    for path in paths:
        r = c.get("/api/v1/supply" + path)
        assert r.status_code == 200, (path, r.text)
        _check(r.json())


def test_sources_endpoint_returns_executed_text_not_template(engine, monkeypatch):
    c = _client(engine, monkeypatch, ALL)
    out = c.get("/api/v1/supply/sources").json()
    texts = {s["id"]: s["sql"] for s in out["sources"]}
    assert texts, "okumada çalışan sorgu listelenmeli"
    for sid, t in texts.items():
        assert P.placeholders_left(t) == [], sid
        assert "{firma}" not in t and "{crm}" not in t and "{bas}" not in t
    assert any("LG_411_01_" in t for t in texts.values())
    assert any("Timas_MSCRM.dbo." in t for t in texts.values())


def test_debt_numbers_point_to_logo_queries_and_fifo_formula(engine, monkeypatch):
    c = _client(engine, monkeypatch, ALL)
    out = c.get("/api/v1/supply/suppliers").json()
    k = out["kaynaklar"]
    ref = k["fields"]["items[].bakiye"]
    assert ref == "hesap:borc" and "FIFO" in k["formulas"]["borc"]["text"]
    # bu yılın Logo firması (411) kopyası: kimlik firma ekiyle
    assert {"tedarik.logo_tedarikci_cari.411", "tedarik.logo_tedarikci_vade.411"} <= set(k["formulas"]["borc"]["inputs"])
    assert k["sources"]["tedarik.logo_tedarikci_cari.411"]["stats"]["rows"] == 2
    assert "LG_411_" in k["sources"]["tedarik.logo_tedarikci_cari.411"]["sql"]


def test_supplier_page_invoices_come_from_the_read_not_a_live_query(engine, monkeypatch):
    """Tedarikçi sayfası Logo'ya gitmez: faturalar turda okunan bütün tedarikçi faturalarından; «i» turda çalışan metni
    ve son okuma tablosunu (kökeniyle) gösterir."""
    c = _client(engine, monkeypatch, ALL)
    out = c.get("/api/v1/supply/suppliers/320.01").json()
    k = _check(out)
    assert {f["no"] for f in out["faturalar"]} == {"BF1"}
    assert "tedarik.logo_tedarikci_faturalar_tumu.411" in k["formulas"]["faturalar"]["inputs"]
    assert not any(s.startswith("tedarik.logo_tedarikci_faturalar.") for s in k["sources"])
    assert "tedarik.logo_tedarikci_faturalar_tumu.411" in k["sources"]["tedarik.portal.okuma"]["origin"]
    assert "semantic_supply_reads" in k["sources"]["tedarik.portal.okuma"]["sql"]


def test_recorder_keys_runs_by_source_and_firm():
    rec = src.Recorder(FakeRun())
    src.read_print_invoices(rec, ["211", "411"], date(Y - 1, 1, 1))
    assert set(rec.runs) == {"logo_baski_faturasi:211", "logo_baski_faturasi:411"}
    assert "LG_211_01_" in rec.runs["logo_baski_faturasi:211"]["sql"]
    rec("SELECT 1")                      # doldurulmamış metin kayda girmez
    assert len(rec.runs) == 2
