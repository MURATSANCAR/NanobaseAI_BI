"""M48 Sistem durumu: olay aç/kapat (iki ardışık hata), tazelik olayı (donmuş Logo kopyası), yalnız iç alıcıya tek
e-posta, hatırlatma ve yeniden deneme, sürüm eşliği, açıkça verilen sayfa yetkisi, köprü uçlarının kapısı, ekranda
teknoloji adı olmaması.

Veriler yapaydır ve yalnız kuralları sınar; gerçek Logo/CRM/SMTP kabulü test sunucusunda
(`scripts/acceptance/M48/kabul.py`, günlük 2026-09-28: DOĞRULANAMADI — sunucu kapalı).
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from semantic_bridge import access as A
from semantic_bridge import it_ops as I
from semantic_bridge import it_ops_sources as S
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.conftest import TENANT

UTC = timezone.utc
T0 = datetime(2026, 9, 28, 9, 0, tzinfo=UTC)
# Bu dosyanın kural testleri deneme sayısını sınar: süre eşiği ve yeniden başlatma payı kapalı. Gürültü önleme
# (süre eşiği, açılış kaydı, tek kopma + tek düzelme) test_ic_bildirim.py'de.
ST = {"everySec": 300, "failsToOpen": 2, "outageMin": 0, "restartGraceMin": 0, "logoStaleDays": 3, "crmStaleHours": 24,
      "remindHours": 24, "staleRemindHours": 24, "weeklyDay": 1, "reportHour": 8}


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    I._ready.discard(id(e))
    I.ensure(e)
    return e


class Outbox:
    """Gönderici yerine: bildirimi (ic_bildirim.Notice) düz metne çevirip saklar."""

    def __init__(self, result: str = "sent"):
        self.result = result
        self.mails: list[tuple[str, str, list[str]]] = []
        self.notices: list = []

    def __call__(self, notice, to):
        from semantic_bridge import ic_bildirim as IB

        self.notices.append(notice)
        self.mails.append((notice.subject, IB.render_text(notice), list(to)))
        return self.result


def tour(engine, results, at, st=ST):
    for r in results:
        I.record_check(engine, TENANT, r["ring"], r["ok"], data_end=r.get("data_end"), detail=r.get("detail", ""), at=at)
    return I.evaluate(engine, TENANT, results, st, now=at)


def open_rows(engine, kind=None):
    with engine.connect() as c:
        q = sa.select(I.INCIDENTS).where(I.INCIDENTS.c.closed_at.is_(None))
        if kind:
            q = q.where(I.INCIDENTS.c.kind == kind)
        return c.execute(q).mappings().all()


# ------------------------------------------------------------------ olay mantığı


def test_one_failure_is_noise_two_open_an_incident_and_success_closes_it(engine):
    out = Outbox()
    assert tour(engine, [{"ring": "logo", "ok": False, "detail": "zaman aşımı"}], T0)["opened"] == []
    assert I.notify(engine, TENANT, ST, out, ["bt@timas.com.tr"], now=T0)["sent"] is None and not out.mails
    # «uygulanmaz» ölçüm araya girse de sayılmaz: ne kopma ne düzelme
    tour(engine, [{"ring": "logo", "ok": None}], T0 + timedelta(minutes=2))
    ch = tour(engine, [{"ring": "logo", "ok": False, "detail": "zaman aşımı"}], T0 + timedelta(minutes=5))
    assert len(ch["opened"]) == 1
    inc = open_rows(engine)[0]
    assert I._aware(inc["opened_at"]) == T0                    # başlangıç ilk başarısız deneme
    assert I.notify(engine, TENANT, ST, out, ["bt@timas.com.tr"], now=T0 + timedelta(minutes=5))["new"] == 1
    subject, text, to = out.mails[-1]
    assert subject.startswith("[Kesinti] Logo bağlantısı") and "NE YAPMALI" in text and to == ["bt@timas.com.tr"]
    # sürerken yeni e-posta yok (alarm yorgunluğu)
    tour(engine, [{"ring": "logo", "ok": False}], T0 + timedelta(minutes=10))
    assert I.notify(engine, TENANT, ST, out, ["bt@timas.com.tr"], now=T0 + timedelta(minutes=10))["sent"] is None
    ch = tour(engine, [{"ring": "logo", "ok": True, "data_end": T0}], T0 + timedelta(minutes=47))
    assert ch["closed"] == [inc["id"]] and not open_rows(engine, "kopma")
    I.notify(engine, TENANT, ST, out, ["bt@timas.com.tr"], now=T0 + timedelta(minutes=47))
    assert out.mails[-1][0].startswith("[Düzeldi]") and "47 dk sürdü" in out.mails[-1][1]
    assert len(out.mails) == 2


def test_unsent_opening_is_retried_and_its_recovery_is_not_announced(engine):
    none = Outbox("no_smtp")
    tour(engine, [{"ring": "crm", "ok": False}], T0)
    tour(engine, [{"ring": "crm", "ok": False}], T0 + timedelta(minutes=5))
    assert I.notify(engine, TENANT, ST, none, ["bt@timas.com.tr"], now=T0 + timedelta(minutes=5))["sent"] == "no_smtp"
    assert I.notify(engine, TENANT, ST, none, ["bt@timas.com.tr"], now=T0 + timedelta(minutes=10))["new"] == 1   # yeniden denendi
    tour(engine, [{"ring": "crm", "ok": True}], T0 + timedelta(minutes=15))
    ok = Outbox()
    I.notify(engine, TENANT, ST, ok, ["bt@timas.com.tr"], now=T0 + timedelta(minutes=15))
    assert ok.mails == []                                         # açılışı bilinmeyen olayın düzelmesi duyurulmaz
    with engine.connect() as c:
        assert c.execute(sa.select(I.INCIDENTS.c.closed_notify)).scalar() == "skip"


def test_reminder_after_remind_hours(engine):
    out = Outbox()
    for m in (0, 5):
        tour(engine, [{"ring": "vpn", "ok": False}], T0 + timedelta(minutes=m))
    I.notify(engine, TENANT, ST, out, ["bt@timas.com.tr"], now=T0 + timedelta(minutes=5))
    assert I.notify(engine, TENANT, ST, out, ["bt@timas.com.tr"], now=T0 + timedelta(hours=23))["remind"] == 0
    r = I.notify(engine, TENANT, ST, out, ["bt@timas.com.tr"], now=T0 + timedelta(hours=24, minutes=6))
    assert r["remind"] == 1 and out.mails[-1][0].startswith("[Sürüyor]")
    # Varsayılan ayarda hatırlatma kapalı: aynı olay için ikinci e-posta yok.
    assert I.settings(lambda k, d="": d)["remindHours"] == 0 and I.settings(lambda k, d="": d)["staleRemindHours"] == 0


def test_frozen_logo_copy_opens_a_staleness_incident_even_when_connected(engine):
    end = datetime(2026, 8, 17, 21, 0, tzinfo=UTC)
    ch = tour(engine, [{"ring": "logo", "ok": True, "data_end": end, "detail": "Bağlandı."}], T0)
    assert len(ch["opened"]) == 1 and open_rows(engine, "tazelik")
    st = I.status(engine, TENANT, ST, now=T0)
    logo = next(r for r in st["rings"] if r["id"] == "logo")
    assert logo["state"] == "stale" and logo["dataEnd"].startswith("2026-08-17") and "gün önce" in logo["dataEndAge"]
    assert st["summary"]["tone"] == "warn" and "Logo verisi eski" in st["summary"]["text"]
    # bağlantı koparsa veri sonu bilinmez: tazelik kararı değişmez, kapanmaz
    tour(engine, [{"ring": "logo", "ok": False}], T0 + timedelta(minutes=5))
    assert open_rows(engine, "tazelik")
    # taze veri gelince kapanır
    ch = tour(engine, [{"ring": "logo", "ok": True, "data_end": T0}], T0 + timedelta(minutes=10))
    assert ch["closed"] and not open_rows(engine, "tazelik")


def test_downtime_counts_minutes_inside_the_window_and_skips_false_alarms(engine):
    for m in (0, 5):
        tour(engine, [{"ring": "model", "ok": False}], T0 + timedelta(minutes=m))
    tour(engine, [{"ring": "model", "ok": True}], T0 + timedelta(minutes=30))
    d = I.downtime(engine, TENANT, T0 - timedelta(days=7), T0 + timedelta(hours=1))
    assert d["model"] == {"count": 1, "minutes": 30} and d["logo"] == {"count": 0, "minutes": 0}
    iid = I.list_incidents(engine, TENANT, state="closed")["items"][0]["id"]
    out, diff = I.update_incident(engine, TENANT, iid, {"falseAlarm": True, "rootCause": "Model sunucusu bakımı"}, "bt")
    assert out["falseAlarm"] and diff["falseAlarm"] == {"from": False, "to": True}
    assert I.downtime(engine, TENANT, T0 - timedelta(days=7), T0 + timedelta(hours=1))["model"]["count"] == 0


def test_postmortem_is_published_only_after_close(engine):
    for m in (0, 5):
        tour(engine, [{"ring": "eposta", "ok": False}], T0 + timedelta(minutes=m))
    iid = open_rows(engine)[0]["id"]
    with pytest.raises(I.ItOpsError):
        I.update_incident(engine, TENANT, iid, {"postmortem": "taslak", "publish": True}, "bt")
    tour(engine, [{"ring": "eposta", "ok": True}], T0 + timedelta(minutes=9))
    out, _ = I.update_incident(engine, TENANT, iid, {"postmortem": "Ne oldu: …", "publish": True}, "bt")
    assert out["postmortemStatus"] == "yayında" and out["postmortemBy"] == "bt"
    msgs = I.draft_prompt(I.get_incident(engine, TENANT, iid))
    assert "uydurma" in msgs[0]["content"] and "Süre: 9 dk" in msgs[1]["content"]


def test_postmortem_draft_numbers_must_come_from_the_incident(engine):
    for m in (0, 5):
        tour(engine, [{"ring": "eposta", "ok": False}], T0 + timedelta(minutes=m))
    tour(engine, [{"ring": "eposta", "ok": True}], T0 + timedelta(minutes=9))
    inc = I.get_incident(engine, TENANT, I.list_incidents(engine, TENANT, state="closed")["items"][0]["id"])
    facts = "\n".join(I.draft_facts(inc))
    day = re.search(r"Başlangıç: (\d\d)\.(\d\d)\.(\d{4}) (\d\d):(\d\d)", facts)
    assert day
    good = (f"Ne oldu:\nE-posta halkası {int(day.group(1))} Eylül {day.group(3)} saat {day.group(4)}:{day.group(5)}'de düştü.\n"
            "Süre:\n9 dk. Başarısız deneme sayısı 2.\nOlası neden:\nvLLM değil, posta sunucusu.")
    text, src, bad = I.guard_draft(good, inc)
    assert src == "zeki" and bad == [] and "vLLM" not in text and "Zeki AI modeli" in text   # teknoloji adı sadeleşir
    text, src, bad = I.guard_draft("Ne oldu:\nKesinti 45 dakika sürdü, 300 kullanıcı etkilendi.", inc)
    assert src == "kural" and bad == ["300", "45"]
    assert text == I.rule_draft(inc) and "Süre:\n9 dk." in text and "başarısız deneme sayısı 2" in text
    assert I.foreign_numbers(text, I.draft_facts(inc)) == []          # kural taslağı da yalnız olgudaki sayıyı taşır
    assert I.guard_draft("  ", inc)[1] == "kural"
    long = dict(inc, minutes=65)
    assert "Süre (dakika): 65" in I.draft_facts(long) and I.foreign_numbers("65 dakika sürdü", I.draft_facts(long)) == []


# ------------------------------------------------------------------ alıcılar, metin, sürüm


def test_only_internal_recipients_get_mail():
    ok, bad = I.internal_recipients("bt@timas.com.tr, dis@gmail.com;ops@nanobase.ai  x@timas.com.tr", "timas.com.tr")
    assert ok == ["bt@timas.com.tr", "x@timas.com.tr"] and bad == ["dis@gmail.com", "ops@nanobase.ai"]
    assert I.internal_recipients("bt@timas.com.tr", "") == ([], ["bt@timas.com.tr"])   # alan adı yoksa kimseye


def test_screen_text_has_no_technology_names():
    t = I.screen_text("OperationalError: FreeTDS pyodbc hata; docker kapsayıcısı; systemctl; vLLM Qwen3.8-27B; openvpn tun0")
    for word in ("freetds", "pyodbc", "docker", "systemctl", "vllm", "qwen", "openvpn"):
        assert word not in t.lower(), word


def test_release_records_and_parity(engine):
    with pytest.raises(I.ItOpsError):
        I.record_release(engine, TENANT, {"env": "prod"})
    with pytest.raises(I.ItOpsError):
        I.record_release(engine, TENANT, {"env": "test", "codeSha": "abc; rm -rf"})
    I.record_release(engine, TENANT, {"env": "test", "codeSha": "a" * 40, "appledoubleCount": 0})
    I.record_release(engine, TENANT, {"env": "vm", "codeSha": "b" * 40, "appledoubleCount": 3, "image": "bridge:latest"})
    r = I.list_releases(engine, TENANT)
    assert r["parity"] is False and r["latest"]["vm"]["appledoubleCount"] == 3
    I.record_release(engine, TENANT, {"env": "vm", "codeSha": "a" * 40, "appledoubleCount": 0})
    assert I.list_releases(engine, TENANT)["parity"] is True


def test_data_end_sql_is_dynamic_and_guarded():
    rows = [{"FIRMNR": 211, "BEGDATE": "2021-01-01", "ENDDATE": "2025-12-31"},
            {"FIRMNR": 411, "BEGDATE": "2026-01-01", "ENDDATE": "2026-12-31"}]
    firm = S.logo_current_firm(lambda sql: rows)
    assert firm in ("411", "211")
    assert "LG_411_01_INVOICE" in S.logo_data_end_sql("411") and "CANCELLED = 0" in S.logo_data_end_sql("411")
    with pytest.raises(ValueError):
        S.logo_data_end_sql("411; DROP")
    assert S.crm_data_end_sql("Timas_MSCRM.dbo").startswith("SELECT MAX(ModifiedOn) AS son FROM Timas_MSCRM.dbo.new_kitapBase")
    with pytest.raises(ValueError):
        S.crm_data_end_sql("x;y.dbo")


# ------------------------------------------------------------------ halkalar ve tur


def _ctx(engine, **kw):
    conf = {"ITOPS_MODEL_TIMEOUT_SEC": "1", "ITOPS_RING_TIMEOUT_SEC": "2", **kw.pop("conf", {})}
    return S.Ctx(engine=engine, tenant=TENANT, conf=lambda k, d="": conf.get(k, d), logo_file=lambda: "", crm_file=lambda: "",
                 in_container=False, **kw)


def test_busy_model_queue_is_not_an_outage(engine):
    class Busy:
        last_wait_ms = 0

        def chat(self, messages, **kw):
            time.sleep(3)
            return "TAMAM"

    r = S.check_model(_ctx(engine, llm=lambda: Busy()))
    assert r["ok"] is None and "meşgul" in r["detail"]

    class Quick:
        last_wait_ms = 0

        def chat(self, messages, **kw):
            kw["on_admitted"]()
            return "TAMAM"

    assert S.check_model(_ctx(engine, llm=lambda: Quick()))["ok"] is True
    assert S.check_model(_ctx(engine, llm=lambda: None))["ok"] is False


def test_vm_ring_reads_the_jobs_heartbeat_inside_the_customer_vm(engine):
    ctx = _ctx(engine)
    ctx.in_container = True
    assert S.check_vm(ctx)["ok"] is None                                         # hiç bildirim yok: ölçülmedi
    I.upsert_job(engine, TENANT, "vm:/api/v1/reports/run-due", label="planlı raporlar", source="jobs-container",
                 last_at=I._now(), last_ok=True)
    assert S.check_vm(ctx)["ok"] is True
    assert S.check_vpn(ctx)["ok"] is None                                        # VM şirket ağının içinde


def test_run_tour_records_opens_notifies_and_sends_the_daily_job_digest(engine, monkeypatch):
    from semantic_bridge import it_ops_api

    fakes = {rid: (lambda ok: (lambda ctx: {"ok": ok, "detail": "sahte", "latency_ms": 5, "data_end": None}))(rid != "vpn")
             for rid in S.CHECKERS}
    ctx = _ctx(engine, overrides=fakes, conf={"ITOPS_RECIPIENTS": "bt@timas.com.tr, dis@gmail.com",
                                              "ITOPS_INTERNAL_DOMAINS": "timas.com.tr",
                                              "ITOPS_OUTAGE_MIN": "0", "ITOPS_RESTART_GRACE_MIN": "0"})
    I.upsert_job(engine, TENANT, "tablo:planli-raporlar", label="Planlı raporlar", source="table", last_at=T0,
                 last_ok=False, last_error="Aylık ciro: Logo'ya ulaşılamadı", failed_count=1)
    out = Outbox()
    r1 = it_ops_api.run_tour(ctx, "logo", send=out, collect=False, now=T0)
    assert r1["checked"] == len(S.CHECKERS) and r1["failed"] == ["vpn"] and r1["opened"] == 0
    assert r1["rejectedRecipients"] == ["dis@gmail.com"]
    assert r1["daily"] == "sent" and "Planlı raporlar" in out.mails[-1][1]
    r2 = it_ops_api.run_tour(ctx, "logo", send=out, collect=False, now=T0 + timedelta(minutes=5))
    assert r2["opened"] == 1 and r2["notify"]["sent"] == "sent" and "daily" not in r2   # günlük özet günde bir
    assert all(m[2] == ["bt@timas.com.tr"] for m in out.mails)
    with engine.connect() as c:
        assert c.execute(sa.select(sa.func.count()).select_from(I.CHECKS)).scalar() == 2 * len(S.CHECKERS)


# ------------------------------------------------------------------ yetki


def test_system_status_page_is_explicit_and_not_given_to_everyone():
    assert {"sayfa:sistem-durumu", "ozellik:sistem.dene", "ozellik:sistem.olay-kapat", "ozellik:sistem.ayar"} <= A.explicit_keys()
    everyone = A.Access(user="biri", admin=False, all=True, perms=frozenset())
    assert not everyone.can("sayfa:sistem-durumu") and everyone.can("sayfa:genel-bakis")
    bt = A.Access(user="bt", admin=False, all=False, perms=frozenset({"sayfa:sistem-durumu"}))
    assert bt.can("sayfa:sistem-durumu") and not bt.can("ozellik:sistem.dene")
    assert A.rule_for("/api/v1/it-ops/run-due") == A.SYSTEM and A.rule_for("/api/v1/it-ops/watchdog") == A.SYSTEM
    assert A.rule_for("/api/v1/it-ops/report-release") == A.SYSTEM and A.rule_for("/api/v1/it-ops/banner") == A.OPEN
    assert A.rule_for("/api/v1/it-ops/status") == frozenset({"sayfa:sistem-durumu"})
    assert A.features_for("POST", "/api/v1/it-ops/check-now") == []   # açıkça verilen yetki ucun içinde denetlenir


def _app(monkeypatch, store, settings):
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import board as board_mod
    from semantic_bridge.app import Runtime, create_app
    from semantic_layer.candidates.llm_client import FakeLlm

    users = {"timas_session=a": "ayse", "timas_session=z": "zekiai", "timas_session=b": "bt"}
    monkeypatch.setattr(board_mod, "_fetch_user", lambda cookie: users.get(cookie))
    monkeypatch.setattr(board_mod, "_fetch_session", lambda cookie: {"username": users.get(cookie), "displayName": "x"})
    monkeypatch.setattr(admin_mod, "admins", lambda: ["zekiai"])
    monkeypatch.delenv("SEMANTIC_CALLER_TOKEN", raising=False)
    monkeypatch.delenv("SEMANTIC_ADMIN_TOKEN", raising=False)
    for rid in list(S.CHECKERS):
        monkeypatch.setitem(S.CHECKERS, rid, lambda ctx: {"ok": True, "detail": "sahte", "latency_ms": 1, "data_end": None})
    monkeypatch.setattr(S, "collect_timers", lambda ctx: 0)
    A._ready.clear()
    A.invalidate()
    app = create_app(Runtime(settings, store=store, llm=FakeLlm([""])))
    return app, TestClient(app)


def test_bridge_gate_and_endpoints(monkeypatch, store, settings):
    app, client = _app(monkeypatch, store, settings)
    a, z, b = ({"cookie": f"timas_session={x}"} for x in "azb")
    # «Herkes» (kurulumda bütün sayfalar) bu sayfayı görmez; üst bant herkese açık
    assert client.get("/api/v1/it-ops/status", headers=a).status_code == 403
    assert client.get("/api/v1/it-ops/banner", headers=a).status_code == 200
    # zamanlayıcı: çerezsiz; kişi çereziyle yalnız yönetici
    assert client.post("/api/v1/it-ops/run-due").status_code == 200
    assert client.post("/api/v1/it-ops/run-due", headers=a).status_code == 403
    st = client.get("/api/v1/it-ops/status", headers=z).json()
    assert st["summary"]["tone"] == "ok" and len(st["rings"]) == 7 and st["me"]["canCheck"] is True
    # sayfası verilen BT personeli okur ama işlem yetkisi yoksa deneyemez
    engine = store.engine
    rid = A.save_role(engine, TENANT, "zekiai", {"name": "BT", "perms": ["sayfa:sistem-durumu"]})["id"]
    A.add_binding(engine, TENANT, "zekiai", rid, {"type": "user", "subject": "bt"})
    A.invalidate()
    assert client.get("/api/v1/it-ops/status", headers=b).status_code == 200
    assert client.post("/api/v1/it-ops/check-now", json={}, headers=b).status_code == 403
    assert client.put("/api/v1/it-ops/settings", json={"values": {"ITOPS_FAILS_TO_OPEN": "3"}}, headers=b).status_code == 403
    A.save_role(engine, TENANT, "zekiai", {"name": "BT", "perms": ["sayfa:sistem-durumu", "ozellik:sistem.dene",
                                                                    "ozellik:sistem.ayar"]}, rid)
    A.invalidate()
    assert client.post("/api/v1/it-ops/check-now", json={"ring": "logo"}, headers=b).json()["checked"] == 1
    bad = client.put("/api/v1/it-ops/settings", json={"values": {"TIMAS_ADMIN_USERS": "bt"}}, headers=b)
    assert bad.status_code == 422                                              # yalnız sistem durumu ayarları
    assert client.put("/api/v1/it-ops/settings", json={"values": {"ITOPS_FAILS_TO_OPEN": "3"}}, headers=b).status_code == 200
    # bekçi ve kurulum betiği
    assert client.post("/api/v1/it-ops/watchdog", json={"job": "kopru-saglik", "ok": False, "detail": "docker yok"}).status_code == 200
    jobs = client.get("/api/v1/it-ops/jobs", headers=b).json()["items"]
    assert jobs[0]["job"] == "kopru-saglik" and jobs[0]["lastOk"] is False and "docker" not in jobs[0]["lastError"].lower()
    rel = client.post("/api/v1/it-ops/report-release", json={"env": "test", "codeSha": "c" * 40, "appledoubleCount": 0})
    assert rel.status_code == 200 and client.get("/api/v1/it-ops/releases", headers=b).json()["latest"]["test"]["codeSha"] == "c" * 40
    assert client.post("/api/v1/it-ops/report-release", json={"env": "prod"}).status_code == 422


def test_screens_have_no_technology_names():
    root = Path(__file__).resolve().parents[3] / "src" / "canvas" / "it-ops"
    banned = re.compile(r"systemd|systemctl|docker|nginx|vllm|openvpn|qwen|socat", re.I)
    hits = []
    for p in root.glob("*.ts*"):
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            if banned.search(line) and not line.strip().startswith(("//", "*", "/*")) and "'systemd'" not in line and "systemd:" not in line:
                hits.append(f"{p.name}:{i}: {line.strip()[:80]}")
    assert hits == []
    for r in I.RINGS:
        assert not banned.search(r["label"] + r["hint"] + r["recipe"])


def test_crm_data_end_text_is_utc():
    """Bağlantı CRM tarihini metin verirse de UTC sayılır (İstanbul sayılınca 3 saat erken görünüyordu)."""
    from datetime import datetime as _D, timezone as _Z
    from semantic_bridge import it_ops_sources as _S
    assert _S.crm_utc("2026-09-28T09:09:15") == _D(2026, 9, 28, 9, 9, 15, tzinfo=_Z.utc)
    assert _S.crm_utc(_D(2026, 9, 28, 9, 9, 15)) == _D(2026, 9, 28, 9, 9, 15, tzinfo=_Z.utc)
    assert _S.crm_utc(None) is None and _S.crm_utc("x") is None
