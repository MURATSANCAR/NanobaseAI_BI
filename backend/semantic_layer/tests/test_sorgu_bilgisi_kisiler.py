"""Sorgu bilgisi — kayıtlar ve kişiler: M12 üretim (/uretim), M8 serbest çalışanlar (/serbest-calisanlar), kişiler
(/kisiler), M7 yazar ilişkileri (/yazar-iliskileri).

Her rakam ucunda: kaynaksız rakam yok, kayıt tutarlı (SQL dolu, yer tutucu yok, köken kayıtlı, sır izi yok), bağlantı
logo|crm|portal. Davranış: üretim okuması ve yazar hazırlığı çalışan CRM/Logo metnini (firma/dönem ve yıl kopyası
yerinde) okuma kaydında saklar; istek anında okunan CRM/Logo metni çalıştırıcının fiziksel metnidir (RunLog).
"""
from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from semantic_bridge import author_copurchase as CP
from semantic_bridge import author_growth as G
from semantic_bridge import author_kaynak as AK
from semantic_bridge import author_relations as R
from semantic_bridge import author_reminders as M
from semantic_bridge import contributors_kaynak as CK
from semantic_bridge import editorial as E
from semantic_bridge import freelance as F
from semantic_bridge import freelance_kaynak as FK
from semantic_bridge import freelance_logo as FL
from semantic_bridge import production as PR
from semantic_bridge import production_kaynak as PK
from semantic_bridge import production_store as PS
from semantic_bridge import provenance as P
from semantic_bridge import rooms
from semantic_bridge import sorgu_kaydi as SK
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.test_author_copurchase import X, Y, Z, _order
from semantic_layer.tests.test_author_growth import ADVICE_INP, _snaps
from semantic_layer.tests.test_author_relations import GUID as AU_GUID
from semantic_layer.tests.test_author_relations import _day
from semantic_layer.tests.test_freelance import NOW as FL_NOW
from semantic_layer.tests.test_freelance import TODAY as FL_TODAY
from semantic_layer.tests.test_freelance import _accepted, _package, _person, _tasks
from semantic_layer.tests.test_production import CARD, _snap

T = "t1"
SCHEMA = "Timas_MSCRM.dbo"


def _check(out, ignore=()):
    k = out["kaynaklar"]
    assert not k.get("error"), k
    assert P.uncovered_numbers(out, ignore) == []
    assert P.problems(out) == []
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == []
        assert s["connection"] in ("logo", "crm", "portal")
    return k


# ================================================================== M12 üretim


class _Conn:
    """Sahte salt okunur bağlantı: sorgu metnindeki ilk eşleşen iğneye göre satır döner."""

    def __init__(self, db, answers):
        self.cfg = {"database": db, "password": "gizli"}
        self.answers = answers
        self.calls: list[str] = []

    def execute(self, sql, limit):
        self.calls.append(sql)
        for needle, rows in self.answers:
            if needle in sql:
                return [], [dict(r) for r in rows], False
        return [], [], False

    def close(self):
        pass


def _strip_firm(rows):
    return [{k: v for k, v in r.items() if k != "firma"} for r in rows]


def _production(tmp_path):
    s = _snap()
    crm = _Conn("CRMDB", [("new_UretimBase", s["cards"]),
                          ("StringMapBase", [{"attr": "new_matbaa", "code": 7, "label": "Örnek Matbaa"},
                                             {"attr": "new_uretimtipi", "code": 100000000, "label": "Kitap"},
                                             {"attr": "new_baskikartidurumu", "code": 1, "label": "Baskı Tekrarı"},
                                             {"attr": "new_baskikartidurumu", "code": 2, "label": "Yeni Baskı"}])])
    logo = _Conn("TIGERDB", [("sys.tables", [{"name": "LG_411_PRODORD"}]), ("L_CAPIPERIOD", [{"firma": 411, "donem": 1}]),
                             ("STFICHE", _strip_firm(s["receipts"])), ("SRVCARD", _strip_firm(s["costs"])),
                             ("o.PLNAMOUNT", _strip_firm(s["orders"]))])
    source = PR.Source(lambda: crm, lambda: logo, lambda: SCHEMA, lambda: date(2024, 1, 1), lambda: tmp_path)
    settings = PR.settings_from(lambda key, default="": default)
    return PR.Service(source, lambda: settings), source, settings


