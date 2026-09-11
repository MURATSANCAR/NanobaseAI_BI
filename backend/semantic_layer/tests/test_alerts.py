"""Uyarılar: kural soru olarak saklanır, kontrol serviste yapılır, bildirim kenarda gider."""

from __future__ import annotations

import smtplib
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from semantic_bridge import alerts as A
from semantic_layer.store.catalog_store import open_store
from semantic_layer.tests.test_runtime import catalog  # noqa: F401

T, D = "t1", "logo"


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    A._ready.discard(id(e))
    A.ensure(e)
    return e


def _rule(engine, **kw):
    body = {"title": "İade tutarı", "question": "bu ay iade tutarı", "condition": "gt", "threshold": 100,
            "recipients": ["cfo@example.com"], **kw}
    return A.create_rule(engine, T, D, body)


def _answer(v):
    return lambda rule: {"records": [{"iade_tutari": v}], "sql": "SELECT 1"}


def test_notification_goes_once_per_breach_and_again_after_recovery(engine):
    r = _rule(engine)
    sent = []
    notify = lambda rule, value: sent.append(value) or "sent"  # noqa: E731
    t0 = datetime(2026, 9, 11, 9, tzinfo=timezone.utc)
    A.check(engine, T, D, _answer(150), notify, now=t0)
    A.check(engine, T, D, _answer(160), notify, now=t0 + timedelta(minutes=15))
    assert sent == [150], "hâlâ aşan kural her kontrolde yeniden e-posta atmamalı"
    A.check(engine, T, D, _answer(90), notify, now=t0 + timedelta(minutes=30))
    assert A.get_rule(engine, T, D, r["id"])["state"] == "ok"
    A.check(engine, T, D, _answer(120), notify, now=t0 + timedelta(minutes=45))
    assert sent == [150, 120]
    A.check(engine, T, D, _answer(130), notify, now=t0 + timedelta(hours=25))
    assert sent == [150, 120, 130], "süre dolunca bir kez hatırlatır"


def test_an_unsent_alert_is_retried_until_it_goes_out(engine):
    _rule(engine)
    results = iter(["no_smtp", "failed", "sent"])
    calls = []
    notify = lambda rule, value: calls.append(1) or next(results)  # noqa: E731
    for i in range(4):
        A.check(engine, T, D, _answer(150), notify, now=datetime(2026, 9, 11, 9, tzinfo=timezone.utc) + timedelta(minutes=15 * i))
    assert len(calls) == 3, "e-posta ayarı sonradan gelse de bekleyen uyarı gitmeli, sonra susmalı"


def test_several_rows_are_an_error_not_a_guess(engine):
    r = _rule(engine)
    out = A.check(engine, T, D, lambda rule: {"records": [{"v": 1}, {"v": 2}]}, lambda *_: "sent")
    rule = A.get_rule(engine, T, D, r["id"])
    assert rule["state"] == "error" and "tek bir değer" in rule["last_error"]
    assert out["errors"] and A.events(engine, r["id"])[0]["error"]


def test_paused_rules_are_not_checked(engine):
    r = _rule(engine)
    A.update_rule(engine, T, D, r["id"], {"status": "paused"})
    assert A.check(engine, T, D, _answer(999), lambda *_: "sent")["checked"] == 0


@pytest.mark.parametrize("bad", [{"recipients": ["yanlis-adres"]}, {"condition": "yaklaşık"}, {"threshold": "çok"},
                                 {"question": "", "sql": ""}])
def test_invalid_rules_are_refused_in_plain_turkish(engine, bad):
    with pytest.raises(A.AlertError):
        _rule(engine, **bad)


def test_smtp_uses_the_configured_server(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            sent["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self, context):
            sent["tls"] = True

        def login(self, user, password):
            sent["login"] = user

        def send_message(self, msg):
            sent["to"], sent["subject"] = msg["To"], msg["Subject"]

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setenv("ALERT_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("ALERT_SMTP_USER", "zeki@example.com")
    monkeypatch.setenv("ALERT_SMTP_PASSWORD", "x")
    rule = {"id": "r1", "title": "İade", "question": "iade", "condition": "gt", "threshold": 1.0,
            "recipients": ["a@example.com", "b@example.com"]}
    assert A.email_notifier("https://ornek/uyarilar")(rule, 2.5) == "sent"
    assert sent == {"server": ("smtp.example.com", 587), "tls": True, "login": "zeki@example.com",
                    "to": "a@example.com, b@example.com", "subject": "ZEKİ uyarı: İade"}


def test_without_a_mail_server_nothing_is_pretended(monkeypatch):
    monkeypatch.delenv("ALERT_SMTP_HOST", raising=False)
    rule = {"id": "r1", "title": "x", "condition": "gt", "threshold": 1.0, "recipients": ["a@example.com"]}
    assert A.email_notifier()(rule, 2) == "no_smtp"
    assert A.email_status() == {"configured": False, "sender": None}


def test_endpoints_measure_a_real_question_on_create(catalog, logo_connector, settings, monkeypatch):
    from semantic_bridge.app import Runtime, create_app

    monkeypatch.delenv("ALERT_SMTP_HOST", raising=False)
    runtime = Runtime(settings, store=catalog, connector=logo_connector, llm=None)
    client = TestClient(create_app(runtime))
    made = client.post("/api/v1/alerts", json={"title": "Net ciro", "question": "2026 yılında net ciro",
                                                "condition": "gt", "threshold": -1, "recipients": "cfo@example.com"})
    assert made.status_code == 200, made.text
    rule = made.json()
    assert rule["state"] == "triggered" and rule["last_value"] is not None, rule
    assert rule["last_notify"] == "no_smtp" and rule["sql"]
    listed = client.get("/api/v1/alerts").json()
    assert [a["id"] for a in listed["alerts"]] == [rule["id"]] and listed["email"]["configured"] is False
    upd = client.patch(f"/api/v1/alerts/{rule['id']}", json={"threshold": 1e18}).json()
    assert upd["state"] == "unknown"
    out = client.post("/api/v1/alerts/check").json()
    assert out["checked"] == 1 and out["triggered"] == 0
    assert client.get(f"/api/v1/alerts/{rule['id']}/events").json()["events"][0]["triggered"] is False
    assert client.post("/api/v1/alerts", json={"question": "x", "condition": "gt", "threshold": 1,
                                                "recipients": "bozuk"}).status_code == 422
    assert client.delete(f"/api/v1/alerts/{rule['id']}").json() == {"ok": True}
    assert client.get("/api/v1/alerts").json()["alerts"] == []
