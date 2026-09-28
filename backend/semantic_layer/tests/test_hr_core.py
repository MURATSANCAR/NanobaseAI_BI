"""İK-0 ortak temeli: açıkça verilen İK sayfaları (Herkes rolü görmez), duyarlı anahtarların yöneticiye rolüyle
verilmesi, CRM ∩ AD çalışan önerisi ve eşitleme (elle düzeltilen alan ezilmez), aydınlatma sürümü, rıza kaydı ve geri
çekme kancası, saklama süresi doğrulaması, imha tutanağı, erişim kaydı ve model sıra kaydında yalnız etiket.

Veriler yapaydır ve yalnız kuralları sınar; gerçek CRM/AD kabulü test sunucusunda (scripts/acceptance/M55).
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import sqlalchemy as sa

from semantic_bridge import access as A
from semantic_bridge import hr_core as H
from semantic_bridge import hr_sources as S
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.conftest import TENANT

TN = "t1"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    H._ready.discard(e)
    H.ensure(e)
    return e


def is_admin(u: str) -> bool:
    return u == "zekiai"


# ------------------------------------------------------------------ yetki


def test_hr_pages_are_explicit_and_everyone_does_not_see_them():
    ik_pages = {p["key"] for p in A.catalog()["pages"] if p["area"] == "ik"}
    # M56–M58 kendi sayfalarını ekler; İK-0/M55 sayfaları her zaman var ve hepsi açıkça verilir.
    # M56–M58 kendi İK sayfalarını ekler; İK-0 ve M55 sayfaları hep var, hepsi açıkça verilir.
    assert ik_pages >= {"sayfa:ik-ise-alim", "sayfa:ik-pozisyonlar", "sayfa:ik-belgeler", "sayfa:ik-kayitlar"}
    assert ik_pages <= A.explicit_keys()
    ik_features = {f["key"] for f in A.catalog()["features"] if f["area"] == "ik"}
    assert ik_features <= A.explicit_keys()
    assert A.sensitive_keys() >= {"ozellik:ik.aday-hepsi", "ozellik:ik.kvkk-yonet", "ozellik:ik.erisim-kaydi",
                                  "ozellik:ik.disa-aktar"}


def test_everyone_role_with_all_pages_still_cannot_open_hr(engine):
    A._ready.clear()
    A.invalidate()
    A.ensure(engine, TENANT)
    acc = A.effective(engine, TENANT, "biri", is_admin)
    assert acc.all and acc.can("sayfa:finansal-denetim")
    assert not acc.can("sayfa:ik-ise-alim") and not acc.can("ozellik:ik.aday-hepsi")


def test_admin_gets_sensitive_hr_keys_only_through_a_role(engine):
    A._ready.clear()
    A.invalidate()
    A.ensure(engine, TENANT)
    admin = A.effective(engine, TENANT, "zekiai", is_admin)
    who = H.who_from(admin, "Zeki", A.sensitive_keys(), admin_sees_personal=False)
    assert who.can("sayfa:ik-ise-alim") and who.can("ozellik:ik.pozisyon-onay")
    assert not who.can("ozellik:ik.aday-hepsi") and not who.can("ozellik:ik.kvkk-yonet")
    assert H.who_from(admin, "Zeki", A.sensitive_keys(), admin_sees_personal=True).can("ozellik:ik.aday-hepsi")
    rid = A.save_role(engine, TENANT, "zekiai", {"name": "İK", "perms": ["sayfa:ik-ise-alim", "ozellik:ik.aday-hepsi"]})["id"]
    A.add_binding(engine, TENANT, "zekiai", rid, {"type": "user", "subject": "zekiai"})
    A.invalidate()
    admin = A.effective(engine, TENANT, "zekiai", is_admin)
    who = H.who_from(admin, "Zeki", A.sensitive_keys(), admin_sees_personal=False)
    assert who.can("ozellik:ik.aday-hepsi") and not who.can("ozellik:ik.kvkk-yonet")


def test_hr_endpoint_rules():
    assert A.rule_for("/api/v1/hr/me") == A.OPEN
    assert A.rule_for("/api/v1/hr/purge/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/hr/recruit/intake") == A.SYSTEM
    assert A.rule_for("/api/v1/hr/recruit/reminders/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/hr/recruit/pipeline") == {"sayfa:ik-ise-alim", "sayfa:ik-pozisyonlar", "sayfa:ik-belgeler"}
    assert "sayfa:ik-kayitlar" in A.rule_for("/api/v1/hr/employees")
    # İK işlem anahtarları sayfa içi kurala (FEATURE_RULES) girmez; hepsi açıkça verilir, ucun içinde denetlenir.
    assert not [k for _, _, k in A.FEATURE_RULES if k.startswith("ozellik:ik.")]


# ------------------------------------------------------------------ çalışan önerisi


USERS = [
    {"id": "u1", "name": "Ayşe Yılmaz", "domainName": "TIMAS\\ayse", "account": "ayse", "adGuid": "g1", "unitId": "b1", "accessMode": 0, "interactive": True},
    {"id": "u2", "name": "Ali Kaya", "domainName": "TIMAS\\ali", "account": "ali", "adGuid": "g2", "unitId": "b1", "accessMode": 0, "interactive": True},
    {"id": "u3", "name": "Entegrasyon", "domainName": "TIMAS\\svc", "account": "svc", "adGuid": "", "unitId": "b2", "accessMode": 4, "interactive": False},
    {"id": "u4", "name": "Eski Çalışan", "domainName": "TIMAS\\eski", "account": "eski", "adGuid": "g4", "unitId": "b2", "accessMode": 1, "interactive": True},
]
UNITS = [{"id": "b1", "name": "Editörya", "parentId": None, "managerId": "u1"},
         {"id": "b2", "name": "Satış", "parentId": "b1", "managerId": None}]
TEAMS = [{"teamId": "t1", "team": "Çocuk", "userId": "u1"}, {"teamId": "t1", "team": "Çocuk", "userId": "u2"}]
AD = {"guid:g1": {"account": "ayse", "lastLogon": None}, "ayse": {"account": "ayse", "lastLogon": None},
      "ali": {"account": "ali.kaya", "lastLogon": None}}


def test_sync_preview_intersects_crm_and_ad_and_counts_for_acceptance():
    pv = S.sync_preview(USERS, UNITS, TEAMS, AD, [], [])
    st = pv["stats"]
    assert (st["crmEnabled"], st["crmInteractive"], st["matched"], st["units"], st["unitsWithManager"]) == (4, 3, 2, 2, 1)
    names = {e["displayName"]: e["username"] for e in pv["employees"]}
    assert names == {"Ayşe Yılmaz": "ayse", "Ali Kaya": "ali.kaya"}          # guid, sonra hesap adı; AD adı kazanır
    assert {u["name"]: u["enabledUsers"] for u in pv["units"]} == {"Editörya": 2, "Satış": 2}
    assert pv["teams"] == [{"teamId": "t1", "team": "Çocuk", "members": 2}]
    no_ad = S.sync_preview(USERS, UNITS, TEAMS, None, [], [])
    assert no_ad["stats"]["matched"] == 3 and any("AD" in n for n in no_ad["notes"])


def test_apply_sync_keeps_manual_fields_and_marks_departed(engine):
    pv = S.sync_preview(USERS, UNITS, TEAMS, None, [], [])
    done = H.apply_sync(engine, TN, "ik", pv, ["units", "new"])
    assert done["units"] == 2 and done["new"] == 3 and done["managers"] == 1
    emps = {e["displayName"]: e for e in H.list_employees(engine, TN)}
    units = {u["name"]: u for u in H.list_units(engine, TN)}
    assert units["Satış"]["parentId"] == units["Editörya"]["id"]
    assert units["Editörya"]["managerEmployeeId"] == emps["Ayşe Yılmaz"]["id"]
    # İK unvanı ve adı elle düzeltir: eşitleme ezmez.
    H.save_employee(engine, TN, "ik", {"displayName": "Ayşe Yılmaz Demir", "title": "Editör"}, emps["Ayşe Yılmaz"]["id"])
    pv2 = S.sync_preview(USERS[:2], UNITS, TEAMS, AD, H.list_employees(engine, TN, status=""), H.list_units(engine, TN))
    ayse = next(e for e in pv2["employees"] if e["crmSystemUserId"] == "u1")
    assert "displayName" not in ayse["changes"]
    assert [d["displayName"] for d in pv2["departed"]] == ["Eski Çalışan"]
    H.apply_sync(engine, TN, "ik", pv2, ["changed", "departed"])
    after = {e["displayName"]: e for e in H.list_employees(engine, TN, status="")}
    assert after["Ayşe Yılmaz Demir"]["title"] == "Editör"
    assert after["Eski Çalışan"]["status"] == "ayrildi" and after["Ali Kaya"]["username"] == "ali.kaya"


def test_unit_cycle_and_employee_validation(engine):
    a, _ = H.save_unit(engine, TN, "ik", {"name": "A"})
    b, _ = H.save_unit(engine, TN, "ik", {"name": "B", "parentId": a["id"]})
    with pytest.raises(H.HrError):
        H.save_unit(engine, TN, "ik", {"parentId": b["id"]}, a["id"])
    with pytest.raises(H.HrError):
        H.save_employee(engine, TN, "ik", {"displayName": ""})
    e, _ = H.save_employee(engine, TN, "ik", {"displayName": "Depo Çalışanı", "unitId": a["id"], "startDate": "2026-01-05"})
    assert e["username"] is None and e["startDate"] == "2026-01-05" and e["source"]["display_name"] == "ik"


# ------------------------------------------------------------------ KVKK kayıtları


def test_consent_needs_a_published_notice_and_withdraw_calls_the_hook(engine):
    e, _ = H.save_employee(engine, TN, "ik", {"displayName": "X"})
    H.register_purpose("test_amac", "Test", "", "calisan")
    body = {"subjectType": "calisan", "subjectId": e["id"], "purpose": "test_amac", "channel": "form"}
    with pytest.raises(H.HrError, match="aydınlatma"):
        H.add_consent(engine, TN, "ik", body)
    n1 = H.publish_notice(engine, TN, "kvkk", {"audience": "calisan", "title": "Çalışan aydınlatma", "body": "..."})
    n2 = H.publish_notice(engine, TN, "kvkk", {"audience": "calisan", "title": "Çalışan aydınlatma", "body": "yeni"})
    assert (n1["version"], n2["version"]) == (1, 2)
    got = H.add_consent(engine, TN, "ik", body, lambda st, sid: H.subject_exists(engine, TN, st, sid))
    assert got["noticeVersion"] == 2 and got["active"]
    with pytest.raises(H.HrError):
        H.add_consent(engine, TN, "ik", body)                        # aynı amaç için ikinci geçerli rıza yok
    with pytest.raises(H.HrError):
        H.add_consent(engine, TN, "ik", {**body, "purpose": "aday_havuzu"})   # amaç bu kişi türüne ait değil
    calls = []
    H.register_withdraw_hook(lambda eng, t, st, sid, p: calls.append((st, sid, p)))
    out = H.withdraw_consent(engine, TN, "ik", got["id"])
    assert not out["active"] and calls[-1] == ("calisan", e["id"], "test_amac")
    with pytest.raises(H.HrError):
        H.withdraw_consent(engine, TN, "ik", got["id"])


def test_retention_needs_days_and_legal_basis(engine):
    with pytest.raises(H.HrError, match="dayanağı"):
        H.put_retention(engine, TN, "kvkk", [{"dataClass": "aday_ret", "keepDays": 180}])
    with pytest.raises(H.HrError):
        H.put_retention(engine, TN, "kvkk", [{"dataClass": "aday_ret", "keepDays": 0, "legalBasis": "x"}])
    items, diff = H.put_retention(engine, TN, "kvkk", [{"dataClass": "aday_ret", "keepDays": 180, "legalBasis": "Politika md. 4"}])
    assert H.keep_days(engine, TN, "aday_ret") == 180 and diff["aday_ret"]["sonra"] == 180
    assert next(i for i in items if i["dataClass"] == "aday_havuz")["keepDays"] is None


def test_purge_writes_a_record_per_class_even_when_nothing_is_due(engine):
    seen = []
    H._purgers.clear()
    H.register_purger(H.Purger("deneme", "Deneme", lambda e, t, now: ["k1", "k2"], lambda e, t, ids, now: seen.extend(ids) or len(ids)))
    H.register_purger(H.Purger("bos", "Boş", lambda e, t, now: [], lambda e, t, ids, now: 0))
    out = H.run_due_purge(engine, TN)
    assert out["ok"] and seen == ["k1", "k2"]
    runs = H.purge_runs(engine, TN)["items"]
    assert {(r["dataClass"], r["purged"]) for r in runs} == {("deneme", 2), ("bos", 0)}
    assert next(r for r in runs if r["dataClass"] == "deneme")["ids"] == ["k1", "k2"]
    H._purgers.clear()


def test_access_log_pages_without_dropping_rows(engine):
    for i in range(5):
        H.log_access(engine, TN, "ayse", "aday", f"a{i}", "goruntule")
    p1 = H.access_log(engine, TN, limit=3)
    p2 = H.access_log(engine, TN, limit=3, before=p1["next"])
    assert p1["hasMore"] and not p2["hasMore"]
    assert [x["subjectId"] for x in p1["items"] + p2["items"]] == [f"a{i}" for i in range(4, -1, -1)]


# ------------------------------------------------------------------ model izi


def test_labelled_model_call_leaves_only_the_label_in_the_queue(tmp_path):
    from semantic_layer.runtime.llm_queue import LlmQueue, QueuedLlm
    from semantic_layer.store import schema as SS

    class Echo:
        model = "x"

        def chat(self, messages, **_):
            return "tamam"

    store = open_store(f"sqlite:///{tmp_path}/q.db")
    q = LlmQueue(store.engine, slots=1, poll_seconds=0.02)
    base = QueuedLlm(Echo(), q)

    class Rt:
        def llm_for(self, module, priority=None):
            return base.for_module(module, priority=priority)

    m = H.hr_llm(Rt(), "özgeçmiş özeti")
    assert m.chat([{"role": "user", "content": "Ayşe Yılmaz, 0532 111 22 33, özgeçmiş…"}]) == "tamam"
    with store.engine.connect() as c:
        rows = c.execute(sa.select(SS.sl_llm_queue.c.question, SS.sl_llm_queue.c.purpose)).all()
    assert rows and all(r.question == "ik: özgeçmiş özeti" for r in rows)
    assert all("ik" in r.purpose for r in rows)


def test_job_runs_in_background_and_reports(engine):
    import time

    j = H.start_job(engine, TN, "ayse", "deneme", "k1", lambda progress: (progress(1, 1), {"n": 1})[1])
    for _ in range(500):   # dolu sunucuda arka plan iş parçacığı 2 sn'yi aşabiliyor
        j = H.job(engine, TN, j["id"], "ayse")
        if j["state"] != "calisiyor":
            break
        time.sleep(0.02)
    assert j["state"] == "bitti" and j["result"] == {"n": 1}
    with pytest.raises(H.HrError):
        H.job(engine, TN, j["id"], "baskasi")


def test_now_helpers_are_timezone_aware():
    assert H.aware("2026-01-01T00:00:00").tzinfo is not None
    assert H.iso(datetime(2026, 1, 1, tzinfo=timezone.utc)).startswith("2026-01-01T00:00:00")
