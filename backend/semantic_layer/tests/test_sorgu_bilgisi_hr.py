"""Sorgu bilgisi · İK (kayıtlar, işe alım, bağlılık, eğitim, performans): her ucun cevabındaki her rakam, o istekte
portal veritabanında çalışan sorguya (değerleri yerinde) ya da Logo/CRM metnine ve bir hesaba bağlı.

Denetlenen: kaynaksız rakam yok (`uncovered_numbers`), kayıt tutarlı (`problems`), yer tutucu yok, İK kaynaklarında satır
sayısı hiç yazılmıyor, eşik altı anket birimi / sonucu ve eğitim anketi «gizli» hesabına bağlı ve o hesap sayı içermiyor.
Uçlar gerçek `register` işlevleriyle kurulur; yalnız oturum (ctx) ve Logo/CRM bağlantısı sahtedir.
"""
from __future__ import annotations

import json
import re
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from semantic_bridge import admin as admin_mod
from semantic_bridge import budget_sources as bsrc
from semantic_bridge import hr_api
from semantic_bridge import hr_core as H
from semantic_bridge import hr_engagement as E
from semantic_bridge import hr_kaynak as HK
from semantic_bridge import hr_learning as L
from semantic_bridge import hr_performance as PF
from semantic_bridge import hr_recruit as R
from semantic_bridge import hr_sources
from semantic_bridge import provenance as P
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.test_hr_engagement import _answer, _survey
from semantic_layer.tests.test_hr_recruit import _candidate, _position

TN = "t1"
CONF = {"HR_PRIVACY_MIN_GROUP": "3", "HR_TRAINING_ACCOUNTS": "770.01", "HR_RECRUIT_SLA_DAYS": "10",
        "HR_LEARNING_ALERT_DAYS": "30"}


class AllWho(H.Who):
    """Test kimliği: bütün İK anahtarları (kapsam kuralları uçların kendi işidir, burada sınanmaz)."""

    def can(self, *keys: str) -> bool:
        return True


CUR = {"user": "ikuzman"}


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    for mod in (H, R, L, PF, E):
        mod._ready.discard(e)
    H._purgers.clear()
    for mod in (R, L, PF, E):
        mod.ensure(e)
        mod.register_hooks()
    admin_mod.ensure(e)
    return e


@pytest.fixture
def seed(engine):
    """Bağlılık düzeni (Editörya → Çocuk, Yetişkin; Satış) + performans zinciri (Yayın: GM → Müdür → Ayşe, Ali) + İK."""
    ids: dict = {}
    ed, _ = H.save_unit(engine, TN, "ik", {"name": "Editörya"})
    cocuk, _ = H.save_unit(engine, TN, "ik", {"name": "Çocuk", "parentId": ed["id"]})
    yet, _ = H.save_unit(engine, TN, "ik", {"name": "Yetişkin", "parentId": ed["id"]})
    satis, _ = H.save_unit(engine, TN, "ik", {"name": "Satış"})
    yayin, _ = H.save_unit(engine, TN, "ik", {"name": "Yayın"})
    ids.update(ed=ed["id"], cocuk=cocuk["id"], yet=yet["id"], satis=satis["id"], yayin=yayin["id"])
    n = 0
    for u, count in (("cocuk", 6), ("yet", 2), ("satis", 5)):
        for _ in range(count):
            n += 1
            e, _ = H.save_employee(engine, TN, "ik", {"displayName": f"Kişi{n} Soyad{n}", "username": f"u{n}", "unitId": ids[u]})
            ids[f"u{n}"] = e["id"]
    mgr, _ = H.save_employee(engine, TN, "ik", {"displayName": "Editörya Müdürü", "username": "edmudur", "unitId": ids["ed"]})
    H.save_unit(engine, TN, "ik", {"managerEmployeeId": mgr["id"]}, ids["ed"])
    for key, name, user, boss in (("gm", "Genel Müdür", "gm", None), ("mdr", "Müdür Bey", "mudur", "gm"),
                                  ("ayse", "Ayşe Yılmaz", "ayse", "mdr"), ("ali", "Ali Kaya", "ali", "mdr"),
                                  ("ik", "İK Uzmanı", "ikuzman", None)):
        e, _ = H.save_employee(engine, TN, "ik", {"displayName": name, "username": user, "unitId": ids["yayin"],
                                                  "managerId": ids.get(boss) if boss else None})
        ids[key] = e["id"]
    return ids


