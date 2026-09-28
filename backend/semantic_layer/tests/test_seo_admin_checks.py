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