@pytest.fixture
def pr_engine():
    e = open_store("sqlite://").engine
    PS._ready.discard(id(e))
    PS.ensure(e)
    return e


def test_production_read_keeps_executed_sql(pr_engine, tmp_path):  # noqa: F811
    svc, source, _ = _production(tmp_path)
    snap = source.read()
    tags = {q["tag"]: q for q in snap["queries"]}
    assert {"crm.kartlar", "crm.secenekler", "logo.tablolar", "logo.donemler", "logo.emirler.411", "logo.girisler.411.01",
            "logo.faturalar.411.01"} <= set(tags)
    assert "LG_411_01_INVOICE" in tags["logo.faturalar.411.01"]["sql"] and "2024-01-01" in tags["logo.faturalar.411.01"]["sql"]
    assert tags["crm.kartlar"]["database"] == "CRMDB" and tags["logo.emirler.411"]["database"] == "TIGERDB"
    assert tags["logo.faturalar.411.01"]["rows"] == 2
    assert all("gizli" not in json.dumps(q) for q in snap["queries"])   # bağlantı dosyasından yalnız veritabanı adı


def test_production_every_endpoint(pr_engine, tmp_path):  # noqa: F811
    svc, source, settings = _production(tmp_path)
    now = date(2026, 9, 28)
    PS.add_quote(pr_engine, T, "ayse", "Ayşe", CARD, {"printer": "Örnek Matbaa", "unitPrice": "9"})
    ov = svc.overview(pr_engine, T, fresh=True, now=now)
    snap = source.last()
    k = _check(P.ekle(ov, PK.for_overview(pr_engine, T, ov, snap)), PK.NOT_RAKAM)
    fat = k["sources"]["uretim.okuma.logo.faturalar.411.01"]
    assert fat["sql"].startswith("USE [TIGERDB];") and "LG_411_01_STLINE" in fat["sql"] and fat["stats"]["rows"] == 2
    assert k["sources"]["uretim.okuma.crm.kartlar"]["sql"].startswith("USE [CRMDB];")

    lst = svc.list(pr_engine, T, durum="hepsi", now=now)
    _check(P.ekle(lst, PK.for_list(pr_engine, T, lst, snap)), PK.NOT_RAKAM)
    dl = svc.delays(pr_engine, T, now=now)
    _check(P.ekle(dl, PK.for_delays(pr_engine, T, dl, snap)), PK.NOT_RAKAM)
    pr = svc.printers(pr_engine, T, now=now)
    _check(P.ekle(pr, PK.for_printers(pr_engine, T, pr, snap)), PK.NOT_RAKAM)
    det = svc.detail(pr_engine, T, CARD, now=now)
    k = _check(P.ekle(det, PK.for_detail(pr_engine, T, det["id"], det, snap)), PK.NOT_RAKAM)
    assert CARD in k["sources"]["uretim.teklifler.kart"]["sql"]
    cal = svc.calendar(pr_engine, T, "2026-12-01")
    _check(P.ekle(cal, PK.for_calendar(pr_engine, T, cal, snap)), PK.NOT_RAKAM)
    meta = {"printers": ["Örnek Matbaa"], "settings": settings}
    _check(P.ekle(meta, PK.for_meta(pr_engine, T, meta, snap)), PK.NOT_RAKAM)


def test_production_old_read_has_no_origin_but_says_so(pr_engine, tmp_path):  # noqa: F811
    svc, source, _ = _production(tmp_path)
    ov = svc.overview(pr_engine, T, fresh=True, now=date(2026, 9, 28))
    old = dict(source.last())
    old.pop("queries")
    k = _check(P.ekle(ov, PK.for_overview(pr_engine, T, ov, old)), PK.NOT_RAKAM)
    assert not any(s.startswith("uretim.okuma.") for s in k["sources"])
    assert "ilk yenilemeden sonra" in k["formulas"]["kart"]["text"]


