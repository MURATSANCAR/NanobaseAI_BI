"""Sessiz başarı yok (2026-10-03): olay döngüsünü tıkayan iş kendi döngüsünde, altyapı hatasıyla düşen
zorunlu adım (kimlik, son okuma) iş akışında yeniden denenir, olmazsa iş FAILED; kalıcı hata eski yol.
Geri doldurma komutunun saf parçaları."""

from __future__ import annotations

import asyncio
import contextvars
import threading
import time
import uuid
from collections.abc import Sequence
from types import SimpleNamespace

import pytest

from editor import offloop, transient

try:                                   # dinamik etkinliğin tip ipucu modül düzeyinde çözülür
    from temporalio.common import RawValue
except ImportError:  # pragma: no cover
    RawValue = object


# ------------------------------------------------------------------ hata sınıfı
def test_transient_classes():
    from editor.llm import ContextOverflow, ModelError
    assert transient.is_transient(ConnectionResetError("reset"))
    assert transient.is_transient(TimeoutError())
    assert transient.is_transient(ModelError("book-director failed after 3 attempts: 503 unavailable"))
    assert transient.is_transient(ModelError("gpu_busy: another job"))
    assert transient.is_transient(ModelError('503 {"error":"model_not_ready"}'))
    assert not transient.is_transient(ModelError("book-director failed after 3 attempts: 400 context length"))
    assert not transient.is_transient(ModelError("finish_reason=length after 900 chars"))
    assert not transient.is_transient(ContextOverflow("400 maximum context length"))
    assert not transient.is_transient(ValueError("bad page"))
    assert not transient.is_transient(KeyError("x"))
    try:                                       # zincirde altyapı hatası: geçici
        try:
            raise ConnectionRefusedError("db")
        except ConnectionRefusedError as e:
            raise RuntimeError("wrapped") from e
    except RuntimeError as e:
        assert transient.is_transient(e)


def test_failure_type_from_temporal():
    assert transient.failure_type_transient("TransientStepFailure")
    assert transient.failure_type_transient("ConnectError")
    assert transient.failure_type_transient("OperationalError")
    assert transient.failure_type_transient("ModelError", "x failed after 3 attempts: 503 busy")
    assert not transient.failure_type_transient("ModelError", "400 context length")
    assert not transient.failure_type_transient("ValueError", "Identity proposal rejected")
    assert not transient.failure_type_transient("ContextOverflow", "503")
    assert not transient.failure_type_transient(None)


def test_workflow_classifies_heartbeat_timeout_as_infrastructure():
    pytest.importorskip("temporalio")
    from temporalio.exceptions import ActivityError, ApplicationError, TimeoutError, TimeoutType
    from editor.workflow.workflows import infrastructure_failure

    def err(cause):
        e = ActivityError("Activity task failed", scheduled_event_id=1, started_event_id=2, identity="w",
                          activity_type="proofreading", activity_id="1", retry_state=None)
        e.__cause__ = cause
        return e
    assert infrastructure_failure(err(TimeoutError("activity Heartbeat timeout", type=TimeoutType.HEARTBEAT,
                                                   last_heartbeat_details=[])))
    assert infrastructure_failure(err(ApplicationError("x", type="TransientStepFailure")))
    assert infrastructure_failure(err(ApplicationError("x", type="ConnectError")))
    assert not infrastructure_failure(err(ApplicationError("bad", type="ValueError", non_retryable=True)))
    assert not infrastructure_failure(err(ApplicationError("400 context length", type="ContextOverflow")))


# ------------------------------------------------------------------ kendi döngüsü
def test_offloop_keeps_the_callers_loop_turning():
    async def blocking(n):
        time.sleep(0.6)                       # senkron iş: yalnız kendi döngüsünü dondurur
        return n * 2

    async def main():
        ticks = 0

        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.05)
                ticks += 1
        t = asyncio.create_task(ticker())
        out = await offloop.run(blocking, 21)
        t.cancel()
        return out, ticks
    out, ticks = asyncio.run(main())
    assert out == 42 and ticks >= 6           # 0,6 sn boyunca çağıranın döngüsü döndü


