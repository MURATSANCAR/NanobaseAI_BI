"""Who a drawn figure is, decided over the whole book at once.

Asking a vision model "who is this?" figure by figure does not scale and does not work:
one reading of one crop is unstable, the cost grows with the cast, and the published
measurements agree — a frontier VLM names comic characters at ~0.47, embedding clusters
at ~0.51 NMI, while the same embeddings under a CONSTRAINED global assignment reach
~0.73 (Magiv2, ACCV 2024). What carries the result is not a better reader but the
constraints the page layout gives away for free.

So:

1. Every figure crop becomes one identity vector (CCIP, trained for "are these two
   drawings the same character?"). Milliseconds per crop, and it is stored, so a new
   rule can be tried without reading a single page again.
2. Figures are clustered under a cannot-link constraint: two figures drawn on the SAME
   page are different characters, whatever the vectors say. Clusters merge in order of
   distance (closest first) and only while their average distance stays under the
   measured threshold, so one bad pair cannot chain two characters together.
3. Names come from the text, globally: a cluster may take the name of a character that
   the story names on most of the pages where the cluster is drawn, each name goes to at
   most one cluster, and every cluster may instead take "no name". That is one assignment
   problem over the whole book, not a page-by-page guess.

Nothing here invents a name: a cluster whose name has too little support in the text
stays unnamed, and its figures stay UNCERTAIN.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
from pathlib import Path

import httpx

from . import db, ledger, prompts, schemas
from .config import settings
from .document import page_text_numbered, render_page
from .llm import Llm, image_part
from .vision import _crop

MODEL_KEY = "ccip"


def _client() -> httpx.Client:
    return httpx.Client(base_url=settings().embed_url, timeout=600)


def _figures(generation_id: str) -> list[dict]:
    """Every drawn figure of the generation, minus the boxes too small to be one: page
    ornaments and slivers were named by older runs, and a rule that only newer scans apply
    would leave them in the clustering for good."""
    small = settings().min_figure_side * 1000
    return [f for f in db.all_rows(
        "SELECT cm.id, cm.page_no, cm.surface_name, vr.bbox FROM character_mention cm"
        " JOIN evidence e ON e.id=cm.evidence_id JOIN visual_region vr ON vr.id=e.region_id"
        " WHERE cm.generation_id=%s AND cm.via='VISUAL' ORDER BY cm.page_no, vr.id", generation_id)
            if min(f["bbox"][2] - f["bbox"][0], f["bbox"][3] - f["bbox"][1]) >= small]


def embed_figures(generation_id: str, batch: int = 32) -> dict:
    """One vector per figure crop; already embedded figures are left alone."""
    gen = db.one("SELECT book_version_id FROM generation WHERE id=%s", generation_id)
    bv = str(gen["book_version_id"])
    have = {str(r["mention_id"]) for r in db.all_rows(
        "SELECT mention_id FROM figure_embedding WHERE generation_id=%s AND model=%s",
        generation_id, MODEL_KEY)}
    todo = [f for f in _figures(generation_id) if str(f["id"]) not in have]
    if not todo:
        return {"figures": len(have), "embedded": 0}
    gdir = Path(render_page(bv, todo[0]["page_no"])["path"]).parent / "gallery" / generation_id
    done = 0
    with _client() as c:
        for i in range(0, len(todo), batch):
            chunk = todo[i:i + batch]
            imgs = [base64.b64encode(_crop(render_page(bv, f["page_no"])["path"], f["bbox"],
                                           gdir / f"fig-{f['id']}.png").read_bytes()).decode()
                    for f in chunk]
            out = c.post("/features", json={"images": imgs}).json()
            with db.tx() as conn:
                for f, vec in zip(chunk, out["features"]):
                    conn.execute("INSERT INTO figure_embedding(generation_id, mention_id, model, vector)"
                                 " VALUES (%s,%s,%s,%s) ON CONFLICT (mention_id, model) DO UPDATE"
                                 " SET vector=EXCLUDED.vector", (generation_id, f["id"], MODEL_KEY, vec))
            done += len(chunk)
    return {"figures": len(have) + done, "embedded": done, "model": out["model"]}


def _distances(vectors: list[list[float]]) -> tuple[list[list[float]], float]:
    with _client() as c:
        out = c.post("/differences", json={"features": vectors}).json()
    return out["matrix"], float(out["threshold"])


def cluster_figures(generation_id: str, limit: float | None = None,
                    only: list[str] | None = None) -> dict:
    """Constrained agglomerative clustering: closest pair first, average linkage, and a
    cannot-link between figures drawn on the same page. `limit` overrides the measured
    threshold and `only` restricts the figures, which is how a cluster the adjudicator
    calls mixed is split again, more strictly, instead of being thrown away."""
    figs = [f for f in _figures(generation_id)
            if db.one("SELECT 1 FROM figure_embedding WHERE mention_id=%s AND model=%s",
                      f["id"], MODEL_KEY)]
    vecs = {str(r["mention_id"]): list(r["vector"]) for r in db.all_rows(
        "SELECT mention_id, vector FROM figure_embedding WHERE generation_id=%s AND model=%s",
        generation_id, MODEL_KEY)}
    figs = [f for f in figs if str(f["id"]) in vecs and (only is None or str(f["id"]) in set(only))]
    if len(figs) < 2:
        return {"figures": len(figs), "clusters": len(figs), "members": {}}
    dist, model_threshold = _distances([vecs[str(f["id"])] for f in figs])
    limit = settings().ccip_same_max if limit is None else limit
    n = len(figs)
    cluster = {i: [i] for i in range(n)}          # id -> member indices
    of = list(range(n))                           # figure index -> cluster id
    pages = {i: {figs[i]["page_no"]} for i in range(n)}

    def avg(a: int, b: int) -> float:
        pairs = [dist[i][j] for i in cluster[a] for j in cluster[b]]
        return sum(pairs) / len(pairs)

    pairs = sorted(((dist[i][j], i, j) for i in range(n) for j in range(i + 1, n)),
                   key=lambda x: x[0])
    merged = 0
    for d, i, j in pairs:
        if d >= limit:
            break
        a, b = of[i], of[j]
        if a == b or pages[a] & pages[b]:          # cannot-link: same page, different people
            continue
        if avg(a, b) >= limit:                     # average linkage: no chaining through one pair
            continue
        cluster[a] += cluster[b]
        pages[a] |= pages[b]
        for k in cluster[b]:
            of[k] = a
        del cluster[b], pages[b]
        merged += 1
    tag = "" if only is None else f"s{round(limit * 100)}-"
    members = {f"{tag}{cid}": [str(figs[k]["id"]) for k in idx] for cid, idx in cluster.items()}
    sizes = sorted((len(v) for v in members.values()), reverse=True)
    return {"figures": n, "clusters": len(members), "merges": merged, "sizes": sizes[:12],
            "threshold": limit, "model_threshold": model_threshold, "members": members,
            "pages": {f"{tag}{cid}": sorted(pages[cid]) for cid in cluster}}


def _hungarian(cost: list[list[float]]) -> list[int]:
    """Minimum-cost assignment (Jonker-Volgenant, O(n^3)); row i -> column result[i].
    Written out rather than pulled in, so the whole decision stays in this file and the
    image keeps no numerical dependency for a matrix of a few dozen rows."""
    if not cost or not cost[0]:
        return []
    n, m = len(cost), len(cost[0])
    inf = float("inf")
    u, v = [0.0] * (n + 1), [0.0] * (m + 1)
    p, way = [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv, used = [inf] * (m + 1), [False] * (m + 1)
        while True:
            used[j0] = True
            i0, delta, j1 = p[j0], inf, 0
            for j in range(1, m + 1):
                if used[j]:
                    continue
                cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                if cur < minv[j]:
                    minv[j], way[j] = cur, j0
                if minv[j] < delta:
                    delta, j1 = minv[j], j
            for j in range(m + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0], j0 = p[j1], j1
    out = [-1] * n
    for j in range(1, m + 1):
        if p[j]:
            out[p[j] - 1] = j - 1
    return out


def cluster_scores(generation_id: str, clusters: dict) -> tuple[list[dict], dict, list[dict]]:
    """Per cluster, how much each character is supported by (a) the story text on the
    cluster's pages and (b) the names the page scans themselves gave those figures.

    Text alone rarely decides in a picture book: the narration usually names everyone on
    the page, so three children on one spread all score 1.0. The scans do discriminate —
    unreliably per figure, but a cluster is a vote of many figures, which is exactly the
    aggregation a single reading lacks."""
    # only an individual can be a drawn figure; a collective ("the children") or a concept cannot
    chars = db.all_rows("SELECT id, canonical_name, aliases, kind, description, traits FROM character"
                        " WHERE generation_id=%s AND COALESCE(traits->>'entity_scope','INDIVIDUAL')="
                        "'INDIVIDUAL' ORDER BY first_page NULLS LAST, canonical_name", generation_id)
    scan = {str(r["id"]): r["surface_name"] for r in _figures(generation_id)}
    with db.tx() as c:
        idx = ledger.PageIndex.load(c, generation_id)
    names = {k: [ch["canonical_name"], *ch["aliases"]] for k, ch in enumerate(chars)}

    def named_near(page: int, k: int) -> bool:
        text = " ".join(idx.text.get(p, "") for p in (page - 1, page, page + 1))
        return any(ledger.has_name(text, n) for n in names[k])

    scores = {}
    for cid, mids in clusters["members"].items():
        pages = clusters["pages"][cid]
        text_support = [sum(named_near(p, k) for p in pages) / len(pages) for k in range(len(chars))]
        votes = [0.0] * len(chars)
        for mid in mids:
            guess = ledger.norm(scan.get(mid) or "")
            for k in range(len(chars)):
                if guess and any(ledger.norm(n) == guess for n in names[k]):
                    votes[k] += 1 / len(mids)
        scores[cid] = {"text": text_support, "scan": votes,
                       "total": [(t + v) / 2 for t, v in zip(text_support, votes)]}
    return chars, scores, []


async def adjudicate(generation_id: str, clusters: dict, chars: list[dict], scores: dict,
                     cids: list[str]) -> dict:
    """Every cluster — but only once per cluster, not once per figure — is shown to the
    vision model: a few of its crops, the candidate people and the pages' text. It answers
    three things: is this a drawn character at all (a page ornament or a patch of scenery
    is not), is it ONE character (the similarity measure does merge two people now and
    then), and which of the named people it is. One call per cluster is what makes the
    expensive model affordable on a corpus; per figure it is not."""
    gen = db.one("SELECT book_version_id FROM generation WHERE id=%s", generation_id)
    bv = str(gen["book_version_id"])
    figs = {str(f["id"]): f for f in _figures(generation_id)}
    gdir = Path(render_page(bv, next(iter(figs.values()))["page_no"])["path"]).parent \
        / "gallery" / generation_id
    llm = Llm(generation_id)
    sem = asyncio.Semaphore(settings().deep_concurrency * 2)
    ref0, _ = prompts.render("cluster_name", pages="-", candidates="-", pages_text="-")
    prompt_ref = f"{ref0.name}@{ref0.version}"

    def card(k: int) -> str:
        ch = chars[k]
        tr = ", ".join(v for v in (ch["traits"] or {}).values() if v and v != "UNKNOWN")
        return f"- {ch['canonical_name']} ({ch['kind']}{', ' + tr if tr else ''}): {ch['description'][:200]}"

    async def one(cid: str) -> tuple[str, dict | None]:
        ranked = sorted(range(len(chars)), key=lambda k: -scores[cid]["total"][k])
        key = hashlib.sha256(",".join(sorted(clusters["members"][cid])).encode()).hexdigest()[:32]
        cached = db.one("SELECT verdict FROM cluster_verdict WHERE generation_id=%s AND members_key=%s"
                        " AND prompt=%s", generation_id, key, prompt_ref)
        if cached:
            v = cached["verdict"]
            pick = next((k for k in range(len(chars)) if v.get("name") and
                         ledger.norm(chars[k]["canonical_name"]) == ledger.norm(v["name"])), None)
            return cid, {**v, "k": pick}
        cands = [k for k in ranked if scores[cid]["total"][k] > 0][:6] or ranked[:6]
        mids = clusters["members"][cid][:3]
        parts = []
        for mid in mids:
            f = figs[mid]
            parts += [{"type": "text", "text": f"Sayfa {f['page_no']}:"},
                      image_part(_crop(render_page(bv, f["page_no"])["path"], f["bbox"],
                                       gdir / f"fig-{mid}.png").read_bytes())]
        pages = clusters["pages"][cid][:4]
        ref, body = prompts.render(
            "cluster_name", pages=", ".join(map(str, clusters["pages"][cid])),
            candidates="\n".join(card(k) for k in cands),
            pages_text="\n".join(page_text_numbered(generation_id, p) for p in pages))
        try:
            async with sem:
                out, _ = await llm.chat("book-vision-deep",
                                        [{"role": "user", "content": parts + [{"type": "text", "text": body}]}],
                                        prompt=ref, schema=schemas.CLUSTER_NAME,
                                        pages=clusters["pages"][cid], max_tokens=6144, temperature=0.0)
        except Exception:  # noqa: BLE001
            return cid, None
        pick = next((k for k in cands if ledger.norm(chars[k]["canonical_name"]) == ledger.norm(out["name"])),
                    None)
        v = {"name": chars[pick]["canonical_name"] if pick is not None else None,
             "is_character": bool(out["is_character"]), "same_character": bool(out["same_character"]),
             "confidence": float(out["confidence"]), "reason": out["reason"][:300]}
        with db.tx() as c:
            c.execute("INSERT INTO cluster_verdict(generation_id, members_key, prompt, verdict)"
                      " VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                      (generation_id, key, prompt_ref, db.J(v)))
        return cid, {**v, "k": pick}

    return dict(await asyncio.gather(*(one(cid) for cid in cids)))


async def name_clusters(generation_id: str, clusters: dict) -> dict:
    """Give each cluster a name, or none.

    A name may cover SEVERAL clusters: the same character is often drawn in ways the
    embedder keeps apart (a face close-up, a different outfit), and one-name-one-cluster
    would leave most of a book unnamed. What a name may NOT do is appear twice on one
    page, so a later cluster only takes a name whose pages do not collide with the pages
    it already covers — the same cannot-link that drives the clustering.

    A cluster the adjudicator does not recognise as one drawn character is dropped, name
    or no name: better a figure without an identity than an ornament with one."""
    if not clusters["members"]:
        return {"named": 0, "assignments": []}
    chars, scores, _ = cluster_scores(generation_id, clusters)
    if not chars:
        return {"named": 0, "assignments": []}
    floor, margin = settings().cluster_name_support, settings().cluster_name_margin
    verdicts = await adjudicate(generation_id, clusters, chars, scores, list(clusters["members"]))
    # A cluster the adjudicator reads as several people is not wrong evidence, it is a
    # threshold that was too loose for those drawings: split it again, more strictly, and
    # let it be judged once more. Its figures are only lost if the split does not help.
    mixed = [cid for cid, v in verdicts.items() if v and v.get("same_character") is False
             and len(clusters["members"][cid]) > 1]
    split_rounds = 0
    for cid in mixed:
        parts = cluster_figures(generation_id, limit=settings().ccip_same_max * 0.6,
                                only=clusters["members"][cid])
        if parts["clusters"] <= 1:
            continue
        split_rounds += 1
        del clusters["members"][cid], clusters["pages"][cid], verdicts[cid]
        clusters["members"].update(parts["members"])
        clusters["pages"].update(parts["pages"])
    if split_rounds:
        chars, scores, _ = cluster_scores(generation_id, clusters)
        new_ids = [cid for cid in clusters["members"] if cid not in verdicts]
        verdicts.update(await adjudicate(generation_id, clusters, chars, scores, new_ids))

    order = sorted(clusters["members"], key=lambda cid: (-max(scores[cid]["total"]),
                                                         -len(clusters["members"][cid])))
    taken: dict[int, set[int]] = {}
    out = []
    for cid in order:
        tot = scores[cid]["total"]
        pages = set(clusters["pages"][cid])
        ranked = sorted(range(len(chars)), key=lambda k: -tot[k])
        v = verdicts.get(cid) or {}
        refused = v.get("is_character") is False or v.get("same_character") is False

        def free(k: int) -> bool:
            return not (taken.get(k, set()) & pages)

        # The adjudicator does not know which names are already spoken for on these pages.
        # When its answer is one of them, the cluster is not nameless: it falls back to the
        # best name the evidence supports and the page constraint still allows.
        best, ok = None, False
        if not refused:
            picks = ([v["k"]] if v.get("k") is not None and v.get("confidence", 0) >= 0.7 else []) + ranked
            for k in picks:
                if not free(k):
                    continue
                rest = max((tot[j] for j in ranked if j != k and free(j)), default=0.0)
                if k == v.get("k") and v.get("confidence", 0) >= 0.7:
                    best, ok = k, True
                    break
                if tot[k] >= floor and tot[k] - rest >= margin:
                    best, ok = k, True
                    break
            if best is None and ranked:
                best = ranked[0]
        second = max((tot[k] for k in ranked if k != best), default=0.0)
        out.append({"cluster": cid, "figures": len(clusters["members"][cid]), "pages": sorted(pages),
                    "name": chars[best]["canonical_name"] if ok else None,
                    "character_id": str(chars[best]["id"]) if ok else None,
                    "by": ("adjudicator" if ok and best == v.get("k") else "evidence") if ok else None,
                    "refused": ("not a character" if v.get("is_character") is False else
                                "several characters" if v.get("same_character") is False else None),
                    "support": round(tot[best], 3) if best is not None else 0.0,
                    "runner_up": round(second, 3), "reason": v.get("reason", "")})
        if ok:
            taken.setdefault(best, set()).update(pages)
    return {"named": sum(1 for x in out if x["name"]), "clusters": len(out),
            "adjudicated": len(verdicts), "split": split_rounds,
            "refused_not_character": sum(1 for x in out if x["refused"] == "not a character"),
            "refused_mixed": sum(1 for x in out if x["refused"] == "several characters"),
            "assignments": out}


async def resolve(generation_id: str, write: bool = True) -> dict:
    """Embed -> cluster -> name. Idempotent; `write=False` measures without touching the
    generation (the figures keep whatever the previous rules decided)."""
    emb = embed_figures(generation_id)
    clusters = cluster_figures(generation_id)
    named = await name_clusters(generation_id, clusters)   # may split clusters as it goes
    stats = {"embedded": emb, "figures": clusters["figures"], "clusters": clusters["clusters"],
             "adjudicated": named.get("adjudicated", 0),
             "refused_not_character": named.get("refused_not_character", 0),
             "refused_mixed": named.get("refused_mixed", 0), "split": named.get("split", 0),
             "threshold": clusters.get("threshold"), "named_clusters": named["named"],
             "named_figures": sum(a["figures"] for a in named["assignments"] if a["name"]),
             "assignments": named["assignments"]}
    by_fig = {}
    for a in named["assignments"]:
        if not a["name"]:
            continue
        for mid in clusters["members"][a["cluster"]]:
            by_fig[mid] = a
    stats["by_figure"] = {mid: a["name"] for mid, a in by_fig.items()}
    if not write:
        return stats
    with db.tx() as c:
        c.execute("UPDATE character_mention SET character_id=NULL, resolution='UNCERTAIN', appearance ="
                  " appearance - 'identified_by' - 'cluster' - 'cluster_support' WHERE generation_id=%s"
                  " AND via='VISUAL'", (generation_id,))
        for mid, a in by_fig.items():
            conf = min(0.95, max(0.6, a["support"]))
            c.execute("UPDATE character_mention SET character_id=%s, resolution='RESOLVED',"
                      " confidence=%s, appearance = appearance || %s WHERE id=%s",
                      (a["character_id"], conf,
                       db.J({"identified_by": "cluster", "cluster": a["cluster"],
                             "cluster_support": a["support"]}), mid))
    return stats
