"""Metin bütçesi ve pencereleme (editor.budget; analiz TUM-KITAP-TURLERI-ANALIZ §6.3).

Sentetik uzun kitap (600 sayfa eşdeğeri) ile: pencere planı (bütçe, liste sınırı, bölüm başı,
örtüşme), birleştirme (etiket çelişkisi, sıra, ortak üyeyle grup birleşmesi), kanıt sayfa aralığı;
olay birleştirme/sıra, anlatı rolleri ve kimlik adımlarının pencereli yolu; kısa kitapta
davranışın değişmediği (tek çağrı, aynı istem). Model, geçit ve veritabanı yok — taklit edilir.
Çalıştırma: editor-py imajında `python -m pytest tests/test_budget_windows.py`."""
from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import json
import pathlib
import re
import sys
import types

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402


class _Stub(types.ModuleType):
    """Kurulu olmayan bağımlılık için yalnız import taklidi; kuruluysa dokunulmaz."""
    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        sub = _Stub(f"{self.__name__}.{name}")
        sys.modules[sub.__name__] = sub
        return sub


def _missing(root: str) -> bool:
    try:
        return importlib.util.find_spec(root) is None
    except ValueError:
        return False


for _mod in ("psycopg", "psycopg.rows", "psycopg.types", "psycopg.types.json", "psycopg_pool", "httpx",
             "yaml", "pymupdf"):
    _root = _mod.split(".")[0]
    if _missing(_root) or _root in sys.modules and isinstance(sys.modules[_root], _Stub):
        sys.modules.setdefault(_mod, _Stub(_mod))
if _missing("langgraph"):                       # knowledge builds its chunk graph at import
    _lg, _lgg = types.ModuleType("langgraph"), types.ModuleType("langgraph.graph")

    class _SG:
        def __init__(self, *a, **k): pass
        def add_node(self, *a, **k): pass
        def add_edge(self, *a, **k): pass
        def add_conditional_edges(self, *a, **k): pass
        def compile(self, *a, **k): return self

    _lgg.StateGraph, _lgg.START, _lgg.END = _SG, "START", "END"
    sys.modules.setdefault("langgraph", _lg)
    sys.modules.setdefault("langgraph.graph", _lgg)

