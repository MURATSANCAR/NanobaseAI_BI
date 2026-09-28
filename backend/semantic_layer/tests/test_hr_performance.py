"""M56 Performans yönetimi: yönetici kapsamı (manager_id zinciri; zincir dışı 403 + erişim kaydı), hedef ağacı ve onay
(gönderen onaylayamaz), check-in ve revizyon, dönem/form akışı (öz → yönetici → paylaşım → yorum → İK onayı; yönetici bölümü
paylaşımdan önce çalışana kapalı), tamamlanma oranı, kalibrasyon (sistem puan üretmez), iş kayıtları özeti (sabit kalıp),
yorum maskesi (ad modele gitmez), Logo temsilci SQL'i, saklama/imha ve köprü kapıları.

Veriler yapaydır ve yalnız kuralları sınar; gerçek veriyle kabul test sunucusunda (scripts/acceptance/M56).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
import sqlalchemy as sa

from semantic_bridge import hr_core as H
from semantic_bridge import hr_engagement_text as T
from semantic_bridge import hr_performance as P
from semantic_bridge import hr_performance_sources as S
from semantic_layer.store.catalog_store import open_store

TN = "t1"
ALL = frozenset({P.F_GOAL_WRITE, P.F_GOAL_APPROVE, P.F_REVIEW_WRITE, P.F_WORK})
HR_KEYS = frozenset({P.F_CYCLE, P.F_REVIEW_APPROVE, P.F_CALIBRATION, P.F_GOAL_APPROVE})


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    H._ready.discard(e)
    P._ready.discard(e)
    P.ensure(e)
    H._purgers.clear()
    P.register_hooks()
    return e


@pytest.fixture
def org(engine):
    """GM → Müdür → (Ayşe, Ali); Veli başka birimde, başka yöneticide. İK uzmanı ayrı."""
    unit, _ = H.save_unit(engine, TN, "ik", {"name": "Editörya"})
    other, _ = H.save_unit(engine, TN, "ik", {"name": "Satış"})
    ids = {}
    for key, name, user, mgr, u in (("gm", "Genel Müdür", "gm", None, unit), ("mdr", "Müdür Bey", "mudur", "gm", unit),
                                    ("ayse", "Ayşe Yılmaz", "ayse", "mdr", unit), ("ali", "Ali Kaya", "ali", "mdr", unit),
                                    ("veli", "Veli Demir", "veli", None, other), ("ik", "İK Uzmanı", "ikuzman", None, other)):
        e, _ = H.save_employee(engine, TN, "ik", {"displayName": name, "username": user, "unitId": u["id"],
                                                  "managerId": ids.get(mgr) if mgr else None})
        ids[key] = e["id"]
    H.save_unit(engine, TN, "ik", {"managerEmployeeId": ids["mdr"]}, unit["id"])
    ids["unit"], ids["other"] = unit["id"], other["id"]
    return ids


def sc(engine, user, keys=frozenset()):
    return P.Scope(engine, TN, H.Who(user, user, False, frozenset(keys)))


# ------------------------------------------------------------------ kapsam


def test_team_is_the_manager_chain_and_outsiders_are_denied_and_logged(engine, org):
    gm, mdr, ayse = sc(engine, "gm", ALL), sc(engine, "mudur", ALL), sc(engine, "ayse")
    assert mdr.team == {org["ayse"], org["ali"]} and mdr.direct == {org["ayse"], org["ali"]}
    assert gm.team == {org["mdr"], org["ayse"], org["ali"]}          # dolaylı ekip dahil
    assert ayse.team == set() and ayse.me_id == org["ayse"]
    assert {p["id"] for p in P.team_view(engine, TN, mdr)["people"]} == {org["ayse"], org["ali"]}
    assert P.team_view(engine, TN, gm, direct_only=True)["people"][0]["id"] == org["mdr"]
    veli = sc(engine, "veli", ALL)
    g, _ = P.save_goal(engine, TN, ayse, {"title": "Redaksiyon süresini kısaltmak", "period": "2026-Q4"})
    with pytest.raises(H.HrError) as e:
        P.get_goal(engine, TN, veli, g["id"])
    assert e.value.status == 403
    with engine.connect() as c:
        row = c.execute(sa.select(H.ACCESS_LOG).where(H.ACCESS_LOG.c.action == "reddedildi")).first()
    assert row.username == "veli" and row.subject_id == org["ayse"]


# ------------------------------------------------------------------ hedefler


def test_goal_tree_approval_needs_second_person_in_chain(engine, org):
    gm, mdr, ayse, ali = sc(engine, "gm", ALL), sc(engine, "mudur", ALL), sc(engine, "ayse"), sc(engine, "ali", ALL)
    company, _ = P.save_goal(engine, TN, gm, {"level": "sirket", "title": "Yıllık ciro hedefi", "period": "2026"})
    assert P.goal_transition(engine, TN, gm, company["id"], "submit")["state"] == "onayda"
    assert P.goal_transition(engine, TN, gm, company["id"], "approve")["state"] == "yururlukte"   # şirket: üst yönetim kararı
    unit_goal, _ = P.save_goal(engine, TN, mdr, {"level": "birim", "unitId": org["unit"], "title": "Termin tutma",
                                                 "period": "2026", "parentGoalId": company["id"]})
    with pytest.raises(H.HrError):                      # Ayşe birim hedefi yazamaz
        P.save_goal(engine, TN, ayse, {"level": "birim", "unitId": org["unit"], "title": "x", "period": "2026"})
    mine, _ = P.save_goal(engine, TN, ayse, {"title": "Redaksiyon süresi", "period": "2026-Q4", "parentGoalId": unit_goal["id"],
                                             "weight": 40, "targetValue": "10"})
    assert mine["aligned"] and mine["ownerEmployeeId"] == org["ayse"]
    with pytest.raises(H.HrError):                      # kişi hedefi kişi hedefine bağlanmaz
        P.save_goal(engine, TN, ayse, {"title": "y", "period": "2026", "parentGoalId": mine["id"]})
    with pytest.raises(H.HrError):                      # başka yılın hedefine bağlanmaz
        P.save_goal(engine, TN, ayse, {"title": "y", "period": "2025", "parentGoalId": unit_goal["id"]})
    P.goal_transition(engine, TN, ayse, mine["id"], "submit")
    with pytest.raises(H.HrError):                      # Ali ekip zincirinde değil
        P.goal_transition(engine, TN, ali, mine["id"], "approve")
    with pytest.raises(H.HrError):                      # geri gönderirken gerekçe şart
        P.goal_transition(engine, TN, mdr, mine["id"], "reject")
    assert P.goal_transition(engine, TN, mdr, mine["id"], "approve")["state"] == "yururlukte"
    with pytest.raises(H.HrError):                      # yürürlükteki hedef düzenlenmez, revizyon ister
        P.save_goal(engine, TN, ayse, {"title": "yeni"}, mine["id"])


def test_checkin_and_revision_flow(engine, org):
    mdr, ayse = sc(engine, "mudur", ALL), sc(engine, "ayse")
    g, _ = P.save_goal(engine, TN, ayse, {"title": "Hedef", "period": "2026-Q4", "targetValue": 10})
    P.goal_transition(engine, TN, ayse, g["id"], "submit")
    P.goal_transition(engine, TN, mdr, g["id"], "approve")
    with pytest.raises(H.HrError):
        P.add_checkin(engine, TN, ayse, g["id"], {"progressPct": 140})
    out = P.add_checkin(engine, TN, ayse, g["id"], {"progressPct": 50, "note": "Yarısı bitti"})
    assert out["lastCheckin"]["progressPct"] == 50 and len(out["checkins"]) == 1
    rv = P.request_revision(engine, TN, ayse, g["id"], {"changes": {"targetValue": "12"}, "reason": "Kapsam büyüdü"})
    assert rv["openRevision"]["changes"] == {"targetValue": 12.0}
    with pytest.raises(H.HrError):                      # ikinci açık talep yok
        P.request_revision(engine, TN, ayse, g["id"], {"changes": {"title": "z"}, "reason": "r"})
    with pytest.raises(H.HrError):                      # talep eden onaylayamaz (yetkisi olsa bile)
        P.decide_revision(engine, TN, sc(engine, "ayse", ALL), rv["openRevision"]["id"], "onay")
    done = P.decide_revision(engine, TN, mdr, rv["openRevision"]["id"], "onay")
    assert done["targetValue"] == 12.0 and done["openRevision"] is None


def test_period_range():
    assert P.period_range("2026-Q4") == (date(2026, 10, 1), date(2026, 12, 31))
    assert P.period_range("2026-Q1") == (date(2026, 1, 1), date(2026, 3, 31))
    assert P.period_range("2026") == (date(2026, 1, 1), date(2026, 12, 31))
    with pytest.raises(H.HrError):
        P.period_range("2026-Q5")


def test_system_measure_is_closed_until_setting_opens_it(engine, org):
    ayse = sc(engine, "ayse")
    body = {"title": "Satış", "period": "2026", "measureKind": "sistem", "systemMeasure": "logo_net_satis", "measureRef": "S01"}
    with pytest.raises(H.HrError):
        P.save_goal(engine, TN, ayse, body)
    g, _ = P.save_goal(engine, TN, ayse, body, system_measures_on=True)
    assert g["measureRef"] == "S01" and g["unitLabel"] == "₺"


def test_logo_salesman_sql_is_invoiced_lines_net_of_returns():
    sql = S.salesman_net_sql("411", "S01", date(2026, 1, 1), date(2026, 8, 17))
    assert "S.INVOICEREF <> 0" in sql and "S.LINETYPE = 0" in sql and "S.CANCELLED = 0" in sql
    assert "TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET" in sql and "TRCODE IN (2,3,7,8,9)" in sql
    assert "S.DATE_ < '2026-08-18'" in sql and "M.CODE = N'S01'" in sql and "LG_411_SLSMAN" in sql
    with pytest.raises(S.SourceError):
        S.salesman_net_sql("411", "x'; DROP TABLE y--", date(2026, 1, 1), date(2026, 1, 2))
    calls = []

    def run(sql):
        calls.append(sql)
        if "L_CAPIPERIOD" in sql:
            return [{"FIRMNR": 211, "BEGDATE": "2021-01-01", "ENDDATE": "2025-12-31"}, {"FIRMNR": 411, "BEGDATE": "2026-01-01", "ENDDATE": "2026-12-31"}]
        return [{"net": 100.0 if "LG_411" in sql else 50.0, "fatura": 2, "son": "2026-08-17"}]
    out = S.salesman_net(run, "S01", date(2025, 12, 1), date(2026, 1, 31))
    assert out["value"] == 150.0 and [y["firm"] for y in out["years"]] == ["211", "411"]   # yıl başına tek firma


# ------------------------------------------------------------------ dönem ve değerlendirme


def _cycle(engine, org, hr):
    form, _ = P.save_form(engine, TN, "ik", {**P.STARTER_FORM, "state": "yururlukte"})
    cy, _ = P.save_cycle(engine, TN, "ik", {"name": "2026 yıllık", "periodStart": "2026-01-01", "periodEnd": "2026-12-31",
                                            "startsOn": "2026-12-01", "endsOn": "2026-12-31", "formTemplateId": form["id"],
                                            "units": [org["unit"]]})
    return P.cycle_transition(engine, TN, hr, cy["id"], "open")


def test_review_flow_hides_manager_part_until_shared_and_hr_approves(engine, org):
    hr = sc(engine, "ikuzman", HR_KEYS)
    cy = _cycle(engine, org, hr)
    assert cy["added"] == 4                                 # Editörya birimi: GM, müdür, Ayşe, Ali
    st = P.cycle_status(engine, TN, hr, cy["id"])
    rid = next(p["reviewId"] for p in st["people"] if p["employeeId"] == org["ayse"])
    ayse, mdr = sc(engine, "ayse"), sc(engine, "mudur", ALL)
    with pytest.raises(H.HrError):                          # öz değerlendirmeyi yalnız çalışan yazar
        P.save_review(engine, TN, mdr, rid, {"self": {}})
    P.save_review(engine, TN, ayse, rid, {"self": {"ratings": {"is_kalitesi": 4}, "notes": {"guclu": "Terminler"}}}, submit="self")
    with pytest.raises(H.HrError):
        P.save_review(engine, TN, ayse, rid, {"self": {}})   # teslimden sonra değişmez
    with pytest.raises(H.HrError):                          # genel puan olmadan teslim yok
        P.save_review(engine, TN, mdr, rid, {"manager": {"notes": {"guclu": "iyi"}}}, submit="manager")
    P.save_review(engine, TN, mdr, rid, {"manager": {"overall": 4, "ratings": {"zaman": 5}, "notes": {"guclu": "iyi"}}}, submit="manager")
    assert P.get_review(engine, TN, ayse, rid)["manager"] is None           # paylaşılmadan çalışana kapalı
    with pytest.raises(H.HrError):                          # paylaşılmadan onay yok
        P.review_action(engine, TN, hr, rid, "approve", {})
    P.review_action(engine, TN, mdr, rid, "share", {"meetingAt": "2026-12-20T10:00:00+03:00"})
    seen = P.get_review(engine, TN, ayse, rid)
    assert seen["manager"]["overall"] == 4 and seen["can"]["comment"]
    P.review_action(engine, TN, ayse, rid, "comment", {"comment": "Katılmıyorum", "objection": True})
    with pytest.raises(H.HrError):                          # değerlendiren yönetici onaylayamaz
        P.review_action(engine, TN, sc(engine, "mudur", ALL | {P.F_REVIEW_APPROVE}), rid, "approve", {})
    done = P.review_action(engine, TN, hr, rid, "approve", {"note": "Görüşüldü"})
    assert done["state"] == "onaylandi" and done["objection"]
    st = P.cycle_status(engine, TN, hr, cy["id"])
    assert st["total"] == 4 and st["selfDone"] == 1 and st["managerDone"] == 1 and st["selfRate"] == 0.25 and st["objections"] == 1
    assert st["noManager"] == 1                               # GM'nin yöneticisi yok
    cal = P.calibration(engine, TN, hr, cy["id"])
    assert cal["overall"] == [0, 0, 0, 1, 0] and cal["units"][0]["people"][0]["score"] == 4


def test_outsider_cannot_read_review_and_chain_can(engine, org):
    hr = sc(engine, "ikuzman", HR_KEYS)
    cy = _cycle(engine, org, hr)
    rid = next(p["reviewId"] for p in P.cycle_status(engine, TN, hr, cy["id"])["people"] if p["employeeId"] == org["ali"])
    with pytest.raises(H.HrError) as e:
        P.get_review(engine, TN, sc(engine, "veli", ALL), rid)
    assert e.value.status == 403
    assert P.get_review(engine, TN, sc(engine, "gm", ALL), rid)["role"] == "chain"
    assert P.get_review(engine, TN, hr, rid)["role"] == "hr"


def test_form_version_bumps_and_cycle_requires_active_form(engine, org):
    f, _ = P.save_form(engine, TN, "ik", dict(P.STARTER_FORM))
    assert f["version"] == 1 and f["state"] == "taslak"
    f2, diff = P.save_form(engine, TN, "ik", {"sections": [{"title": "Tek", "kind": "acik"}]}, f["id"])
    assert f2["version"] == 2 and diff["bolumler"]
    cy, _ = P.save_cycle(engine, TN, "ik", {"name": "x", "periodStart": "2026-01-01", "periodEnd": "2026-12-31",
                                            "startsOn": "2026-12-01", "endsOn": "2026-12-31", "formTemplateId": f["id"]})
    with pytest.raises(H.HrError):
        P.cycle_transition(engine, TN, sc(engine, "ikuzman", HR_KEYS), cy["id"], "open")
    with pytest.raises(H.HrError):
        P.save_form(engine, TN, "ik", {"name": "x", "sections": [{"title": "Y", "kind": "yetkinlik", "items": []}]})


def test_work_summary_text_has_no_score_and_says_it_is_informational():
    txt = P.work_text({"editorial": {"available": True, "done": 14, "withDue": 12, "onTime": 11, "openOverdue": 1},
                       "crm": {"available": True, "projects": 5, "contracts": 3}})
    assert "14 editörlük görevi" in txt and "11 tanesi" in txt and "5 proje" in txt
    assert "puan ya da değerlendirme değildir" in txt
    assert "okunamadı" in P.work_text({"editorial": {"available": False}, "crm": {"available": False, "reason": "bağlantı yok"}})


def test_editorial_facts_count_done_and_on_time(engine):
    from semantic_bridge import editorial_assign as ea

    ea._md.create_all(engine)
    now = datetime(2026, 6, 10, tzinfo=timezone.utc)
    rows = [("t1", "tamamlandi", now, date(2026, 6, 15)), ("t2", "tamamlandi", now, date(2026, 6, 1)),
            ("t3", "tamamlandi", datetime(2025, 1, 1, tzinfo=timezone.utc), None), ("t4", "calisiyor", None, date(2026, 3, 1))]
    with engine.begin() as c:
        for i, stt, done, due in rows:
            c.execute(ea.TASKS.insert().values(id=i, tenant_id=TN, crm_project_id="p", editor_id="ABC", role="editor", status=stt,
                                               source="atama", due_date=due, created_by="x", created_at=now, done_at=done))
    f = S.editorial_facts(engine, TN, "abc", date(2026, 1, 1), date(2026, 12, 31))
    assert f == {"available": True, "done": 2, "withDue": 2, "onTime": 1, "openOverdue": 1, "source": "semantic_editorial_tasks"}


def test_rewrite_mask_hides_names_contacts_and_special_lines():
    names = ["Ayşe Yılmaz", "Mehmet Öz"]
    masked, counts = T.mask_text("Ayşe çok iyi çalıştı, Mehmet Öz ile uyumlu. Tel 0532 111 22 33\nSendika toplantısına gitti",
                                 names, keep="Ayşe Yılmaz", keep_as="[çalışan]")
    assert "Ayşe" not in masked and "Mehmet" not in masked and "0532" not in masked and "Sendika" not in masked
    assert "[çalışan] çok iyi" in masked and "[kişi]" in masked and counts["ad"] >= 2


def test_purge_removes_left_employee_records_after_retention(engine, org):
    ayse = sc(engine, "ayse")
    g, _ = P.save_goal(engine, TN, ayse, {"title": "H", "period": "2026"})
    assert P.due_purge(engine, TN, H.now()) == []           # süre girilmedi → imha yok
    H.put_retention(engine, TN, "ik", [{"dataClass": P.DATA_CLASS, "keepDays": 30, "legalBasis": "İş K. md. 75"}])
    H.save_employee(engine, TN, "ik", {"status": "ayrildi", "endDate": (date.today() - timedelta(days=40)).isoformat()}, org["ayse"])
    assert P.due_purge(engine, TN, H.now()) == [org["ayse"]]
    out = H.run_due_purge(engine, TN)
    assert next(x for x in out["classes"] if x["key"] == P.DATA_CLASS)["purged"] == 1
    with engine.connect() as c:
        assert c.execute(sa.select(sa.func.count()).select_from(P.GOALS)).scalar() == 0


def test_reminders_need_threshold_and_count_without_names(engine, org):
    hr = sc(engine, "ikuzman", HR_KEYS)
    cy = _cycle(engine, org, hr)
    assert P.due_reminders(engine, TN, None) == []
    items = P.due_reminders(engine, TN, 60, today=date(2026, 12, 1))
    assert items[0]["selfMissing"] == 4 and "Ayşe" not in P.reminder_text(items, "")
    P.mark_reminded(engine, TN, items, date(2026, 12, 1))
    assert P.due_reminders(engine, TN, 60, today=date(2026, 12, 1)) == []
    _ = cy


# ------------------------------------------------------------------ köprü


def test_bridge_gates_performance_pages(monkeypatch, store, settings):
    from fastapi.testclient import TestClient

    from semantic_bridge import access as A
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm

    users = {"timas_session=a": "ayse", "timas_session=z": "zekiai"}
    monkeypatch.setattr(board_mod, "_fetch_user", lambda cookie: users.get(cookie))
    monkeypatch.setattr(board_mod, "_fetch_session", lambda cookie: {"username": users.get(cookie), "displayName": "x"})
    monkeypatch.setattr(admin_mod, "admins", lambda: ["zekiai"])
    monkeypatch.delenv("SEMANTIC_CALLER_TOKEN", raising=False)
    A._ready.clear()
    A.invalidate()
    client = TestClient(create_app(Runtime(settings, store=store, llm=FakeLlm([""]))))
    a, z = {"cookie": "timas_session=a"}, {"cookie": "timas_session=z"}
    assert client.get("/api/v1/hr/performance/me", headers=a).status_code == 403     # Herkes rolü İK sayfasını açmaz
    assert client.post("/api/v1/hr/performance/reminders/run-due", headers=a).status_code == 403
    assert client.get("/api/v1/hr/performance/me", headers=z).status_code == 200
    meta = client.get("/api/v1/hr/performance/meta", headers=z).json()
    assert meta["me"]["can"]["calibration"] is False                                  # duyarlı: yöneticiye rolsüz gelmez
    assert client.post("/api/v1/hr/performance/reminders/run-due").json()["mail"] == "esik_yok"
    A._ready.clear()
    A.invalidate()