# ================================================================== kişiler


def _crm_run(answers):
    def run(sql):
        for needle, rows in answers:
            if needle in sql:
                return {"records": rows, "physicalSql": sql, "dbMs": 7, "computedAt": 1_790_000_000.0, "totalRows": len(rows)}
        return {"records": [], "physicalSql": sql, "dbMs": 1, "computedAt": 1_790_000_000.0, "totalRows": 0}
    return run


def test_contributors_list_roles_and_person():
    gid = "0a1b2c3d-1111-2222-3333-444455556666"
    run = _crm_run([("COUNT(*) AS n", [{"n": 2, "son12_kisi": 1, "katki": 5}]),
                    ("OFFSET", [{"ContactId": gid, "FullName": "Ayşe Yazar", "eser": 3, "son": "2026-01-01", "son12": 1}]),
                    ("new_Katilimsaglayan IN", [{"new_Katilimsaglayan": gid, "rol": "Yazar", "eser": 3}]),
                    ("AS kayit", [{"rol": "Yazar", "kayit": 10, "kisi": 4}]),
                    ("new_kisaozgecmis", [{"ContactId": gid, "FullName": "Ayşe Yazar", "new_kisaozgecmis": "x"}]),
                    ("new_sozlesmetarafiBase", [{"new_sozlesmeId": "s1", "new_name": "S-1", "statuscode": "Aktif",
                                                 "new_Telif": 10, "new_Odeme": 50}]),
                    ("new_projeBase", [{"new_projeId": "p1", "new_name": "Proje"}]),
                    ("new_eserkatilimBase e JOIN", [{"new_kitapId": "b1", "kitap": "Kitap", "rol": "Yazar"}])])
    roles = ["Yazar", "Tercüme"]
    out = SK.bagla_run(run, lambda r: E.contributors_page(SCHEMA, r, roles, 0),
                       lambda o, log: CK.for_contributors(o, log, SCHEMA, roles, 0))
    k = _check(out, CK.NOT_RAKAM)
    assert "N'Tercüme'" in k["sources"]["kisiler.sayim"]["sql"] and k["sources"]["kisiler.liste"]["stats"]["rows"] == 1
    assert "hesap:kisiBasi" == k["fields"]["kisiBasinaEser"]
    fac = SK.bagla_run(run, lambda r: E.role_facets(SCHEMA, r), lambda o, log: CK.for_roles(o, log, SCHEMA))
    _check(fac, CK.NOT_RAKAM)
    per = SK.bagla_run(run, lambda r: E.person(SCHEMA, r, gid), lambda o, log: CK.for_person(o, log, SCHEMA, gid))
    k = _check(per, CK.NOT_RAKAM)
    assert gid in k["sources"]["kisiler.sozlesmeler"]["sql"] and "sayac.eser" in k["fields"]
    # Kişisel veri kayda girmez: kişi adı yalnız sonuç satırıydı.
    assert "Ayşe Yazar" not in json.dumps(k, ensure_ascii=False)


# ================================================================== M8 serbest çalışanlar


@pytest.fixture
def fl_engine(monkeypatch, tmp_path):
    monkeypatch.setattr(F, "_today", lambda: FL_TODAY)
    monkeypatch.setattr(F, "_now", lambda: FL_NOW)
    monkeypatch.setenv("FREELANCE_DIR", str(tmp_path))
    e = open_store("sqlite://").engine
    F._ready.discard(id(e))
    F.ensure(e)
    return e


