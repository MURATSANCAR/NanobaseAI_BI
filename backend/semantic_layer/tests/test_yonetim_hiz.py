"""Yönetim genel durumu hızı (2026-09-29): sistem durumu 10 ayrı `systemctl` süreci yerine iki süreçle, kısa bellekte.

Eski hesap (birim başına `_unit` + `_timer_times`) ile yeni hesap aynı sonucu verir; bellek süresince süreç açılmaz;
«yenile» (fresh) beklenerek yeniden okur; systemctl yoksa hepsi «bilinmiyor» (eskisi gibi).
"""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from semantic_bridge import admin as A

PROPS = {
    "timas-alerts.timer": dict(ActiveState="active", SubState="waiting", LastTriggerUSec="Tue 2026-09-29 10:00:00 +03",
                               NextElapseUSecRealtime="", Result="success"),
    "timas-reports.timer": dict(ActiveState="active", SubState="waiting", LastTriggerUSec="n/a",
                                NextElapseUSecRealtime="Tue 2026-09-29 10:05:00 +03", Result="success"),
    "nanobase-semantic-bridge.service": dict(ActiveState="active", SubState="running", LastTriggerUSec="",
                                             NextElapseUSecRealtime="", Result="success"),
    "timas-vpn-mfa.service": dict(ActiveState="failed", SubState="failed", LastTriggerUSec="", NextElapseUSecRealtime="",
                                  Result="exit-code"),
}
LIST_TIMERS = (
    "Tue 2026-09-29 10:15:00 +03 9min left Tue 2026-09-29 10:00:00 +03 5min ago timas-alerts.timer timas-alerts.service\n"
    "- - Mon 2026-09-28 03:00:00 +03 1 day ago timas-seo.timer timas-seo.service\n"
)


def _block(name: str) -> str:
    p = PROPS.get(name, dict(ActiveState="inactive", SubState="dead", LastTriggerUSec="", NextElapseUSecRealtime="",
                             Result="success"))
    wanted = ["Id", "ActiveState", "SubState", "LastTriggerUSec", "NextElapseUSecRealtime", "Result"]
    vals = {"Id": name, **p}
    return "\n".join(f"{k}={vals[k]}" for k in wanted if k in vals)


@pytest.fixture
def fake_systemctl(monkeypatch):
    calls: list[list[str]] = []

    def run(cmd, capture_output=True, text=True, timeout=5):  # noqa: ARG001
        calls.append(list(cmd))
        if cmd[:2] == ["systemctl", "list-timers"]:
            return SimpleNamespace(stdout=LIST_TIMERS)
        assert cmd[:2] == ["systemctl", "show"]
        names = [c for c in cmd[2:cmd.index("-p")]]
        props = cmd[cmd.index("-p") + 1].split(",")
        blocks = []
        for n in names:
            lines = [ln for ln in _block(n).splitlines() if ln.split("=", 1)[0] in props]
            blocks.append("\n".join(lines))
        return SimpleNamespace(stdout="\n\n".join(blocks) + "\n")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(A, "_status_mem", None)
    return calls


def _old_status() -> dict:
    times = A._timer_times()
    timers = []
    for t in A.TIMERS:
        u = {**t, **A._unit(t["unit"])}
        nxt, last = times.get(t["unit"], (None, None))
        u["next"] = nxt or u.get("next")
        u["last"] = last or u.get("last")
        timers.append(u)
    return {"services": [{**s, **A._unit(s["unit"])} for s in A.SERVICES], "timers": timers}


def test_eski_hesapla_ayni_ve_iki_surec(fake_systemctl):
    old = _old_status()
    old_calls = len(fake_systemctl)
    assert old_calls == 1 + len(A.TIMERS) + len(A.SERVICES)
    fake_systemctl.clear()
    new = A.system_status()
    assert new == old
    assert len(fake_systemctl) == 2, "bütün birimler tek show + zamanlayıcı listesi"
    assert A.system_status() == old and len(fake_systemctl) == 2, "kısa bellek: yeniden süreç açılmaz"
    assert A.system_status(fresh=True) == old and len(fake_systemctl) == 4, "yenile beklenerek okur"


def test_systemctl_yoksa_bilinmiyor(monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError("systemctl")

    monkeypatch.setattr(subprocess, "run", boom)
    monkeypatch.setattr(A, "_status_mem", None)
    out = A.system_status()
    assert out == _old_status()
    assert all(u["state"] == "unknown" for u in out["services"] + out["timers"])


def test_eslenemeyen_blok_tek_basina_okunur(monkeypatch):
    """Toplu çıktıda birimin bloğu yoksa (beklenmedik çıktı) o birim eskisi gibi tek başına okunur."""
    def run(cmd, capture_output=True, text=True, timeout=5):  # noqa: ARG001
        if cmd[:2] == ["systemctl", "list-timers"]:
            return SimpleNamespace(stdout="")
        names = cmd[2:cmd.index("-p")]
        if len(names) > 1:
            return SimpleNamespace(stdout="")          # toplu okuma boş döndü
        return SimpleNamespace(stdout=_block(names[0]) + "\n")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(A, "_status_mem", None)
    out = A.system_status()
    assert out == _old_status()
    assert next(s for s in out["services"] if s["unit"] == "timas-vpn-mfa.service")["state"] == "failed"
