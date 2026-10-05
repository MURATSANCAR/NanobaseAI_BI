"""Gece toplu düşmeleri (2026-10-05 02:23–02:33): işçinin olay döngüsü 81–93 sn durdu, o an süren bütün etkinlikler
sinyal (heartbeat) sınırıyla düştü. Bu dosya kuralı bekler:

- hiçbir etkinlik ana döngüde senkron DB/IO/CPU yapmaz: statik denetim (gövdede her await `_t` / `_own_loop`, modül
  işlevi döngüde çağrılmaz) + çalışma denetimi (gerçekten bloklayan sahte DB ile döngü döner, sinyal sürer),
- yönetmen kapasitesi döngüler arası tek sıra (offloop.SharedSemaphore),
- çıktı SUPERSEDED dönerse sınırlı sayıda, aralıklı yeniden kurulur (iş akışı bayrağı outputs-superseded-retry-v1),
- toplu düzeltme komutları okuması süren (QUEUED/RUNNING) nesle yazmaz, atladıklarını sonda listeler."""
from __future__ import annotations

import ast
import asyncio
import contextlib
import inspect
import pathlib
import pkgutil
import sys
import textwrap
import threading
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import pytest  # noqa: E402
import types  # noqa: E402


class _Stub(types.ModuleType):
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        sub = _Stub(f"{self.__name__}.{name}")
        sys.modules[sub.__name__] = sub
        return sub


# Öteki test dosyaları gibi: gerçek veritabanı sürücüsü yüklenmez. Bu dosya alfabede ilk sırada; gerçek psycopg'yi
# o yüklerse sonraki dosyaların DB'ye dokunan testleri (ör. test_loop_and_rebuild_queue) sahte sürücüde hemen
# düşmek yerine DB'siz ortamda 300 sn havuz bekler ve tam set saatlerce sürer.
for _mod in ("psycopg", "psycopg.rows", "psycopg.types", "psycopg.types.json", "psycopg_pool"):
    sys.modules.setdefault(_mod, _Stub(_mod))

pytest.importorskip("temporalio")

import editor  # noqa: E402
from editor import offloop  # noqa: E402
from editor.workflow import activities as A  # noqa: E402

BLOCK = 0.6           # sahte DB'nin gerçekten blokladığı süre (sn)
MAX_GAP = 0.25        # döngünün bundan uzun durması bloklama sayılır


class Ticker:
    def __init__(self):
        self.max_gap = 0.0
        self._task = None

    async def _run(self):
        last = time.monotonic()
        while True:
            await asyncio.sleep(0.01)
            now = time.monotonic()
            self.max_gap = max(self.max_gap, now - last)
            last = now

    def __enter__(self):
        self._task = asyncio.get_running_loop().create_task(self._run())
        return self

    def __exit__(self, *a):
        self._task.cancel()


# ------------------------------------------------------------------ statik: etkinlik gövdesi döngüde iş yapmaz
#: Saf, anlık çağrılar (DB'ye / dosyaya / modele gitmez).
PURE_CALLS = {"db.J", "book_type.is_book", "activity.info"}
#: Kendisi yalnız dağıtan (her parçası kendi döngüsünde/iş parçacığında) eşyordamlar.
LOOP_SAFE_AWAITS = {"proofing.run_all"}     # her denetim offloop'ta, kayıt okuması to_thread'de
WRAPPERS = {"_t", "_own_loop"}


def _dotted(node) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}"
    if isinstance(node, ast.Call):
        return _dotted(node.func) + "()"
    return type(node).__name__


def _own_nodes(fn: ast.AST):
    """The activity's own statements; functions defined inside it are passed to a wrapper, not run here."""
    stack = list(fn.body)
    while stack:
        n = stack.pop()
        yield n
        for child in ast.iter_child_nodes(n):
            if not isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                stack.append(child)


def test_no_activity_body_works_on_the_loop():
    modules = {m.name for m in pkgutil.iter_modules(editor.__path__)}
    problems = []
    for fn in A.ALL:
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn))).body[0]
        assert isinstance(tree, ast.AsyncFunctionDef), fn
        for n in _own_nodes(tree):
            if isinstance(n, ast.Await):
                name = _dotted(n.value.func) if isinstance(n.value, ast.Call) else _dotted(n.value)
                if name not in WRAPPERS | LOOP_SAFE_AWAITS:
                    problems.append(f"{tree.name}: await {name} ana döngüde")
            if isinstance(n, ast.Call):
                name = _dotted(n.func)
                root = name.split(".")[0]
                if name in WRAPPERS | PURE_CALLS | LOOP_SAFE_AWAITS:
                    continue
                if root in modules:
                    problems.append(f"{tree.name}: {name}() ana döngüde")
                obj = getattr(A, name, None) if "." not in name else None
                if callable(obj) and getattr(obj, "__module__", "").startswith("editor"):
                    problems.append(f"{tree.name}: {name}() ana döngüde")
    assert not problems, "\n".join(problems)