def test_freelance_every_endpoint(fl_engine):
    e = fl_engine
    p = _person(e, roles=("kapak", "cizer"), logoCard="320.01.001", email="ayse@ornek.com")
    pkg, _ = _accepted(e, p, "Kapak A", price=4000)
    _accepted(e, p, "Kapak B", units=2, price=1250.5)
    open_pkg = _package(e, [{"title": "Çizim 1", "units": 3, "unitPrice": 500}, {"title": "Çizim 2", "units": 2}])
    free = [t["id"] for t in _tasks(e, open_pkg["id"])]
    F.post_message(e, T, "editor1", "Editör", f"p:{open_pkg['id']}", {"kind": "ic", "body": "Not"})

    ov = F.overview(e, T, "editor2")
    ov.update(email={"configured": False, "sender": None}, me={"username": "editor2", "canManage": True, "canApprove": False})
    k = _check(P.ekle(ov, FK.for_overview(e, T, "editor2", ov)), FK.NOT_RAKAM)
    assert "semantic_freelance_tasks" in k["sources"]["serbest.ozet.gorevler"]["sql"]

    people = F.list_people(e, T, status="aktif")
    _check(P.ekle(people, FK.for_people(e, T, people, "aktif")), FK.NOT_RAKAM)
    person = F.get_person(e, T, p["id"])
    k = _check(P.ekle(person, FK.for_person(e, T, p["id"], person)), FK.NOT_RAKAM)
    assert p["id"] in k["sources"]["serbest.kisi"]["sql"]
    pkgs = F.list_packages(e, T, "editor2", status="")
    k = _check(P.ekle(pkgs, FK.for_packages(e, T, "editor2", pkgs, "")), FK.NOT_RAKAM)
    assert "'p:'" in k["sources"]["serbest.iletiler.paket"]["sql"]
    one = F.get_package(e, T, pkg["id"])
    _check(P.ekle(one, FK.for_package(e, T, pkg["id"], one)), FK.NOT_RAKAM)
    cap = F.capacity(e, T)
    _check(P.ekle(cap, FK.for_capacity(e, T, cap)), FK.NOT_RAKAM)
    sug = {"items": F.suggest(e, T, free)}
    _check(P.ekle(sug, FK.for_suggest(e, T, free, sug)), FK.NOT_RAKAM)
    pay = {"items": F.payable(e, T)}
    _check(P.ekle(pay, FK.for_payable(e, T, pay)), FK.NOT_RAKAM)
    doc = F.create_payout(e, T, "editor1", {"personId": p["id"]})
    lst = F.list_payouts(e, T)
    _check(P.ekle(lst, FK.for_payouts(e, T, lst)), FK.NOT_RAKAM)
    got = F.get_payout(e, T, doc["id"])
    _check(P.ekle(got, FK.for_payout(e, T, doc["id"], got)), FK.NOT_RAKAM)
    box = F.inbox(e, T, "editor2")
    assert box["unread"] > 0
    _check(P.ekle(box, FK.for_inbox(e, T, "editor2", box)), FK.NOT_RAKAM)


def test_freelance_statement_refactor_keeps_answers(fl_engine):
    """Okumalar *_stmt()'e ayrıldı (alt sorgular dahil); cevaplar aynı kalır."""
    e = fl_engine
    p = _person(e, roles=("kapak",))
    pkg, _ = _accepted(e, p)
    assert F.list_packages(e, T, "u", status="")["items"][0]["counts"]["onaylandi"] == 1
    assert F.get_package(e, T, pkg["id"])["tasks"][0]["deliveries"][0]["decision"] == "kabul"
    assert F.list_packages(e, T, "u", status="iptal") == {"items": [], "total": 0}


def test_freelance_logo_movements_show_the_executed_2026_copy():
    def run(sql):
        phys = sql
        if "TOP 1" in sql:
            return {"records": [{"CODE": "320.01.001", "DEFINITION_": "Ayşe Çizer", "SPECODE": "ÇİZER"}], "physicalSql": phys}
        return {"records": [{"DAY": "2026-07-01", "TRCODE": 46, "SIGN": 1, "AMOUNT": 5000},
                            {"DAY": "2026-07-10", "TRCODE": 21, "SIGN": 0, "AMOUNT": 4000}],
                "physicalSql": phys, "dbMs": 12, "computedAt": 1_790_000_000.0}

    out = SK.bagla_run(run, lambda r: FL.movements(r, "320.01.001"), lambda o, log: FK.for_logo(o, log, "320.01.001", None))
    k = _check(out, FK.NOT_RAKAM)
    sql = k["sources"]["serbest.logo.hareketler"]["sql"]
    assert "LG_411_01_CLFLINE" in sql and "'20260101'" in sql and k["sources"]["serbest.logo.hareketler"]["stats"]["rows"] == 2
    assert "Ayşe" not in json.dumps(k, ensure_ascii=False)


