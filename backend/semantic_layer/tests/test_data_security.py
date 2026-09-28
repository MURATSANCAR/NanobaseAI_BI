"""M49 Veri güvenliği: erişim kaydı, giriş olaylarının çekilmesi, kural tabanlı uyarılar, saklama süresi (önizleme →
uygulama, kapalıyken hiçbir şey silinmez), «Herkes» daraltma önizlemesi, açıkça verilen sayfa, hesap hijyeni ve kişisel
veri defterinin köprü tablolarını kapsaması.

Veriler yapaydır ve yalnız kuralları sınar; gerçek giriş servisi, AD, CRM ve katalog kabulü test sunucusunda
(scripts/acceptance/M49).
"""

from __future__ import annotations

import ast
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa

from semantic_bridge import access as A
from semantic_bridge import admin as admin_mod
from semantic_bridge import data_security as D
from semantic_layer.store import schema as S
from semantic_layer.store.catalog_store import open_store

TN = "default"
DS = "ds1"
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=timezone.utc)      # Pazartesi 15:00 (İstanbul)


@pytest.fixture
def engine(monkeypatch):
    for k in [s["key"] for s in admin_mod.SPEC if s["key"].startswith("SECURITY_")]:
        monkeypatch.delenv(k, raising=False)
    e = open_store("sqlite://").engine
    S.metadata.create_all(e, checkfirst=True)
    D._ready.discard(id(e))
    D.ensure(e)
    admin_mod._ready.discard(id(e))
    admin_mod.ensure(e)
    admin_mod._cache["at"] = 0.0
    A._ready.clear()
    A.invalidate()
    A.ensure(e, TN)
    return e


def is_admin(u: str) -> bool:
    return u == "zekiai"


# ------------------------------------------------------------------ yetki kuralları


def test_rules_and_explicit_page():
    assert A.rule_for("/api/v1/data-security/run-due") == A.SYSTEM
    assert A.rule_for("/api/v1/data-security/export-notice") == A.OPEN
    assert A.rule_for("/api/v1/data-security/logins") == frozenset({"sayfa:veri-guvenligi"})
    assert A.features_for("PATCH", "/api/v1/data-security/alerts/3") == ["ozellik:guvenlik.uyari-kapat"]
    assert A.features_for("POST", "/api/v1/data-security/sessions/revoke") == []     # açıkça verilir, ucun içinde
    assert {"sayfa:veri-guvenligi", "ozellik:guvenlik.oturum-kapat", "ozellik:guvenlik.saklama"} <= A.explicit_keys()
    assert "ozellik:guvenlik.uyari-kapat" not in A.explicit_keys()


def test_everyone_with_all_pages_does_not_open_the_security_screen(engine):
    acc = A.effective(engine, TN, "biri", is_admin)
    assert acc.all and acc.can("sayfa:finansal-denetim")
    assert not acc.can("sayfa:veri-guvenligi")                       # «Herkes»in bütün sayfaları bu ekranı açmaz
    rid = A.save_role(engine, TN, "zekiai", {"name": "Güvenlik", "perms": ["sayfa:veri-guvenligi"]})["id"]
    A.add_binding(engine, TN, "zekiai", rid, {"type": "user", "subject": "guvenlikci"})
    assert A.effective(engine, TN, "guvenlikci", is_admin).can("sayfa:veri-guvenligi")
    assert A.effective(engine, TN, "zekiai", is_admin).can("sayfa:veri-guvenligi")


# ------------------------------------------------------------------ erişim kaydı


def test_access_log_and_not_permitted_from_query_log(engine):
    D.record_access(engine, "Ayse", "forbidden", "GET", "/api/v1/financial-audit/overview", "sayfa:finansal-denetim",
                    at=NOW - timedelta(minutes=5))
    D.record_access(engine, "ali", "export", "GET", "/api/v1/board/export.xlsx", "ozellik:veri.disa-aktar", at=NOW)
    with engine.begin() as c:
        c.execute(S.sl_query_log.insert().values(
            id="q1", tenant_id=TN, datasource_id=DS, question="maaşlar", normalized_question="maaşlar", resolved_json={},
            username="Veli", answer_type="NOT_PERMITTED", answer_summary="rolünüzde yok", created_at=NOW - timedelta(minutes=1)))
    out = D.list_access(engine, engine, TN, DS)
    assert [(i["kind"], i["username"]) for i in out["items"]] == [("export", "ali"), ("not_permitted", "veli"), ("forbidden", "ayse")]
    assert out["items"][2]["permKey"] == "sayfa:finansal-denetim"
    assert [i["kind"] for i in D.list_access(engine, engine, TN, DS, kind="forbidden")["items"]] == ["forbidden"]
    page = D.list_access(engine, engine, TN, DS, page_size=1)
    assert len(page["items"]) == 1 and page["next"]
    rest = D.list_access(engine, engine, TN, DS, before=page["next"], page_size=10)
    assert len(rest["items"]) == 2