def test_the_static_check_catches_a_blocking_body():
    """Bekçinin kendisi: eski `narrative_roles` / `set_step` biçimleri yakalanır."""
    modules = {m.name for m in pkgutil.iter_modules(editor.__path__)}
    bad = ast.parse(textwrap.dedent('''
        async def narrative_roles(generation_id):
            x = db.one("SELECT 1")
            return await knowledge.assign_narrative_roles(generation_id)
    ''')).body[0]
    names = [_dotted(n.func) for n in _own_nodes(bad) if isinstance(n, ast.Call)]
    assert {"db.one", "knowledge.assign_narrative_roles"} <= set(names)
    assert all(nm.split(".")[0] in modules for nm in ("db.one", "knowledge.assign_narrative_roles"))


# ------------------------------------------------------------------ çalışma: gerçekten bloklayan sahte iş
def _slow(result=None):
    async def coro(*a, **k):
        time.sleep(BLOCK)                 # senkron DB gibi: kendi döngüsünü dondurur
        return {} if result is None else result

    def sync(*a, **k):
        time.sleep(BLOCK)
        return {} if result is None else result
    return coro, sync


ASYNC_TARGETS = [
    ("narrative_roles", ("g",), "knowledge", "assign_narrative_roles"),
    ("verify_modality", ("g",), "knowledge", "verify_event_modality"),
    ("merge_events", ("g",), "knowledge", "merge_events"),
    ("confirm_text_visual", ("g",), "vision", "confirm_text_visual"),
    ("ocr_page", ("g", "bv", 3), "document", "run_ocr"),
    ("page_manifest", ("bv",), "document", "create_page_manifest_async"),
    ("text_layer", ("g", "bv"), "document", "extract_text_layer_async"),
    ("extract_chunk", ("g", [1, 4]), "knowledge", "extract_chunk"),
    ("critic", ("g",), "quality", "critic_pass"),
    ("event_actors", ("g",), "knowledge", "attribute_event_actors"),
    ("detect_contradictions", ("g",), "knowledge", "detect_contradictions"),
    ("embed_index", ("g",), "retrieval", "embed_passages"),
    ("build_card", ("g",), "catalog", "build_card"),
    ("chapter_summary", ("g", {"n": 1}), "summary", "chapter_summary"),
    ("book_summary", ("g",), "summary", "book_summary"),
    ("scan_page_fast", ("g", 2), "vision", "analyze_page_visual"),
]


@pytest.mark.parametrize("name,args,module,attr", ASYNC_TARGETS, ids=[t[0] for t in ASYNC_TARGETS])
def test_activity_keeps_the_loop_turning(name, args, module, attr, monkeypatch):
    import importlib
    mod = importlib.import_module(f"editor.{module}")
    monkeypatch.setattr(mod, attr, _slow()[0])

    async def main():
        with Ticker() as t:
            await getattr(A, name)(*args)
        return t.max_gap
    started = time.monotonic()
    gap = asyncio.run(main())
    assert time.monotonic() - started >= BLOCK                 # iş gerçekten blokladı ...
    assert gap < MAX_GAP, f"{name}: olay döngüsü {gap:.2f} sn durdu"   # ... ama ana döngüde değil