def test_offloop_runs_in_another_thread_with_the_callers_context():
    var = contextvars.ContextVar("v", default=None)

    async def where():
        return threading.get_ident(), var.get()

    async def main():
        var.set("activity-context")
        return threading.get_ident(), await offloop.run(where)
    me, (other, seen) = asyncio.run(main())
    assert me != other and seen == "activity-context"


def test_offloop_raises_the_steps_error():
    async def boom():
        raise ConnectionResetError("model gone")

    async def main():
        await offloop.run(boom)
    with pytest.raises(ConnectionResetError):
        asyncio.run(main())


def test_offloop_cancel_reaches_the_inner_task():
    state = {"cancelled": False, "finished": False}

    async def long():
        try:
            await asyncio.sleep(30)
            state["finished"] = True
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    async def main():
        t = asyncio.create_task(offloop.run(long))
        await asyncio.sleep(0.2)
        t.cancel()
        with pytest.raises(asyncio.CancelledError):
            await t
    asyncio.run(main())
    assert state == {"cancelled": True, "finished": False}


def test_model_client_is_per_loop_and_closed_with_it():
    from editor import llm

    async def mine():
        return llm.client()

    async def main():
        a = llm.client()
        b = await offloop.run(mine)
        return a, b
    a, b = asyncio.run(main())
    assert a is not b and b.is_closed and not any(c is b for _, c in llm._clients.values())


# ------------------------------------------------------------------ son okuma: kaldığı yerden, geçici hata işareti
class _Check:
    def __init__(self, name, fn, version="1"):
        self.NAME, self.VERSION, self.LABEL, self.fn = name, version, name, fn

    async def run(self, gid):
        return self.fn(gid)


def _fake_proofing(monkeypatch, mods, done=None):
    from editor import proofing as P
    rec, failed = [], []
    monkeypatch.setattr(P, "checks", lambda: dict(mods))

    async def profile(gid):
        return {"form": "FICTION", "audience": "ADULT"}
    monkeypatch.setattr(P.book_type, "profile", profile)
    monkeypatch.setattr(P, "advisory_reason", lambda name, prof: None)
    monkeypatch.setattr(P, "record", lambda gid, mod, f, s, t0: rec.append(mod.NAME) or {"run_id": mod.NAME,
                                                                                         "findings": len(f)})
    monkeypatch.setattr(P, "_failed", lambda gid, name, mod, e, t0: failed.append(name))
    monkeypatch.setattr(P, "recorded", lambda gid: dict(done or {}))
    return P, rec, failed


def test_run_all_marks_infrastructure_failures_and_runs_off_the_loop(monkeypatch):
    from editor.llm import ModelError
    loops = []

    def ok(gid):
        loops.append(threading.get_ident())
        return [{"page": 1, "severity": "WARN", "message": "m"}]

    def down(gid):
        raise ModelError("book-director failed after 3 attempts: 503 unavailable")

    def bug(gid):
        raise ValueError("kuralın kendi hatası")
    mods = {"a": _Check("a", ok), "b": _Check("b", down), "c": _Check("c", bug)}
    P, rec, failed = _fake_proofing(monkeypatch, mods)
    seen = []
    out = asyncio.run(P.run_all("g", progress=lambda **kw: seen.append(kw.get("check"))))
    assert rec == ["a"] and failed == ["b", "c"]
    assert out["b"]["transient"] is True and "transient" not in out["c"]
    assert loops and loops[0] != threading.get_ident()
    assert seen == ["a", "b", "c", None]


def test_run_all_resume_skips_recorded_checks(monkeypatch):
    mods = {"a": _Check("a", lambda g: []), "b": _Check("b", lambda g: [])}
    P, rec, failed = _fake_proofing(monkeypatch, mods, done={"a": "run-1"})
    out = asyncio.run(P.run_all("g", resume=True))
    assert rec == ["b"] and out["a"] == {"resumed": "run-1"}
    P, rec, failed = _fake_proofing(monkeypatch, mods, done={"a": "run-1"})
    asyncio.run(P.run_all("g"))                  # resume yoksa eskisi gibi hepsi
    assert rec == ["a", "b"]


