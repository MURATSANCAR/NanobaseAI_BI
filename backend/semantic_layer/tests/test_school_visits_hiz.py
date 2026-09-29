"""M31 Okul tanıtım — hız (2026-09-29): `GET /schools/plan` hazır cevapsız 35–177 sn ölçüldü.

Sözleşme:
- İstek canlı CRM + Logo okumasını beklemez: son okuma (bellekte, yoksa `semantic_school_snapshot`'ta saklanan) hemen
  döner; eskiyse ya da «Verileri yenile» geldiyse yenisi arkada okunur. Yalnız hiç okuma yokken ve zamanlayıcıda beklenir.
- Saklanan okuma açılınca satırlar aynı tür ve değerle gelir (Decimal, tarih, GUID) → aynı dizin, aynı rakam.
- Rakamlar değişmez: puan/kapsam, plan, kart ve liste eski hesapla (bu dosyadaki birebir kopyası) aynı; yazmadan sonra
  yalnız girdisi değişen okul yeniden puanlanır, sonuç yine eski tam hesapla aynı.
- Plan ve kart 68 bin okulun tam puanını beklemez (yalnız kendi okullarını hesaplar).
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from semantic_bridge import school_visits as SV
from semantic_bridge import school_visits_api as API
from semantic_bridge import school_visits_sources as src
from semantic_bridge.school_visits import fold
from semantic_layer.tests.test_school_visits import S1, S2, S3, T, _settings, _snap, engine  # noqa: F401 — fikstür

TODAY = date(2026, 9, 30)
WEEK = date(2026, 9, 28)


# ------------------------------------------------------------------ eski hesap (origin/main, değiştirilmeden kopya)


def _old_scored(engine, m):  # noqa: F811
    ctx = SV.load_context(engine, T)
    portal_last = SV.last_visits(engine, T)
    portal_owner = SV.portal_owners(engine, T)
    links = SV.approved_links(engine, T)
    st = m.settings
    refs = SV._ref_students(m)
    now = SV.today()
    fit_memo = {}
    out = {}
    owners = {}
    rules = set(st["owners"])
    for sid, sc in m.schools.items():
        crm = m.crm_visits(sid)
        crm_last = max((v["day"] for v in crm if v["done"] and v["day"]), default=None)
        last = max((x for x in (crm_last, portal_last.get(sid)) if x), default=None)
        if sc["grades"] not in fit_memo:
            fit_memo[sc["grades"]] = len(m.fitting_books(sc["grades"]))
        endeks = (ctx["ilce_endeks"].get(f"{fold(sc['il'])}|{fold(sc['ilce'])}") or {}).get("endeks")
        s = SV.score_school(sc, weights=st["weights"], ref_students=refs.get(sc["kurumTipiKod"], 0.0), last_visit=last,
                            orders=m.orders_by_school.get(sid, []), fitting=fit_memo[sc["grades"]], endeks=endeks,
                            endeks_range=ctx["endeksRange"], has_dealer=bool(links.get(sid)), now=now)
        s["lastVisit"] = last
        s["dealers"] = [{"code": x["cari_kodu"], "name": x["bayi_adi"]} for x in links.get(sid, [])]
        out[sid] = s
        who = set(portal_owner.get(sid, set()))
        if "sahip" in rules and sc["owner"]:
            who.add(sc["owner"])
        if "il" in rules and sc["ilOwner"]:
            who.add(sc["ilOwner"])
        if "ziyaret" in rules:
            who.update(v["owner"] for v in crm if v["owner"])
        owners[sid] = who
    return {"model": m, "ctx": ctx, "scores": out, "owners": owners, "links": links}


def _old_plan(engine, m, user, can_all, week, owner, everyone):  # noqa: F811
    res = _old_scored(engine, m)
    who = None if (everyone and can_all) else (owner if (owner and can_all) else user)
    rows = SV.load_plans(engine, T, week=week, owner=who)
    visits = SV.load_visits(engine, T, owner=who, since=datetime(week.year, week.month, week.day, tzinfo=SV.TZ))
    items = []
    for r in rows:
        sc = m.schools.get(r["ziyaret_yeri_id"]) or {}
        day = r.get("gun")
        conf = SV.conflicts(res["ctx"], day or week, day or (week + timedelta(days=4)), sc.get("il")) if r["durum"] != "iptal" else []
        v = API.Service._realized(r, visits, m)
        pv = SV.plan_view(r, v, conf)
        pv.update({"il": sc.get("il"), "ilce": sc.get("ilce"), "kademe": sc.get("kademe") or sc.get("gradesText"),
                   "students": sc.get("students"), "lastVisit": (res["scores"].get(r["ziyaret_yeri_id"]) or {}).get("lastVisit"),
                   "dealers": (res["scores"].get(r["ziyaret_yeri_id"]) or {}).get("dealers", [])})
        items.append(pv)
    nexts = []
    for r in SV.load_visits(engine, T, owner=who):
        if r.get("sonraki_tarih") and r.get("hatirlatildi") is None and r["sonraki_tarih"] <= week + timedelta(days=6):
            sc = m.schools.get(r["hedef_kimlik"]) or {}
            nexts.append({"visitId": r["id"], "school": r["hedef_kimlik"], "schoolName": sc.get("name"), "step": r.get("sonraki_adim"),
                          "day": SV._dstr(r["sonraki_tarih"]), "late": r["sonraki_tarih"] < SV.today(), "owner": r["sahip"]})
    nexts.sort(key=lambda x: x["day"] or "")
    cal = [e for e in res["ctx"].get("takvim") or [] if not (e["bitis"] < week.isoformat() or e["baslangic"] > (week + timedelta(days=6)).isoformat())]
    return {"week": week.isoformat(), "weekEnd": (week + timedelta(days=6)).isoformat(), "term": SV.term_of(week),
            "owner": who, "items": items, "nextSteps": nexts, "calendar": cal,
            "done": sum(1 for x in items if x["realized"]), "planned": sum(1 for x in items if x["state"] != "iptal"),
            "days": [{"day": (week + timedelta(days=i)).isoformat(), "label": API.DAYS_TR[i]} for i in range(5)]}


def _old_list_ids(res, user, can_all, *, il="", ilce="", kademe="", tur="", min_score=None, q="", kapsam="", sort="puan"):
    m = res["model"]
    qf = fold(q)
    search_all = len(qf) >= 3 and kapsam != "benim"
    mine = {sid for sid, who in res["owners"].items() if user in who}
    scope = (mine if kapsam == "benim" else None) if can_all else (None if search_all else mine)
    items = []
    for sid, sc in m.schools.items():
        if scope is not None and sid not in scope:
            continue
        if il and fold(sc["il"]) != fold(il):
            continue
        if ilce and fold(sc["ilce"]) != fold(ilce):
            continue
        if kademe and str(sc["kademeKod"] or "") != kademe and fold(sc["kademe"]) != fold(kademe):
            continue
        if tur and str(sc["kurumTuruKod"] or "") != tur:
            continue
        if min_score is not None and res["scores"][sid]["score"] < min_score:
            continue
        if qf and qf not in fold(sc["name"]) and qf not in fold(sc["code"]):
            continue
        items.append(sid)
    sc_ = res["scores"]
    key = {
        "ad": lambda x: (fold(m.schools[x]["name"]),),
        "ogrenci": lambda x: (-(m.schools[x]["students"] or -1), fold(m.schools[x]["name"])),
        "son": lambda x: (sc_[x]["lastVisit"] or "0000", fold(m.schools[x]["name"])),
    }.get(sort, lambda x: (-sc_[x]["score"], fold(m.schools[x]["name"])))
    items.sort(key=key)
    return items, len(mine)


# ------------------------------------------------------------------ yardımcılar


class _Src:
    """Sabit okuma (bellekte); `at` değişince yeni okuma sayılır."""

    def __init__(self):
        self.snap = _snap()
        self.snap["sorgular"] = []

    def snapshot(self, fresh=False):
        return self.snap


def _svc():
    return API.Service(_Src(), lambda: _settings(), lambda _p: None)


def _plan_row(pid, sid, owner, day, durum="oneri"):
    return {"id": pid * 32, "tenant_id": T, "sahip": owner, "sahip_ad": owner.title(), "donem": SV.term_of(WEEK),
            "hafta": WEEK, "gun": day, "ziyaret_yeri_id": sid, "okul_adi": "x", "puan": 50.0, "gerekce": "g",
            "model_gerekce": None, "durum": durum, "not": None, "onaylayan": None, "onay_zamani": None, "olusturan": owner,
            "olusturma": datetime.now(timezone.utc), "guncelleyen": None, "guncelleme": None}


def _seed(engine, m):  # noqa: F811
    """Bayi bağı, portal ziyaretleri, plan satırları, takvim ve ilçe endeksi."""
    SV.sync_history_links(engine, T, m)                                                   # S1 ↔ 120.01 onaylı
    SV.insert_plans(engine, [_plan_row("a", S1, "ayse", date(2026, 9, 29)), _plan_row("b", S3, "ayse", date(2026, 10, 1)),
                             _plan_row("c", "cccccccc-0000-0000-0000-000000000009", "ayse", None),
                             _plan_row("d", S2, "mehmet", date(2026, 9, 30), durum="iptal")])
    vals = SV.visit_values({"durum": "yapildi", "gerceklesen": "2026-09-29", "ilgi": "yuksek", "sonrakiAdim": "Teklif",
                            "sonrakiTarih": "2026-10-02"}, m, TODAY)
    SV.add_visit(engine, T, "ayse", "Ayşe", S1, vals)
    cal = SV.parse_context("takvim", SV.read_table({"csv": "baslangic;bitis;tur;ad;il\n2026-10-01;2026-10-01;tatil;Bayram;\n"}), {})
    SV.save_context(engine, T, "mudur", "takvim", cal["items"], "MEB", None)


# ------------------------------------------------------------------ okumanın saklanması


def test_pack_roundtrip_keeps_types_and_values():
    snap = {"schools": [{"id": uuid.UUID(S1), "tutar": Decimal("12.3400"), "degisti": datetime(2026, 5, 1, 9, 30),
                         "aware": datetime(2026, 5, 1, 9, 30, tzinfo=timezone.utc), "gun": date(2026, 5, 1), "b": b"\x00\x01",
                         "n": None, "f": 1.5, "i": 7, "ok": True, "s": "Kadıköy «ö»"}],
            "firms": {2025: "211", 2026: "411"}, "stock": {"15201001": 40.0}, "at": 1.5, "sorgular": [{"sql": "SELECT 1"}]}
    out = src.unpack(src.pack(snap))
    assert out == snap
    r = out["schools"][0]
    assert type(r["id"]) is uuid.UUID and type(r["tutar"]) is Decimal and str(r["tutar"]) == "12.3400"
    assert type(r["degisti"]) is datetime and r["degisti"].tzinfo is None and r["aware"].tzinfo is not None
    assert type(r["gun"]) is date and r["b"] == b"\x00\x01" and out["firms"] == {2025: "211", 2026: "411"}


def test_pack_writes_big_lists_in_pieces(monkeypatch):
    monkeypatch.setattr(src, "_CHUNK", 2)
    rows = [{"cari_kodu": f"120.{i:02d}", "adet": Decimal(i)} for i in range(5)]
    snap = {"dealerItems": rows, "empty": [], "two": rows[:2], "three": rows[:3], "firms": {}, "at": 2.0}
    assert src.unpack(src.pack(snap)) == snap


def test_saved_read_builds_the_same_model_as_the_live_read():
    snap = _snap()
    snap["schools"][0]["ogrenci"] = 1240
    snap["orders"][0]["tutar"] = Decimal("1500.25")
    snap["visits"][0]["gerceklesen"] = datetime(2025, 10, 1, 7, 0)
    a = SV.Model(snap, _settings(), {})
    b = SV.Model(src.unpack(src.pack(snap)), _settings(), {})
    assert a.schools == b.schools and a.visits == b.visits and a.visits_by_name == b.visits_by_name
    assert a.orders == b.orders and a.books == b.books and a.dealers == b.dealers and a.dealer_items == b.dealer_items


def test_store_roundtrip_and_old_shape_is_not_used(engine):  # noqa: F811
    snap = _snap()
    snap["at"] = time.time()
    assert SV.load_snapshot(engine) is None
    assert SV.save_snapshot(engine, snap) > 0
    assert SV.load_snapshot(engine) == snap
    snap["at"] += 1
    SV.save_snapshot(engine, snap)                                                        # üzerine: tek satır
    with engine.connect() as c:
        assert c.execute(SV.sa.select(SV.sa.func.count()).select_from(SV.SNAPSHOT)).scalar() == 1
    with engine.begin() as c:
        c.execute(SV.SNAPSHOT.update().values(bicim="eski-sorgular"))
    assert SV.load_snapshot(engine) is None                                               # sorgu şekli değişti


# ------------------------------------------------------------------ kaynak: istek okumayı beklemez


class _Slow(src.Source):
    def __init__(self, store=None):
        super().__init__(lambda: None, lambda: None, lambda: "S.dbo", lambda: _settings(), store=store)
        self.reads = 0
        self.gate = threading.Event()
        self.gate.set()
        self.heard = []
        self.on_read(lambda s: self.heard.append(s["n"]))

    def read(self):
        assert self.gate.wait(5)
        self.reads += 1
        return {"n": self.reads, "at": time.time()}


def test_request_gets_last_read_at_once_and_new_read_happens_in_background():
    s = _Slow()
    a = s.snapshot()                                                                      # hiç okuma yok: bekler
    assert a["n"] == 1 and s.heard == [1]
    assert s.snapshot() is a and s.reads == 1                                             # taze: okuma yok
    s._at -= src.TTL + 1                                                                  # eskidi
    s.gate.clear()
    t0 = time.monotonic()
    assert s.snapshot() is a                                                              # beklemeden son okuma
    assert time.monotonic() - t0 < 1.0 and s.busy
    assert s.snapshot(fresh=True) is a and s.reads == 1                                   # okuma sürüyor: ikincisi yok
    s.gate.set()
    s._bg.join(5)
    assert not s.busy and s.snapshot()["n"] == 2 and s.heard == [1, 2]
    s.snapshot(fresh=True)                                                                # az önce okundu: yeni okuma yok
    assert not s.busy and s.reads == 2
    s.started -= src.FRESH_MIN_SEC + 1                                                    # «Verileri yenile»: arkada
    assert s.snapshot(fresh=True)["n"] == 2
    s._bg.join(5)
    assert s.reads == 3
    assert s.snapshot(wait=True)["n"] == 4                                                # zamanlayıcı bekler


def test_failed_background_read_keeps_the_last_read():
    s = _Slow()
    a = s.snapshot()
    s._at -= src.TTL + 1

    def boom():
        raise RuntimeError("CRM yok")
    s.read = boom
    s.snapshot()
    s._bg.join(5)
    assert s.snapshot() is a and s.last_error == "CRM yok"


def test_after_restart_the_saved_read_is_used_without_touching_crm(engine):  # noqa: F811
    snap = _snap()
    snap["at"] = time.time()
    SV.save_snapshot(engine, snap)

    def boom():
        raise AssertionError("canlı okuma olmamalı")
    s = src.Source(boom, boom, lambda: "S.dbo", lambda: _settings(), store=SV.SnapshotStore(lambda: engine))
    heard = []
    s.on_read(heard.append)
    assert s.snapshot() == snap and not s.busy and heard == []                            # saklanan okuma yeni veri değil
    live = _Slow(store=SV.SnapshotStore(lambda: engine))
    live.snapshot(wait=True)                                                              # canlı okuma saklanır
    assert SV.load_snapshot(engine)["n"] == 1


# ------------------------------------------------------------------ servis: rakamlar eski hesapla aynı


def test_scores_equal_the_old_full_computation_also_after_writes(engine, monkeypatch):  # noqa: F811
    monkeypatch.setattr(SV, "today", lambda: TODAY)
    svc = _svc()
    m = svc.model(engine, T)
    SV.sync_history_links(engine, T, m)

    def same():
        res = svc.scored(engine, T)
        old = _old_scored(engine, res["model"])
        assert res["scores"] == old["scores"] and res["owners"] == old["owners"] and res["links"] == old["links"]
        return res

    first = same()
    assert same() is first                                                                # yazma yok: hazır sonuç
    SV.add_visit(engine, T, "mehmet", "Mehmet", S3, SV.visit_values({"durum": "yapildi", "gerceklesen": "2026-09-29",
                                                                        "ilgi": "orta"}, m, TODAY))
    second = same()
    assert second is not first and second["scores"][S2] == first["scores"][S2]
    SV.add_link(engine, T, "mudur", S2, m.dealers["120.02"], kaynak="elle", durum="onayli", puan=None, gerekce=None,
                approver="mudur")
    same()
    parsed = SV.parse_context("ilce_endeks", SV.read_table({"csv": "il;ilce;endeks\nİstanbul;Kadıköy;4,85\n"
                                                                   "İstanbul;Üsküdar;3,10\n"}), {})
    SV.save_context(engine, T, "mudur", "ilce_endeks", parsed["items"], "SEGE", None)       # aralık değişti: hepsi
    same()
    SV.insert_plans(engine, [_plan_row("e", S2, "zeynep", date(2026, 9, 29))])            # kapsam değişti
    assert "zeynep" in same()["owners"][S2]
    monkeypatch.setattr(SV, "today", lambda: TODAY + timedelta(days=1))                   # gün değişti
    same()


def test_plan_equals_old_and_does_not_score_every_school(engine, monkeypatch):  # noqa: F811
    monkeypatch.setattr(SV, "today", lambda: TODAY)
    svc = _svc()
    m = svc.model(engine, T)
    _seed(engine, m)
    for user, can_all, owner, everyone in (("ayse", False, None, False), ("mudur", True, None, True),
                                           ("mudur", True, "ayse", False), ("mehmet", True, None, False)):
        svc = _svc()
        m = svc.model(engine, T)
        new = svc.plan(engine, T, user, can_all, WEEK, owner, everyone)
        assert svc._scored is None                                                        # tam puan beklenmedi
        old = _old_plan(engine, m, user, can_all, WEEK, owner, everyone)
        assert new == old
        svc.scored(engine, T)                                                             # tam sonuç hazırken de aynı
        assert svc.plan(engine, T, user, can_all, WEEK, owner, everyone) == old
    ayse = _old_plan(engine, m, "ayse", False, WEEK, None, False)
    assert ayse["done"] == 1 and ayse["planned"] == 3 and ayse["calendar"]              # veri gerçekten sınandı
    s1 = next(x for x in ayse["items"] if x["school"] == S1)
    assert s1["lastVisit"] == "2026-09-29" and s1["dealers"] == [{"code": "120.01", "name": "Moda Kitabevi"}]
    assert next(x for x in ayse["items"] if x["school"] == S3)["conflicts"]                # 1 Ekim bayram


def test_card_and_list_equal_old(engine, monkeypatch):  # noqa: F811
    monkeypatch.setattr(SV, "today", lambda: TODAY)
    svc = _svc()
    m = svc.model(engine, T)
    _seed(engine, m)
    old = _old_scored(engine, m)
    for user, can_all in (("ayse", False), ("mehmet", True), ("zeynep", False)):
        fresh_svc = _svc()
        card = fresh_svc.card(engine, T, user, can_all, S1)
        assert fresh_svc._scored is None                                                  # kart tek okulu hesaplar
        s = old["scores"][S1]
        assert (card["score"], card["parts"], card["reason"], card["lastVisit"]) == (s["score"], s["parts"], s["reason"],
                                                                                      s["lastVisit"])
        assert card["inScope"] == (user in old["owners"][S1])
        fresh_svc.scored(engine, T)
        assert fresh_svc.card(engine, T, user, can_all, S1) == card
    cases = [{}, {"il": "istanbul"}, {"ilce": "Kadıköy"}, {"kademe": "3"}, {"kademe": "İlkokul"}, {"tur": "2"},
             {"q": "moda"}, {"q": "USKUDAR"}, {"min_score": 40.0}, {"sort": "ad"}, {"sort": "ogrenci"}, {"sort": "son"},
             {"kapsam": "benim"}]
    for user, can_all in (("ayse", True), ("ayse", False), ("mehmet", False)):
        for kw in cases:
            try:
                new = svc.list(engine, T, user, can_all, **kw)
            except SV.SchoolError:
                continue
            ids, mine = _old_list_ids(old, user, can_all, **kw)
            assert [x["id"] for x in new["items"]] == ids[:SV.PAGE_SIZE] and new["total"] == len(ids)
            assert new["mineCount"] == mine
            for x in new["items"]:
                o = old["scores"][x["id"]]
                assert (x["score"], x["reason"], x["lastVisit"], x["dealers"]) == (o["score"], o["reason"], o["lastVisit"],
                                                                                  o["dealers"])


def test_new_read_is_indexed_in_background_and_request_does_not_wait(engine, monkeypatch):  # noqa: F811
    monkeypatch.setattr(SV, "today", lambda: TODAY)
    svc = _svc()
    m1 = svc.model(engine, T)
    svc.scored(engine, T)
    new = _snap()
    new["sorgular"] = []
    new["at"] = 2.0
    new["schools"] = new["schools"][:2]
    svc.source.snap = new
    assert svc.model(engine, T) is m1                                                     # eski dizinle hemen döner
    svc._prep.join(5)
    m2 = svc.model(engine, T)
    assert m2 is not m1 and set(m2.schools) == {S1, S2}
    assert svc._scored[1]["model"] is m2                                                  # tam puan da arkada hazır


def test_term_report_and_dealers_do_not_need_full_scores(engine, monkeypatch):  # noqa: F811
    monkeypatch.setattr(SV, "today", lambda: TODAY)
    svc = _svc()
    m = svc.model(engine, T)
    _seed(engine, m)
    tr = svc.term_report(engine, T, "mudur", True, "2026-2027/1")
    assert svc._scored is None and tr["visits"]["portal"] == 1
    assert svc.term_report(engine, T, "mudur", True, "2026-2027/1", il="İSTANBUL")["byIl"] == tr["byIl"]
    assert svc.term_report(engine, T, "mudur", True, "2026-2027/1", il="Ankara")["byIl"] == []
    d = svc.dealers(engine, T, S3)
    assert svc._scored is None and d["candidates"]
    counts = {c["code"]: c for c in d["candidates"]}
    assert "120.02" in counts