from editor import budget as B  # noqa: E402


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    """Sabit, ölçülebilir bir ortam: bağlam 131072 (sunulan), geçide sayım sorulmaz."""
    for k in ("EDITOR_BUDGET_FORCE_TOKENS", "EDITOR_BUDGET_CHARS_PER_TOKEN", "EDITOR_WINDOW_OVERLAP_PAGES",
              "EDITOR_WINDOW_OVERLAP_ITEMS", "EDITOR_WINDOW_CHAPTER_SNAP", "EDITOR_JUDGE_CONTEXT_TOKENS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("EDITOR_CONTEXT_TOKENS", "131072")
    monkeypatch.setenv("EDITOR_BUDGET_TOKENIZE", "0")


# ------------------------------------------------------------------ sentetik kitap
PAGES = 600
CHAPTER_EVERY = 40                    # 15 bölüm


def _sentence(p: int, k: int) -> str:
    return f"Sayfa {p} cümle {k}: yolcular sabah erkenden yola çıktı ve akşam olunca konak kapısına vardı."


def _book(pages: int = PAGES, per_page: int = 20) -> list[dict]:
    """~1800 karakterlik sayfalar (roman/tarih sayfası boyu); her bölümün ilk sayfası büyük harfli başlıkla."""
    out = []
    for p in range(1, pages + 1):
        spans = []
        if (p - 1) % CHAPTER_EVERY == 0:
            spans.append({"idx": 0, "text": f"BÖLÜM {(p - 1) // CHAPTER_EVERY + 1} YOLCULUK"})
        spans += [{"idx": k + 1, "text": _sentence(p, k)} for k in range(per_page)]
        out.append({"page_no": p, "spans": spans, "issues": []})
    return out


def _render(pages: list[dict]) -> str:
    return "\n".join(f"[s{p['page_no']} p{s['idx']}] {s['text']}" for p in pages for s in p["spans"])


# ------------------------------------------------------------------ bütçe
def test_budget_from_setting_and_alias(monkeypatch):
    b = B.for_call("book-director", 12000)
    assert (b.context, b.output, b.input) == (131072, 12000, 131072 - 12000 - B.safety_tokens())
    monkeypatch.delenv("EDITOR_CONTEXT_TOKENS")
    from editor import llm
    monkeypatch.setattr(llm, "_aliases", {"book-director": {"args": ["--max-model-len=65536"]}})
    assert B.context_tokens("book-director") == 65536           # geçidin bildirdiği sunulan bağlam
    monkeypatch.setattr(llm, "_aliases", None)
    assert B.context_tokens("book-director") == B.SERVED_CONTEXT
    monkeypatch.setenv("EDITOR_BUDGET_FORCE_TOKENS", "5000")    # ölçüm: sığan kitabı pencereli yoldan geçir
    assert B.for_call("book-director", 12000).input == 5000


def test_fit_short_text_is_not_counted(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("kısa metin için geçide sayım sorulmamalı")
    monkeypatch.setattr(B, "count", boom)
    f = asyncio.run(B.fit("book-director", "kısa bir metin", 4000))
    assert f.fits and f.counted_by == "estimate"


def test_fit_near_budget_uses_real_count(monkeypatch):
    text = "x" * 400000                                          # tahmin ~143k token
    async def count(alias, t):
        return 100000, "tokenize"                               # gerçek sayım: sığıyor
    monkeypatch.setattr(B, "count", count)
    f = asyncio.run(B.fit("book-director", text, 4000))
    assert f.fits and f.counted_by == "tokenize" and f.ratio == pytest.approx(4.0)


def test_600_page_book_does_not_fit_one_call():
    whole = _render(_book())
    assert B.estimate(whole) > B.for_call("book-director", 12000).input


# ------------------------------------------------------------------ pencere planı
def _page_plan(max_tokens: int = 12000, **kw):
    book = _book()
    costs = [B.estimate(_render([p])) + 1 for p in book]
    starts = [i for i, p in enumerate(book) if (p["page_no"] - 1) % CHAPTER_EVERY == 0]
    wins = B.plan(costs, B.for_call("book-director", max_tokens).input, overhead=1500,
                  overlap=B.overlap_pages(), breaks=starts, pages=[(p["page_no"], p["page_no"]) for p in book], **kw)
    return book, costs, wins


def test_plan_covers_every_page_in_order_within_budget():
    book, costs, wins = _page_plan()
    cap = B.for_call("book-director", 12000).input - 1500
    assert len(wins) >= 4
    assert wins[0].start == 0 and wins[-1].end == len(book)
    for a, b in zip(wins, wins[1:]):
        assert b.start <= a.end and b.own_start == a.end         # boşluk yok; her sayfa tek sahipli
        assert b.start >= a.start + 1                            # ilerler
    for w in wins:
        assert sum(costs[w.start:w.end]) <= cap and w.tokens <= cap and not w.oversize
        assert w.page_from == book[w.start]["page_no"] and w.page_to == book[w.end - 1]["page_no"]
    owned = [u for u in range(len(book)) if B.owner(wins, u).start <= u < B.owner(wins, u).end]
    assert len(owned) == len(book)


def test_plan_cuts_at_chapter_start_without_overlap():
    book, _, wins = _page_plan()
    cut = [w for w in wins[:-1] if w.cut_at_chapter]
    assert cut, "bölüm başına denk gelen kesim bekleniyor"
    for w in cut:
        nxt = wins[w.index + 1]
        assert (book[w.end]["page_no"] - 1) % CHAPTER_EVERY == 0   # sonraki pencere bölüm başında
        assert nxt.start == w.end                                    # bölüm sınırında örtüşme yok


def test_plan_overlaps_inside_a_chapter(monkeypatch):
    monkeypatch.setenv("EDITOR_WINDOW_CHAPTER_SNAP", "1.0")          # bölüme hiç yaslanma
    monkeypatch.setenv("EDITOR_WINDOW_OVERLAP_PAGES", "2")
    book, _, wins = _page_plan()
    inner = [(a, b) for a, b in zip(wins, wins[1:]) if not a.cut_at_chapter]
    assert inner and all(a.end - b.start == 2 for a, b in inner)


def test_plan_respects_schema_list_bound():
    """Böcekleri ölçümü: 677 olayın 102'si sıraya girmişti (liste sınırı 120). Pencere ≤ 120 kayıt."""
    n = 677
    wins = B.plan([20] * n, 100000, max_units=120, overlap=8)
    assert all(w.end - w.start <= 120 for w in wins)
    assert wins[-1].end == n and len(wins) >= 6


def test_plan_counts_items_per_unit():
    counts = [1, 50, 50, 50, 3, 70, 1]                               # sayfa başına anma sayısı
    wins = B.plan([10] * len(counts), 100000, max_units=120, counts=counts)
    assert all(sum(counts[w.start:w.end]) <= 120 for w in wins) and wins[-1].end == len(counts)


def test_plan_single_window_when_it_fits():
    wins = B.plan([10, 10, 10], 1000, overhead=100, pages=[(1, 1), (2, 3), (4, 4)])
    assert len(wins) == 1 and (wins[0].start, wins[0].end, wins[0].page_from, wins[0].page_to) == (0, 3, 1, 4)


def test_plan_oversize_unit_and_no_room():
    wins = B.plan([10, 5000, 10], 1000)
    assert [w.oversize for w in wins] == [False, True, False]
    with pytest.raises(B.BudgetError):
        B.plan([10], 100, overhead=100)


# ------------------------------------------------------------------ birleştirme
def test_merge_labels_central_window_wins_and_conflict_is_reported():
    wins = B.plan([1] * 30, 10**6, max_units=12, overlap=4)
    per = []
    for w in wins:                                   # kenardaki kayıt EDGE, ortadaki MID okunuyor
        per.append({u: ("EDGE" if min(u - w.start, w.end - 1 - u) < 2 else "MID") for u in w.units})
    labels, conflicts = B.merge_labels(wins, per)
    assert set(labels) == set(range(30))
    assert conflicts and all(len(c["readings"]) >= 2 for c in conflicts)
    for c in conflicts:
        w = wins[c["chosen_window"]]
        u = c["unit"]
        others = [wins[r["window"]] for r in c["readings"]]
        assert min(u - w.start, w.end - 1 - u) == max(min(u - o.start, o.end - 1 - u) for o in others)
        assert all(r["pages"] == wins[r["window"]].evidence()["pages"] for r in c["readings"])


def test_merge_labels_failed_window_is_skipped():
    wins = B.plan([1] * 10, 10**6, max_units=6, overlap=2)
    labels, _ = B.merge_labels(wins, [None] + [{u: "X" for u in w.units} for w in wins[1:]])
    assert all(u >= wins[1].start for u in labels)


def test_merge_order_first_appearance_and_own_units_only():
    wins = B.plan([1] * 10, 10**6, max_units=6, overlap=2)
    orders = [[2, 0, 1, 5, 4, 3], [4, 5, 9, 6, 7, 8, 0]]           # 0 ikinci pencerenin değil
    assert B.merge_order(wins, orders) == [2, 0, 1, 5, 4, 3, 9, 6, 7, 8]


def test_union_groups_joins_across_windows_never_within_one():
    groups = [(0, ["a", "b"]), (1, ["b", "c"]), (0, ["x"]), (1, ["x", "y"]), (1, ["c", "z"])]
    sets, refused = B.union_groups(groups)
    joined = [sorted(s) for s in sets]
    assert [0, 1] in joined and [4] in joined
    assert any(r["reason"] == "SAME_WINDOW" and r["member"] == "c" for r in refused)   # 1 ile 4 aynı pencere
    assert [2, 3] in joined


def test_union_groups_refuse_callback():
    groups = [(0, ["m1"]), (1, ["m1"])]
    sets, refused = B.union_groups(groups, refuse=lambda a, b: "SEX_CONFLICT")
    assert sorted(map(sorted, sets)) == [[0], [1]] and refused[0]["reason"] == "SEX_CONFLICT"


def test_dedupe_keeps_every_provenance():
    items = [{"k": 1, "window": {"window": 0, "pages": [1, 40]}},
             {"k": 1, "window": {"window": 1, "pages": [40, 80]}}, {"k": 2, "window": {"window": 1, "pages": [40, 80]}}]
    out = B.dedupe(items, key=lambda x: x["k"])
    assert len(out) == 2 and [w["window"] for w in out[0]["windows"]] == [0, 1]


def test_cap_hits_reports_lists_at_their_bound():
    from editor import schemas
    out = {"groups": [], "story_order": [f"e{i}" for i in range(120)]}
    assert B.cap_hits(out, schemas.MERGE_EVENTS) == [{"path": "/story_order", "items": 120, "max": 120}]
    assert B.list_cap(schemas.THEMES, "themes", "[]", "source_ids") == 120


# ------------------------------------------------------------------ yargı bağlamı
def test_around_whole_when_it_fits_and_neighbourhood_when_not():
    book = _book()
    small = book[:10]
    text, used = B.around(small, [3, 7], 10**6, _render)
    assert text == _render(small) and used == list(range(1, 11))
    text, used = B.around(book, [100, 480], 20000, _render)
    assert 100 in used and 480 in used and len(used) < len(book)
    assert B.estimate(text) <= 20000 + 200
    assert "bu soruya gösterilmedi" in text and "[s100 p1]" in text and "[s480 p1]" in text
    # sayfalar her iki odak çevresinde dengeli büyür
    assert {99, 101, 479, 481} <= set(used)


def test_judge_text_short_book_is_the_whole_text():
    from editor.proofing import _continuity as C
    pages = _book(12)
    ctx = asyncio.run(C.judge_text(pages))
    assert ctx.fits and ctx.for_pages([2, 9]) == C.book_text(pages)
    f = ctx.mark({"details": {}}, [2, 9])
    assert "judge_context" not in f["details"]


def test_judge_text_long_book_marks_the_pages_seen(monkeypatch):
    from editor.proofing import _continuity as C
    monkeypatch.setenv("EDITOR_JUDGE_CONTEXT_TOKENS", "8000")
    pages = _book()
    ctx = asyncio.run(C.judge_text(pages))
    assert not ctx.fits and ctx.stats()["context_tokens"] == 8000
    text = ctx.for_pages([200, 205])
    assert "[s200 p1]" in text and "[s205 p1]" in text and "[s1 p1]" not in text
    f = ctx.mark({"details": {}}, [205, 200])
    jc = f["details"]["judge_context"]
    assert jc["whole_book"] is False and jc["pages"][0] <= 200 and jc["pages"][1] >= 205


# ------------------------------------------------------------------ olay birleştirme ve sıra
class _Cur:
    def __init__(self, rows=None):
        self.rows = rows or []

    def fetchall(self):
        return self.rows

    def fetchone(self):
        return self.rows[0] if self.rows else None


class FakeDB:
    def __init__(self, rows: dict[str, list[dict]]):
        self.rows, self.executed = rows, []

    def all_rows(self, sql, *args):
        for key, rows in self.rows.items():
            if key in sql:
                return rows
        return []

    @contextlib.contextmanager
    def tx(self):
        outer = self

        class C:
            def execute(self, sql, params=()):
                outer.executed.append((sql, params))
                return _Cur()
        yield C()


def _events(n: int, dup_every: int = 50) -> list[dict]:
    """n olay kitaba yayılmış; her dup_every'de bir, bir sonraki parçadan gelen tekrar (aynı sayfa)."""
    evs = []
    for i in range(n):
        p = 1 + i * PAGES // n
        evs.append({"id": f"ev{i}", "page_from": p, "page_to": p, "modality": "REALIZED",
                    "summary": f"olay {i}", "model_call_id": p // 4})
        if i % dup_every == 0:
            evs.append({"id": f"ev{i}d", "page_from": p, "page_to": p, "modality": "REALIZED",
                        "summary": f"olay {i}", "model_call_id": p // 4 + 1000})
    return evs


LINE = re.compile(r"^(e\d+) \| s(\d+)-(\d+) \| (\w+) \| (.*)$", re.M)


class MergeLlm:
    calls: list[str] = []

    def __init__(self, gid=None):
        pass

    async def chat(self, alias, messages, **kw):
        body = messages[0]["content"]
        MergeLlm.calls.append(body)
        rows = LINE.findall(body)
        by_summary: dict[str, list[str]] = {}
        for eid, *_rest, summary in rows:
            by_summary.setdefault(summary, []).append(eid)
        groups = [{"event_ids": ids, "summary": s} for s, ids in by_summary.items() if len(ids) > 1]
        return {"groups": groups, "story_order": [r[0] for r in rows]}, 1


def _wire(monkeypatch, k, db, llm_cls):
    monkeypatch.setattr(k.db, "all_rows", db.all_rows)
    monkeypatch.setattr(k.db, "tx", db.tx)
    monkeypatch.setattr(k, "Llm", llm_cls)
    monkeypatch.setattr(k, "chapters", lambda gid: [
        {"title": f"B{i}", "page_from": 1 + i * CHAPTER_EVERY, "page_to": (i + 1) * CHAPTER_EVERY}
        for i in range(PAGES // CHAPTER_EVERY)])


def test_merge_events_short_book_is_one_unchanged_call(monkeypatch):
    from editor import knowledge as k, prompts
    evs = _events(10, dup_every=100)
    db = FakeDB({"FROM event e LEFT JOIN claim": evs})
    _wire(monkeypatch, k, db, MergeLlm)
    MergeLlm.calls = []
    res = asyncio.run(k.merge_events("g"))
    lines = [f"e{i} | s{e['page_from']}-{e['page_to']} | {e['modality']} | {e['summary']}" for i, e in enumerate(evs)]
    assert MergeLlm.calls == [prompts.render("merge_events", events="\n".join(lines))[1]]
    assert "reading" not in res and res["ordered"] == len(evs) and res["merged"] == 1


def test_merge_events_long_book_is_windowed_and_nothing_is_cut(monkeypatch):
    from editor import knowledge as k
    evs = _events(700)
    db = FakeDB({"FROM event e LEFT JOIN claim": evs})
    _wire(monkeypatch, k, db, MergeLlm)
    MergeLlm.calls = []
    res = asyncio.run(k.merge_events("g"))
    assert len(MergeLlm.calls) > 1
    assert all(len(LINE.findall(c)) <= 120 for c in MergeLlm.calls)          # liste sınırı pencereyi belirler
    assert all("NOT: Bu liste kitabın yalnız s" in c for c in MergeLlm.calls)
    assert res["ordered"] == len(evs)                                          # her olay sırada, bir kez
    orders = [p[0] for sql, p in db.executed if sql.startswith("UPDATE event SET story_order")]
    assert orders == list(range(1, len(evs) + 1))
    assert res["merged"] == 14                                                 # 700/50 tekrar, pencere sınırında da
    r = res["reading"]
    assert r["windowed"] and r["windows"][0]["pages"][0] == 1 and r["windows"][-1]["pages"][1] == PAGES
    assert r["failed"] == [] and res["cap_hits"] == []


class RolesLlm:
    bodies: list[str] = []

    def __init__(self, gid=None):
        pass

    async def chat(self, alias, messages, **kw):
        RolesLlm.bodies.append(messages[0]["content"])
        ids = re.findall(r"^(e\d+) \|", messages[0]["content"], re.M)
        # her pencere kenarındaki iki olayı dönüm noktası sayar: örtüşmede iki pencere çelişir
        return {"events": [{"event_id": e, "role": "TURNING_POINT" if i < 2 or i >= len(ids) - 2 else "ORDINARY",
                            "reason": ""} for i, e in enumerate(ids)]}, 1


def test_narrative_roles_windowed_conflicts_decided_by_the_central_window(monkeypatch):
    from editor import knowledge as k
    tl = [{"id": f"t{i}", "story_order": i + 1, "page_from": 1 + i * 2, "page_to": 1 + i * 2,
           "modality": "REALIZED", "summary": f"olay {i}", "participants": [], "confidence": 0.9,
           "narrative_role": None} for i in range(300)]
    db = FakeDB({"FROM timeline": tl})
    _wire(monkeypatch, k, db, RolesLlm)
    RolesLlm.bodies = []
    monkeypatch.setattr(k, "chapters", lambda gid: [])       # bölümsüz kitap: her kesim örtüşür
    res = asyncio.run(k.assign_narrative_roles("g"))
    assert all(len(re.findall(r"^e\d+ \|", b, re.M)) <= 119 for b in RolesLlm.bodies)
    roles = [p for sql, p in db.executed if sql.startswith("UPDATE event SET narrative_role")]
    assert len(roles) == len(tl) and len({p[1] for p in roles}) == len(tl)   # her olaya bir rol
    r = res["reading"]
    assert r["windowed"] and r["role_conflicts"]
    for c in r["role_conflicts"]:
        assert {x["label"] for x in c["readings"]} == {"TURNING_POINT", "ORDINARY"}
        assert c["chosen"] == "ORDINARY"          # kenardan uzak okuyan pencere kazanır


class OffLoopDB(FakeDB):
    """Veritabanı işi olay döngüsünün iş parçacığında yapılırsa düşer. 2026-10-04 23:29–23:31: emotions_themes
    duygu bağlarını ve tema yazımını işçinin ortak döngüsünde yapıyordu, döngü 80–90 sn durdu ve aynı anda okunan
    bütün kitapların aktiviteleri heartbeat'siz kalıp «Activity task timed out» ile düştü."""
    def __init__(self, rows):
        super().__init__(rows)
        self.calls = 0

    def _off_loop(self):
        self.calls += 1
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise AssertionError("veritabanı işi işçinin olay döngüsünde yapıldı")

    def all_rows(self, sql, *args):
        self._off_loop()
        return super().all_rows(sql, *args)

    @contextlib.contextmanager
    def tx(self):
        self._off_loop()
        with super().tx() as c:
            yield c


def test_director_steps_keep_database_work_off_the_worker_loop(monkeypatch):
    from editor import knowledge as k
    evs = _events(10, dup_every=100)
    tl = [{"id": f"t{i}", "story_order": i + 1, "page_from": 1 + i, "page_to": 1 + i, "modality": "REALIZED",
           "summary": f"olay {i}", "participants": [], "confidence": 0.9, "narrative_role": None} for i in range(5)]
    db = OffLoopDB({"FROM event e LEFT JOIN claim": evs, "FROM timeline": tl})
    _wire(monkeypatch, k, db, MergeLlm)
    asyncio.run(k.merge_events("g"))
    monkeypatch.setattr(k, "Llm", RolesLlm)
    asyncio.run(k.assign_narrative_roles("g"))
    asyncio.run(k.verify_event_modality("g"))
    asyncio.run(k.link_emotions_and_themes("g"))
    assert db.calls >= 7
    assert any(sql.startswith("UPDATE event SET story_order") for sql, _ in db.executed)
    assert any(sql.startswith("UPDATE event SET narrative_role") for sql, _ in db.executed)


# ------------------------------------------------------------------ kimlik
def _identity_book(n_pages: int = 300):
    pages, mentions = [], []
    for p in range(1, n_pages + 1):
        name = "Ali" if p % 2 else "Zeynep"
        text = f"{name} koştu." if name == "Ali" else f"{name} güldü."
        spans = [{"idx": 1, "text": text}]
        if p == 5:
            spans.append({"idx": 2, "text": "Ali ile Zeynep kardeştir."})
        pages.append({"page_no": p, "spans": spans, "issues": []})
        mentions.append({"id": f"id{p}", "page_no": p, "surface_name": name, "confidence": 0.9, "quote": text})
    return pages, mentions


def _fake_propose(calls):
    async def propose(gid, mentions, corrections=""):
        calls.append([m["page_no"] for m in mentions])
        by: dict[str, list[str]] = {}
        for i, m in enumerate(mentions):
            by.setdefault(m["surface_name"], []).append(f"m{i}")
        chars = [{"canonical_name": n, "kind": "HUMAN_CHILD", "sex": "MALE" if n == "Ali" else "FEMALE",
                  "age_band": "CHILD", "entity_scope": "INDIVIDUAL", "aliases": [], "description": f"{n} bir çocuk",
                  "mention_ids": ids, "merge_basis": "ad", "identity_confidence": 0.9} for n, ids in by.items()]
        return {"characters": chars, "unresolved_mention_ids": [], "conflicts": []}, len(calls), {"attempts": [{}]}
    return propose


class CrossLlm:
    seen: list[str] = []

    def __init__(self, gid=None):
        pass

    async def chat(self, alias, messages, **kw):
        body = messages[0]["content"]
        CrossLlm.seen.append(body)
        rows = [json.loads(x) for x in body.splitlines() if x.startswith('{"group_id"')]
        ali = sorted([r for r in rows if r["names"][0] == "Ali"], key=lambda r: r["pages"][0])
        zey = sorted([r for r in rows if r["names"][0] == "Zeynep"], key=lambda r: r["pages"][0])
        merges = [
            # Ali örtüşen sayfalarla bütün pencerelerde tek grup oldu; o pencerelerin ayırdığı
            # Zeynep'le birleşmez (aynı pencere iki kişi dedi)
            {"keep_group": ali[0]["group_id"], "fold_group": zey[-1]["group_id"], "name": "Ali",
             "evidence_quote": "Ali ile Zeynep kardeştir.", "basis": "aynı sahne"},
            # uydurma alıntı: kitapta yok, kod reddeder
            {"keep_group": zey[0]["group_id"], "fold_group": zey[1]["group_id"], "name": "Zeynep",
             "evidence_quote": "Zeynep gökyüzünde uçtu.", "basis": "ad"}]
        merges += [{"keep_group": rows_[0]["group_id"], "fold_group": r["group_id"], "name": r["names"][0],
                    "evidence_quote": ("Ali koştu." if r["names"][0] == "Ali" else "Zeynep güldü."), "basis": "ad"}
                   for rows_ in (ali, zey) for r in rows_[1:]]
        return {"merges": merges}, 99


def test_identity_short_book_is_exactly_propose(monkeypatch):
    from editor import identity
    pages, mentions = _identity_book(6)
    calls = []
    monkeypatch.setattr(identity.source, "read", lambda gid, page_no=None: pages)
    monkeypatch.setattr(identity, "propose", _fake_propose(calls))
    out, call_id, audit = asyncio.run(identity.propose_book("g", mentions, "-"))
    assert calls == [[1, 2, 3, 4, 5, 6]] and "windowed" not in audit


def test_identity_long_book_windows_joins_and_guards(monkeypatch):
    from editor import identity, knowledge
    pages, mentions = _identity_book(300)
    calls = []
    monkeypatch.setattr(identity.source, "read", lambda gid, page_no=None: pages)
    monkeypatch.setattr(identity, "propose", _fake_propose(calls))
    monkeypatch.setattr(identity, "Llm", CrossLlm)
    monkeypatch.setattr(knowledge, "chapters", lambda gid: [{"title": "K", "page_from": 1, "page_to": 300}])
    CrossLlm.seen = []
    out, call_id, audit = asyncio.run(identity.propose_book("g", mentions, "-"))
    assert len(calls) >= 3 and all(len(c) <= 120 for c in calls)            # her pencere liste sınırında
    assert audit["windowed"] and audit["failed"] == []
    names = sorted(c["canonical_name"] for c in out["characters"])
    assert names == ["Ali", "Zeynep"]                                         # pencereler arası tek kişi
    assert sorted(m for c in out["characters"] for m in c["mention_ids"]) == sorted(f"m{i}" for i in range(300))
    assert out["unresolved_mention_ids"] == []
    assert audit["overlap_joins"] == 2                                        # örtüşen sayfadaki anma birleştirdi (Ali)
    reasons = {r["reason"] for r in audit["cross_window"]["refused"]}
    assert {"SAME_WINDOW", "QUOTE_NOT_IN_BOOK"} <= reasons                    # kod koruması, alıntı birebir
    assert len(audit["cross_window"]["merges"]) == 2                          # Zeynep üç pencereden tek kişi
    for c in out["characters"]:
        pages_seen = sorted(p for w in c["windows"] for p in w["pages"])
        assert pages_seen[0] <= 2 and pages_seen[-1] >= 299                   # kanıt: hangi pencereler
    # birleşik karakterin her anması bir kez
    ids = [m for c in out["characters"] for m in c["mention_ids"]]
    assert len(ids) == len(set(ids))


def test_cross_window_guard_quote_is_searched_verbatim():
    from editor import identity, ledger
    by_mid = {"m0": {"surface_name": "Ali", "page_no": 1}, "m1": {"surface_name": "Zeynep", "page_no": 300},
              "m2": {"surface_name": "Ali", "page_no": 299}}
    ali = [{"canonical_name": "Ali", "mention_ids": ["m0"], "kind": "HUMAN_CHILD", "sex": "MALE",
            "entity_scope": "INDIVIDUAL"}]
    zey = [{"canonical_name": "Zeynep", "mention_ids": ["m1"], "kind": "HUMAN_CHILD", "sex": "FEMALE",
            "entity_scope": "INDIVIDUAL"}]
    ali2 = [{**ali[0], "mention_ids": ["m2"]}]
    book = ledger.norm("Ali ile Zeynep kardeştir. Ali koştu. Ali eve döndü.")
    g = identity.cross_guard
    assert g(ali, zey, {0}, {2}, "Ali ile Zeynep kardeştir.", book, by_mid) == "SEX_CONFLICT"
    assert g(ali, ali2, {0}, {2}, "Ali gökyüzünde uçtu.", book, by_mid) == "QUOTE_NOT_IN_BOOK"
    assert g(ali, ali2, {0}, {2}, "eve döndü", book, by_mid) == "QUOTE_DOES_NOT_NAME_BOTH"
    assert g(ali, ali2, {0, 1}, {1}, "Ali eve döndü.", book, by_mid) == "SAME_WINDOW"
    assert g(ali, ali2, {0}, {2}, "Ali eve döndü.", book, by_mid) is None


def test_identity_incompatible_guard():
    from editor import identity
    a = [{"kind": "HUMAN_CHILD", "sex": "MALE", "entity_scope": "INDIVIDUAL"}]
    assert identity.incompatible(a, [{"kind": "ANIMAL", "sex": "MALE", "entity_scope": "INDIVIDUAL"}]) == "KIND_CONFLICT"
    assert identity.incompatible(a, [{"kind": "HUMAN_CHILD", "sex": "FEMALE", "entity_scope": "INDIVIDUAL"}]) == "SEX_CONFLICT"
    assert identity.incompatible(a, [{"kind": "HUMAN_CHILD", "sex": "UNKNOWN", "entity_scope": "COLLECTIVE"}]) \
        == "INDIVIDUAL_COLLECTIVE"
    assert identity.incompatible(a, [{"kind": "OTHER", "sex": "UNKNOWN", "entity_scope": "UNKNOWN"}]) is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