def test_proofreading_activity_raises_retryable_on_infrastructure(monkeypatch):
    pytest.importorskip("temporalio")
    from temporalio.exceptions import ApplicationError
    from editor import proofing as P
    from editor.workflow import activities as act
    calls = []

    async def run_all(gid, only=None, *, resume=False, progress=None):
        calls.append(resume)
        return {"a": {"run_id": "1"}, "b": {"failed": "503", "transient": True}, "c": {"failed": "bug"}}
    monkeypatch.setattr(P, "run_all", run_all)
    monkeypatch.setattr(act.activity, "info", lambda: SimpleNamespace(attempt=2))
    with pytest.raises(ApplicationError) as e:
        asyncio.run(act.proofreading("g"))
    assert e.value.type == transient.TYPE and not e.value.non_retryable and calls == [True]

    async def fine(gid, only=None, *, resume=False, progress=None):
        return {"a": {"run_id": "1"}, "c": {"failed": "bug"}}
    monkeypatch.setattr(P, "run_all", fine)
    assert asyncio.run(act.proofreading("g"))["c"] == {"failed": "bug"}     # kalıcı hata işi düşürmez


def test_identity_activity_strict_never_asks_on_last_attempt(monkeypatch):
    pytest.importorskip("temporalio")
    from editor.workflow import activities as act
    seen = []

    async def resolve(gid, final_attempt=False):
        seen.append(final_attempt)
        return {"characters": 2}
    monkeypatch.setattr(act.knowledge, "resolve_character_identity", resolve)
    monkeypatch.setattr(act.activity, "info", lambda: SimpleNamespace(attempt=4))
    asyncio.run(act.resolve_identity("g"))
    asyncio.run(act.resolve_identity("g", True))
    assert seen == [True, False]


# ------------------------------------------------------------------ iş akışı
def _run(profile: str, behave: dict):
    """BookFullAnalysis'i sahte etkinliklerle koşturur; `behave[name](call_no, *args)` sonucu döner ya da atar."""
    testing = pytest.importorskip("temporalio.testing")
    from temporalio import activity
    from temporalio.worker import Worker
    from editor.workflow.workflows import BookFullAnalysis
    calls: list[tuple[str, list]] = []
    base = {
        "prepare_generation": lambda n, job: {"generation_id": "g1", "book_version_id": "bv1", "profile": profile},
        "page_manifest": lambda n, bv: {"page_count": 3, "needs_ocr": []},
        "archive_visual_pages": lambda n, bv: {"pages": [1]},
        "scan_page_fast": lambda n, gid, p: {"page_no": p, "uncertain": False},
        "confirm_text_visual": lambda n, gid: {"pages": 0, "proposed": 0, "confirmed": 0, "confirmed_pages": [],
                                               "pages_failed": []},
        "text_chunks": lambda n, gid: [[1, 3]],
        "resolve_identity": lambda n, gid, *strict: {"characters": 1},
        "narrative_roles": lambda n, gid: {"pages": []},
        "rebuild_outputs": lambda n, gid: {"technical_status": "SUCCEEDED"},
        "archive_outputs": lambda n, gid: {"technical_status": "SUCCEEDED"},
        "detect_contradictions": lambda n, gid: {"found": 0},
        "queue_contradictions": lambda n, gid: {"queued": 0},
        **behave,
    }

    @activity.defn(dynamic=True)
    async def fake(args: Sequence[RawValue]) -> dict:
        name = activity.info().activity_type
        vals = [activity.payload_converter().from_payload(a.payload) for a in args]
        calls.append((name, vals))
        fn = base.get(name)
        return fn(sum(1 for n, _ in calls if n == name), *vals) if fn else {}

    async def main():
        try:
            env = await testing.WorkflowEnvironment.start_time_skipping()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"Temporal test sunucusu yok: {e}")
        async with env, Worker(env.client, task_queue="t", workflows=[BookFullAnalysis], activities=[fake]):
            wid = f"wf-{uuid.uuid4().hex}"
            try:
                out = await env.client.execute_workflow("BookFullAnalysis", "job1", id=wid, task_queue="t")
            except Exception as e:  # noqa: BLE001 - iş FAILED
                out = e
            hist = await env.client.get_workflow_handle(wid).fetch_history()
            marks = []
            for ev in hist.events:
                if ev.HasField("marker_recorded_event_attributes"):
                    for p in ev.marker_recorded_event_attributes.details.values():
                        marks += [x.data.decode("utf-8", "replace") for x in p.payloads]
            return out, " ".join(marks)
    out, hist = asyncio.run(main())
    return out, calls, hist