def test_db_activities_keep_the_loop_turning(monkeypatch):
    """Senkron DB yapan bileşik etkinlikler (adım, nesil hazırlığı, kayıt, bitiş, duygu/tema, süreklilik)."""
    from editor import book_type, db, knowledge, ledger, prompts, quality, vision
    coro, sync = _slow()

    def one(sql, *a):
        time.sleep(BLOCK / 3)
        if "FROM analysis_job j" in sql:
            return {"book_version_id": "bv", "book_id": "b", "profile": "full", "progress": {}}
        if "FROM generation WHERE job_id" in sql:
            return {"id": "g", "book_version_id": "bv"}
        return {"n": 0}

    def all_rows(sql, *a):
        time.sleep(BLOCK / 3)
        return [{"page_no": 1}] if "page_scan" in sql else []

    async def profile(gid):
        time.sleep(BLOCK / 3)
        return {"form": "FICTION"}

    monkeypatch.setattr(db, "one", one)
    monkeypatch.setattr(db, "all_rows", all_rows)
    monkeypatch.setattr(db, "J", lambda v: v)
    monkeypatch.setattr(book_type, "profile", profile)
    monkeypatch.setattr(knowledge, "text_chunks", lambda gid: (time.sleep(BLOCK / 3), [(1, 4)])[1])
    monkeypatch.setattr(knowledge, "link_emotions_and_themes", coro)
    monkeypatch.setattr(vision, "persist_page_visual", lambda gid, p: (time.sleep(BLOCK / 3), {})[1])
    monkeypatch.setattr(quality, "create_analysis_report", lambda gid, kind: (time.sleep(BLOCK / 3),
                                                                              {"report_id": "r"})[1])
    monkeypatch.setattr(quality, "contradictions_to_queue", sync)
    monkeypatch.setattr(knowledge, "identity_unresolved", sync)
    monkeypatch.setattr(prompts, "register_all", sync)
    monkeypatch.setattr(ledger, "corrections_for_book", lambda c, b: [])

    async def main():
        with Ticker() as t:
            await A.set_step("j", 2, "x", {})
            assert await A.prepare_generation("j") == {"generation_id": "g", "book_version_id": "bv",
                                                         "profile": "full"}
            assert await A.text_chunks("g") == [[1, 4]]
            assert await A.persist_visual("g", "deep") == {"pages": 1, "visual_mentions": 0}
            await A.emotions_themes("g")
            await A.continuity_checks("g")
            await A.queue_contradictions("g")
            await A.identity_unresolved("g", "x")
            assert await A.report("g") == {"report_id": "r"}
            await A.finish_job("j", "FAILED", {"error": "x"})
        return t.max_gap
    gap = asyncio.run(main())
    assert gap < MAX_GAP, f"olay döngüsü {gap:.2f} sn durdu"


def test_heartbeat_keeps_going_while_the_database_is_slow(monkeypatch):
    """İşçinin nabzı (HeartbeatActivityInterceptor gibi döngüde koşan görev) yavaş DB boyunca sürer."""
    testing = pytest.importorskip("temporalio.testing")
    from temporalio import activity
    from editor import db, knowledge

    def one(sql, *a):
        time.sleep(1.0)                   # her sorgu 1 sn bloklar
        return {"n": 1}

    async def roles(gid):
        for _ in range(3):
            db.one("SELECT 1")
        return {"pages": []}
    monkeypatch.setattr(db, "one", one)
    monkeypatch.setattr(knowledge, "assign_narrative_roles", roles)
    beats: list[float] = []
    env = testing.ActivityEnvironment()
    env.on_heartbeat = lambda *d: beats.append(time.monotonic())

    async def body():
        async def pulse():
            while True:
                activity.heartbeat({"kind": "worker_liveness"})
                await asyncio.sleep(0.05)
        task = asyncio.create_task(pulse())
        try:
            return await A.narrative_roles("g")
        finally:
            task.cancel()

    async def main():
        return await env.run(body)
    assert asyncio.run(main()) == {"pages": []}
    gaps = [b - a for a, b in zip(beats, beats[1:])]
    assert len(beats) >= 30 and max(gaps) < MAX_GAP, f"nabız {max(gaps):.2f} sn kesildi"


# ------------------------------------------------------------------ yönetmen kapasitesi döngüler arası tek sıra
def test_director_slots_are_one_queue_across_loops(monkeypatch):
    from editor import knowledge
    monkeypatch.setenv("EDITOR_DIRECTOR_CONCURRENCY", "2")
    state = {"now": 0, "peak": 0}
    lock = threading.Lock()

    async def call():
        async with knowledge.director_slots():
            with lock:
                state["now"] += 1
                state["peak"] = max(state["peak"], state["now"])
            await asyncio.sleep(0.05)
            with lock:
                state["now"] -= 1

    async def book():                     # her kitap kendi döngüsünde (offloop), içinde 6 eşzamanlı çağrı
        await asyncio.gather(*(call() for _ in range(6)))

    async def main():
        await asyncio.gather(*(offloop.run(book) for _ in range(4)))
    asyncio.run(main())
    assert state["peak"] == 2
    assert knowledge.director_slots().value == 2              # hiçbir yer kaybolmadı