def test_export_notice_validates_and_records(engine):
    with pytest.raises(D.SecurityError):
        D.export_notice(engine, "ali", {"what": "", "format": "csv"})
    with pytest.raises(D.SecurityError):
        D.export_notice(engine, "ali", {"what": "Rehber", "format": "exe"})
    D.export_notice(engine, "ali", {"what": "Dahili rehber", "format": "csv", "rows": 130, "page": "/"})
    item = D.list_access(engine, engine, TN, DS, kind="export")["items"][0]
    assert item["detail"] == {"what": "Dahili rehber", "format": "csv", "rows": 130, "client": True}


# ------------------------------------------------------------------ giriş olayları


class FakeLogin:
    def __init__(self, events, page=2):
        self.items = events
        self.page = page
        self.configured = True

    def events(self, after, limit=1000):
        rows = [e for e in self.items if e["id"] > after]
        return {"items": rows[:self.page], "more": len(rows) > self.page, "maxId": max([e["id"] for e in self.items] or [0])}


def _ev(i, user, ok, reason, at):
    return {"id": i, "at": at.timestamp(), "username": user, "ok": ok, "reason": reason, "addr": "10.0.0.9", "ua": "abc"}


def test_pull_logins_pages_dedups_and_survives_service_reset(engine):
    evs = [_ev(i, "ali", i % 2 == 0, "ok" if i % 2 == 0 else "bad_password", NOW + timedelta(seconds=i)) for i in range(1, 6)]
    fake = FakeLogin(evs)
    assert D.pull_logins(engine, fake)["imported"] == 5
    assert D.pull_logins(engine, fake)["imported"] == 0
    fake.items = [_ev(1, "veli", True, "ok", NOW + timedelta(hours=1))]      # giriş servisi veritabanı yenilendi
    assert D.pull_logins(engine, fake)["imported"] == 1
    rows = D.list_logins(engine)["items"]
    assert len(rows) == 6 and rows[0]["username"] == "veli"
    assert D.list_logins(engine, ok=False)["items"][0]["reasonLabel"] == D.REASON_LABEL["bad_password"]


def test_pull_without_token_is_off(engine):
    out = D.pull_logins(engine, D.LoginClient(token=""))
    assert out == {"ok": False, "configured": False, "imported": 0}


# ------------------------------------------------------------------ kurallar


def _logins(engine, rows):
    with engine.begin() as c:
        c.execute(D.LOGINS.insert(), [{"at": at, "username": u, "ok": ok, "reason": r, "addr": "1.2.3.4"} for u, ok, r, at in rows])


def test_failed_login_rule_opens_one_alert_per_burst(engine):
    D.state_set(engine, "rules_at", (NOW - timedelta(minutes=30)).isoformat())
    _logins(engine, [("ali", False, "bad_password", NOW - timedelta(minutes=9 - i)) for i in range(5)]
            + [("veli", False, "bad_password", NOW - timedelta(minutes=20 * i)) for i in range(1, 3)])
    new = D.evaluate(engine, TN, NOW)
    assert [(a["rule"], a["username"], a["severity"]) for a in new] == [("hatali_giris", "ali", "kritik")]
    assert "5 hatalı giriş" in new[0]["summary"] and "1.2.3.4" in new[0]["summary"]
    assert D.evaluate(engine, TN, NOW + timedelta(minutes=5)) == []            # aynı patlama ikinci kez uyarı açmaz