def _app_error(msg, typ):
    from temporalio.exceptions import ApplicationError
    return ApplicationError(msg, type=typ)


def _finish(calls):
    return [v[1] for n, v in calls if n == "finish_job"][-1], [v[2] for n, v in calls if n == "finish_job"][-1]


def test_proofreading_infrastructure_failure_is_retried_then_succeeds():
    def proof(n, gid, *resume):
        if n <= 4:                              # ilk tur: dört deneme de düşer (Temporal yeniden denemesi)
            raise _app_error("son okuma denetimleri altyapı hatasıyla tamamlanamadı: layout", "TransientStepFailure")
        return {"layout": {"run_id": "r"}, "age_fit": {"failed": "kural"}}
    out, calls, hist = _run("full", {"proofreading": proof})
    status, result = _finish(calls)
    assert status == "SUCCEEDED" and "infra-step-retry-v1" in hist
    runs = [v for n, v in calls if n == "proofreading"]
    assert runs[0] == ["g1"] and runs[-1] == ["g1", True]        # ikinci tur kaldığı yerden
    assert "proofreading" not in result["failures"]
    assert result["failures"]["proofreading_checks"] == ["age_fit"]


def test_proofreading_that_never_passes_fails_the_job():
    def proof(n, gid, *resume):
        raise _app_error("Heartbeat yok", "TransientStepFailure")
    out, calls, hist = _run("full", {"proofreading": proof})
    status, result = _finish(calls)
    assert status == "FAILED" and "proofreading" in result["error"]
    assert isinstance(out, Exception)
    assert sum(1 for n, _ in calls if n == "proofreading") == 12          # 3 tur × 4 deneme
    assert "rebuild_outputs" not in [n for n, _ in calls]


def test_proofreading_permanent_failure_keeps_the_old_handling():
    def proof(n, gid, *resume):
        raise _app_error("kural hatası", "ValueError")
    out, calls, hist = _run("full", {"proofreading": proof})
    status, result = _finish(calls)
    assert status == "SUCCEEDED" and "kural hatası" in result["failures"]["proofreading"][0]
    assert sum(1 for n, _ in calls if n == "proofreading") == 1           # ValueError yeniden denenmez


def test_identity_infrastructure_failure_fails_the_job_instead_of_zero_characters():
    def ident(n, gid, *strict):
        assert strict == (True,)
        raise _app_error("connection refused", "ConnectError")
    out, calls, hist = _run("archive", {"resolve_identity": ident})
    status, result = _finish(calls)
    assert status == "FAILED" and "identity" in result["error"]
    assert "identity_unresolved" not in [n for n, _ in calls]


def test_identity_permanent_failure_still_goes_to_the_editor():
    def ident(n, gid, *strict):
        raise _app_error("Identity proposal rejected", "ValueError")
    out, calls, hist = _run("full", {"resolve_identity": ident})
    status, result = _finish(calls)
    assert status == "SUCCEEDED" and "identity" in result["failures"]
    assert "identity_unresolved" in [n for n, _ in calls]


def test_archive_still_defers_proofreading():
    out, calls, hist = _run("archive", {})
    assert "proofreading" not in [n for n, _ in calls] and _finish(calls)[0] == "SUCCEEDED"


# ------------------------------------------------------------------ geri doldurma (saf parçalar)
def test_backfill_selects_steps_in_order_and_skips():
    from editor import backfill as B
    f = {"proofreading": ["activity Heartbeat timeout"], "identity": ["activity Heartbeat timeout"],
         "deep_scan": [{"failed": 3}], "ocr": []}
    assert B.failed_steps(f) == ["identity", "proofreading"]
    assert B.failed_steps(f, ("proofreading",)) == ["proofreading"]
    assert B.failed_steps({"identity": []}) == []
    ok = {"generation_id": "g", "sealed_at": None, "origin": "TRACKED", "newer": 0, "profile": "full"}
    assert B.skip_reason(ok) is None
    assert B.skip_reason({**ok, "newer": 1})
    assert B.skip_reason({**ok, "sealed_at": "2026-10-01"})
    assert B.skip_reason({**ok, "origin": "LEGACY"})
    assert B.actions(["identity", "proofreading"], "full")[-1] == "son okuma baştan"
    assert B.actions(["proofreading"], "full")[-1] == "son okuma: eksik denetimler"
    assert not any("son okuma" in a for a in B.actions(["identity"], "archive"))