# ================================================================== M7 yazar ilişkileri


@pytest.fixture
def au_engine():
    e = open_store("sqlite://").engine
    for mod in (R, G, M, rooms):
        mod._ready.discard(id(e))
        mod.ensure(e)
    CP._ready.clear()
    CP.ensure(e)
    return e


def _author_seed(e):
    c = R.create_card(e, T, "ayse", {"name": "Portal Adayı", "owner": "ayse"})
    R.create_meeting(e, T, "ayse", "Ayşe", False, {"cardId": c["id"], "status": "yapildi", "date": _day(-2), "time": "10:00",
                                                   "topic": "t", "tone": "olumlu", "nextStep": "Dosya iste", "nextDue": _day(-1)})
    R.create_meeting(e, T, "ayse", "Ayşe", False, {"cardId": c["id"], "status": "planlandi", "date": _day(3), "time": "11:00",
                                                   "topic": "Randevu", "minutes": 45})
    row, _ = R.card_for_crm(e, T, "ayse", AU_GUID, "CRM Yazarı", "yazar")
    R.create_meeting(e, T, "ayse", "Ayşe", False, {"cardId": row.id, "status": "yapildi", "date": _day(-5), "time": "09:00",
                                                   "topic": "t2", "tone": "notr"})
    return c


def test_author_cards_agenda_reminders_card_and_crm(au_engine):
    e = au_engine
    c = _author_seed(e)
    cards = R.list_cards(e, T, "ayse")
    _check(P.ekle(cards, AK.for_cards(e, T, cards)), AK.NOT_RAKAM)
    ag = R.agenda(e, T, "ayse", False)
    k = _check(P.ekle(ag, AK.for_agenda(e, T, ag)), AK.NOT_RAKAM)
    assert ag["horizon"][:10] in k["sources"]["yazar.ajanda"]["sql"]          # çalışan ufuk
    mine = M.digests(e, T).get("ayse", {"randevu": [], "not": [], "adim": []})
    me = {"enabled": True, "smtp": False, "today": {key: len(v) for key, v in mine.items()}}
    _check(P.ekle(me, AK.for_reminders_me(e, T, me)), AK.NOT_RAKAM)
    det = R.card_detail(e, T, "ayse", False, c["id"])
    _check(P.ekle(det, AK.for_card(e, T, SCHEMA, det)), AK.NOT_RAKAM)
    by = R.by_crm(e, T, "ayse", False, AU_GUID)
    k = _check(P.ekle(by, AK.for_by_crm(e, T, SCHEMA, AU_GUID, by)), AK.NOT_RAKAM)
    assert "yazar.iz" in k["formulas"]["isi"]["inputs"]                   # CRM son izi ısının girdisi


