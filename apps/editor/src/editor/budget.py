"""Metin bütçesi ve pencereleme (docs/TUM-KITAP-TURLERI-ANALIZ.md §6.3, docs/METIN-BUTCESI.md).

Bütün kitabı tek istemde modele veren adımlar (kimlik, olay birleştirme ve sıra, anlatı rolleri,
tema birleştirme, çelişki, son okuma hakemleri) uzun kitapta ya bağlamı aşıp düşüyordu ya da
şemanın liste sınırında (schemas.arr, 120) sessizce kırpılıyordu. Bu modül üç şey verir:

  1. **Bütçe** — bir çağrıya ne kadar girdi sığar: modelin sunduğu bağlam (ayar
     `EDITOR_CONTEXT_TOKENS`, yoksa geçidin bildirdiği `--max-model-len`, o da yoksa sunulan
     131072) − çağrının cevap payı (max_tokens) − güvenlik payı. Sayım önce tahmindir (karakter /
     `EDITOR_BUDGET_CHARS_PER_TOKEN`); tahmin eşiğe yaklaşınca (`EDITOR_BUDGET_COUNT_ABOVE`) geçidin
     `/tokenize` ucuyla gerçek sayılır. Sığan girdi bugünkü yoldan, tek çağrıyla geçer:
     kısa kitapta hiçbir şey değişmez, fazladan çağrı da yapılmaz.
  2. **Pencere planı** — sığmayan girdi ardışık tam birimlere (sayfa ya da sayfa sırasındaki
     kayıt: olay, tema, anma) bölünür. Birim hiçbir zaman bölünmez; pencere bölüm başına denk
     gelecek yerde oradan kesilir (`EDITOR_WINDOW_CHAPTER_SNAP`); bölüm içinden kesilen iki pencere
     `EDITOR_WINDOW_OVERLAP_*` birim örtüşür. Pencere başına kayıt sayısı şemanın liste sınırını
     geçmez: sınır bir kırpma değil, pencerenin boyudur.
  3. **Birleştirme** — pencere sonuçları kodla birleşir: aynı birime iki pencere farklı etiket
     verirse birimin ortada kaldığı (kenardan en uzak) pencere kazanır ve çelişki sayılır; sıra ilk
     görüldüğü pencereden gelir; ortak birim üzerinden gruplar birleşir, aynı pencerenin ayırdığı
     iki grup hiçbir zincirle birleşmez. Her sonuç hangi pencereden (sayfa aralığı) geldiğini taşır.

Kitaba ya da türe özel kural yoktur; her eşik fiziksel anlamıyla ayardan okunur. Model sayı
üretmez; alıntılar her zamanki gibi metinde birebir aranır (ledger) — bu modül yalnız neyin hangi
çağrıya gideceğine karar verir. Sınıra çarpan her liste `cap_hits` ile sayılır ve raporlanır.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

# The context the director is served with (gateway: "bağlam 131072"; analysis §4). Used only
# when neither the setting nor the gateway's alias list says otherwise.
SERVED_CONTEXT = 131072


# ------------------------------------------------------------------ settings
def setting(name: str, default):
    """`EDITOR_<NAME>` from the environment, typed like the default. Read at call time, so a
    measurement run can change it without a restart of the code that imported this module."""
    raw = os.environ.get("EDITOR_" + name.upper())
    if raw is None or str(raw).strip() == "":
        return default
    if isinstance(default, bool):
        return str(raw).strip().lower() not in ("0", "false", "no")
    if isinstance(default, int):
        return int(raw)
    if isinstance(default, float):
        return float(raw)
    return raw


def chars_per_token() -> float:
    # Measured on the corpus (analysis §4: token ≈ karakter/2,8). Lower = more cautious.
    return max(0.5, setting("budget_chars_per_token", 2.8))


def safety_tokens() -> int:
    # Room the chat template, the schema guidance and a count error need next to the input.
    return max(0, setting("budget_safety_tokens", 2048))


def count_above() -> float:
    # An estimate below this share of the budget fits without asking the tokenizer.
    return min(1.0, max(0.0, setting("budget_count_above", 0.8)))


def overlap_pages() -> int:
    return max(0, setting("window_overlap_pages", 1))


def overlap_items() -> int:
    return max(0, setting("window_overlap_items", 8))


def chapter_snap() -> float:
    # A window is cut at a chapter start only when at least this share of it is already filled:
    # 0.5 = never waste more than half a window to keep chapters whole.
    return min(1.0, max(0.0, setting("window_chapter_snap", 0.5)))


def force_tokens() -> int:
    # > 0: the input budget is lowered to this many tokens. For measurement only: runs a book
    # that fits through the windowed path, to compare both paths on the same book (analysis §8).
    return max(0, setting("budget_force_tokens", 0))


def window_parallel() -> int:
    return max(1, setting("window_parallel", 4))


# ------------------------------------------------------------------ budget
@dataclass(frozen=True)
class Budget:
    context: int          # tokens the model is served with
    output: int           # the call's own answer budget (max_tokens)
    safety: int           # template, schema guidance, count error
    forced: int = 0       # measurement override (force_tokens)

    @property
    def input(self) -> int:
        room = max(0, self.context - self.output - self.safety)
        return min(room, self.forced) if self.forced else room

    def as_dict(self) -> dict:
        return {"context": self.context, "output": self.output, "safety": self.safety,
                "input": self.input, "forced": self.forced or None}


def context_tokens(alias: str) -> int:
    """The served context of `alias`: the setting, else the gateway's alias list if this worker
    has already read it (every recorded model call reads it), else the served default."""
    v = setting("context_tokens", 0)
    if v > 0:
        return v
    try:
        from . import llm
        meta = (llm._aliases or {}).get(alias) or {}
        n = llm.context_length(meta)
        if n:
            return n
    except Exception:  # noqa: BLE001 - no alias list: the served default
        pass
    return SERVED_CONTEXT


def for_call(alias: str, max_tokens: int) -> Budget:
    return Budget(context=context_tokens(alias), output=max(0, int(max_tokens)),
                  safety=safety_tokens(), forced=force_tokens())


def estimate(text: str, ratio: float | None = None) -> int:
    """Tokens of `text` by its length. Rounded up; an empty text costs nothing."""
    if not text:
        return 0
    return int(math.ceil(len(text) / (ratio or chars_per_token())))


async def count(alias: str, text: str) -> tuple[int, str]:
    """Real token count from the gateway's /tokenize (the model's own tokenizer, chat template
    included); on any failure the estimate, and the answer says which one it is."""
    if setting("budget_tokenize", True):
        try:
            from . import llm
            r = await llm.client().post("/v1/tokenize", json={
                "model": alias, "messages": [{"role": "user", "content": text}],
                "add_generation_prompt": True})
            if r.status_code < 400:
                n = int(r.json()["count"])
                if n > 0:
                    return n, "tokenize"
        except Exception:  # noqa: BLE001 - counting is an optimisation; the estimate stands in
            pass
    return estimate(text), "estimate"


@dataclass
class Fit:
    fits: bool
    tokens: int
    counted_by: str
    ratio: float          # characters per token for this text (measured when counted)
    budget: Budget

    def as_dict(self) -> dict:
        return {"fits": self.fits, "tokens": self.tokens, "counted_by": self.counted_by,
                "chars_per_token": round(self.ratio, 3), "budget": self.budget.as_dict()}


async def fit(alias: str, text: str, max_tokens: int) -> Fit:
    """Does this whole request fit? Far below the budget: yes, without a count (short books do
    exactly what they did). Near or above it: the tokenizer decides, and its count also gives
    the characters-per-token of THIS text for planning the windows."""
    b = for_call(alias, max_tokens)
    est = estimate(text)
    if est <= b.input * count_above():
        return Fit(True, est, "estimate", chars_per_token(), b)
    n, how = await count(alias, text)
    ratio = (len(text) / n) if (how == "tokenize" and n) else chars_per_token()
    return Fit(n <= b.input, n, how, ratio, b)


def fit_sync(alias: str, text: str, max_tokens: int) -> Fit:
    """The estimate-only fit, for code that cannot await (no tokenizer call)."""
    b = for_call(alias, max_tokens)
    est = estimate(text)
    return Fit(est <= b.input, est, "estimate", chars_per_token(), b)


# ------------------------------------------------------------------ windows
class BudgetError(ValueError):
    """The fixed part of a request (instructions, shared tables) leaves no room for any input."""


@dataclass
class Window:
    index: int
    start: int                    # first unit (inclusive)
    end: int                      # last unit (exclusive)
    own_start: int                # first unit this window owns (after the overlap it shares)
    page_from: int | None = None
    page_to: int | None = None
    tokens: int = 0
    oversize: bool = False        # one unit alone is larger than the budget; sent as it is
    cut_at_chapter: bool = False  # this window ends where a chapter starts

    @property
    def units(self) -> range:
        return range(self.start, self.end)

    def evidence(self) -> dict:
        """What every windowed result carries: which window, which pages."""
        return {"window": self.index, "pages": [self.page_from, self.page_to]}

    def as_dict(self) -> dict:
        return {"window": self.index, "units": [self.start, self.end], "own_from": self.own_start,
                "pages": [self.page_from, self.page_to], "tokens": self.tokens,
                "oversize": self.oversize, "cut_at_chapter": self.cut_at_chapter}


def plan(costs: Sequence[int], budget: int, *, overhead: int = 0, max_units: int | None = None,
         overlap: int = 0, breaks: Iterable[int] = (), snap: float | None = None,
         pages: Sequence[tuple[int, int]] | None = None,
         counts: Sequence[int] | None = None) -> list[Window]:
    """Split units (in reading order) into windows whose cost, next to `overhead`, stays within
    `budget` and whose item count stays within `max_units` (`counts[i]` items in unit i; one
    each when not given — a page unit can carry several items, e.g. the mentions on it).

    `breaks`: unit indices that begin a chapter. A window that would end inside a chapter is cut
    back to the last chapter start in it, when that keeps at least `snap` of the window; a window
    cut at a chapter start does not overlap the next one (a chapter is a natural boundary),
    any other cut overlaps `overlap` units. `pages[i]` = (page_from, page_to) of unit i, for the
    evidence each window carries. One window = the whole input: the caller's single-call path."""
    n = len(costs)
    if n == 0:
        return []
    cap = budget - overhead
    if cap <= 0:
        raise BudgetError(f"fixed part of the request ({overhead} tokens) leaves no room in {budget}")
    snap = chapter_snap() if snap is None else snap
    brk = sorted({b for b in breaks if 0 < b < n})
    max_units = max_units if (max_units or 0) > 0 else None
    counts = list(counts) if counts is not None else [1] * n

    def page_span(s: int, e: int) -> tuple[int | None, int | None]:
        if not pages:
            return None, None
        return min(p[0] for p in pages[s:e]), max(p[1] for p in pages[s:e])

    total = sum(costs)
    if total <= cap and (max_units is None or sum(counts) <= max_units):
        pf, pt = page_span(0, n)
        return [Window(0, 0, n, 0, pf, pt, total)]
    out: list[Window] = []
    s, own = 0, 0
    while s < n:
        e, used, cnt = s, 0, 0
        while e < n and used + costs[e] <= cap and (max_units is None or cnt + counts[e] <= max_units):
            used += costs[e]
            cnt += counts[e]
            e += 1
        if e <= own and s < own:
            # the shared overlap alone fills the window (heavy units): drop the overlap, never
            # emit a window that owns nothing
            s = own
            continue
        oversize = False
        if e == s:                       # a single unit larger than the budget: alone, flagged
            e, used, oversize = s + 1, costs[s], True
        at_chapter = False
        if e < n:
            filled = 0
            best = None
            for b in brk:
                if s < b < e:
                    filled = sum(costs[s:b])
                    if used and filled >= snap * used and b > own:
                        best = b
            if best is not None:
                e, used, at_chapter = best, sum(costs[s:best]), True
            elif e in brk:
                at_chapter = True
        pf, pt = page_span(s, e)
        out.append(Window(len(out), s, e, own, pf, pt, used, oversize, at_chapter))
        if e >= n:
            break
        own = e
        ov = 0 if at_chapter else min(overlap, (e - s) // 2)
        s = max(e - ov, s + 1)
    return out


def owner(windows: Sequence[Window], unit: int) -> Window:
    """The window responsible for a unit: overlaps belong to the earlier window's successor
    from `own_start` on, so every unit has exactly one owner."""
    best = windows[0]
    for w in windows:
        if w.own_start <= unit:
            best = w
    return best


def central(windows: Sequence[Window], unit: int, among: Iterable[int] | None = None) -> Window:
    """Of the windows holding `unit` (optionally only those in `among`), the one where it sits
    farthest from an edge: it was read with the most context around it."""
    allowed = set(among) if among is not None else None
    cands = [w for w in windows if w.start <= unit < w.end and (allowed is None or w.index in allowed)]
    if not cands:
        return owner(windows, unit)
    return max(cands, key=lambda w: (min(unit - w.start, w.end - 1 - unit), -w.index))


# ------------------------------------------------------------------ merging
def merge_labels(windows: Sequence[Window], per_window: Sequence[dict[int, Any] | None]
                 ) -> tuple[dict[int, Any], list[dict]]:
    """unit -> label from the windows that answered (None = that window failed). Where windows
    disagree, the label of the window the unit sits most centrally in stands and the
    disagreement is returned (unit, every window's label and pages, the chosen one)."""
    seen: dict[int, list[tuple[int, Any]]] = {}
    for w, got in zip(windows, per_window):
        if got is None:
            continue
        for u, lab in got.items():
            if w.start <= u < w.end:            # a window can only label its own units
                seen.setdefault(u, []).append((w.index, lab))
    labels: dict[int, Any] = {}
    conflicts: list[dict] = []
    for u, got in sorted(seen.items()):
        chosen_w = central(windows, u, among=[i for i, _ in got])
        chosen = next(lab for i, lab in got if i == chosen_w.index)
        labels[u] = chosen
        if len({repr(lab) for _, lab in got}) > 1:
            conflicts.append({"unit": u, "chosen": chosen, "chosen_window": chosen_w.index,
                              "readings": [{"window": i, "pages": windows[i].evidence()["pages"],
                                            "label": lab} for i, lab in got]})
    return labels, conflicts


def merge_order(windows: Sequence[Window], per_window: Sequence[list[int] | None]) -> list[int]:
    """A global order from window orders: windows in reading order, each unit at its first
    appearance. An order across two windows is never invented: what one window cannot see it
    does not reorder."""
    out: list[int] = []
    placed: set[int] = set()
    for w, order in zip(windows, per_window):
        for u in order or []:
            if w.start <= u < w.end and u not in placed:
                placed.add(u)
                out.append(u)
    return out


def union_groups(groups: Sequence[tuple[int, Sequence[Any]]],
                 refuse: Callable[[set[int], set[int]], str | None] | None = None
                 ) -> tuple[list[list[int]], list[dict]]:
    """Groups proposed by windows, as (window index, members). Two groups that share a member
    are one group — unless they come from the same window (that window kept them apart on
    purpose) or `refuse(a, b)` gives a reason (sets of group indices). Returns the merged sets
    (group indices, first-seen order) and every refused link with its member and reason."""
    parent = list(range(len(groups)))
    wins = [{w} for w, _ in groups]

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    members_of: dict[Any, list[int]] = {}
    for gi, (_, ms) in enumerate(groups):
        for m in dict.fromkeys(ms):
            members_of.setdefault(m, []).append(gi)
    refused: list[dict] = []
    for m, gis in members_of.items():
        for a, b in zip(gis, gis[1:]):
            ra, rb = find(a), find(b)
            if ra == rb:
                continue
            if wins[ra] & wins[rb]:
                refused.append({"member": m, "groups": [a, b], "reason": "SAME_WINDOW"})
                continue
            if refuse is not None:
                sa = {i for i in range(len(groups)) if find(i) == ra}
                sb = {i for i in range(len(groups)) if find(i) == rb}
                why = refuse(sa, sb)
                if why:
                    refused.append({"member": m, "groups": [a, b], "reason": why})
                    continue
            parent[rb] = ra
            wins[ra] |= wins[rb]
    sets: dict[int, list[int]] = {}
    for i in range(len(groups)):
        sets.setdefault(find(i), []).append(i)
    return list(sets.values()), refused


def dedupe(items: Iterable[dict], key: Callable[[dict], Any], *, provenance: str = "windows") -> list[dict]:
    """Stable de-duplication: the first item of each key stays, the provenance of every copy
    (its `window` evidence) is collected on it under `provenance`."""
    out: dict[Any, dict] = {}
    for it in items:
        k = key(it)
        ev = it.get("window")
        if k in out:
            if ev is not None and ev not in out[k][provenance]:
                out[k][provenance].append(ev)
            continue
        out[k] = {**it, provenance: [ev] if ev is not None else []}
    return list(out.values())


def cap_hits(out: Any, schema: dict, path: str = "") -> list[dict]:
    """Every list in a model answer that reached its schema bound (maxItems): it may have been
    cut there. Counted and reported, never silent."""
    hits: list[dict] = []
    if isinstance(schema, dict) and schema.get("type") == "array" and isinstance(out, list):
        mx = schema.get("maxItems")
        if mx is not None and len(out) >= mx:
            hits.append({"path": path or "/", "items": len(out), "max": mx})
        for i, x in enumerate(out):
            hits += cap_hits(x, schema.get("items") or {}, f"{path}[{i}]")
    elif isinstance(schema, dict) and schema.get("type") == "object" and isinstance(out, dict):
        for k, sub in (schema.get("properties") or {}).items():
            if k in out:
                hits += cap_hits(out[k], sub, f"{path}/{k}")
    return hits


def items_room(cap: int | None) -> int | None:
    """How many items one call may carry when its answer lists one entry per item and that list
    is bounded by `cap`: one fewer, because a list AT its bound cannot be told apart from a list
    cut there (cap_hits would rightly report it)."""
    return None if cap is None else max(1, cap - 1)


def list_cap(schema: dict, *path: str) -> int | None:
    """maxItems of the list at `path` (object properties, `[]` for list items)."""
    node = schema
    for p in path:
        node = (node.get("items") if p == "[]" else (node.get("properties") or {}).get(p)) or {}
    return node.get("maxItems")


# ------------------------------------------------------------------ context around pages
def around(pages: Sequence[dict], focus: Iterable[int], budget_tokens: int,
           render: Callable[[list[dict]], str], ratio: float | None = None) -> tuple[str, list[int]]:
    """The text a judge needs for a question about `focus` pages: the whole text when it fits
    (the same string for every question, so the server caches it once — today's behaviour),
    otherwise the focus pages and their neighbours, growing one page at a time on every side
    while it fits. Skipped stretches are marked so the model knows the text is not continuous.
    Returns (text, pages used) — the pages are the evidence of what the judge saw."""
    ordered = sorted(pages, key=lambda p: p["page_no"])
    whole = render(ordered)
    if estimate(whole, ratio) <= budget_tokens:
        return whole, [p["page_no"] for p in ordered]
    pos = {p["page_no"]: i for i, p in enumerate(ordered)}
    want = sorted({pos[f] for f in focus if f in pos})
    if not want:
        return "", []
    cost = [estimate(render([p]), ratio) + 1 for p in ordered]
    chosen: set[int] = set()
    used = 0
    for i in want:                           # the focus pages themselves come first
        if i not in chosen:
            chosen.add(i)
            used += cost[i]
    r = 1
    grew = True
    while grew:
        grew = False
        for i in want:
            for j in (i - r, i + r):
                if 0 <= j < len(ordered) and j not in chosen and used + cost[j] <= budget_tokens:
                    chosen.add(j)
                    used += cost[j]
                    grew = True
        r += 1
    parts: list[str] = []
    prev = None
    for i in sorted(chosen):
        if prev is not None and i != prev + 1:
            parts.append(f"[… s{ordered[prev + 1]['page_no']}–s{ordered[i - 1]['page_no']} bu soruya "
                         f"gösterilmedi …]")
        parts.append(render([ordered[i]]))
        prev = i
    return "\n".join(parts), [ordered[i]["page_no"] for i in sorted(chosen)]


def report(windows: Sequence[Window], **extra) -> dict:
    """The part of a step's result that says how it was read (stored with the step)."""
    return {"windowed": len(windows) > 1, "windows": [w.as_dict() for w in windows], **extra}


@dataclass
class Run:
    """Collected results of a windowed map step."""
    windows: list[Window]
    results: list[Any] = field(default_factory=list)       # per window: result or None
    errors: list[dict] = field(default_factory=list)       # per failed window: pages + error

    @property
    def failed(self) -> int:
        return len(self.errors)


async def map_windows(windows: Sequence[Window], fn: Callable[[Window], Any], *,
                      parallel: int | None = None) -> Run:
    """Run `fn(window)` for every window (at most `parallel` at once). A failed window does not
    stop the others: its result is None and its pages and error are listed, never dropped."""
    import asyncio
    sem = asyncio.Semaphore(parallel or window_parallel())

    async def one(w: Window):
        async with sem:
            return await fn(w)

    got = await asyncio.gather(*(one(w) for w in windows), return_exceptions=True)
    run = Run(list(windows))
    for w, g in zip(windows, got):
        if isinstance(g, BaseException):
            if isinstance(g, (KeyboardInterrupt, SystemExit)):
                raise g
            run.results.append(None)
            run.errors.append({**w.evidence(), "error": f"{type(g).__name__}: {str(g)[:300]}"})
        else:
            run.results.append(g)
    return run