def _fake_logo(sql: str):
    if "L_CAPIPERIOD" in sql:
        return [{"FIRMNR": 411, "BEGDATE": date(2026, 1, 1), "ENDDATE": date(2026, 12, 31)}]
    if "EMFLINE" in sql and "MAX(DATE_)" in sql:
        return [{"son": date(2026, 8, 17)}]
    if "EMFLINE" in sql:
        return [{"ay": 1, "hesap": "770.01", "hesap_adi": "Eğitim giderleri", "tutar": 1500.0}]
    if "temsilcili" in sql:
        return [{"satir": 10, "temsilcili": 7}]
    return []


def _fake_crm(sql: str):
    if "TeamMembership" in sql:
        return [{"TeamId": "t-1", "TeamName": "Satış ekibi", "UserId": "c-1"}]
    if "BusinessUnitBase" in sql:
        return [{"BusinessUnitId": "b-1", "Name": "Satış", "ParentId": None, "ManagerId": None}]
    if "SystemUserBase" in sql:
        return [{"SystemUserId": "c-1", "FullName": "Kişi Bir", "DomainName": "TIMAS\\kisi1", "AdGuid": None,
                 "BusinessUnitId": "b-1", "AccessMode": 0}]
    return []


@pytest.fixture
def client(engine, seed, monkeypatch):
    rt = SimpleNamespace(settings=SimpleNamespace(connection_file=None, tenant_id=TN), store=SimpleNamespace(engine=engine))
    monkeypatch.setattr(hr_api.HrContext, "ctx", lambda self, request: (engine, TN, AllWho(CUR["user"], CUR["user"], False)))
    monkeypatch.setattr(hr_api.HrContext, "system", lambda self: (engine, TN))
    monkeypatch.setattr(hr_api.HrContext, "llm", lambda self, label, priority=None: None)
    monkeypatch.setattr(bsrc, "runner", lambda path, *a, **k: _fake_logo)
    monkeypatch.setattr(hr_sources, "runner", lambda path, *a, **k: _fake_crm)
    from semantic_bridge import hr_engagement_api, hr_learning_api, hr_performance_api, hr_recruit_api

    app = FastAPI()
    hr = hr_api.register(app, lambda: rt, lambda request: None)
    hr.conf = lambda k: CONF.get(k, "")
    for mod in (hr_recruit_api, hr_learning_api, hr_performance_api, hr_engagement_api):
        mod.register(app, hr)
    return TestClient(app)


def _check(out: dict) -> dict:
    k = out.get("kaynaklar")
    assert k and not k.get("error"), k
    assert P.uncovered_numbers(out) == [], P.uncovered_numbers(out)
    assert P.problems(out) == []
    assert k["sources"], "en az bir sorgu olmalı"
    for s in k["sources"].values():
        assert s["sql"].strip() and P.placeholders_left(s["sql"]) == [], (s["id"], P.placeholders_left(s["sql"]))
        assert s["stats"] is None or s["stats"]["rows"] is None, s["id"]         # İK: satır sayısı yazılmaz
    for f in k["formulas"].values():
        assert not re.search(r"(?i)\b(python|postgres\w*|sqlalchemy|llm|vllm)\b", f["text"])
    json.dumps(out, default=str)
    return k


def _get(c: TestClient, path: str, user: str = "ikuzman") -> dict:
    CUR["user"] = user
    r = c.get(path)
    assert r.status_code == 200, (path, r.status_code, r.text[:400])
    return r.json()


# ------------------------------------------------------------------ yakalama


