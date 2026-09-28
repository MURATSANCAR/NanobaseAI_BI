"""Müşteri yığınının iş çalıştırıcısı (infra/docker/bi/jobs.py) test sunucusunun zamanlayıcılarını birebir okur mu."""
from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location("vm_jobs", ROOT / "infra/docker/bi/jobs.py")
jobs = importlib.util.module_from_spec(SPEC)
sys.modules["vm_jobs"] = jobs  # dataclass, `from __future__ import annotations` ile modülü sys.modules'ta arar
SPEC.loader.exec_module(jobs)  # type: ignore[union-attr]
IST = ZoneInfo("Europe/Istanbul")
SCHED = str(ROOT / "scripts/server")


def at(s: str) -> datetime:
    return datetime.fromisoformat(s).replace(tzinfo=IST)


def test_every_repo_timer_loads_or_is_deliberately_off():
    loaded, skipped = jobs.load_jobs(SCHED)
    off = {n for n, why in skipped if "JOBS_EXCLUDE" in why}
    broken = [(n, why) for n, why in skipped if n not in off]
    assert broken == []
    assert off == {n for n in off if n == "timas-web-watch" or n.startswith("timas-model-quality-")}
    names = {j.name for j in loaded}
    assert {"timas-stock", "timas-seo", "timas-shipping", "timas-alerts", "timas-dealers-gunluk"} <= names
    assert len(loaded) >= 60


def test_templated_service_and_query():
    loaded, _ = jobs.load_jobs(SCHED)
    by = {j.name: j for j in loaded}
    assert by["timas-dealers-gunluk"].path == "/api/v1/dealers/run-due?tur=gunluk"
    assert by["timas-channels-report"].path == "/api/v1/channels/run-due?tur=rapor"
    assert by["timas-seo"].timeout == 1700 and by["timas-seo"].persistent


def test_calendar_forms():
    daily = jobs.parse_calendar("*-*-* 06:30:00")
    assert daily.next_after(at("2026-09-28T06:29:59")) == at("2026-09-28T06:30:00")
    assert daily.next_after(at("2026-09-28T06:30:00")) == at("2026-09-29T06:30:00")
    mon = jobs.parse_calendar("Mon *-*-* 08:00:00")  # 2026-09-28 pazartesi
    assert mon.next_after(at("2026-09-28T09:00:00")) == at("2026-10-05T08:00:00")
    second = jobs.parse_calendar("*-*-02 08:00:00")
    assert second.next_after(at("2026-09-28T00:00:00")) == at("2026-10-02T08:00:00")
    hourly = jobs.parse_calendar("*-*-* *:35:00")
    assert hourly.next_after(at("2026-09-28T10:40:00")) == at("2026-09-28T11:35:00")
    q = jobs.parse_calendar("*:0/15")
    assert q.next_after(at("2026-09-28T10:16:00")) == at("2026-09-28T10:30:00")
    office = jobs.parse_calendar("*-*-* 08..19:00/15:00 Europe/Istanbul")
    assert office.next_after(at("2026-09-28T19:50:00")) == at("2026-09-29T08:00:00")
    assert office.next_after(at("2026-09-28T08:01:00")) == at("2026-09-28T08:15:00")
    weekdays = jobs.parse_calendar("Mon..Fri *-*-* 08..19:30:00 Europe/Istanbul")
    assert weekdays.next_after(at("2026-10-02T19:31:00")) == at("2026-10-05T08:30:00")  # cuma → pazartesi


def test_persistent_catchup_point():
    job = jobs.Job(name="x", label="x", path="/api/x", timeout=10, calendars=[jobs.parse_calendar("*-*-* 03:00:00")])
    assert job.last_due(at("2026-09-28T10:00:00")) == at("2026-09-28T03:00:00")
    assert job.last_due(at("2026-09-28T02:00:00")) == at("2026-09-27T03:00:00")


def test_spans():
    assert jobs.parse_span("15min") == 900 and jobs.parse_span("1h") == 3600 and jobs.parse_span("2min 30s") == 150


def test_non_bridge_call_is_rejected():
    import pytest

    with pytest.raises(ValueError):
        jobs.parse_exec("/data/nanobaseai/bi/frontend/scripts/server/model-quality-run.sh gece")
    with pytest.raises(ValueError):
        jobs.parse_exec("curl -fsS http://127.0.0.1:8447/api/x")
