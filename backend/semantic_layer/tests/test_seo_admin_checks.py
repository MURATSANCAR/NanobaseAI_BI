"""Yönetim «Bağlantıyı sına»: satır satır sonuç, özet kuralı ve anahtarın mesaja sızmaması."""
from __future__ import annotations

import httpx

from semantic_bridge.seo_geo import checks, connections


def test_summarize_rules():
    ok = {"label": "A", "state": "ok", "message": "", "ms": 1}
    err = {"label": "B", "state": "err", "message": "", "ms": 1}
    off = {"label": "C", "state": "off", "message": "", "ms": 0}
    assert checks.summarize([off, off]) == (False, "Hiçbir bağlantı girilmemiş.")
    good, msg = checks.summarize([ok, off])
    assert good and "1 tanesi girilmemiş" in msg
    bad, msg = checks.summarize([ok, err, off])
    assert not bad and "1 / 2" in msg and "B" in msg


def test_key_never_in_message(monkeypatch):
    secret = "AIzaSECRET123"

    def boom(*a, **k):
        raise httpx.ConnectError(f"failed https://x/?key={secret}")

    monkeypatch.setattr(httpx.Client, "get", boom)
    monkeypatch.setattr(connections, "_conf", lambda k: secret if k == "YOUTUBE_API_KEY" else "")
    part = checks._run("YouTube", checks._youtube, secret)
    assert part["state"] == "err"
    assert secret not in part["message"]


def test_off_when_nothing_entered(monkeypatch):
    monkeypatch.setattr(connections, "_conf", lambda k: "")
    parts = checks.seo_parts() + checks.geo_parts()
    assert parts and all(p["state"] == "off" for p in parts)


def test_merchant_off_without_account_id(monkeypatch):
    monkeypatch.setattr(connections, "_conf", lambda k: "{}" if k == "GOOGLE_SERVICE_ACCOUNT_JSON" else "")
    monkeypatch.setattr(checks, "_run", lambda label, fn, *s: {"label": label, "state": "ok", "message": "", "ms": 0})
    part = next(p for p in checks.seo_parts() if p["label"] == "Google Merchant Center")
    assert part["state"] == "off" and "Merchant Center kimliği" in part["message"]


def test_merchant_403_is_err_without_secret(monkeypatch):
    token = "ya29.SECRETTOKEN"
    conf = {"GOOGLE_SERVICE_ACCOUNT_JSON": "{}", "MERCHANT_ACCOUNT_ID": "123456"}
    monkeypatch.setattr(connections, "_conf", lambda k: conf.get(k, ""))
    monkeypatch.setattr(connections, "google_token", lambda: token)
    monkeypatch.setattr(connections, "service_account_email", lambda: "sa@proj.iam.gserviceaccount.com")
    seen = {}

    def fake_get(self, url, **kw):
        seen["url"] = url
        return httpx.Response(403, json={"error": {"message": f"denied {token}"}}, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.Client, "get", fake_get)
    part = checks._run("Google Merchant Center", checks._merchant)
    assert part["state"] == "err"
    assert "Erişim yok" in part["message"]
    assert token not in part["message"]
    assert seen["url"].endswith("/accounts/v1/accounts/123456")