def test_offhours_bulk_export_rule(engine):
    night = datetime(2026, 9, 28, 20, 40, tzinfo=timezone.utc)               # 23:40 İstanbul
    D.state_set(engine, "rules_at", (night - timedelta(hours=1)).isoformat())
    for i in range(3):
        D.record_access(engine, "ali", "export", "GET", "/api/v1/reports/r1/file", "ozellik:veri.disa-aktar",
                        at=night + timedelta(minutes=i))
    for i in range(3):                                                        # mesai içi: sayılmaz
        D.record_access(engine, "veli", "export", "GET", "/api/v1/board/export.xlsx", "ozellik:veri.disa-aktar",
                        at=NOW + timedelta(minutes=i))
    new = D.evaluate(engine, TN, night + timedelta(minutes=10))
    assert [(a["rule"], a["username"]) for a in new] == [("mesai_disi_aktarim", "ali")]
    assert D.off_hours(night, D.settings()) and not D.off_hours(NOW, D.settings())
    saturday = datetime(2026, 9, 26, 10, 0, tzinfo=timezone.utc)
    assert D.off_hours(saturday, D.settings())


def test_new_admin_and_everyone_widened_after_baseline(engine):
    assert D.evaluate(engine, TN, NOW, admin_set={"zekiai"}, everyone={"all": False, "perms": ["sayfa:panolar"]}) == []
    new = D.evaluate(engine, TN, NOW + timedelta(minutes=5), admin_set={"zekiai", "Ayse"},
                     everyone={"all": False, "perms": ["sayfa:panolar", "sayfa:butce"]})
    assert sorted((a["rule"], a["username"]) for a in new) == [("herkes_genisledi", None), ("yeni_yonetici", "ayse")]
    assert "sayfa:butce" in next(a for a in new if a["rule"] == "herkes_genisledi")["summary"]
    # Daraltma uyarı değildir.
    assert D.evaluate(engine, TN, NOW + timedelta(minutes=10), admin_set={"zekiai"},
                      everyone={"all": False, "perms": []}) == []


def test_retention_stalled_only_when_applying(engine, monkeypatch):
    assert D.evaluate(engine, TN, NOW, retention_last_ok=NOW - timedelta(days=5)) == []
    monkeypatch.setenv("SECURITY_RETENTION_APPLY", "1")
    new = D.evaluate(engine, TN, NOW, retention_last_ok=NOW - timedelta(days=3))
    assert [a["rule"] for a in new] == ["saklama_durdu"]
    assert D.evaluate(engine, TN, NOW + timedelta(hours=1), retention_last_ok=NOW - timedelta(days=3)) == []


def test_close_alert_needs_verdict_and_reason(engine):
    D.state_set(engine, "admins_seen", [])
    a = D.evaluate(engine, TN, NOW, admin_set={"ayse"})[0]
    with pytest.raises(D.SecurityError):
        D.close_alert(engine, a["id"], "zekiai", {})
    with pytest.raises(D.SecurityError):
        D.close_alert(engine, a["id"], "zekiai", {"verdict": "gercek-degil"})
    out, diff = D.close_alert(engine, a["id"], "zekiai", {"verdict": "gercek-degil", "note": "planlı devir"})
    assert out["state"] == "closed" and out["closedBy"] == "zekiai" and diff["to"]["verdict"] == "gercek-degil"
    assert D.list_alerts(engine)["counts"] == {"open": 0, "closed": 1}
    out, _ = D.close_alert(engine, a["id"], "zekiai", {"state": "open"})
    assert out["state"] == "open" and out["verdict"] is None
    with pytest.raises(D.SecurityError) as e:
        D.close_alert(engine, 999, "zekiai", {"verdict": "gercek"})
    assert e.value.status == 404


# ------------------------------------------------------------------ saklama süresi