def test_author_heatmap_live_and_prepared(au_engine, tmp_path, monkeypatch):
    e = au_engine
    _author_seed(e)
    month = datetime.now(R.TZ)

    def fetch_all(sql):
        if "UNION ALL" in sql and "tur" in sql:
            return [{"kisi": AU_GUID, "tur": "eser", "yil": month.year, "ay": month.month, "adet": 2}]
        if "ilk" in sql and "aktif" in sql:
            return [{"kisi": AU_GUID, "ilk": "2015-01-01", "son": "2026-01-01", "eser": 2, "sozlesme": 1, "aktif": 1}]
        return [{"ContactId": AU_GUID, "FullName": "Sözleşmeli", "sozlesme": 1, "en_yakin_bitis": "2026-12-01"}]

    status = {"intervalSeconds": 300, "refreshing": False, "crm": None, "sales": None}
    hm = dict(R.heatmap(SCHEMA, fetch_all, e, T, "ayse", loyalty=lambda: G.loyalty_map(fetch_all("ilk aktif"))), snapshot=status)
    k = _check(P.ekle(hm, AK.for_heatmap(e, T, SCHEMA, hm, None)), AK.NOT_RAKAM)
    assert "yazar.canli.olaylar" in k["sources"]

    crm = {"authors": fetch_all("x"), "events": fetch_all("UNION ALL tur"), "loyalty": fetch_all("ilk aktif"), "books": [],
           "pool": [{"ContactId": "p1", "FullName": "Aday", "new_projeId": "j1", "new_name": "P", "statuscode": "Açık",
                     "CreatedOn": "2026-09-01T10:00:00", "editor": "E", "kapali": 0}]}
    snaps, _ = _snaps(tmp_path, monkeypatch, crm, {month.year: []})
    snaps.snap.refresh(force=True)
    q = snaps.queries()
    assert {x["tag"] for x in q["crm"]} >= {"sozlesmeliYazarlar", "olaylar", "sadakat", "kitaplar", "havuz"}
    assert q["sales"] and f"V_SatisRaporu_{month.year}" in q["sales"][0]["sql"]
    hm2 = dict(R.heatmap(SCHEMA, fetch_all, e, T, "ayse", crm=snaps.crm_for_heatmap()), snapshot=snaps.status())
    k = _check(P.ekle(hm2, AK.for_heatmap(e, T, SCHEMA, hm2, q)), AK.NOT_RAKAM)
    assert "yazar.hazirlik.olaylar" in k["sources"]
    pool = dict(snaps.pool_page(e, T, 0), snapshot=snaps.status())
    k = _check(P.ekle(pool, AK.for_pool_snapshot(e, T, pool, q)), AK.NOT_RAKAM)
    assert "yazar.hazirlik.havuz" in k["formulas"]["havuz"]["inputs"]


def test_author_pool_live_similar_related(au_engine):
    e = au_engine
    run = _crm_run([("COUNT(*) OVER ()", [{"ContactId": AU_GUID, "FullName": "Deniz Yazar", "toplam": 3, "yazar": 1}]),
                    ("COUNT(DISTINCT k.ContactId)", [{"n": 1}]),
                    ("OFFSET", [{"ContactId": "0a1b2c3d-1111-2222-3333-444455556667", "FullName": "Aday", "proje": 2,
                                 "son": "2026-09-01"}]),
                    ("new_OlasYazarYazar IN", [])])
    status = {"intervalSeconds": 300, "refreshing": False, "crm": None, "sales": None}
    pool = SK.bagla_run(run, lambda r: dict(R.pool_crm(SCHEMA, r, e, T, "2024-01-01", 0), snapshot=status),
                        lambda o, log: AK.for_pool_live(e, T, o, log, SCHEMA, "2024-01-01", 0))
    k = _check(pool, AK.NOT_RAKAM)
    assert k["sources"]["yazar.havuz.sayim"]["stats"]["rows"] == 1
    sim = SK.bagla_run(run, lambda r: R.similar(SCHEMA, r, e, T, "Deniz Yazar"),
                       lambda o, log: AK.for_similar(o, log, SCHEMA, "Deniz Yazar"))
    _check(sim, AK.NOT_RAKAM)

    authors = {"1": {X}, "2": {Y}, "3": {Z}}
    # X + Y birlikte 4 sipariş, Z tek başına 10 sipariş: lift = 4 × 14 / (4 × 4) = 3,5 ≥ eşik.
    orders = [_order(f"xy{i}", "2026-09-01", ["1", "2"]) for i in range(4)] + [_order(f"z{i}", "2026-09-02", ["3"]) for i in range(10)]
    CP.sync(e, T, lambda path, q: {"data": orders[q["start"]:q["start"] + q["limit"]]}, since=date(2026, 9, 1))
    CP.compute(e, T, authors, {"1": "Kitap X", "2": "Kitap Y", "3": "Kitap Z"}, {X: "Yazar X", Y: "Yazar Y", Z: "Yazar Z"})
    rel = CP.related(e, T, X)
    assert rel["items"]
    k = _check(P.ekle(rel, AK.for_related(e, T, SCHEMA, X, 0, rel)), AK.NOT_RAKAM)
    assert "yazar.siparisler" in k["sources"]["yazar.capraz.liste"]["origin"]