def test_shared_semaphore_cancelled_waiter_never_loses_a_slot():
    sem = offloop.SharedSemaphore(1)

    async def holder():
        async with sem:
            await asyncio.sleep(0.2)

    async def waiter():
        async with sem:
            await asyncio.sleep(10)

    async def main():
        h = asyncio.create_task(holder())
        await asyncio.sleep(0.01)
        ws = [asyncio.create_task(offloop.run(waiter)) for _ in range(3)]
        await asyncio.sleep(0.1)
        for w in ws:
            w.cancel()
        await asyncio.gather(*ws, return_exceptions=True)
        await h
        async with sem:                   # yer geri geldi
            return sem.value
    assert asyncio.run(main()) == 0 and sem.value == 1


# ------------------------------------------------------------------ SUPERSEDED: sınırlı, aralıklı yeniden kurulum
def _superseded(times):
    def out(n, gid):
        return {"technical_status": "SUPERSEDED" if n <= times else "SUCCEEDED"}
    return out


def test_archive_outputs_superseded_is_built_again():
    from test_step_retry import _finish, _run
    out, calls, hist = _run("archive", {"archive_outputs": _superseded(2)})
    status, result = _finish(calls)
    assert status == "SUCCEEDED" and "outputs-superseded-retry-v1" in hist
    assert sum(1 for n, _ in calls if n == "archive_outputs") == 3


def test_full_outputs_superseded_is_built_again():
    from test_step_retry import _finish, _run
    out, calls, hist = _run("full", {"rebuild_outputs": _superseded(1),
                                     "proofreading": lambda n, gid, *r: {"layout": {"run_id": "r"}}})
    status, _ = _finish(calls)
    assert status == "SUCCEEDED" and sum(1 for n, _ in calls if n == "rebuild_outputs") == 2


def test_outputs_superseded_every_time_fails_after_three_retries():
    from test_step_retry import _finish, _run
    out, calls, hist = _run("archive", {"archive_outputs": _superseded(99)})
    status, result = _finish(calls)
    assert status == "FAILED" and "SUPERSEDED" in result["error"]
    assert sum(1 for n, _ in calls if n == "archive_outputs") == 4            # 1 + 3


def test_no_marker_when_outputs_are_not_superseded():
    from test_step_retry import _run
    out, calls, hist = _run("archive", {})
    assert "outputs-superseded-retry-v1" not in hist


# ------------------------------------------------------------------ toplu komutlar süren okumaya yazmaz
RUNNING = "okuma sürüyor: iş j1 RUNNING (full)"


def _busy(monkeypatch, running: set, after_calls: int = 0):
    """batch_guard.busy: `running` nesilleri meşgul; `after_calls` > 0 ise ancak o kadar sorgudan sonra."""
    from editor import batch_guard
    seen = {"n": 0}

    def busy(ids):
        seen["n"] += 1
        if seen["n"] <= after_calls:
            return {}
        return {g: RUNNING for g in ids if g in running}
    monkeypatch.setattr(batch_guard, "busy", busy)
    return seen


def test_busy_query_covers_own_job_and_redaction_job(monkeypatch):
    from editor import batch_guard, db
    got = {}

    def all_rows(sql, *a):
        got["sql"], got["args"] = sql, a
        return [{"generation_id": "g1", "job_id": "j1", "status": "RUNNING", "profile": "redaction"}]
    monkeypatch.setattr(db, "all_rows", all_rows)
    assert batch_guard.busy(["g1", "g2", "g1"]) == {"g1": "okuma sürüyor: iş j1 RUNNING (redaction)"}
    assert got["args"] == (["g1", "g2"],)
    assert "j.id = g.job_id" in got["sql"] and "progress->>'generation_id'" in got["sql"]
    assert "('QUEUED','RUNNING')" in got["sql"]
    assert batch_guard.busy([]) == {}


def _fold_plan(gid, title=None):
    return {"generation_id": gid, "characters": 2, "records_folded": 1, "records_blocked": 0, "characters_after": 1,
            "joins": [{"name": "Ali", "keep": "c1", "keep_status": "X", "fold": ["c2"], "fold_status": ["X"],
                       "fold_names": ["Ali"], "rules": ["SAME_NAME"], "evidence": [], "blocked_by_attributes": [],
                       "mentions_moved": 1}],
            "refused": [], "narrator": None, "alias_conflicts": [], "unnamed": 0, "minor": 0,
            "_unnamed": {}, "_units": {}}


