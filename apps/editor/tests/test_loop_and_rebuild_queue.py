"""Toplu okumada «Activity task timed out» kök nedenleri (2026-10-02):

- senkron DB/CPU işi worker'ın tek olay döngüsünü dondurmasın (kalp atışı aynı döngüde),
- rebuild.pending FAILED işi ve aynı kitabın daha yeni işi varken eski nesli almasın,
- aynı girdiyle yargılanmış iddia yeniden yargılanmasın, onarılmış iddia yeniden onarılmasın,
- model çağrıları kitaplar arası ortak, model kapasitesine göre sınırlı bir sıradan geçsin,
- bölüm özetleri sınırlı paralel koşsun, sıra korunsun.

Veritabanı ve model taklit: her DB çağrısı `time.sleep` ile gerçekten bloklar; döngü dönüyor mu
diye ayrı bir tıkırtı coroutine'i ölçülür."""
from __future__ import annotations

import asyncio
import contextlib
import logging
import pathlib
import re
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from editor import db, document, foundation, knowledge, outputs, quality, rebuild  # noqa: E402

BLOCK = 0.25          # her taklit DB çağrısının gerçekten bloklama süresi (sn)
MAX_GAP = 0.2         # döngünün bu kadar uzun durması bloklama sayılır


class Ticker:
    """Döngü dönüyorsa her ~10 ms bir tık atar; en uzun aralığı ölçer."""

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


class Result:
    def __init__(self, rows):
        self.rows = rows
        self.rowcount = len(rows)

    def fetchone(self):
        return self.rows[0] if self.rows else None

    def fetchall(self):
        return list(self.rows)

    def __iter__(self):
        return iter(self.rows)


class FakeConn:
    def __init__(self, store):
        self.store = store

    def execute(self, sql, args=()):
        time.sleep(self.store.get("sleep", BLOCK / 5))
        self.store.setdefault("sql", []).append(sql)
        if "INSERT INTO operation_receipt" in sql:
            self.store.setdefault("receipts", set()).add(args[2])
        if "INSERT INTO event_actor" in sql:
            self.store.setdefault("actors", []).append(args)
        if "FROM event_actor ea JOIN character" in sql:
            ev = args[0]
            return Result([{"event_id": ev, "character_id": a[1], "role": a[6], "listed_by_extractor": a[7],
                            "canonical_name": "Ali", "p_absent": a[5], "p_actor": a[3]}
                           for a in self.store.get("actors", []) if a[0] == ev])
        return Result([])


@pytest.fixture
def store(monkeypatch):
    s: dict = {}

    @contextlib.contextmanager
    def tx():
        time.sleep(BLOCK / 5)
        yield FakeConn(s)

    monkeypatch.setattr(db, "tx", tx)
    # Başka bir test psycopg'yi taklitle yüklemiş olabilir (sıra bağımlı): Jsonb'yi düz geçir.
    monkeypatch.setattr(db, "J", lambda v: v)
    monkeypatch.setattr(knowledge.ledger, "queue_review", lambda *a, **k: s.setdefault("queued", []).append(k))
    return s


# ------------------------------------------------------------ 1. döngü bloklanmıyor
def test_event_actors_never_block_the_loop(monkeypatch, store):
    chars = [{"id": "c1", "canonical_name": "Ali", "aliases": [], "kind": "PERSON", "description": ""}]
    evs = [{"id": f"e{i}", "summary": "Ali kapıyı açtı", "page_from": i + 1, "page_to": i + 1,
            "participants": ["Ali"], "claim_id": f"k{i}", "participants_invalidated": False,
            "quotes": "Ali kapıyı açtı"} for i in range(4)]

    def all_rows(sql, *args):
        time.sleep(BLOCK)
        if "FROM character" in sql:
            return chars
        if "FROM event e" in sql:
            return evs
        return []

    def page_text(gid, p):
        time.sleep(BLOCK / 5)
        return f"[s{p} p1] Ali kapıyı açtı."

    class FakeLlm:
        def __init__(self, gid=None):
            pass

        async def choose(self, alias, messages, choices, **kw):
            await asyncio.sleep(0.01)
            return {"A": 0.9, "B": 0.05, "C": 0.05}, 1

    monkeypatch.setattr(db, "all_rows", all_rows)
    monkeypatch.setattr(knowledge, "page_text_numbered", page_text)
    monkeypatch.setattr(knowledge, "Llm", FakeLlm)

    async def main():
        with Ticker() as t:
            stats = await knowledge.attribute_event_actors("g1")
        return stats, t.max_gap

    started = time.monotonic()
    stats, gap = asyncio.run(main())
    assert stats["pairs"] == 4 and stats["actor"] == 4 and stats["pairs_failed"] == 0
    assert time.monotonic() - started > BLOCK * 3          # iş gerçekten blokladı ...
    assert gap < MAX_GAP, f"olay döngüsü {gap:.2f} sn durdu"  # ... ama döngüde değil