def _seed_retention(engine):
    with engine.begin() as c:
        for i, age in enumerate((200, 120, 10)):
            c.execute(S.sl_query_log.insert().values(
                id=f"q{i}", tenant_id=TN, datasource_id=DS, question=f"soru {i}", normalized_question=f"soru {i}",
                resolved_json={}, result_json={"columns": ["a"], "records": [{"a": 1}]}, created_at=NOW - timedelta(days=age)))
        c.execute(S.sl_query_log.insert().values(      # başka veri kaynağı: dokunulmaz
            id="qx", tenant_id=TN, datasource_id="baska", question="x", normalized_question="x", resolved_json={},
            result_json={"a": 1}, created_at=NOW - timedelta(days=400)))
        c.execute(S.sl_llm_queue.insert().values(id="l1", tenant_id=TN, datasource_id=DS, purpose="ask", question="metin",
                                                 status="DONE", enqueued_at=NOW - timedelta(days=40)))
        c.execute(S.sl_llm_queue.insert().values(id="l2", tenant_id=TN, datasource_id=DS, purpose="ask", question="bekliyor",
                                                 status="WAITING", enqueued_at=NOW - timedelta(days=40)))
        c.execute(S.sl_llm_job.insert().values(id="j1", tenant_id=TN, datasource_id=DS, module="m", priority=1, status="DONE",
                                               messages_json='[{"role":"user","content":"gizli"}]', params_json="{}",
                                               result="cevap", attempts=1, created_at=NOW - timedelta(days=40),
                                               llm_ms=1200, queue_wait_ms=30))
    _logins(engine, [("ali", True, "ok", NOW - timedelta(days=400)), ("ali", True, "ok", NOW - timedelta(days=3))])


def test_retention_is_preview_only_until_applied(engine):
    _seed_retention(engine)
    prev = {p["id"]: p for p in D.preview(engine, engine, TN, DS, NOW)}
    assert prev["query_result"]["rows"] == 2 and prev["llm_text"]["rows"] == 2 and prev["login"]["rows"] == 1
    assert prev["audit"]["days"] == 0 and prev["audit"]["rows"] is None                  # süresiz
    out = D.run_retention(engine, engine, TN, DS, now=NOW)
    assert out["apply"] is False and all(o["mode"] == "onizleme" for o in out["objects"])
    with engine.connect() as c:
        assert c.execute(sa.select(sa.func.count()).select_from(S.sl_query_log)
                         .where(S.sl_query_log.c.result_json.isnot(None))).scalar() == 4
    runs = D.list_runs(engine)["items"]
    assert {r["mode"] for r in runs} == {"onizleme"} and len(runs) == len(D.RETENTION)


def test_retention_apply_matches_its_preview(engine, monkeypatch):
    _seed_retention(engine)
    monkeypatch.setenv("SECURITY_RETENTION_APPLY", "1")
    before = {p["id"]: p["rows"] for p in D.preview(engine, engine, TN, DS, NOW)}
    out = D.run_retention(engine, engine, TN, DS, now=NOW)
    applied = {o["id"]: o["rows"] for o in out["objects"] if o["mode"] == "uygulama"}
    assert applied == {k: v for k, v in before.items() if v}
    with engine.connect() as c:
        q = {r.id: r.result_json for r in c.execute(sa.select(S.sl_query_log.c.id, S.sl_query_log.c.result_json))}
        assert q["q0"] is None and q["q1"] is None and q["q2"] is not None and q["qx"] is not None
        assert c.execute(sa.select(S.sl_query_log.c.question).where(S.sl_query_log.c.id == "q0")).scalar() == "soru 0"
        ql = dict(c.execute(sa.select(S.sl_llm_queue.c.id, S.sl_llm_queue.c.question)).all())
        assert ql == {"l1": None, "l2": "bekliyor"}
        j = c.execute(sa.select(S.sl_llm_job)).mappings().one()
        assert j["messages_json"] == "[]" and j["result"] is None and j["llm_ms"] == 1200
        assert c.execute(sa.select(sa.func.count()).select_from(D.LOGINS)).scalar() == 1
    assert all(v in (0, None) for v in (p["rows"] for p in D.preview(engine, engine, TN, DS, NOW)))
    assert D.last_retention_ok(engine) is not None
    assert {r["mode"] for r in D.list_runs(engine)["items"]} == {"onizleme", "uygulama"}


def test_turning_retention_on_requires_the_preview(engine):
    with pytest.raises(D.SecurityError):
        D.retention_update(engine, "zekiai", {"apply": True}, [])
    with pytest.raises(D.SecurityError):
        D.retention_update(engine, "zekiai", {"days": {"login": 3}}, [])                 # 7 günden kısa olamaz
    D.retention_update(engine, "zekiai", {"apply": True, "onizlemeGoruldu": True, "days": {"login": 400}},
                       [{"id": "login", "days": 400, "rows": 0}])
    admin_mod._cache["at"] = 0.0
    cfg = D.settings()
    assert cfg["apply"] is True and cfg["days"]["login"] == 400
    kinds = [(a["kind"], a["objectId"]) for a in admin_mod.audit_list(engine)["items"]]
    assert ("setting", "SECURITY_RETENTION_APPLY") in kinds