def test_backfill_apply_marks_only_finished_steps(monkeypatch):
    from editor import backfill as B
    from editor import figure_identity, knowledge
    done, notes = [], []

    async def resolve(gid, final_attempt=False):
        assert final_attempt is False
        return {"characters": 3, "confirmed": 2}

    async def proofread(gid, resume):
        assert resume is False                  # kimlik yeniden okunduysa denetimler baştan
        return {"a": {}}, [], ["layout"]        # bir denetim yine altyapıdan düştü

    async def outputs(gid, profile):
        return {"technical_status": "SUCCEEDED"}
    monkeypatch.setattr(knowledge, "resolve_character_identity", resolve)
    monkeypatch.setattr(B, "close_identity_question", lambda gid, n: 1)
    monkeypatch.setattr(B, "proofread", proofread)
    monkeypatch.setattr(B, "outputs", outputs)
    monkeypatch.setattr(B, "mark_done", lambda job, step, s: done.append(step))
    monkeypatch.setattr(B, "note_checks", lambda job, lost: notes.append(lost))
    import editor.db as db
    monkeypatch.setattr(db, "one", lambda sql, *a: {"n": 0})
    from editor.workflow import activities

    async def cont(gid):
        return {"checked": []}
    monkeypatch.setattr(activities, "continuity_checks", cont)
    monkeypatch.setattr(figure_identity, "resolve", None)          # görsel anma yok: çağrılmaz
    res = asyncio.run(B.apply_one({"generation_id": "g", "job_id": "j", "profile": "full",
                                   "steps": ["identity", "proofreading"]}))
    assert done == ["identity"] and res["identity"]["characters"] == 3 and res["proofreading"]["transient"]


def _outputs_with(monkeypatch, results):
    """backfill.outputs, rebuild.run sırayla `results`ı verir (istisna ise yükseltir); bekleme ve kuyruk sayılır."""
    from editor import backfill as B, rebuild
    calls, slept, queued = [], [], []

    async def run(gid):
        r = results[len(calls)]
        calls.append(gid)
        if isinstance(r, BaseException):
            raise r
        return r

    async def sleep(s):
        slept.append(s)
    monkeypatch.setattr(rebuild, "run", run)
    monkeypatch.setattr(rebuild, "requeue", lambda gid, reason="": queued.append(reason) or True)
    return B, calls, slept, queued, sleep


def test_backfill_outputs_retries_infrastructure_errors_then_succeeds(monkeypatch):
    B, calls, slept, queued, sleep = _outputs_with(
        monkeypatch, [ConnectionError("bağlantı koptu"), {"technical_status": "SUCCEEDED"}])
    res = asyncio.run(B.outputs("g", "full", waits=(1.0, 2.0), sleep=sleep))
    assert res == {"technical_status": "SUCCEEDED"} and len(calls) == 2 and slept == [1.0] and queued == []


def test_backfill_outputs_queues_when_busy_or_still_failing(monkeypatch):
    B, calls, slept, queued, sleep = _outputs_with(monkeypatch, [{"technical_status": "BUSY"}])
    res = asyncio.run(B.outputs("g", "full", waits=(1.0,), sleep=sleep))
    assert res["technical_status"] == "QUEUED" and queued == ["backfill:busy"] and slept == []
    B, calls, slept, queued, sleep = _outputs_with(
        monkeypatch, [ConnectionError("x"), ConnectionError("y")])
    res = asyncio.run(B.outputs("g", "full", waits=(1.0,), sleep=sleep))
    assert res["technical_status"] == "QUEUED" and len(calls) == 2 and queued == ["backfill:transient"]


def test_backfill_outputs_does_not_retry_book_errors(monkeypatch):
    B, calls, slept, queued, sleep = _outputs_with(monkeypatch, [ValueError("Rebuild retry budget exhausted")])
    res = asyncio.run(B.outputs("g", "full", waits=(1.0, 2.0), sleep=sleep))
    assert res["technical_status"] == "FAILED" and len(calls) == 1 and slept == [] and queued == []