def _claims(n, created_by="extract"):
    return [{"id": f"00000000-0000-0000-0000-{i:012d}", "kind": "EVENT", "subject": None,
             "claim": f"İddia {i}", "confidence": 0.9, "payload": {"model_confidence": 0.9},
             "source_pages": [1], "created_by": created_by,
             "ev": [{"id": f"ev{i}", "page": 1, "kind": "TEXT", "quote": f"alıntı {i}", "verified": True}]}
            for i in range(n)]


class CriticLlm:
    calls = 0
    in_flight = 0
    peak = 0
    verdict = "SUPPORTED"

    def __init__(self, gid=None):
        pass

    async def chat(self, alias, messages, **kw):
        cls = CriticLlm
        cls.calls += 1
        cls.in_flight += 1
        cls.peak = max(cls.peak, cls.in_flight)
        try:
            await asyncio.sleep(0.02)
        finally:
            cls.in_flight -= 1
        ids = re.findall(r"^(c\d+) \[", messages[0]["content"], re.M)
        return {"verdicts": [{"claim_id": k, "supported": cls.verdict, "modality_ok": True,
                              "identity_ok": True, "note": "tamam"} for k in ids]}, 1


@pytest.fixture
def critic(monkeypatch, store):
    claims = _claims(40)

    def all_rows(sql, *args):
        time.sleep(BLOCK)
        if "FROM operation_receipt" in sql:
            return [{"input_digest": d} for d in args[2] if d in store.get("receipts", set())]
        if "c.generation_id=%s" in sql:
            return claims
        return []

    def facts(c, claim_id):
        time.sleep(BLOCK / 20)
        return {"claim": {}, "evidence": [{"kind": "TEXT", "page_no": 1, "quote": "x", "quote_verified": True}]}

    for k in ("calls", "in_flight", "peak"):
        setattr(CriticLlm, k, 0)
    CriticLlm.verdict = "SUPPORTED"
    monkeypatch.setattr(db, "all_rows", all_rows)
    monkeypatch.setattr(quality, "_claim_facts", facts)
    monkeypatch.setattr(quality, "Llm", CriticLlm)
    return claims


def test_critic_pass_never_blocks_the_loop(critic):
    async def main():
        with Ticker() as t:
            stats = await quality.critic_pass("g1", recheck=True)
        return stats, t.max_gap

    stats, gap = asyncio.run(main())
    assert stats["checked"] == 40 and stats["verified"] == 40
    assert gap < MAX_GAP, f"olay döngüsü {gap:.2f} sn durdu"


def test_rebuild_validate_never_blocks_the_loop(monkeypatch):
    def one(sql, *args):
        time.sleep(BLOCK * 2)
        return {"knowledge_revision": 7}

    async def fake_async(gid, **kw):
        await asyncio.sleep(0.01)
        return {}

    def slow(gid):
        time.sleep(BLOCK)
        return {"passed": True}

    monkeypatch.setattr(db, "one", one)
    monkeypatch.setattr(quality, "critic_pass", fake_async)
    monkeypatch.setattr(knowledge, "attribute_event_actors", fake_async)
    monkeypatch.setattr(knowledge, "detect_contradictions", fake_async)
    monkeypatch.setattr(quality, "contradictions_to_queue", slow)
    monkeypatch.setattr(quality, "run_regression_suite", slow)

    async def main():
        with Ticker() as t:
            out = await rebuild.validate("g1")
        return out, t.max_gap

    out, gap = asyncio.run(main())
    assert out["start_revision"] == 7 and out["regression_passed"] is True
    assert gap < MAX_GAP, f"olay döngüsü {gap:.2f} sn durdu"


# ------------------------------------------------------- 3. yeniden yargılama yok
def test_already_judged_claims_are_not_judged_again(critic, store):
    first = asyncio.run(quality.critic_pass("g1", recheck=True))
    calls = CriticLlm.calls
    assert first["checked"] == 40 and calls > 0 and len(store["receipts"]) == 40
    again = asyncio.run(quality.critic_pass("g1", recheck=True))
    assert CriticLlm.calls == calls, "aynı girdiyle yargılanmış iddia yeniden modele soruldu"
    assert again["already_judged"] == 40 and again["checked"] == 0


def test_changed_evidence_is_a_new_question(critic, store):
    asyncio.run(quality.critic_pass("g1", recheck=True))
    critic[0]["ev"] = critic[0]["ev"] + [{"id": "yeni", "page": 1, "kind": "TEXT", "quote": "y", "verified": True}]
    calls = CriticLlm.calls
    again = asyncio.run(quality.critic_pass("g1", recheck=True))
    assert again["already_judged"] == 39 and again["checked"] == 1 and CriticLlm.calls == calls + 1


def test_repaired_claim_is_never_repaired_again(critic, monkeypatch):
    critic[:] = _claims(5, created_by=quality.REPAIRED_BY)
    CriticLlm.verdict = "PARTIAL"
    tried = []

    async def repair(*a):
        tried.append(a)
        return None

    monkeypatch.setattr(quality, "_repair", repair)
    stats = asyncio.run(quality.critic_pass("g1", recheck=True))
    assert tried == [] and stats["repair_tried"] == 0 and stats["partial"] == 5