# ------------------------------------------------------------------ «Herkes» önizlemesi


class FakeDir:
    def __init__(self, people, crm=None, fail_ad=False):
        self.people = people
        self.crm = crm or []
        self.fail_ad = fail_ad

    def list_people(self):
        if self.fail_ad:
            raise RuntimeError("AD kapalı")
        return [{"subject": u, "label": n} for u, n in self.people.items()]

    def _crm_prefix(self):
        return "Timas_MSCRM.dbo."

    def _crm_rows(self, sql):
        return [{"FullName": n, "DomainName": f"TIMAS\\{u}"} for u, n in self.crm]


def test_everyone_preview_counts_only_people_who_lose_it(engine):
    fin = A.save_role(engine, TN, "zekiai", {"name": "Finans", "perms": ["sayfa:finansal-denetim"]})["id"]
    A.add_binding(engine, TN, "zekiai", fin, {"type": "user", "subject": "mehmet"})
    A.invalidate()
    people = {"ali": "Ali", "ayse": "Ayşe", "mehmet": "Mehmet", "zekiai": "Zeki"}
    out = D.preview_everyone(engine, TN, people=people, is_admin=is_admin, remove=["sayfa:finansal-denetim"])
    assert out["admins"] == 1 and out["people"] == 4
    lose = {k["key"]: k["lose"] for k in out["byKey"]}
    assert lose == {"sayfa:finansal-denetim": 2}
    assert sorted(r["username"] for r in out["items"]) == ["ali", "ayse"]
    # Yalnız Kampüs'e daraltma: herkes bütün sayfaları kaybeder, Finans rolündeki kişi finansal denetimi tutar.
    out = D.preview_everyone(engine, TN, people=people, is_admin=is_admin, perms=[])
    m = next(r for r in out["items"] if r["username"] == "mehmet")
    assert "sayfa:finansal-denetim" not in [x["key"] for x in m["lost"]]
    assert "sayfa:veri-guvenligi" not in {k["key"] for k in out["byKey"]}             # açıkça verilen sayfa zaten yoktu
    with pytest.raises(D.SecurityError):
        D.preview_everyone(engine, TN, people=people, is_admin=is_admin, perms=["sayfa:yok-boyle"])


def test_everyone_preview_equals_effective_when_nothing_changes(engine):
    people = {"ali": "Ali"}
    out = D.preview_everyone(engine, TN, people=people, is_admin=is_admin, remove=[])
    assert out["affected"] == 0


# ------------------------------------------------------------------ hesap hijyeni


def test_hygiene_findings(engine, monkeypatch):
    monkeypatch.setenv("TIMAS_ADMIN_USERS", "zekiai,eskiyonetici")
    admin_mod._cache["at"] = 0.0
    _logins(engine, [("ali", True, "ok", NOW - timedelta(days=200)), ("veli", True, "ok", NOW - timedelta(days=1)),
                     ("qa-deneme", True, "ok", NOW - timedelta(days=2))])
    dirx = FakeDir({"zekiai": "Zeki", "ali": "Ali", "veli": "Veli"}, crm=[("ali", "Ali"), ("ayrildi", "Ayrılan Kişi")])
    sessions = [{"id": "a" * 16, "username": "ayrildi"}, {"id": "b" * 16, "username": "veli"}]
    out = D.hygiene(engine, TN, DS, directory=dirx, sessions=sessions, is_admin=lambda u: u in ("zekiai", "eskiyonetici"), now=NOW)
    kinds = {(i["kind"], i["username"]) for i in out["items"]}
    assert ("oturum_ad_disi", "ayrildi") in kinds
    assert ("yonetici_ad_disi", "eskiyonetici") in kinds
    assert ("crm_etkin_ad_kapali", "ayrildi") in kinds and ("crm_etkin_ad_kapali", "ali") not in kinds
    assert ("test_adi", "qa-deneme") in kinds
    assert ("uzun_suredir_girmedi", "ali") in kinds
    assert ("yalniz_herkes", "veli") in kinds
    assert out["items"][0]["severity"] == "kritik"
    # AD okunamazsa AD'ye dayanan bulgu çıkmaz, not düşülür.
    out = D.hygiene(engine, TN, DS, directory=FakeDir({}, fail_ad=True), sessions=sessions, is_admin=is_admin, now=NOW)
    assert not any(i["kind"] in ("oturum_ad_disi", "yonetici_ad_disi", "crm_etkin_ad_kapali") for i in out["items"])
    assert any("Active Directory" in n for n in out["notes"])