def test_capture_renders_the_executed_select_with_values(engine, seed):
    with HK.capture(engine) as got:
        H.list_employees(engine, TN, status="aktif", q="Kişi")
    sel = [g for g in got if g["kind"] == "portal"]
    assert sel and all(P.placeholders_left(g["sql"]) == [] for g in sel)
    assert any("semantic_hr_employees" in g["sql"] and "'aktif'" in g["sql"] for g in sel)
    with HK.capture(engine) as other:
        pass
    assert other == []                                     # yakalayıcı kapalıyken hiçbir şey birikmez


# ------------------------------------------------------------------ uçlar


def test_records_and_recruit_endpoints(client, engine, seed):
    pos = _position(engine)
    _candidate(engine, pos["id"])
    for path in ("/api/v1/hr/employees", "/api/v1/hr/units", "/api/v1/hr/notices", "/api/v1/hr/retention",
                 "/api/v1/hr/purge/preview", "/api/v1/hr/purge/runs", "/api/v1/hr/access-log",
                 "/api/v1/hr/recruit/pipeline", "/api/v1/hr/recruit/positions", f"/api/v1/hr/recruit/positions/{pos['id']}",
                 "/api/v1/hr/recruit/templates"):
        _check(_get(client, path))
    cand = _get(client, "/api/v1/hr/recruit/pipeline")
    first = next(c for col in cand["columns"].values() for c in col)
    _check(_get(client, f"/api/v1/hr/recruit/candidates/{first['id']}"))
    CUR["user"] = "ikuzman"
    pv = client.post("/api/v1/hr/employees/sync-preview")
    assert pv.status_code == 200, pv.text[:300]
    k = _check(pv.json())
    crm = [s for s in k["sources"].values() if s["connection"] == "crm"]
    assert crm and any("SystemUserBase" in s["sql"] for s in crm)


def test_engagement_endpoints_and_hidden_units(client, engine, seed):
    s = _survey(engine, minGroup=3, unitBreakdown=True)
    for n in range(1, 7):
        _answer(engine, s["id"], f"u{n}", {"enps": 10})
    for n in (7, 8):                                        # Yetişkin: 2 yanıt (eşik altı)
        _answer(engine, s["id"], f"u{n}", {"enps": 0})
    for n in (9, 10, 11):
        _answer(engine, s["id"], f"u{n}", {"enps": 5})
    E.close_survey(engine, TN, "ikuzman", s["id"])
    E.share_results(engine, TN, "ikuzman", s["id"])
    B = "/api/v1/hr/engagement"
    for path in (f"{B}/templates", f"{B}/surveys", f"{B}/surveys/{s['id']}", f"{B}/surveys/{s['id']}/progress",
                 f"{B}/surveys/{s['id']}/themes", f"{B}/trend", f"{B}/suggestions"):
        _check(_get(client, path))
    _check(_get(client, f"{B}/me/surveys", "u1"))
    _check(_get(client, f"{B}/suggestions/mine", "u1"))
    res = _get(client, f"{B}/surveys/{s['id']}/results")
    k = _check(res)
    hidden = [u for u in res["units"] if not u["shown"]]
    assert hidden, "eşik altı birim olmalı"
    for u in hidden:
        assert k["fields"][f"units[]:{u['unitId']}"] == "hesap:gizli"
    assert not re.search(r"\d", k["formulas"]["gizli"]["text"])       # gizli hesabı sayı taşımaz
    one = _get(client, f"{B}/surveys/{s['id']}/results?scope={seed['yet']}")
    assert one["suppressed"]
    mine = _get(client, f"{B}/my-units", "edmudur")
    km = _check(mine) if P.numeric_paths(mine) else mine["kaynaklar"]
    for r in mine["results"]:
        if r["suppressed"]:
            assert km["fields"][f"results[]:{r['survey']['id']}:{r.get('scope')}"] == "hesap:gizli"