def test_identity_fold_apply_skips_running_generations(monkeypatch, capsys):
    from editor import identity_fold as F
    monkeypatch.setattr(F, "_latest_generations", lambda: [{"id": "g-run", "title": "Süren"},
                                                           {"id": "g-ok", "title": "Biten"}])
    planned, applied = [], []
    monkeypatch.setattr(F, "plan", lambda gid, title=None: planned.append(gid) or _fold_plan(gid, title))
    monkeypatch.setattr(F, "apply", lambda p: applied.append(p["generation_id"]) or {"applied": []})
    _busy(monkeypatch, {"g-run"})
    F.main(["--apply"])
    out = capsys.readouterr()
    assert planned == ["g-ok"] and applied == ["g-ok"]
    assert "g-run" in out.err and "atlandı" in out.err and '"skipped_running": ["g-run"]' in out.out


def test_identity_fold_rechecks_right_before_writing(monkeypatch, capsys):
    from editor import identity_fold as F
    monkeypatch.setattr(F, "plan", _fold_plan)
    applied = []
    monkeypatch.setattr(F, "apply", lambda p: applied.append(p["generation_id"]))
    _busy(monkeypatch, {"g1"}, after_calls=1)             # plan sırasında okuma başladı
    F.main(["--generation", "g1", "--apply"])
    assert applied == [] and "g1" in capsys.readouterr().err


def test_book_type_recheck_skips_running_generations(monkeypatch, capsys):
    from editor import book_type as bt
    monkeypatch.setattr(bt, "_read_generations", lambda: [{"id": "g-run", "title": "S"}, {"id": "g-ok", "title": "B"}])
    seen = []
    monkeypatch.setattr(bt, "recheck", lambda gid, apply=False: seen.append((gid, apply)) or None)
    _busy(monkeypatch, {"g-run"})
    bt.main(["recheck", "--apply"])
    assert seen == [("g-ok", True)] and "g-run" in capsys.readouterr().err


def test_page_scope_rebuild_skips_running_generations(monkeypatch, capsys):
    from editor import foundation, page_scope as P
    monkeypatch.setattr(foundation, "read_snapshot", lambda: contextlib.nullcontext(None))
    monkeypatch.setattr(P, "read_generations", lambda c, profile=None, all_generations=False: [
        {"id": "g-run", "title": "S", "profile": "full"}, {"id": "g-ok", "title": "B", "profile": "archive"}])
    done = []

    async def regenerate(gid):
        done.append(gid)
        return {"generation_id": gid}
    monkeypatch.setattr(P, "regenerate", regenerate)
    _busy(monkeypatch, {"g-run"})
    P.main(["rebuild", "--all-read"])
    assert done == ["g-ok"] and "g-run" in capsys.readouterr().err


def test_recommend_fill_skips_running_generations(monkeypatch, capsys):
    from editor import recommend as R
    done = []

    async def run(gid):
        done.append(gid)
        return {"status": "OK"}
    monkeypatch.setattr(R, "run", run)
    _busy(monkeypatch, {"g-run"})
    res = asyncio.run(R.fill([{"id": "g-run", "title": "S"}, {"id": "g-ok", "title": "B"}]))
    assert done == ["g-ok"] and res == {"OK": 1, "FAILED": 0, "SKIPPED_RUNNING": 1}
    assert "g-run" in capsys.readouterr().err


def test_backfill_apply_skips_running_generations(monkeypatch, capsys):
    from editor import backfill as B
    items = [{"job_id": "j", "generation_id": g, "title": g, "profile": "full", "finished_at": "", "steps": ["identity"],
              "state": {"characters": 0, "unresolved_mentions": 0, "checks_recorded": 0, "checks_total": 0},
              "actions": []} for g in ("g-run", "g-ok")]
    monkeypatch.setattr(B, "plan", lambda wanted, gens: [dict(x) for x in items])
    done = []

    async def apply_one(x):
        done.append(x["generation_id"])
        return {}
    monkeypatch.setattr(B, "apply_one", apply_one)
    _busy(monkeypatch, {"g-run"})
    B.main(["steps", "--failed", "--apply"])
    assert done == ["g-ok"] and "g-run" in capsys.readouterr().err
