"""Sorgu bilgisi — Grup 4 pazarlama çekirdeği: M15 yeni kitap planı (liste, karne, emsal adayları, plan, geçmiş,
«CRM'e işlenecek») ve M18 aylık plan / föy (ay ekranı, çakışmalar, hedef açığı, föy listesi, tek föy).

Her uç için: cevaptaki her rakam bir kaynağa bağlı (`uncovered_numbers` boş), kayıt tutarlı (`problems` boş), SQL'lerde
yer tutucu yok, CRM/Logo SQL'i çalışan metin (şablon değil). Veriler yapaydır; gerçek CRM/Logo'da kopyala-çalıştır
kabulü `scripts/acceptance/sorgu-bilgisi/pazarlama_cekirdek.py` ile test sunucusunda yapılır.
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from semantic_bridge import budget as B
from semantic_bridge import provenance as PV
from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import foy as F
from semantic_bridge.marketing import kaynak_aylik as KA
from semantic_bridge.marketing import kaynak_plan as KP
from semantic_bridge.marketing import monthly as M
from semantic_bridge.marketing import monthly_gaps as MG
from semantic_bridge.marketing import plans as P
from semantic_layer.store.catalog_store import open_store

T = "t1"
SCHEMA = "Timas_MSCRM.dbo"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    for s in (C._ready, B._ready, M._ready, F._ready):
        s.discard(id(e))
    C.ensure(e)
    B.ensure(e)
    M.ensure(e)
    F.ensure(e)
    yield e
    for s in (C._ready, B._ready, M._ready, F._ready):
        s.discard(id(e))


def _check(out: dict, ignore=()) -> dict:
    k = out.get("kaynaklar")
    assert k and not k.get("error"), k
    assert PV.uncovered_numbers(out, ignore) == []
    assert PV.problems(out) == []
    assert k["sources"]
    for s in k["sources"].values():
        assert s["sql"].strip() and PV.placeholders_left(s["sql"]) == [], (s["id"], s["sql"][:200])
        assert s["connection"] in ("logo", "crm", "portal")
    json.dumps(out, default=str)
    return k


def _book(code, pub, **kw):
    b = {"kitapId": "11111111-2222-3333-4444-555555555555", "stokKodu": code, "ad": f"Kitap {code}", "yazar": "Yazar A",
         "yayinevi": "Timaş", "kitaplik": "Roman", "hedefKitle": "Yetişkin", "statu": None, "kapak": None,
         "tarihler": {"crm-kitap": pub, "crm-proje": None, "uretim-dagilim": None, "uretim-depo": None},
         "projeId": None, "projeAdi": None, "sorumlu": None, "sorumluHesap": "ayse"}
    b.update(kw)
    return b


class FakeCrm:
    def __init__(self, books=(), detail=None):
        self._books, self._detail = list(books), detail

    def schema(self):
        return SCHEMA

    def new_books(self, frm, to, fresh=False):
        return list(self._books)

    def book(self, stok, fresh=False):
        return self._detail

    def rivals(self, kitap_id):
        return [{"ad": "Rakip", "yayinevi": "X", "yazarlar": "Y", "satisAdedi": 1200, "listeFiyati": 180.0, "kategoriler": None,
                 "tanitim": None}]

    def special_days(self, kitap_id):
        return []

    def spend(self, since, fresh=False):
        return [{"id": "s1", "ad": "Basın", "tip": 1, "tipAdi": "Basın", "tutar": 1000.0, "baslangic": "2025-01-01", "stokKodu": None}]

    def campaigns(self, frm, to, fresh=False):
        return [{"id": "c1", "ad": "Kasım B2B", "tip": 1, "baslangic": "2026-11-01", "bitis": "2026-11-30", "mecra": 2,
                 "ekIskonto": 5.0, "netIskonto": 40.0, "planlananCiro": 100000.0, "gerceklesenCiro": 20000.0, "urunSayisi": 12}]

    def all_special_days(self, fresh=False):
        return [{"id": "d1", "ad": "Öğretmenler Günü", "hafta1": None, "hafta2": None, "tarih": "2020-11-24", "kitapSayisi": 7}]

    def region_targets(self, year, month, codes):
        return {c: {"adet": 300.0, "bolge": 4} for c in codes}

    def foy_books(self, codes, fresh=False):
        return {}

    def email_of(self, user):
        return None


def _approved_budget(engine, year, codes):
    """Onaylı bütçe planı + kitap hedefleri (hedef kaynağı)."""
    now = B._now()
    with engine.begin() as c:
        c.execute(B.PLANS.insert().values(id="BP1", tenant_id=T, year=year, version=1, title="Bütçe", scenario="temel",
                                          status="onayli", params_json="{}", basis_json="{}", created_by="x", created_at=now,
                                          updated_at=now))
        for code in codes:
            c.execute(B.BOOKS.insert().values(plan_id="BP1", stok_kodu=code, ad=f"Kitap {code}", segment="yeni", adet=1000, oneri_json="{}",
                                              ciro=200000.0, marj=0.4))


def _sales(engine, year, month, rows):
    with engine.begin() as c:
        c.execute(B.SALES.insert(), [{"year": year, "month": month, "stok_kodu": s, "adet": a, "ciro": ci, "maliyet": 0,
                                      "maliyetli_ciro": 0} for s, a, ci in rows])
    B.meta_set(engine, f"sales:{year}", {"rows": len(rows), "dbMs": 1200, "firm": "411"})
    B.meta_set(engine, "data_end", {"date": f"{year}-{month:02d}-28"})


# ------------------------------------------------------------------ M15


def test_new_books_every_number_has_a_source(engine):
    today = date.today()
    d = lambda n: (today + timedelta(days=n)).isoformat()  # noqa: E731
    books = [_book("A", d(20)), _book("B", d(90))]
    _approved_budget(engine, int(d(20)[:4]), ["A"])
    pid = C.create_plan(engine, T, "ayse", kind="yeni", baslik="B · plan", stok_kodu="B", yayin_tarihi=d(90),
                        yayin_kaynagi="crm-kitap", hedef={"planId": None})
    C.replace_lines(engine, T, "ayse", pid, [{"kanal": "basin", "tutar": 500}])
    trace: dict = {}
    frm, to = today, today + timedelta(days=120)
    out = P.new_books(engine, T, "ayse", FakeCrm(books), P.settings(lambda k: ""), frm=frm, to=to, trace=trace)
    assert trace["codes"] == ["A", "B"] and trace["planIds"] == [pid]
    out = PV.ekle(out, KP.for_new_books(engine, T, SCHEMA, P.settings(lambda k: ""), out, trace, frm, to))
    k = _check(out, KP.NOT_RAKAM)
    crm = k["sources"]["mkt.crm.yeni"]["sql"]
    # çalışan metin, tarih yerinde: CRM UTC saklar; İstanbul gününün başı (UTC+3) bir önceki gün 21:00
    assert "new_kitap" in crm and "{" not in crm and f"{(frm - timedelta(days=1)).isoformat()} 21:00:00" in crm
    assert k["fields"]["kpi.plansiz"].startswith("hesap:") and "mkt.planlar" in k["sources"]


def test_card_every_number_has_a_source_and_crm_sql_is_the_executed_text(engine):
    pub = (date.today() + timedelta(days=60)).isoformat()
    _approved_budget(engine, int(pub[:4]), ["N1"])
    _sales(engine, int(pub[:4]) - 1, 5, [("Y1", 10, 1000.0)])
    with engine.begin() as c:
        c.execute(B.BOOKINFO.insert().values(stok_kodu="Y1", ad="Yazarın öteki kitabı", yazar="Yazar A", in_logo=True))
    detail = {**_book("N1", pub), "turler": "Roman", "yas": [12, 16], "fiyat": 250.0, "sayfa": 320.0,
              "metinler": {"new_ozet": "Arka kapak"}, "proje": {"toplam": 50000.0, "basin": 10000.0, "oncelik": 2}}
    st = P.settings(lambda k: "")
    card = P.build_card(engine, T, FakeCrm(detail=detail), None, "N1", st)
    assert card["yazar"]["items"] and card["yazar"]["yillar"]
    out = PV.ekle(dict(card), KP.for_card(engine, T, SCHEMA, SimpleNamespace(), card, None))
    k = _check(out, KP.NOT_RAKAM)
    assert "N'N1'" in k["sources"]["mkt.crm.kitap"]["sql"] or "'N1'" in k["sources"]["mkt.crm.kitap"]["sql"]
    assert k["sources"]["mkt.karne"]["origin"]                                   # karne önbelleğinin asıl CRM sorgusu
    assert "logo.satis." + str(int(pub[:4]) - 1) in k["sources"]                 # yazar satışının asıl Logo sorgusu
    assert "sql" not in card["yazar"]                                            # eski, çalışmayan metin gitti


def test_emsal_candidates_use_the_snapshots_executed_sql(engine):
    snap = {"asOf": "2026-09-20", "sourceStats": {
        "crm_kitaplar": {"rows": 900, "dbMs": 800, "sql": "SELECT k.new_stokkodu FROM Timas_MSCRM.dbo.new_kitap AS k"},
        "crm_emsal": {"rows": 50, "dbMs": 100, "sql": "SELECT 1 AS emsal"},
        "logo_aylik_kanal": {"rows": 5000, "dbMs": 9000, "sql": "SELECT s.[Yıl] FROM dbo.V_SatisRaporu_2026 AS s"},
    }}
    state = SimpleNamespace(management_reports=SimpleNamespace(first_print=SimpleNamespace(load=lambda: (snap, None))))
    out = {"gerekli": True, "hazir": True, "items": [{"sira": 1, "stokKodu": "E1", "ad": "E", "yazar": None, "kitaplik": None,
                                                      "gerekce": [], "lansman": "2025-03", "ilk3": 100, "ilk6": 180, "ilk12": 300,
                                                      "gozlenenAy": 18}], "kaynak": "x"}
    out = PV.ekle(out, KP.for_emsal_candidates(state, out))
    k = _check(out, KP.NOT_RAKAM)
    assert k["sources"]["mkt.ilkbaski.logo_aylik_kanal"]["stats"]["rows"] == 5000
    # Görüntüde şablon (yer tutuculu) metin kalmışsa o kayıt açılmaz
    snap["sourceStats"]["logo_aylik_kanal"]["sql"] = "SELECT * FROM {satis:yil}"
    k2 = KP.for_emsal_candidates(state, out).to_dict()
    assert "mkt.ilkbaski.logo_aylik_kanal" not in k2["sources"]


def test_plan_events_and_todo_every_number_has_a_source(engine):
    pid = C.create_plan(engine, T, "ayse", kind="yeni", baslik="P · plan", stok_kodu="N1", yayin_tarihi="2026-11-15",
                        yayin_kaynagi="crm-kitap", hedef={"planId": "BP1", "year": 2026, "version": 1, "adet": 1000, "ciro": 200000.0})
    C.replace_lines(engine, T, "ayse", pid, [{"kanal": "basin", "tutar": 4000}, {"kanal": "dijital", "tutar": 1500}])
    C.set_fields(engine, pid, butce_cerceve=6000.0,
                 butce_cerceve_json=C.dump({"tutar": 6000.0, "kaynak": "oran", "oran": {"kaynak": "veri", "yil": 2025, "oran": 0.03}}),
                 zeki_json=C.dump({"emsal": [{"stokKodu": "E1", "ad": "E", "karar": "emsal", "olasilik": 0.91}], "dusen": 2}))
    C.add_material(engine, T, "ayse", pid, "foy", "Föy metni", "zeki", {"dusen": [], "dusenSayisi": 0})
    plan = C.plan_full(engine, T, pid)
    plan["ustOnayGerekli"], plan["eksikMateryal"] = False, ["sosyal"]
    out = PV.ekle(dict(plan), KP.for_plan(engine, T, plan, None))
    k = _check(out, KP.NOT_RAKAM)
    assert "mkt.oran.gider" in k["sources"] and "mkt.oran.ciro" in k["sources"]  # oranın dayanağı
    ev = PV.ekle({"items": C.events(engine, pid)}, KP.for_events(engine, pid))
    _check(ev)
    todo = PV.ekle({"items": P.crm_todo(plan, None), "planOnayli": False}, KP.for_todo(engine, T, plan, None))
    _check(todo)


# ------------------------------------------------------------------ M18


def _month_targets(monkeypatch):
    def fake(engine, tenant, year, codes=None, segment="", yayinevi="", with_actuals=True):
        aylik = [{"ay": i + 1, "adet": 10.0, "ciro": 1000.0} for i in range(12)]
        return {"year": year, "plan": {"id": "BP1", "version": 1, "title": "Bütçe", "scenario": "temel"},
                "items": [{"stokKodu": "N1", "segment": "yeni", "aylik": aylik, "hedef": {"adet": 120, "ciro": 12000.0, "marj": None}}]}
    monkeypatch.setattr(B, "approved_targets", fake)


def test_month_view_conflicts_gaps_and_events_every_number_has_a_source(engine, monkeypatch):
    _month_targets(monkeypatch)
    _approved_budget(engine, 2026, ["N1"])
    _sales(engine, 2026, 10, [("N1", 5, 500.0)])
    crm = FakeCrm(books=[_book("N1", "2026-11-10"), _book("N2", "2026-11-11")])
    st = M.settings(lambda k: "")
    M.build(engine, T, "ayse", crm, st, "2026-11")
    v = M.view(engine, T, "2026-11", st)
    v["foy"] = {"toplam": 2, "onayli": 0, "eksik": 1, "uyumsuz": 0, "eski": 0}
    v["varsayilanDonem"] = "2026-11"
    out = PV.ekle(v, KA.for_month(engine, T, SCHEMA, v, "TIGERDB"))
    k = _check(out, KA.NOT_RAKAM)
    assert "aylik.crm.kampanya" in k["sources"] and "aylik.crm.bolge.1" in k["sources"]
    assert k["sources"]["aylik.kalem"]["origin"]                                 # kalemi dolduran CRM/portal sorguları
    assert k["sources"]["logo.satis.2026"]["sql"].startswith("USE [TIGERDB];")    # önceki ayın asıl Logo sorgusu
    h = M.find_plan(engine, T, "2026-11")
    items = [x for x in M.items_of(engine, h["id"]) if x["cakisma"]]
    conf = PV.ekle({"donem": "2026-11", "items": [{"id": x["id"], "cakisma": x["cakisma"]} for x in items], "total": len(items)},
                   KA.for_conflicts(engine, T, h["id"]))
    _check(conf, KA.NOT_RAKAM)
    g = MG.with_paragraph(engine, T, MG.gaps(engine, T, "2026-11", {"N9": {"oran": 0.4, "eksik": 3000.0, "ad": "Dokuz"}}))
    _check(PV.ekle(g, KA.for_gaps(engine, T, "2026-11")), KA.NOT_RAKAM)
    _check(PV.ekle({"items": C.events(engine, h["id"])}, KA.for_month_events(engine, h["id"])))


def _raw(**kw):
    r = {"stok_kodu": "N1", "ad": "Kitap", "yazar": "Yazar", "yayinevi": "Timaş", "kitaplik": "Roman", "dizi": None,
         "hedef_kitle": "Genç", "yas_bas": 12, "yas_bit": 16, "siniflar": None, "ean13": "9786050812345", "isbn13": "9786050812345",
         "kdv_dahil_fiyat": 250.0, "perakende_fiyat": None, "uzeri_fiyat": 250.0, "foy_taslak_fiyat": "250 TL", "sayfa": 320,
         "ebat": "13,5x21", "cilt": "Amerikan Cilt", "kapak": None, "ilk_yayin": "2026-11-10",
         "new_TantmFyMetni": "Tanıtım.", "new_tanitimfoymetni": None, "new_kitapspotu": None, "new_ozet": "Arka kapak.",
         "new_kitabinonecikanyanlari": "- Güçlü", "new_editorunkitabaveyazaradairgorusleri": None}
    r.update(kw)
    return r


def test_logo_price_runs_are_recorded_and_shown_on_the_foy(engine):
    this_year = date.today().year
    views = [{"name": f"V_SatisRaporu_{y}"} for y in range(2020, this_year + 2)]

    def runner():
        def run(sql):
            if "sys.views" in sql:
                return views
            return [{"stok_kodu": "N1", "birim_fiyat": 240.0, "son_fiyat_degisikligi": None}]
        return run

    logo = F.LogoPrices(runner)
    prices, note = logo.read(["N1"], "satis")
    assert prices["N1"]["fiyat"] == 240.0 and note is None
    runs = logo.runs_for(["N1"])
    assert len(runs) == 2 and all(PV.placeholders_left(r["sql"]) == [] for r in runs)
    fst = F.settings(lambda k: "")
    F.upsert_from_crm(engine, T, "N1", "2026-11", _raw(), "2026-11-10", "crm-kitap", prices.get("N1"), note, fst)
    out = F.get(engine, T, "N1", fst["required"], "2026-11")
    out["crmTodo"], out["logo"], out["kitap"] = [], next((x for x in out["uyumsuzluk"] if x["tur"] == "fiyat-logo"), None), {}
    out = PV.ekle(out, KA.for_foy(engine, T, SCHEMA, out, logo, "TIGERDB"))
    k = _check(out, KA.NOT_RAKAM)
    assert any(s.startswith("foy.logo.fiyat.") for s in k["sources"])
    assert "foy.crm.alan" in k["sources"]["foy.kayit"]["origin"]
    rows = F.list_month(engine, T, "2026-11", fst["required"])
    page = {"donem": "2026-11", "donemAdi": "Kasım 2026", "items": rows,
            "kpi": {"toplam": 1, "onayli": 0, "onayda": 0, "eksik": 0, "uyumsuz": 1, "eski": 0, "hazir": 0},
            "notlar": [], "logoNotu": None, "gonderimler": F.sends_of(engine, T, "2026-11"), "zorunlu": fst["required"],
            "logoKaynak": "satis"}
    _check(PV.ekle(page, KA.for_foy_list(engine, T, SCHEMA, page, logo, None)), KA.NOT_RAKAM)