def test_learning_endpoints_and_hidden_feedback(client, engine, seed):
    k = L.save_course(engine, TN, "ik", {"title": "İş sağlığı ve güvenliği", "kind": "zorunlu", "delivery": "ic",
                                         "validityDays": 365})[0]["id"]
    s = L.create_session(engine, TN, "ik", {"courseId": k, "startsAt": "2026-09-01T10:00:00+03:00", "employeeIds": [seed["ayse"]]})
    L.set_attendance(engine, TN, "ik", s["id"], [{"enrollmentId": s["enrollments"][0]["id"], "attendance": "katildi"}])
    L.close_session(engine, TN, "ik", s["id"])
    token = L.me(engine, TN, "ayse", None)["feedback"][0]["token"]
    L.submit_feedback(engine, TN, token, seed["ayse"], {"answers": {"genel": 5, "fayda": 4}, "comment": "Yararlıydı"})
    Lp = "/api/v1/hr/learning"
    for path in (f"{Lp}/dashboard", f"{Lp}/expiring", f"{Lp}/courses", f"{Lp}/sessions", f"{Lp}/sessions/{s['id']}",
                 f"{Lp}/certificates", f"{Lp}/needs", f"{Lp}/usage-map", f"{Lp}/guides", f"{Lp}/spend?year=2026"):
        _check(_get(client, path))
    for path in (f"{Lp}/me", f"{Lp}/me/usage", f"{Lp}/me/guides"):
        _check(_get(client, path, "ayse"))
    _check(_get(client, f"{Lp}/me/team", "mudur"))
    fb = _get(client, f"{Lp}/sessions/{s['id']}/feedback-summary")
    kf = _check(fb)
    assert fb["hidden"] is True                              # 1 yanıt < eşik 3
    assert kf["fields"]["averages"] == "hesap:gizli" and kf["fields"]["themes"] == "hesap:gizli"
    spend = _get(client, f"{Lp}/spend?year=2026")
    ks = _check(spend)
    logo = [x for x in ks["sources"].values() if x["connection"] == "logo"]
    assert logo and any("LG_411_01_EMFLINE" in x["sql"] and "770.01" in x["sql"] for x in logo)


def test_performance_endpoints(client, engine, seed):
    hr_scope = PF.Scope(engine, TN, H.Who("ikuzman", "ikuzman", False, frozenset({PF.F_CYCLE, PF.F_REVIEW_APPROVE,
                                                                                  PF.F_CALIBRATION, PF.F_GOAL_APPROVE})))
    ayse = PF.Scope(engine, TN, H.Who("ayse", "ayse", False, frozenset()))
    g, _ = PF.save_goal(engine, TN, ayse, {"title": "Redaksiyon süresini kısaltmak", "period": "2026-Q4"})
    form, _ = PF.save_form(engine, TN, "ik", {**PF.STARTER_FORM, "state": "yururlukte"})
    cy, _ = PF.save_cycle(engine, TN, "ik", {"name": "2026 yıllık", "periodStart": "2026-01-01", "periodEnd": "2026-12-31",
                                             "startsOn": "2026-12-01", "endsOn": "2026-12-31", "formTemplateId": form["id"],
                                             "units": [seed["yayin"]]})
    PF.cycle_transition(engine, TN, hr_scope, cy["id"], "open")
    st = PF.cycle_status(engine, TN, hr_scope, cy["id"])
    rid = next(p["reviewId"] for p in st["people"] if p["employeeId"] == seed["ayse"])
    Bp = "/api/v1/hr/performance"
    for path in (f"{Bp}/me", f"{Bp}/goals", f"{Bp}/goals/{g['id']}", f"{Bp}/goals/{g['id']}/progress"):
        _check(_get(client, path, "ayse"))
    for path in (f"{Bp}/team", f"{Bp}/team/{seed['ayse']}", f"{Bp}/reviews/{rid}"):
        _check(_get(client, path, "mudur"))
    for path in (f"{Bp}/cycles", f"{Bp}/cycles/{cy['id']}/status", f"{Bp}/cycles/{cy['id']}/calibration",
                 f"{Bp}/logo-salesman-fill?year=2026"):
        _check(_get(client, path))
    fill = _get(client, f"{Bp}/logo-salesman-fill?year=2026")
    assert any("LG_411_01_INVOICE" in s["sql"] for s in fill["kaynaklar"]["sources"].values() if s["connection"] == "logo")
