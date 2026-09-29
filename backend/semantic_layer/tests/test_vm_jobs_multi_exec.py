"""Müşteri yığınının iş çalıştırıcısı çok satırlı birimi systemd gibi koşar mı (Type=oneshot, bütün ExecStart'lar sırayla)."""
from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("vm_jobs_multi", ROOT / "infra/docker/bi/jobs.py")
jobs = importlib.util.module_from_spec(SPEC)
sys.modules["vm_jobs_multi"] = jobs
SPEC.loader.exec_module(jobs)  # type: ignore[union-attr]
SCHED = str(ROOT / "scripts/server")

CURL = "/bin/sh -c 'curl -fsS -m {t} -X POST \"http://127.0.0.1:8795{p}\"'"


def _unit(tmp_path: Path, name: str, execs: list[str]) -> None:
    (tmp_path / f"{name}.timer").write_text(f"[Timer]\nOnCalendar=*-*-* 04:00:00\nUnit={name}.service\n", encoding="utf-8")
    body = "\n".join(f"ExecStart={e}" for e in execs)
    (tmp_path / f"{name}.service").write_text(f"[Service]\nType=oneshot\nDescription={name}\n{body}\n", encoding="utf-8")


@pytest.fixture()
def calls(monkeypatch):
    """Köprü çağrılarını kaydeder; `fail` kümesindeki yollar hata verir."""
    rec = {"posted": [], "fail": set(), "reports": [], "state": []}

    def post(path, body, timeout):
        rec["posted"].append(path)
        if path in rec["fail"]:
            raise RuntimeError(f"500 {path}")
        return {"ok": True}

    monkeypatch.setattr(jobs, "_post", post)
    monkeypatch.setattr(jobs, "report", lambda job, ok, detail="": rec["reports"].append((ok, detail)))
    monkeypatch.setattr(jobs, "_write_state", lambda name, at: rec["state"].append(name))
    return rec


def test_channels_unit_loads_every_exec_in_order():
    loaded, skipped = jobs.load_jobs(SCHED)
    assert [n for n, why in skipped if "JOBS_EXCLUDE" not in why] == []
    ch = {j.name: j for j in loaded}["timas-channels"]
    assert [s.path for s in ch.steps] == [
        "/api/v1/channels/run-due?tur=gece",
        "/api/v1/channels/trendyol/run-due",
        "/api/v1/channels/amazon/run-due",
    ]
    assert [s.ignore_failure for s in ch.steps] == [False, True, True]
    assert [s.timeout for s in ch.steps] == [3590, 3590, 3590]
    assert ch.path == "/api/v1/channels/run-due?tur=gece"  # eski alan ilk adımı gösterir, son satırı değil


def test_single_line_units_keep_one_step():
    loaded, _ = jobs.load_jobs(SCHED)
    by = {j.name: j for j in loaded}
    assert len(by["timas-stock"].steps) == 1 and by["timas-stock"].steps[0].path == by["timas-stock"].path
    d = by["timas-dealers-gunluk"]
    assert [s.path for s in d.steps] == ["/api/v1/dealers/run-due?tur=gunluk"] and d.unit == "timas-dealers@gunluk"
    assert by["timas-stock"].unit == "timas-stock"


def test_all_lines_run_in_order(tmp_path, calls):
    _unit(tmp_path, "timas-x", [CURL.format(t=10, p="/api/a"), CURL.format(t=20, p="/api/b"), CURL.format(t=30, p="/api/c")])
    (job,), _ = jobs.load_jobs(str(tmp_path), exclude=[])
    assert [s.timeout for s in job.steps] == [10, 20, 30]
    assert jobs.run(job) is True
    assert calls["posted"] == ["/api/a", "/api/b", "/api/c"]
    assert calls["reports"] == [(True, "")] and calls["state"] == ["timas-x"]


def test_failure_stops_following_lines(tmp_path, calls):
    _unit(tmp_path, "timas-x", [CURL.format(t=10, p="/api/a"), CURL.format(t=10, p="/api/b"), CURL.format(t=10, p="/api/c")])
    (job,), _ = jobs.load_jobs(str(tmp_path), exclude=[])
    calls["fail"] = {"/api/b"}
    assert jobs.run(job) is False
    assert calls["posted"] == ["/api/a", "/api/b"]
    (ok, detail), = calls["reports"]
    assert ok is False and "/api/b" in detail and "koşmadı: /api/c" in detail
    assert calls["state"] == ["timas-x"]


def test_dash_prefixed_failure_does_not_stop(tmp_path, calls):
    _unit(tmp_path, "timas-x", [CURL.format(t=10, p="/api/a"), "-" + CURL.format(t=10, p="/api/b"),
                                "-" + CURL.format(t=10, p="/api/c")])
    (job,), _ = jobs.load_jobs(str(tmp_path), exclude=[])
    calls["fail"] = {"/api/b"}
    assert jobs.run(job) is True
    assert calls["posted"] == ["/api/a", "/api/b", "/api/c"]
    (ok, detail), = calls["reports"]
    assert ok is True and "yok sayıldı" in detail


def test_first_line_failure_stops_dash_lines_too(tmp_path, calls):
    """systemd: öneksiz satır düşerse sonraki `-` satırlar da koşmaz (timas-channels'ta gece turu düşerse)."""
    _unit(tmp_path, "timas-x", [CURL.format(t=10, p="/api/a"), "-" + CURL.format(t=10, p="/api/b")])
    (job,), _ = jobs.load_jobs(str(tmp_path), exclude=[])
    calls["fail"] = {"/api/a"}
    assert jobs.run(job) is False
    assert calls["posted"] == ["/api/a"]


def test_empty_execstart_resets(tmp_path):
    _unit(tmp_path, "timas-x", [CURL.format(t=10, p="/api/old"), "", CURL.format(t=10, p="/api/new")])
    (job,), _ = jobs.load_jobs(str(tmp_path), exclude=[])
    assert [s.path for s in job.steps] == ["/api/new"]


def test_non_bridge_line_rejects_whole_unit(tmp_path):
    _unit(tmp_path, "timas-x", [CURL.format(t=10, p="/api/a"), "/usr/local/bin/betik.sh"])
    loaded, skipped = jobs.load_jobs(str(tmp_path), exclude=[])
    assert loaded == [] and skipped and skipped[0][0] == "timas-x"


def test_same_unit_does_not_run_twice(tmp_path, calls, monkeypatch):
    _unit(tmp_path, "timas-x", [CURL.format(t=10, p="/api/a"), CURL.format(t=10, p="/api/b")])
    (job,), _ = jobs.load_jobs(str(tmp_path), exclude=[])
    entered, release = threading.Event(), threading.Event()
    real = jobs._post

    def slow(path, body, timeout):
        if path == "/api/a" and not entered.is_set():
            entered.set()
            release.wait(5)
        return real(path, body, timeout)

    monkeypatch.setattr(jobs, "_post", slow)
    t = threading.Thread(target=jobs.run, args=(job,))
    t.start()
    assert entered.wait(5)
    assert jobs.run(job) is False  # birinci tur sürerken ikinci tetik atlanır
    release.set()
    t.join(5)
    assert calls["posted"] == ["/api/a", "/api/b"]
    assert jobs.run(job) is True  # tur bitince yeniden koşabilir