# --------------------------------------------- 4. ortak, kapasiteye göre sınırlı sıra
def test_model_calls_share_one_capacity_bound(critic, store, monkeypatch):
    monkeypatch.setenv("EDITOR_DIRECTOR_CONCURRENCY", "3")
    monkeypatch.setattr(quality, "_claim_facts", lambda c, i: {"claim": {}, "evidence": [
        {"kind": "TEXT", "page_no": 1, "quote": "x", "quote_verified": True}]})
    store["sleep"] = 0
    critic[:] = _claims(300)

    async def main():
        a = knowledge.director_slots()
        assert knowledge.director_slots() is a       # kitaplar arası tek sıra
        await asyncio.gather(quality.critic_pass("g1"), quality.critic_pass("g2"))

    asyncio.run(main())
    assert CriticLlm.calls >= 20 and CriticLlm.peak == 3


def test_capacity_comes_from_model_manifest(monkeypatch, tmp_path):
    monkeypatch.delenv("EDITOR_DIRECTOR_CONCURRENCY", raising=False)
    y = tmp_path / "models.yaml"
    y.write_text("aliases:\n  book-director:\n    args:\n      - --max-model-len=1000\n      - --max-num-seqs=17\n")
    monkeypatch.setattr(knowledge, "settings", lambda: type("S", (), {"models_yaml": y, "page_concurrency": 5})())
    assert knowledge.director_capacity() == 17
    y.write_text("aliases: {}\n")
    assert knowledge.director_capacity() == 5


# --------------------------------------------------- 5. bölüm özetleri sınırlı paralel
def test_chapter_summaries_run_bounded_in_parallel_and_keep_order(monkeypatch):
    monkeypatch.setenv("EDITOR_DIRECTOR_CONCURRENCY", "3")
    state = {"now": 0, "peak": 0}

    async def summarize(snap, claims, label, plot_only=False):
        state["now"] += 1
        state["peak"] = max(state["peak"], state["now"])
        await asyncio.sleep(0.1)
        state["now"] -= 1
        return {"sentences": [label], "status": "OK"}

    monkeypatch.setattr(outputs, "summarize", summarize)
    snap = {"chapters": [{"title": f"B{i}", "page_from": i, "page_to": i} for i in range(1, 10)],
            "claims": []}
    started = time.monotonic()
    out = asyncio.run(rebuild.build("chapter_summaries", snap, {}, "k"))
    took = time.monotonic() - started
    assert [c["title"] for c in out["chapters"]] == [f"B{i}" for i in range(1, 10)]
    assert [c["sentences"] for c in out["chapters"]] == [[f"B{i}"] for i in range(1, 10)]
    assert state["peak"] == 3 and took < 0.9 * 0.1 * 9


def test_chapter_summary_failure_stops_the_rest(monkeypatch):
    monkeypatch.setenv("EDITOR_DIRECTOR_CONCURRENCY", "2")
    finished = []

    async def summarize(snap, claims, label, plot_only=False):
        if label == "B1":
            raise ValueError("bozuk")
        await asyncio.sleep(0.2)
        finished.append(label)
        return {"sentences": [], "status": "OK"}

    monkeypatch.setattr(outputs, "summarize", summarize)
    snap = {"chapters": [{"title": f"B{i}", "page_from": i, "page_to": i} for i in range(1, 6)], "claims": []}
    with pytest.raises(ValueError):
        asyncio.run(rebuild.build("chapter_summaries", snap, {}, "k"))
    assert len(finished) < 4


# ------------------------------------------------------------ 2. rebuild kuyruğu
def test_pending_skips_failed_jobs_and_superseded_generations(monkeypatch):
    seen = []

    class Conn:
        def execute(self, sql, args=()):
            seen.append(sql)
            if "runtime_control" in sql:
                return Result([{"maintenance": False}])
            return Result([])

    @contextlib.contextmanager
    def snap():
        yield Conn()

    monkeypatch.setattr(foundation, "read_snapshot", snap)
    assert rebuild.pending() == []
    sql = " ".join(seen[-1].split())
    assert "j.status NOT IN ('QUEUED','RUNNING','FAILED')" in sql
    newer = sql[sql.index("NOT EXISTS (SELECT 1 FROM ed.analysis_job n"):sql.index("AND (r.attempted_code_version")]
    assert "nv.book_id=bv.book_id" in newer and "n.status IN ('QUEUED','RUNNING')" in newer
    assert "n.created_at>j.created_at" in newer and "n.id<>j.id" in newer


# ------------------------------------------------------------ bekçi
def test_loop_watchdog_reports_a_blocked_loop(caplog):
    from editor.workflow.worker import LoopWatchdog

    async def main():
        w = LoopWatchdog(threshold=0.2, tick=0.05)
        w.start()
        await asyncio.sleep(0.1)
        time.sleep(0.6)                      # döngüyü bilerek dondur
        await asyncio.sleep(0.3)
        w.stop()
        return w

    with caplog.at_level(logging.WARNING, logger="editor.worker"):
        w = asyncio.run(main())
    assert w.stalls and w.stalls[0] >= 0.4
    assert any("event loop blocked" in r.getMessage() and "test_loop_watchdog_reports_a_blocked_loop"
               in r.getMessage() for r in caplog.records)
