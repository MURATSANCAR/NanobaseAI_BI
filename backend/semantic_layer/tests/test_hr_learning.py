"""M57 Eğitim ve gelişim: açıkça verilen sayfalar ve uç kuralları, zorunlu eğitim durumunun sertifikadan hesaplanması,
oturum kapanışı (yoklama şartı, sertifika, anket jetonu), katılım onay zinciri, anonim geri bildirim (şemada kişi yok,
ikinci gönderim 409), kullanım haritasında hesap adı olmaması ve gizlilik eşiği, rehberde altyapı adı denetimi,
modele kişi bilgisi gitmemesi, imha bağları ve Logo gider SQL'inin tanımı.

Veriler yapaydır ve yalnız kuralları sınar; gerçek veri kabulü test sunucusunda (scripts/acceptance/M57).
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
import sqlalchemy as sa

from semantic_bridge import access as A
from semantic_bridge import admin as admin_mod
from semantic_bridge import hr_core as H
from semantic_bridge import hr_learning as L
from semantic_bridge import hr_learning_sources as S
from semantic_layer.store.catalog_store import open_store

TN = "t1"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    H._ready.discard(e)
    L._ready.discard(e)
    L.ensure(e)
    admin_mod.ensure(e)
    return e


def who(user: str, *keys: str) -> H.Who:
    return H.Who(user=user, display=user, admin=False, keys=frozenset(keys))


def emp(engine, name: str, username: str | None, unit: str | None = None, manager: str | None = None) -> str:
    body = {"displayName": name, "username": username, "unitId": unit}
    if manager:
        body["managerId"] = manager
    return H.save_employee(engine, TN, "ik", body)[0]["id"]


def unit(engine, name: str) -> str:
    return H.save_unit(engine, TN, "ik", {"name": name})[0]["id"]


def course(engine, **kw) -> str:
    body = {"title": "İş sağlığı ve güvenliği", "kind": "zorunlu", "delivery": "ic", "validityDays": 365, **kw}
    return L.save_course(engine, TN, "ik", body)[0]["id"]


# ------------------------------------------------------------------ yetki


def test_learning_pages_and_keys_are_explicit_and_personal_key_is_sensitive():
    pages = {p["key"] for p in A.catalog()["pages"]}
    assert {"sayfa:ik-egitim", "sayfa:ik-egitimlerim"} <= pages
    assert {"sayfa:ik-egitim", "sayfa:ik-egitimlerim"} <= A.explicit_keys()
    feats = {f["key"] for f in A.catalog()["features"]}
    for k in (L.F_MANAGE, L.F_APPROVE, L.F_BUDGET, L.F_USAGE, L.F_GUIDES):
        assert k in feats and k in A.explicit_keys()
    assert L.F_MANAGE in A.sensitive_keys() and L.F_EXPORT in A.sensitive_keys()
    assert L.F_USAGE not in A.sensitive_keys()


def test_learning_endpoint_rules():
    assert A.rule_for("/api/v1/hr/visit") == A.OPEN
    assert A.rule_for("/api/v1/hr/learning/me") == A.OPEN
    assert A.rule_for("/api/v1/hr/learning/me/usage") == A.OPEN
    assert A.rule_for("/api/v1/hr/learning/me/feedback/abc") == A.OPEN
    assert A.rule_for("/api/v1/hr/learning/reminders/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/hr/learning/usage-map") == {"sayfa:ik-egitim"}
    # «/me» öneki «/meta» gibi yolları açmaz.
    assert A.rule_for("/api/v1/hr/learning/meta") == {"sayfa:ik-egitim"}
    assert "sayfa:ik-egitim" in A.rule_for("/api/v1/hr/employees")
    assert "sayfa:ik-egitimlerim" not in A.rule_for("/api/v1/hr/employees")


def test_everyone_role_does_not_get_learning_pages(engine):
    A._ready.clear()
    A.invalidate()
    A.ensure(engine, "t1")
    acc = A.effective(engine, "t1", "biri", lambda u: False)
    assert acc.all and not acc.can("sayfa:ik-egitim") and not acc.can(L.F_MANAGE)


def test_admin_gets_personal_learning_key_only_through_role(engine):
    A._ready.clear()
    A.invalidate()
    A.ensure(engine, "t1")
    admin = A.effective(engine, "t1", "zekiai", lambda u: u == "zekiai")
    w = H.who_from(admin, "Zeki", A.sensitive_keys(), admin_sees_personal=False)
    assert w.can("sayfa:ik-egitim") and w.can(L.F_USAGE) and not w.can(L.F_MANAGE)


# ------------------------------------------------------------------ zorunlu eğitim durumu


def cert(engine, eid: str, cid: str, issued: date, expires: date | None, verified: bool = True) -> None:
    with engine.begin() as c:
        c.execute(L.CERTIFICATES.insert().values(id=H.new_id("srt"), tenant_id=TN, employee_id=eid, course_id=cid, source="ik",
                                                 issued_on=issued, expires_on=expires, created_at=H.now(),
                                                 verified_by="ik" if verified else None, verified_at=H.now() if verified else None))


def test_mandatory_status_from_latest_verified_certificate(engine):
    u1, u2 = unit(engine, "Depo"), unit(engine, "Editörya")
    a, b, c_, d, e = (emp(engine, n, n.lower(), u1) for n in ("Ayşe", "Ali", "Can", "Deniz", "Ece"))
    other = emp(engine, "Fatma", "fatma", u2)
    k = course(engine, requiredUnits=[u1])
    t = L.today()
    cert(engine, a, k, t - timedelta(days=400), t - timedelta(days=35))            # doldu
    cert(engine, c_, k, t - timedelta(days=10), t + timedelta(days=355))           # geçerli
    cert(engine, d, k, t - timedelta(days=355), t + timedelta(days=10))            # dolacak
    cert(engine, e, k, t - timedelta(days=5), t + timedelta(days=360), verified=False)   # doğrulanmamış → sayılmaz
    cert(engine, a, k, t - timedelta(days=800), t - timedelta(days=435))           # eski belge, en sonuncusu sayılır
    st = {x["employeeId"]: x["status"] for x in L.mandatory_status(engine, TN, days=30)}
    assert st == {a: "doldu", b: "hic_yok", c_: "gecerli", d: "dolacak", e: "hic_yok"}
    assert other not in st                                                          # birim listesinde değil
    st0 = {x["employeeId"]: x["status"] for x in L.mandatory_status(engine, TN, days=0)}
    assert st0[d] == "gecerli"                                                      # eşik yokken yalnız dolmuş


def test_zorunlu_only_has_unit_list(engine):
    with pytest.raises(H.HrError):
        course(engine, kind="gelisim", requiredUnits=[unit(engine, "Satış")])


# ------------------------------------------------------------------ oturum


def test_close_requires_attendance_then_writes_certificates_and_tokens(engine):
    u = unit(engine, "Depo")
    a, b = emp(engine, "Ayşe", "ayse", u), emp(engine, "Ali", "ali", u)
    k = course(engine, validityDays=730)
    s = L.create_session(engine, TN, "ik", {"courseId": k, "startsAt": "2026-09-01T10:00:00+03:00", "employeeIds": [a, b, a]})
    assert s["counts"]["approved"] == 2
    enr = {x["employeeId"]: x["id"] for x in s["enrollments"]}
    with pytest.raises(H.HrError) as ex:
        L.close_session(engine, TN, "ik", s["id"])
    assert ex.value.status == 409
    L.set_attendance(engine, TN, "ik", s["id"], [{"enrollmentId": enr[a], "attendance": "katildi"},
                                                 {"enrollmentId": enr[b], "attendance": "gelmedi"}])
    out = L.close_session(engine, TN, "ik", s["id"])
    assert out == {"completed": 1, "absent": 1, "feedbackInvited": 1}
    certs = L.list_certificates(engine, TN, employee_id=a)
    assert len(certs) == 1 and certs[0]["verified"] and certs[0]["issuedOn"] == "2026-09-01"
    assert certs[0]["expiresOn"] == (date(2026, 9, 1) + timedelta(days=730)).isoformat()
    assert L.list_certificates(engine, TN, employee_id=b) == []
    with engine.connect() as c:
        assert c.execute(sa.select(sa.func.count()).select_from(L.FEEDBACK_TOKENS)).scalar() == 1
    with pytest.raises(H.HrError):
        L.set_attendance(engine, TN, "ik", s["id"], [{"enrollmentId": enr[b], "attendance": "katildi"}])


def test_dashboard_completion_rate_counts_approved_non_cancelled(engine):
    u = unit(engine, "Satış")
    a, b = emp(engine, "Ayşe", "ayse", u), emp(engine, "Ali", "ali", u)
    k = course(engine, kind="gelisim", validityDays=None)
    s1 = L.create_session(engine, TN, "ik", {"courseId": k, "startsAt": "2026-09-01T10:00:00+03:00", "employeeIds": [a, b]})
    e = {x["employeeId"]: x["id"] for x in s1["enrollments"]}
    L.set_attendance(engine, TN, "ik", s1["id"], [{"enrollmentId": e[a], "attendance": "katildi"},
                                                  {"enrollmentId": e[b], "attendance": "gelmedi"}])
    L.close_session(engine, TN, "ik", s1["id"])
    s2 = L.create_session(engine, TN, "ik", {"courseId": k, "startsAt": "2026-10-01T10:00:00+03:00", "employeeIds": [b]})
    L.update_session(engine, TN, "ik", s2["id"], {"state": "iptal"})
    d = L.dashboard(engine, TN, alert_days=None, people=False)
    assert d["counters"]["completionRate"] == 0.5 and d["counters"]["expiring"] is None
    assert "attention" not in d
    assert d["matrix"] == [{"unitId": u, "unitName": "Satış", "courseId": k, "courseTitle": "İş sağlığı ve güvenliği",
                            "enrolled": 2, "completed": 1, "rate": 0.5}]


# ------------------------------------------------------------------ onay zinciri


def test_approval_chain_manager_then_hr_for_external(engine):
    u = unit(engine, "Editörya")
    boss = emp(engine, "Müdür", "mudur", u)
    worker = emp(engine, "Çalışan", "calisan", u, manager=boss)
    stranger = emp(engine, "Başka", "baska", u)
    k = course(engine, kind="gelisim", delivery="dis", validityDays=None)
    s = L.create_session(engine, TN, "ik", {"courseId": k, "startsAt": "2030-01-10T10:00:00+03:00"})
    L.enroll(engine, TN, "calisan", s["id"], [worker], "bekliyor")
    eid = L.get_session(engine, TN, s["id"], people=True)["enrollments"][0]["id"]
    with pytest.raises(H.HrError) as ex:
        L.decide_enrollment(engine, TN, who("baska", L.F_APPROVE), eid, "onayla")
    assert ex.value.status == 403
    assert L.decide_enrollment(engine, TN, who("mudur", L.F_APPROVE), eid, "onayla")["approval"] == "yonetici_onayladi"
    with pytest.raises(H.HrError):
        L.decide_enrollment(engine, TN, who("mudur", L.F_APPROVE), eid, "onayla")      # son onay İK'nın
    assert L.decide_enrollment(engine, TN, who("ik", L.F_MANAGE), eid, "onayla")["approval"] == "onaylandi"
    assert stranger


# ------------------------------------------------------------------ geri bildirim


def test_feedback_table_has_no_person_column_and_token_is_single_use(engine):
    cols = {c.name for c in L.FEEDBACK.columns}
    assert not cols & {"employee_id", "username", "user", "actor", "created_by"}
    assert "submitted_on" in cols and isinstance(L.FEEDBACK.c.submitted_on.type, sa.Date)
    assert isinstance(L.FEEDBACK_TOKENS.c.used_on.type, sa.Date)
    u = unit(engine, "Depo")
    a = emp(engine, "Ayşe", "ayse", u)
    k = course(engine)
    s = L.create_session(engine, TN, "ik", {"courseId": k, "startsAt": "2026-09-01T10:00:00+03:00", "employeeIds": [a]})
    L.set_attendance(engine, TN, "ik", s["id"], [{"enrollmentId": s["enrollments"][0]["id"], "attendance": "katildi"}])
    L.close_session(engine, TN, "ik", s["id"])
    token = L.me(engine, TN, "ayse", None)["feedback"][0]["token"]
    with pytest.raises(H.HrError):
        L.submit_feedback(engine, TN, token, a, {"answers": {"genel": 7}})
    L.submit_feedback(engine, TN, token, a, {"answers": {"genel": 5, "fayda": 4}, "comment": "Örnekler iyiydi, ayse@timas.com.tr"})
    with pytest.raises(H.HrError) as ex:
        L.submit_feedback(engine, TN, token, a, {"answers": {"genel": 1}})
    assert ex.value.status == 409
    summary = L.feedback_summary(engine, TN, s["id"], None)
    assert summary["averages"]["genel"] == {"avg": 5.0, "n": 1}
    assert "ayse@timas.com.tr" not in summary["comments"][0]
    assert L.feedback_summary(engine, TN, s["id"], 3)["hidden"] is True


# ------------------------------------------------------------------ kullanım


def test_usage_map_has_no_account_names_and_merges_small_units(engine):
    big, small = unit(engine, "Satış"), unit(engine, "Hukuk")
    for i in range(4):
        emp(engine, f"S{i}", f"satis{i}", big)
    emp(engine, "H0", "hukuk0", small)
    for u in ("satis0", "satis1", "hukuk0", "disaridan"):
        L.record_visit(engine, TN, u, "telif-sozlesme")
    L.record_visit(engine, TN, "satis0", "telif-sozlesme")
    m = S.usage_map(engine, TN, 30, None)
    assert "satis0" not in repr(m) and "hukuk0" not in repr(m) and "disaridan" not in repr(m)
    rows = {r["unitName"]: r for r in m["rows"]}
    assert rows["Satış"]["cells"]["telif-sozlesme"] == 2 and rows["Satış"]["employees"] == 4
    assert rows["Hukuk"]["cells"]["telif-sozlesme"] == 1
    assert m["totals"]["telif-sozlesme"] == 4 and m["note"]
    merged = S.usage_map(engine, TN, 30, 3)
    names = [r["unitName"] for r in merged["rows"]]
    assert "Hukuk" not in names and any(r["merged"] and r["cells"]["telif-sozlesme"] == 2 for r in merged["rows"])
    mine = S.my_usage(engine, TN, "satis0", 30)
    assert mine["screens"] == [{"key": "telif-sozlesme", "days": 1, "visits": 2}]
    with pytest.raises(H.HrError):
        L.record_visit(engine, TN, "satis0", "../yonetim")


# ------------------------------------------------------------------ rehber ve model


def test_guide_rejects_tech_names_and_votes_follow_version(engine):
    g = L.save_guide(engine, TN, "portal", {"moduleRoute": "telif-sozlesme", "title": "Sözleşmeler", "body": "Qwen ile çalışır."})
    with pytest.raises(H.HrError):
        L.publish_guide(engine, TN, "portal", g["id"])
    L.save_guide(engine, TN, "portal", {"body": "Zeki AI sözleşme özetini hazırlar."}, g["id"])
    L.publish_guide(engine, TN, "portal", g["id"])
    L.vote_guide(engine, TN, "ayse", g["id"], True)
    assert L.list_guides(engine, TN)[0]["votes"] == {"useful": 1, "notUseful": 0}
    L.save_guide(engine, TN, "portal", {"body": "Yeni sürüm: Zeki AI özet ve takvim hazırlar."}, g["id"])
    assert L.read_guide(engine, TN, g["id"], "ayse")["body"] == "Zeki AI sözleşme özetini hazırlar."   # yayımdaki sürüm
    L.publish_guide(engine, TN, "portal", g["id"])
    assert L.list_guides(engine, TN)[0]["votes"] == {"useful": 0, "notUseful": 0}
    assert L.read_guide(engine, TN, g["id"], "ayse")["myVote"] is None


def test_need_suggestion_sends_no_person_data_to_model(engine):
    u = unit(engine, "Satış")
    a = emp(engine, "Ayşe Yılmaz", "ayse", u)
    k = course(engine, title="Excel ileri düzey", kind="gelisim", validityDays=None)
    n = L.add_need(engine, TN, "mudur", {"text": "Pivot tablo bilmiyor, ayse@timas.com.tr 0555 111 22 33"},
                   source="yonetici", employee_id=a)
    seen: list[str] = []

    def choose(prompt, choices, system=None):
        seen.append(prompt + " ".join(choices))
        idx = 0
        return SimpleNamespace(choice=choices[idx], index=idx, probability=0.9, method="logprobs")

    def chat(messages):
        seen.append(" ".join(m["content"] for m in messages))
        return "Pivot tablo ihtiyacı Excel eğitimiyle karşılanır."

    s = L.suggest_need(n, L.list_courses(engine, TN, active_only=True), choose, chat)
    assert s["courseId"] == k and s["priority"] == "yuksek"
    text = " ".join(seen)
    assert "Ayşe" not in text and "ayse@timas.com.tr" not in text and "0555 111 22 33" not in text
    L.apply_suggestion(engine, TN, n["id"], s)
    out = L.list_needs(engine, TN)
    assert out["summary"][0]["courseId"] == k and out["summary"][0]["yuksek"] == 1
    assert "text" not in L.list_needs(engine, TN, people=False)["items"][0]


# ------------------------------------------------------------------ imha


def test_purge_departed_learning_records_only_after_retention(engine):
    u = unit(engine, "Depo")
    a = emp(engine, "Ayşe", "ayse", u)
    b = emp(engine, "Ali", "ali", u)
    k = course(engine)
    cert(engine, a, k, date(2025, 1, 1), None)
    cert(engine, b, k, date(2025, 1, 1), None)
    H.save_employee(engine, TN, "ik", {"status": "ayrildi", "endDate": (L.today() - timedelta(days=100)).isoformat()}, a)
    t = datetime.now(timezone.utc)
    assert L.due_departed(engine, TN, t) == []                                   # süre girilmedi → imha yok
    L.register_hooks()
    H.put_retention(engine, TN, "ik", [{"dataClass": "egitim_kaydi", "keepDays": 30, "legalBasis": "İş K. md. 75"}])
    assert L.due_departed(engine, TN, t) == [a]
    assert L.purge_departed(engine, TN, [a], t) == 1
    assert L.list_certificates(engine, TN, employee_id=a) == [] and len(L.list_certificates(engine, TN, employee_id=b)) == 1


def test_purge_visits_by_day_without_account_names(engine):
    L.register_hooks()
    with engine.begin() as c:
        c.execute(L.PAGE_VISITS.insert().values(tenant_id=TN, day=L.today() - timedelta(days=400), route_prefix="panolar",
                                                username="ayse", count=3))
    L.record_visit(engine, TN, "ayse", "panolar")
    H.put_retention(engine, TN, "ik", [{"dataClass": "egitim_kullanim", "keepDays": 365, "legalBasis": "Amaçla sınırlı"}])
    t = datetime.now(timezone.utc)
    due = L.due_visits(engine, TN, t)
    assert due == [(L.today() - timedelta(days=400)).isoformat()] and "ayse" not in repr(due)
    assert L.purge_visits(engine, TN, due, t) == 1
    assert S.my_usage(engine, TN, "ayse", 30)["screens"][0]["visits"] == 1


# ------------------------------------------------------------------ Logo gideri


def test_spend_sql_definition_and_account_setting():
    sql = S.spend_sql("411", 2026, ["770.01.005"])
    assert "CANCELLED = 0" in sql and "SUM(F.DEBIT - F.CREDIT)" in sql
    assert "A.CODE = '770.01.005' OR A.CODE LIKE '770.01.005.%'" in sql
    assert "LEFT(KA.CODE, 3) IN ('711'" in sql and "'2026-01-01'" in sql and "'2027-01-01'" in sql
    assert L.parse_accounts("770.01.005; 760.02") == ["770.01.005", "760.02"]
    for bad in ("153.01", "770'; DROP", "abc"):
        with pytest.raises(H.HrError):
            L.parse_accounts(bad)
    assert L.settings(lambda k: "")["alertDays"] is None and L.settings(lambda k: "")["minGroup"] is None


def test_api_module_imports_request_at_module_level():
    import semantic_bridge.hr_learning_api as api

    assert getattr(api, "Request", None) is not None