def test_author_growth_prepared_live_and_advice(au_engine, tmp_path, monkeypatch):
    e = au_engine
    this = date.today().year
    crm = {"authors": [], "events": [], "loyalty": [{"kisi": AU_GUID.lower(), "ilk": "2015-01-01", "son": f"{this}-01-01",
                                                     "eser": 2, "sozlesme": 1, "aktif": 1}],
           "books": [{"kisi": AU_GUID, "new_kitapId": "b1", "new_name": "Kitap", "new_StokKodu": "K1", "new_EKitapStokKodu": None,
                      "new_ean13": None, "new_ilkyayintarihi": "2020-01-01", "CreatedOn": "2020-01-01"}], "pool": []}
    sales = {this: [{"kod": "K1", "ay": 1, "tur": "Satış", "miktar": 10, "net": 100}]}
    snaps, _ = _snaps(tmp_path, monkeypatch, crm, sales)
    snaps.snap.refresh(force=True)
    ready = snaps.growth_inputs(AU_GUID)
    run = _crm_run([])
    g = G.compute(SCHEMA, run, ready["logo"], e, T, AU_GUID, web_enabled=False, books_rows=ready["books"],
                  loyalty_row=ready["loyalty"], prepared=True)
    assert [q["asked"] for q in g["_sorgular"]["crm"]] == [G.contracts_sql(SCHEMA, AU_GUID)]
    out = dict(g, cached=True, preparedAt="2026-09-28T10:00:00+00:00", snapshot=snaps.status())
    k = _check(P.ekle(out, AK.for_growth(e, T, SCHEMA, AU_GUID, out, snaps.queries(), None)), AK.NOT_RAKAM)
    assert "_sorgular" not in out
    assert f"V_SatisRaporu_{this}" in k["sources"][f"yazar.hazirlik.satis.{this}"]["sql"]

    run2 = _crm_run([("new_EKitapStokKodu", [{"new_kitapId": "b1", "new_name": "Kitap", "new_StokKodu": "K1"}]),
                     ("ilk", [{"kisi": AU_GUID, "ilk": "2015-01-01", "son": "2026-01-01", "eser": 1, "sozlesme": 0, "aktif": 0}])])
    live = G.compute(SCHEMA, run2, lambda codes, a, b: ([{"kod": "K1", "yil": this, "ay": 1, "tur": "Satış", "miktar": 4,
                                                          "net": 40}], date(this, 8, 17), []),
                     e, T, AU_GUID, web_enabled=False)
    out = dict(live, snapshot=snaps.status())
    k = _check(P.ekle(out, AK.for_growth(e, T, SCHEMA, AU_GUID, out, None, None)), AK.NOT_RAKAM)
    assert "yazar.gelisim.kitaplar" in k["sources"] and "Logo satış sorgusu bu yolda kaydedilmez" in k["formulas"]["satis"]["text"]

    made = G.make_advice(e, T, "ayse", AU_GUID, ADVICE_INP,
                         lambda m: '{"ozet": "Son 12 ayda 1200 adet.", "oneriler": [{"baslik": "b", "neden": "n"}]}')
    _check(P.ekle(dict(made), AK.for_advice(e, T, AU_GUID, dict(made), "")), AK.NOT_RAKAM)
    got = {"advice": G.latest_advice(e, T, AU_GUID), "modelReady": True}
    _check(P.ekle(got, AK.for_advice(e, T, AU_GUID, got)), AK.NOT_RAKAM)