# ------------------------------------------------------------------ envanter


_PII = re.compile(r"(e_?mail|eposta|phone|telefon|gsm|mobile|tckn|tc_?kimlik|iban|adres|address|birth|dogum|photo|foto"
                  r"|display|full_?name|ad_?soyad|contact|author_name)", re.I)


def _bridge_tables() -> dict[str, list[str]]:
    root = Path(D.__file__).parent
    out: dict[str, list[str]] = {}
    for f in root.rglob("*.py"):
        tree = ast.parse(f.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) == "Table"
                    and node.args and isinstance(node.args[0], ast.Constant) and str(node.args[0].value).startswith("semantic_")):
                cols = [a.args[0].value for a in node.args[2:] if isinstance(a, ast.Call) and getattr(a.func, "attr", "") == "Column"
                        and a.args and isinstance(a.args[0], ast.Constant)]
                out[node.args[0].value] = cols
    return out


def test_registry_covers_every_bridge_table_with_personal_columns():
    reg = {t["object"]: t for t in D.registry()["tables"]}
    tables = _bridge_tables()
    missing = []
    for name, cols in tables.items():
        pii = [c for c in cols if _PII.search(c)]
        if pii and (name not in reg or not set(pii) <= set(reg[name]["columns"])):
            missing.append((name, pii))
    assert missing == [], "data_security_inventory.json'a eklenmeli: " + json.dumps(missing, ensure_ascii=False)
    for t in reg.values():
        assert t.get("retention") in (None, *[o["id"] for o in D.RETENTION]), t["object"]
        if t["object"].startswith("semantic_") and t["object"] in tables:
            assert set(t["columns"]) <= set(tables[t["object"]]), t["object"]


class _Col:
    def __init__(self, name, sensitive=False, reason=None):
        self.name, self.sensitive, self.sensitivity_reason = name, sensitive, reason


class _Prof:
    def __init__(self, entity, schema, cols):
        self.entity, self.schema_name, self.table_name, self.columns = entity, schema, entity, cols


def test_inventory_lists_masked_and_name_columns_without_values(engine):
    profs = [_Prof("CONTACTBASE", "Timas_MSCRM.dbo", [_Col("new_tckimlikno", True, "TC kimlik / vergi no"), _Col("FullName"),
                                                       _Col("StateCode")]),
             _Prof("CLCARD", "dbo", [_Col("EMAILADDR", True, "e-posta"), _Col("DEFINITION_")])]
    out = D.inventory(engine, engine, profs)
    cols = {(s["entity"], s["column"], s["masked"]) for s in out["source"]}
    assert cols == {("CONTACTBASE", "new_tckimlikno", True), ("CONTACTBASE", "FullName", False), ("CLCARD", "EMAILADDR", True)}
    assert out["sensitiveCount"] == 2 and out["nameCount"] == 1
    sec = next(p for p in out["portal"] if p["object"] == "semantic_security_logins")
    assert sec["rows"] == 0 and sec["retention"] == "login"


def test_daily_due_once_per_local_day(engine):
    cfg = D.settings()
    early = datetime(2026, 9, 28, 0, 30, tzinfo=timezone.utc)        # 03:30 İstanbul
    late = datetime(2026, 9, 28, 0, 45, tzinfo=timezone.utc)         # 03:45
    assert not D.daily_due(engine, early, cfg)
    assert D.daily_due(engine, late, cfg)
    D.mark_daily(engine, late)
    assert not D.daily_due(engine, late + timedelta(hours=5), cfg)
    assert D.daily_due(engine, late + timedelta(days=1), cfg)
