"""book_vision tools. book-vision-fast scans every page; pages it marks
uncertain (identity, text-visual mismatch, unclear scene, important event) go to
book-vision-deep (NIHAI-KARAR.md §5 steps 5-6, §6)."""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from pathlib import Path

from . import source, db, ledger, prompts, schemas
from .config import settings
from .document import page_text_numbered, region_ink_ratio, render_page
from .llm import Llm, image_part

_NAME = re.compile(r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})\b")
_STOP = {"Bir", "Bu", "Şu", "Ama", "Ve", "Ben", "Sen", "Biz", "Siz", "Onlar", "Evet", "Hayır",
         "Belki", "Hem", "Sonra", "Şimdi", "Neden", "Nasıl", "Ne", "Tamam", "Hadi", "Çünkü",
         "Aa", "Oh", "Of", "Peki", "Eğer", "Bugün", "Yarın", "Dün", "Hey", "Merhaba", "Haydi",
         "Ancak", "Oysa", "Bütün", "Her", "Hiç", "Kim", "Sanki", "Yine", "Artık", "Birden"}


def contradicts(chk: dict) -> bool:
    """A text-visual check is a finding only when the picture shows something that
    conflicts with the text (older scans stored a plain `consistent` flag)."""
    return chk.get("relation") == "CONTRADICTS" if "relation" in chk else not chk.get("consistent", True)


EMPTY_SCAN = {"scene": {"setting": "", "time_of_day": "", "mood": "", "description": ""},
              "characters": [], "objects": [], "text_in_image": [], "text_visual_checks": [],
              "important_event": False, "uncertain": False, "uncertainty_reasons": []}


def known_names(generation_id: str) -> list[str]:
    """Capitalised words that recur mid-sentence in the book text: a hint list
    for the scanner, not a claim."""
    c: Counter = Counter()
    for r in source.passages(generation_id):
        for m in _NAME.finditer(r["text"]):
            start = m.start()
            if start > 1 and r["text"][start - 2] not in ".!?\"“":
                w = m.group(1)
                if w not in _STOP:
                    c[w.rstrip("'’")] += 1
    return [w for w, n in c.most_common(40) if n >= 3]


async def analyze_page_visual(generation_id: str, page_no: int, depth: str = "fast",
                              reasons: list[str] | None = None) -> dict:
    """One vision pass over a page; stored in page_scan (FAST or DEEP)."""
    gen = db.one("SELECT book_version_id FROM generation WHERE id=%s", generation_id)
    pg = db.one("SELECT nontext_ink FROM page WHERE book_version_id=%s AND page_no=%s",
                gen["book_version_id"], page_no)
    if pg and pg["nontext_ink"] is not None and pg["nontext_ink"] < settings().min_illustration_ink:
        # Nothing but text on the page: asking a vision model what it "sees" only
        # invites figures invented from the text. Record an empty scan instead.
        out = dict(EMPTY_SCAN)
        with db.tx() as c:
            c.execute("INSERT INTO page_scan(generation_id, page_no, pass, alias, result, uncertain,"
                      " uncertainty_reasons) VALUES (%s,%s,'FAST','no-illustration',%s,false,'{}')"
                      " ON CONFLICT (generation_id, page_no, pass) DO NOTHING",
                      (generation_id, page_no, db.J(out)))
        return {"page_no": page_no, "pass": "FAST", "uncertain": False, "reasons": [],
                "characters": 0, "skipped": "no illustration"}
    if depth == "fast" and settings().vision_screen == "deep":
        # No fast screening: the pixel measure already separated text-only pages, and the
        # deep model reads every illustrated page first-hand.
        with db.tx() as c:
            c.execute("INSERT INTO page_scan(generation_id, page_no, pass, alias, result, uncertain,"
                      " uncertainty_reasons) VALUES (%s,%s,'FAST','deferred-to-deep',%s,true,%s)"
                      " ON CONFLICT (generation_id, page_no, pass) DO NOTHING",
                      (generation_id, page_no, db.J(dict(EMPTY_SCAN)), ["DEEP_FIRST"]))
        return {"page_no": page_no, "pass": "FAST", "uncertain": True, "reasons": ["DEEP_FIRST"],
                "characters": 0, "skipped": "deferred to deep"}
    png = Path(render_page(str(gen["book_version_id"]), page_no)["path"]).read_bytes()
    text = page_text_numbered(generation_id, page_no)
    if depth == "fast":
        ref, body = prompts.render("page_scan_fast", page_no=str(page_no), page_text=text,
                                   known_names=", ".join(known_names(generation_id)) or "-")
        alias, pass_, max_tokens, thinking = "book-vision-fast", "FAST", 4096, None
    else:
        fast = db.one("SELECT result, uncertainty_reasons FROM page_scan WHERE generation_id=%s "
                      "AND page_no=%s AND pass='FAST'", generation_id, page_no)
        ctx = "\n".join(page_text_numbered(generation_id, p) for p in (page_no - 1, page_no + 1)
                        if p > 0)
        ref, body = prompts.render(
            "page_scan_deep", page_no=str(page_no),
            reasons=", ".join(reasons or (fast or {}).get("uncertainty_reasons") or []) or "-",
            fast_result="-" if (fast or {}).get("uncertainty_reasons") == ["DEEP_FIRST"] else
            json.dumps((fast or {}).get("result") or {}, ensure_ascii=False),
            page_text=text, context_text=ctx or "-",
            known_characters=known_characters_text(generation_id))
        alias, pass_, max_tokens, thinking = "book-vision-deep", "DEEP", 16384, None
    out, call_id = await Llm(generation_id).chat(
        alias, [{"role": "user", "content": [image_part(png), {"type": "text", "text": body}]}],
        prompt=ref, schema=schemas.PAGE_SCAN, pages=[page_no], max_tokens=max_tokens,
        temperature=0.1, thinking=thinking)
    if depth == "fast":
        # Which pages need the deep model is decided by evidence, not by the fast model's
        # own word (measured: it misnames figures on ~1 in 4 illustrated pages, sometimes
        # with high confidence and no flag; and every single page looks "important" to a
        # model that sees one page). A drawn figure's identity is never settled by the
        # fast pass; importance is decided later, over the whole timeline.
        png_path = render_page(str(gen["book_version_id"]), page_no)["path"]
        need = set()
        if any(region_ink_ratio(png_path, ch["bbox"]) >= settings().min_figure_ink
               for ch in out["characters"]):
            need.add("IDENTITY")
        if any(contradicts(chk) for chk in out["text_visual_checks"]):
            need.add("TEXT_VISUAL")
        if "SCENE" in out["uncertainty_reasons"]:
            need.add("SCENE")
        out = {**out, "uncertain": bool(need), "uncertainty_reasons": sorted(need)}
    with db.tx() as c:
        c.execute(
            "INSERT INTO page_scan(generation_id, page_no, pass, alias, result, uncertain,"
            " uncertainty_reasons, model_call_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)"
            " ON CONFLICT (generation_id, page_no, pass) DO UPDATE SET result=EXCLUDED.result,"
            " uncertain=EXCLUDED.uncertain, uncertainty_reasons=EXCLUDED.uncertainty_reasons,"
            " model_call_id=EXCLUDED.model_call_id",
            (generation_id, page_no, pass_, alias, db.J(out), bool(out["uncertain"]),
             sorted(set(out["uncertainty_reasons"])), call_id))
    return {"page_no": page_no, "pass": pass_, "uncertain": out["uncertain"],
            "reasons": out["uncertainty_reasons"], "characters": len(out["characters"])}


def best_scan(generation_id: str, page_no: int) -> dict | None:
    return db.one("SELECT pass, result, model_call_id FROM page_scan WHERE generation_id=%s AND "
                  "page_no=%s AND alias<>'deferred-to-deep' ORDER BY (pass='DEEP') DESC LIMIT 1",
                  generation_id, page_no)


def known_characters_text(generation_id: str) -> str:
    """Names and looks seen so far (best scan per page), as a hint for deep passes."""
    looks: dict[str, list[str]] = {}
    for r in db.all_rows("SELECT DISTINCT ON (page_no) page_no, result FROM page_scan WHERE "
                         "generation_id=%s ORDER BY page_no, (pass='DEEP') DESC", generation_id):
        for ch in r["result"].get("characters", []):
            if ch.get("name") and not ch.get("identity_uncertain"):
                a = ch.get("appearance") or {}
                looks.setdefault(ch["name"], []).append(
                    f"s{r['page_no']}: {a.get('hair','')}, {a.get('clothes','')}, {a.get('distinctive','')}")
    return "\n".join(f"- {n}: " + " | ".join(v[:4]) for n, v in looks.items()) or "-"


async def _ensure_scan(generation_id: str, page_no: int) -> dict:
    s = best_scan(generation_id, page_no)
    if s is None:
        await analyze_page_visual(generation_id, page_no, "fast")
        s = best_scan(generation_id, page_no)
    return s


async def detect_characters(generation_id: str, page_no: int) -> list[dict]:
    return (await _ensure_scan(generation_id, page_no))["result"]["characters"]


async def detect_objects(generation_id: str, page_no: int) -> list[dict]:
    return (await _ensure_scan(generation_id, page_no))["result"]["objects"]


async def detect_scene(generation_id: str, page_no: int) -> dict:
    s = (await _ensure_scan(generation_id, page_no))["result"]
    return {"scene": s["scene"], "important_event": s["important_event"],
            "text_in_image": s["text_in_image"]}


def persist_page_visual(generation_id: str, page_no: int) -> dict:
    """Best scan -> visual regions, visual character mentions, scene claim. Idempotent
    per page. Text-visual findings are written by `confirm_text_visual`."""
    s = best_scan(generation_id, page_no)
    if s is None:
        return {"page_no": page_no, "skipped": "no scan"}
    res, call_id, pass_ = s["result"], s["model_call_id"], s["pass"]
    with db.tx() as c:
        if c.execute("SELECT 1 FROM visual_region WHERE generation_id=%s AND page_no=%s LIMIT 1",
                     (generation_id, page_no)).fetchone():
            return {"page_no": page_no, "skipped": "already persisted"}
        idx = ledger.PageIndex.load(c, generation_id)
        created_by = f"vision:{pass_.lower()}"
        mentions = unseen = 0
        png_path = render_page(str(c.execute("SELECT book_version_id FROM generation WHERE id=%s",
                                             (generation_id,)).fetchone()["book_version_id"]), page_no)["path"]
        front = c.execute("SELECT 1 FROM page_role WHERE generation_id=%s AND page_no=%s AND"
                          " role='FRONT_MATTER' AND source='editor'", (generation_id, page_no)).fetchone() is not None
        near_text = " ".join(idx.text.get(p, "") for p in (page_no - 1, page_no, page_no + 1))
        for ch in res["characters"]:
            # A figure is a visual claim: its box must actually contain ink.
            if region_ink_ratio(png_path, ch["bbox"]) < settings().min_figure_ink or \
                    min(ch["bbox"][2] - ch["bbox"][0], ch["bbox"][3] - ch["bbox"][1]) < settings().min_figure_side * 1000:
                unseen += 1
                continue
            # A name needs a basis in the story text on or next to this page. Cover and
            # other front-matter art has no narrative text, so its figures stay unnamed
            # candidates; so do names the fast pass gives (it guesses from the hint list).
            named_here = bool(ch["name"]) and ledger.has_name(near_text, ch["name"])
            if front or pass_ == "FAST" or not named_here:
                ch = {**ch, "identity_uncertain": True, "confidence": min(ch["confidence"], 0.6)}
            desc = ", ".join(v for v in (ch["appearance"] or {}).values() if v)
            label = ch["name"] or ch["label"]
            reg = c.execute(
                "INSERT INTO visual_region(generation_id, page_no, label, kind, bbox, description,"
                " model_call_id) VALUES (%s,%s,%s,'character',%s,%s,%s) RETURNING id",
                (generation_id, page_no, label, db.J(ch["bbox"]),
                 f"{ch['label']}: {desc}; {ch['action']}", call_id)).fetchone()
            eid, ok = ledger.save_evidence(c, generation_id, idx, page=page_no, kind="VISUAL",
                                           region_id=str(reg["id"]),
                                           quote=f"{ch['label']}: {desc}; {ch['action']}")
            uncertain = ch["identity_uncertain"] or not ch["name"]
            c.execute(
                "INSERT INTO character_mention(generation_id, page_no, surface_name, via, appearance,"
                " resolution, confidence, evidence_id) VALUES (%s,%s,%s,'VISUAL',%s,%s,%s,%s)",
                (generation_id, page_no, ch["name"] or None, db.J(ch["appearance"]),
                 "UNCERTAIN" if uncertain else "UNRESOLVED", ch["confidence"], eid))
            mentions += 1
        for ob in res["objects"]:
            c.execute("INSERT INTO visual_region(generation_id, page_no, label, kind, bbox,"
                      " description, model_call_id) VALUES (%s,%s,%s,'object',%s,%s,%s)",
                      (generation_id, page_no, ob["label"], db.J(ob["bbox"]), ob["note"], call_id))
        sc = res["scene"]
        if sc.get("description"):
            reg = c.execute("INSERT INTO visual_region(generation_id, page_no, label, kind,"
                            " description, model_call_id) VALUES (%s,%s,'scene','scene',%s,%s)"
                            " RETURNING id", (generation_id, page_no, sc["description"], call_id)
                            ).fetchone()
            ev = ledger.save_evidence(c, generation_id, idx, page=page_no, kind="VISUAL",
                                      region_id=str(reg["id"]), quote=sc["description"])
            ledger.save_claim(c, generation_id, kind="VISUAL_SCENE", subject=f"sayfa {page_no}",
                              claim=sc["description"], evidence=[(ev[0], ev[1], page_no)],
                              confidence=0.7 if pass_ == "FAST" else 0.8, created_by=created_by,
                              payload={"setting": sc["setting"], "time_of_day": sc["time_of_day"],
                                       "mood": sc["mood"], "important_event": res["important_event"]},
                              model_call_id=call_id)
    return {"page_no": page_no, "pass": pass_, "visual_mentions": mentions,
            "figures_dropped_unseen": unseen}


async def confirm_text_visual(generation_id: str) -> dict:
    """"Görsel-metinsel uyuşmazlık doğrudan hata değil, aday bulgu olur" — and one reading of
    one page is not even a stable candidate (measured: the same model and prompt gave 5 on
    one run and 0 on the next). So a page's candidates are the union of its scan and one
    focused second reading, and each candidate is then put to independent votes that see
    only the picture and the sentence. It is written to the ledger when a majority of the
    votes see a contradiction; the votes are kept either way."""
    gen = db.one("SELECT book_version_id FROM generation WHERE id=%s", generation_id)
    n_votes = settings().text_visual_votes
    todo = db.all_rows(
        "SELECT s.page_no FROM page_scan s WHERE s.generation_id=%s AND s.pass='DEEP' AND NOT EXISTS"
        " (SELECT 1 FROM text_visual_check t WHERE t.generation_id=s.generation_id AND t.page_no=s.page_no)"
        " AND NOT EXISTS (SELECT 1 FROM page_role r WHERE r.generation_id=s.generation_id AND"
        " r.page_no=s.page_no AND r.role='FRONT_MATTER' AND r.source='editor') ORDER BY s.page_no", generation_id)
    sem = asyncio.Semaphore(settings().deep_concurrency * 2)
    llm = Llm(generation_id)

    async def ask(prompt_name: str, schema: dict, page_no: int, png: bytes, temperature: float, **kw):
        ref, body = prompts.render(prompt_name, page_no=str(page_no), **kw)
        async with sem:
            return await llm.chat("book-vision-deep", [{"role": "user", "content": [
                image_part(png), {"type": "text", "text": body}]}], prompt=ref, schema=schema,
                pages=[page_no], max_tokens=8192, temperature=temperature)

    async def one_page(page_no: int) -> dict:
        with db.tx() as c:
            idx = ledger.PageIndex.load(c, generation_id)
        text = page_text_numbered(generation_id, page_no)
        scan = best_scan(generation_id, page_no)
        if not idx.text.get(page_no, "").strip():
            proposals = []
        else:
            png = Path(render_page(str(gen["book_version_id"]), page_no)["path"]).read_bytes()
            second, _ = await ask("text_visual_recheck", schemas.TEXT_VISUAL_RECHECK, page_no, png, 0.1,
                                  page_text=text)
            proposals = []
            for src, checks in (("scan", scan["result"]["text_visual_checks"]), ("recheck", second["checks"])):
                for chk in checks:
                    quote = chk["text_quote"].strip()
                    if not contradicts(chk) or not quote:
                        continue
                    if not idx.verify(page_no, quote, "TEXT"):
                        quote = ledger.snap_quote(quote, idx.raw.get(page_no, "")) or ""
                    # a contradiction is between the picture and a sentence that is on the page
                    if not quote:
                        continue
                    same = next((p for p in proposals if ledger.norm(p["text_quote"]) in ledger.norm(quote)
                                 or ledger.norm(quote) in ledger.norm(p["text_quote"])), None)
                    if same:
                        same["proposed_by"].append(src)
                    else:
                        proposals.append({**chk, "text_quote": quote, "proposed_by": [src]})
        confirmed = 0
        for p in proposals:
            votes = await asyncio.gather(*(ask("text_visual_vote", schemas.TEXT_VISUAL_VOTE, page_no, png, 0.6,
                                               text_quote=p["text_quote"]) for _ in range(n_votes)),
                                         return_exceptions=True)
            got = [v[0] for v in votes if not isinstance(v, BaseException)]
            yes = [v for v in got if v["relation"] == "CONTRADICTS"]
            p["votes"] = [{"relation": v["relation"], "confidence": v["confidence"],
                           "visual_observation": v["visual_observation"]} for v in got]
            p["confirmed"] = len(got) == n_votes and len(yes) * 2 > n_votes
            if not p["confirmed"]:
                continue
            confirmed += 1
            conf = min(sum(v["confidence"] for v in yes) / len(yes), len(yes) / n_votes)
            obs = max(yes, key=lambda v: v["confidence"])["visual_observation"].strip() or p["visual_observation"]
            with db.tx() as c:
                idx = ledger.PageIndex.load(c, generation_id)
                ev_t = ledger.save_evidence(c, generation_id, idx, page=page_no, kind="TEXT",
                                            paragraph_idx=p["paragraph"] or None, quote=p["text_quote"])
                ev_v = ledger.save_evidence(c, generation_id, idx, page=page_no, kind="VISUAL", quote=obs)
                claim_id = ledger.save_claim(
                    c, generation_id, kind="TEXT_VISUAL_MISMATCH", subject=f"sayfa {page_no}",
                    claim=f"Metin: “{p['text_quote']}” — Görsel: {obs}",
                    evidence=[(ev_t[0], ev_t[1], page_no), (ev_v[0], ev_v[1], page_no)], confidence=conf,
                    created_by="vision:text-visual-votes",
                    payload={"votes": f"{len(yes)}/{n_votes}", "proposed_by": p["proposed_by"]})
                c.execute("INSERT INTO contradiction(generation_id, kind, description, pages, claim_ids,"
                          " confidence) VALUES (%s,'TEXT_VISUAL',%s,%s,%s,%s)",
                          (generation_id, obs, [page_no], [claim_id] if claim_id else [], conf))
        with db.tx() as c:
            c.execute("INSERT INTO text_visual_check(generation_id, page_no, proposed, confirmed, detail)"
                      " VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                      (generation_id, page_no, len(proposals), confirmed, db.J(proposals)))
        return {"page_no": page_no, "proposed": len(proposals), "confirmed": confirmed}

    res = await asyncio.gather(*(one_page(r["page_no"]) for r in todo), return_exceptions=True)
    ok = [r for r in res if not isinstance(r, BaseException)]
    failed = [str(r)[:200] for r in res if isinstance(r, BaseException)]
    if todo and not ok:
        raise RuntimeError(f"text-visual confirmation failed on every page: {failed[:3]}")
    return {"pages": len(ok), "proposed": sum(r["proposed"] for r in ok),
            "confirmed": sum(r["confirmed"] for r in ok),
            "confirmed_pages": [r["page_no"] for r in ok if r["confirmed"]], "pages_failed": failed}


async def check_text_visual_consistency(generation_id: str, page_no: int) -> dict:
    """Findings are the voted ones; a scan's own unvoted candidates are reported as such."""
    s = await _ensure_scan(generation_id, page_no)
    persist_page_visual(generation_id, page_no)
    voted = db.one("SELECT proposed, confirmed, detail FROM text_visual_check WHERE generation_id=%s AND"
                   " page_no=%s", generation_id, page_no)
    checks = s["result"]["text_visual_checks"]
    return {"page_no": page_no, "pass": s["pass"], "voted": voted is not None,
            "findings": [p for p in (voted or {}).get("detail", []) if p.get("confirmed")],
            "not_confirmed": [p for p in (voted or {}).get("detail", []) if not p.get("confirmed")],
            "unvoted_candidates": [] if voted else [c for c in checks if contradicts(c)],
            "consistent": sum(1 for c in checks if not contradicts(c))}


async def compare_character_appearances(generation_id: str, character: str,
                                        pages: list[int]) -> dict:
    """Deep model looks at up to 6 pages of one character; differences become
    VISUAL_CONTINUITY claims and CONTINUITY contradiction candidates."""
    pages = sorted(set(pages))[:6]
    gen = db.one("SELECT book_version_id FROM generation WHERE id=%s", generation_id)
    # The character's own verified crops, not whole pages: on a full page the model may
    # compare a different figure. (A page without a verified crop falls back to the page.)
    bv = str(gen["book_version_id"])
    crops = {r["page_no"]: r for r in db.all_rows(
        "SELECT cm.page_no, cm.id, vr.bbox FROM character_mention cm JOIN character ch ON ch.id=cm.character_id"
        " JOIN evidence e ON e.id=cm.evidence_id JOIN visual_region vr ON vr.id=e.region_id WHERE"
        " cm.generation_id=%s AND cm.via='VISUAL' AND cm.resolution='RESOLVED' AND cm.page_no = ANY(%s) AND"
        " (ch.canonical_name ILIKE %s OR %s = ANY(ch.aliases))", generation_id, pages, character, character)}
    gdir = Path(render_page(bv, pages[0])["path"]).parent / "gallery" / generation_id
    images: dict[int, dict] = {}
    for p in pages:
        if p in crops:
            png = _crop(render_page(bv, p)["path"], crops[p]["bbox"], gdir / f"fig-{crops[p]['id']}.png").read_bytes()
        else:
            png = Path(render_page(bv, p, 1200)["path"]).read_bytes()
        images[p] = image_part(png)
    parts = [x for p in pages for x in ({"type": "text", "text": f"Sayfa {p}:"}, images[p])]
    # Only the pictures: feeding the scans' descriptions made the model compare wordings
    # ("kırmızımsı kahverengi" vs "kırmızı") instead of drawings.
    ref, body = prompts.render("compare_appearance", pages=", ".join(map(str, pages)), character=character)
    llm = Llm(generation_id)
    out, call_id = await llm.chat(
        "book-vision-deep", [{"role": "user", "content": parts + [{"type": "text", "text": body}]}],
        prompt=ref, schema=schemas.APPEARANCE, pages=pages, max_tokens=16384, temperature=0.1)

    # One comparison is a proposal (measured: hair parting mirrored by the pose, hair wet in the
    # rain were reported as continuity errors in one run and not in the next). Each proposed
    # difference goes to independent votes that see only the crops of its pages and the NAME of
    # the attribute, not the proposal's description. It is a finding when a majority says DIFFERENT.
    n_votes = settings().continuity_votes

    async def vote(d: dict) -> list[dict]:
        ps = [p for p in d["pages"] if p in images]
        vref, vbody = prompts.render("continuity_vote", pages=", ".join(map(str, ps)), character=character,
                                     attribute=d["attribute"])
        content = [x for p in ps for x in ({"type": "text", "text": f"Sayfa {p}:"}, images[p])]
        res = await asyncio.gather(*(llm.chat(
            "book-vision-deep", [{"role": "user", "content": content + [{"type": "text", "text": vbody}]}],
            prompt=vref, schema=schemas.CONTINUITY_VOTE, pages=ps, max_tokens=8192, temperature=0.6)
            for _ in range(n_votes)), return_exceptions=True)
        return [r[0] for r in res if not isinstance(r, BaseException)]

    proposals = [d for d in out["differences"] if d["continuity_candidate"] and not d["explained_by_story"]
                 and len([p for p in d["pages"] if p in images]) >= 2]
    ballots = await asyncio.gather(*(vote(d) for d in proposals))
    confirmed, rejected = [], []
    with db.tx() as c:
        idx = ledger.PageIndex.load(c, generation_id)
        for d, votes in zip(proposals, ballots):
            yes = [v for v in votes if v["verdict"] == "DIFFERENT"]
            tally = {"attribute": d["attribute"], "pages": d["pages"], "description": d["description"],
                     "votes": [v["verdict"] for v in votes]}
            if len(votes) < n_votes or len(yes) * 2 <= n_votes:
                rejected.append(tally)
                continue
            confirmed.append(tally)
            conf = min(sum(v["confidence"] for v in yes) / len(yes), len(yes) / n_votes)
            seen = max(yes, key=lambda v: v["confidence"])["seen"].strip() or d["description"]
            evs = [(*ledger.save_evidence(c, generation_id, idx, page=p, kind="VISUAL",
                                          quote=f"{character} — {d['attribute']}: {seen}"), p)
                   for p in d["pages"] if p in images]
            cid = ledger.save_claim(
                c, generation_id, kind="VISUAL_CONTINUITY", subject=character,
                claim=f"{character}: {d['attribute']} sayfalar arasında farklı — {seen}",
                evidence=evs, confidence=conf, created_by="vision:continuity-votes",
                payload={"votes": f"{len(yes)}/{n_votes}", "proposal": d["description"]}, model_call_id=call_id)
            c.execute("INSERT INTO contradiction(generation_id, kind, description, pages,"
                      " claim_ids, confidence) VALUES (%s,'CONTINUITY',%s,%s,%s,%s)",
                      (generation_id, f"{character}: {d['attribute']} — {seen}", d["pages"],
                       [cid] if cid else [], conf))
    out = {**out, "differences": confirmed, "proposed": len(proposals), "not_confirmed": rejected}
    return {"character": character, "pages": pages, **out}


def _crop(png_path: str, bbox: list[int], out: Path, blank: list[list[int]] | None = None) -> Path:
    """Figure crop (with a small margin). `blank`: boxes of OTHER figures inside this box,
    painted white, so a crop of a tall figure with someone standing in front of him shows
    him alone (the model otherwise "recognises" whoever is visible in the crop)."""
    import pymupdf
    pm = pymupdf.Pixmap(png_path)
    if pm.alpha:
        pm = pymupdf.Pixmap(pm, 0)
    mx, my = (bbox[2] - bbox[0]) * 0.08, (bbox[3] - bbox[1]) * 0.08
    rect = pymupdf.IRect(max(0, int((bbox[0] - mx) / 1000 * pm.width)), max(0, int((bbox[1] - my) / 1000 * pm.height)),
                         min(pm.width, int((bbox[2] + mx) / 1000 * pm.width)),
                         min(pm.height, int((bbox[3] + my) / 1000 * pm.height)))
    for b in blank or []:
        r = pymupdf.IRect(int(b[0] / 1000 * pm.width), int(b[1] / 1000 * pm.height),
                          int(b[2] / 1000 * pm.width), int(b[3] / 1000 * pm.height)) & rect
        if not r.is_empty:
            pm.set_rect(r, (255,) * pm.n)
    sub = pymupdf.Pixmap(pm.colorspace, rect, 0)
    sub.copy(pm, rect)
    out.parent.mkdir(parents=True, exist_ok=True)
    sub.save(str(out))
    return out


def _kinds_clash(a: str | None, b: str | None) -> bool:
    """Two characters can be mistaken for each other in a picture only if they are the same
    kind of being. A child and an old man are both human but not rivals; an unknown kind
    may clash with anything."""
    known = set(GATE) | {"HUMAN_CHILD", "HUMAN_ADULT"}
    return a not in known or b not in known or a == b


GATE = {"HUMAN_CHILD": "H", "HUMAN_ADULT": "H", "ANIMAL": "A", "ROBOT_OR_MACHINE": "R",
        "FANTASY_CREATURE": "F"}            # OTHER / UNKNOWN: no gate (compatible with anything)


def _compatible(kind_a: str | None, kind_b: str | None) -> bool:
    ga, gb = GATE.get(kind_a or ""), GATE.get(kind_b or "")
    return ga is None or gb is None or ga == gb


async def resolve_visual_identity(generation_id: str) -> dict:
    """Who a drawn figure is, decided by comparing CROPS: never by the scan's own guess
    (measured: scans swap children in group scenes), never by box numbers on a full page
    (measured: the model mixes them up), never by the scan's idea of a figure's kind
    (measured: robot -> ANIMAL, cat -> HUMAN_CHILD). Idempotent: it reads scans and text,
    not its own earlier output.

    1. Reference candidates. A deep-scanned, non-front-matter figure whose name is in the
       text on/next to its page and maps to exactly one text character C; no other figure
       on the page is unnamed or named as a character of C's kind group; the near text names
       no other character of C's exact kind (a rival). The crop must cover >= 2% of the page.
       A rival the text puts in another class (sex, age band) is no rival, provided the crop
       itself shows the figure in C's class. Each candidate crop is CHECKED (one whole figure?
       of C's kind group? of C's declared sex/age?). The largest accepted crop is C's reference.
    2. Every other figure's crop is compared with all references: same kind, no conflicting
       distinctive feature, confidence >= 0.8. On a page a character is at most one figure.
    3. Elimination: if a page shows N figures of one kind, the near text names exactly N
       characters of that kind, and N-1 are already identified, the last figure is the last
       character (confidence 0.8; never used as a reference).
    Everything else stays uncertain and unattached."""
    chars = db.all_rows("SELECT id, canonical_name, aliases, kind, traits FROM character WHERE generation_id=%s "
                        "AND COALESCE(traits->>'entity_scope','INDIVIDUAL')='INDIVIDUAL'",
                        generation_id)
    figs = db.all_rows(
        "SELECT cm.id, cm.page_no, cm.surface_name, vr.bbox, (SELECT bool_or(s.pass='DEEP') FROM page_scan s"
        " WHERE s.generation_id=cm.generation_id AND s.page_no=cm.page_no) AS deep, EXISTS (SELECT 1 FROM"
        " page_role r WHERE r.generation_id=cm.generation_id AND r.page_no=cm.page_no AND"
        " r.role='FRONT_MATTER' AND r.source='editor') AS front FROM character_mention cm JOIN evidence e ON e.id=cm.evidence_id"
        " JOIN visual_region vr ON vr.id=e.region_id WHERE cm.generation_id=%s AND cm.via='VISUAL'"
        " ORDER BY cm.page_no, vr.id", generation_id)
    stats = {"figures": len(figs), "reference_candidates": 0, "references_refused": 0,
             "characters_with_reference": 0, "matched": 0, "by_elimination": 0,
             "scan_name_corrected": 0, "left_uncertain": 0, "calls_failed": 0,
             "references_refused_by_traits": 0}
    if not chars or not figs:
        return stats
    gen = db.one("SELECT book_version_id FROM generation WHERE id=%s", generation_id)
    bv = str(gen["book_version_id"])
    ckind = {str(ch["id"]): ch["kind"] for ch in chars}
    # what the TEXT declares about a character; "UNKNOWN" is not a value, it is silence
    ctrait = {str(ch["id"]): {a: v for a, v in (ch["traits"] or {}).items() if a in ("sex", "age_band") and v and v != "UNKNOWN"}
              for ch in chars}

    def separating(cid: str, rival: str) -> dict[str, str]:
        """Traits on which the text puts these two in different classes (empty: it does not)."""
        return {a: v for a, v in ctrait[cid].items() if ctrait[rival].get(a, v) != v}

    cname = {str(ch["id"]): ch["canonical_name"] for ch in chars}
    cnames = {str(ch["id"]): [ch["canonical_name"], *ch["aliases"]] for ch in chars}
    name_to: dict[str, set] = {}
    for cid, names in cnames.items():
        for n in names:
            name_to.setdefault(ledger.norm(n), set()).add(cid)
    unique = {n: next(iter(v)) for n, v in name_to.items() if len(v) == 1}
    with db.tx() as c:
        idx = ledger.PageIndex.load(c, generation_id)

    def near(page: int) -> str:
        return " ".join(idx.text.get(p, "") for p in (page - 1, page, page + 1))

    def named_near(page: int, cid: str) -> bool:
        t = near(page)
        return any(ledger.has_name(t, n) for n in cnames[cid])

    import pymupdf
    page_px: dict[int, tuple[int, int]] = {}
    for p in {f["page_no"] for f in figs}:
        pm_ = pymupdf.Pixmap(render_page(bv, p)["path"])
        page_px[p] = (pm_.width, pm_.height)
    by_page: dict[int, list] = {}
    for f in figs:
        f["cid"] = unique.get(ledger.norm(f["surface_name"] or ""))          # the scan's claim
        f["area"] = max(0, f["bbox"][2] - f["bbox"][0]) * max(0, f["bbox"][3] - f["bbox"][1]) / 1e6
        # what makes a reference usable is how many pixels show the figure (a cat is small on
        # the page and still perfectly drawn), measured on the rendered page
        f["short_px"] = min((f["bbox"][2] - f["bbox"][0]) / 1000 * page_px[f["page_no"]][0],
                            (f["bbox"][3] - f["bbox"][1]) / 1000 * page_px[f["page_no"]][1])
        by_page.setdefault(f["page_no"], []).append(f)

    def holds(a: list[int], b: list[int]) -> bool:
        """Is at least half of box b inside box a?"""
        w = min(a[2], b[2]) - max(a[0], b[0])
        h = min(a[3], b[3]) - max(a[1], b[1])
        area_b = max(1, (b[2] - b[0]) * (b[3] - b[1]))
        return w > 0 and h > 0 and w * h / area_b >= 0.5

    # Where two boxes overlap, the overlap shows the SMALLER figure (a child in front of a tall
    # adult; measured: a professor's box whose overlap showed a girl's face was matched to the
    # girl). So in the larger box's crop the smaller figure's part is blanked, whatever the size
    # of the overlap. If blanking leaves less than half of the box, or two boxes cover each
    # other, the crop cannot show this figure alone (a "group": neither reference nor matched).
    def area(b: list[int]) -> int:
        return max(1, (b[2] - b[0]) * (b[3] - b[1]))

    def overlap(a: list[int], b: list[int]) -> int:
        return max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))

    for fs in by_page.values():
        for f in fs:
            same = any(g is not f and holds(f["bbox"], g["bbox"]) and holds(g["bbox"], f["bbox"]) for g in fs)
            smaller = [g["bbox"] for g in fs if g is not f and area(g["bbox"]) < area(f["bbox"])
                       and overlap(f["bbox"], g["bbox"]) > 0]
            f["blank"] = smaller
            # (overlaps of the blanked boxes with each other are counted twice: errs towards "group")
            f["group"] = same or sum(overlap(f["bbox"], b) for b in smaller) / area(f["bbox"]) > 0.5
    stats["group_crops"] = sum(1 for f in figs if f["group"])
    gdir = Path(render_page(bv, figs[0]["page_no"])["path"]).parent / "gallery" / generation_id
    sem = asyncio.Semaphore(settings().deep_concurrency * 2)
    crops: dict[str, Path] = {}

    def crop_of(f: dict) -> Path:
        k = str(f["id"])
        if k not in crops:
            crops[k] = _crop(render_page(bv, f["page_no"])["path"], f["bbox"], gdir / f"fig-{k}.png", f.get("blank"))
        return crops[k]

    # ---- 1. reference candidates, each checked on its crop
    cands = []
    for page, fs in by_page.items():
        for f in fs:
            cid = f["cid"]
            if not (cid and not f["group"] and f["deep"] and not f["front"]
                    and f["short_px"] >= settings().min_reference_px
                    and named_near(page, cid)):
                continue
            others_here = [x for x in fs if x is not f]
            if any(x["cid"] is None for x in others_here):
                continue                       # a figure nobody could name might be anyone
            # A rival is another character of the same kind that could be this figure: one drawn
            # on the page, or one named in the text. For a lone figure only the page's own text
            # counts (a name in someone's speech next door is not a second person in this
            # picture); in a group scene the facing pages count too.
            here = idx.text.get(page, "")
            rivals = {x["cid"] for x in others_here if _kinds_clash(ckind[x["cid"]], ckind[cid])}
            rivals |= {o for o in cname if o != cid and _kinds_clash(ckind[o], ckind[cid]) and (
                any(ledger.has_name(here, n) for n in cnames[o]) if not others_here else named_near(page, o))}
            # A rival the text puts in another class (the mother is not the grandfather) is no
            # rival, as long as the drawing itself shows this figure in THIS character's class.
            need: dict[str, str] = {}
            for o in rivals - {cid}:
                sep = separating(cid, o)
                if not sep:
                    break
                need.update(sep)
            else:
                cands.append((f, cid, need))
    stats["reference_candidates"] = len(cands)

    async def check(f: dict, cid: str, need: dict[str, str] | None = None):
        ref, body = prompts.render("check_reference", name=cname[cid])
        try:
            async with sem:
                out, _ = await Llm(generation_id).chat(
                    "book-vision-deep", [{"role": "user", "content": [
                        image_part(crop_of(f).read_bytes()), {"type": "text", "text": body}]}],
                    prompt=ref, schema=schemas.CHECK_REFERENCE, pages=[f["page_no"]], max_tokens=4096,
                    temperature=0.0)
            if out and need and any(out.get(a) != v for a, v in need.items()):
                out = None          # the drawing does not show the class the text declared
                stats["references_refused_by_traits"] = stats.get("references_refused_by_traits", 0) + 1
            return f, cid, out
        except Exception:  # noqa: BLE001
            stats["calls_failed"] += 1
            return f, cid, None

    gallery: dict[str, dict] = {}
    accepted: list[tuple[dict, str]] = []
    for f, cid, out in await asyncio.gather(*(check(f, cid, need) for f, cid, need in cands)):
        if out and out["whole_figure"] and _compatible(out["kind"], ckind[cid]):
            f["kind"] = out["kind"]
            accepted.append((f, cid))
            if cid not in gallery or f["area"] > gallery[cid]["area"]:
                gallery[cid] = {"fig": f, "area": f["area"], "kind": out["kind"], "features": out["features"]}
        else:
            stats["references_refused"] += 1
    stats["characters_with_reference"] = len(gallery)
    anchored = {str(f["id"]): cid for f, cid in accepted}

    # ---- 2. crop-to-crop matching against references
    async def match(f: dict, refmap: dict[str, dict]):
        refs, best = list(refmap), None
        for k in range(0, len(refs), 5):                     # five references + the figure per request
            ids = {f"R{i + 1}": cid for i, cid in enumerate(refs[k:k + 5])}
            parts: list[dict] = []
            for rid, cid in ids.items():
                parts += [{"type": "text", "text": f"Referans {rid}: {cname[cid]}"},
                          image_part(crop_of(refmap[cid]["fig"]).read_bytes())]
            ref, body = prompts.render("match_figures", page_no=str(f["page_no"]),
                                       references=", ".join(f"{r} = {cname[c]}" for r, c in ids.items()))
            parts += [{"type": "text", "text": "FİGÜR:"}, image_part(crop_of(f).read_bytes()),
                      {"type": "text", "text": body}]
            try:
                async with sem:
                    out, _ = await Llm(generation_id).chat(
                        "book-vision-deep", [{"role": "user", "content": parts}], prompt=ref,
                        schema=schemas.MATCH_FIGURE, pages=[f["page_no"]], max_tokens=6144, temperature=0.0)
            except Exception:  # noqa: BLE001
                stats["calls_failed"] += 1
                continue
            cid = ids.get(out["reference"])
            # the verdict is the model's: it answers NONE when a distinctive feature conflicts
            if cid and out["figure_is_whole"] and out["same_kind"] and out["confidence"] >= 0.8 \
                    and (best is None or out["confidence"] > best[1]["confidence"]):
                best = (cid, out)
        return f, best

    resolved: dict[str, tuple[str, str, dict | None]] = {str(f["id"]): (cid, "anchor", None) for f, cid in accepted}
    ref_pages = {(f["page_no"], cid) for f, cid in accepted}

    async def match_round(refmap: dict[str, dict]) -> None:
        todo = [f for f in figs if str(f["id"]) not in resolved and f["area"] > 0 and not f["group"]]
        per_page: dict[tuple[int, str], tuple] = {}
        for f, best in await asyncio.gather(*(match(f, refmap) for f in todo)):
            taken_here = {(g["page_no"], resolved[str(g["id"])][0]) for g in figs if str(g["id"]) in resolved}
            if best and (f["page_no"], best[0]) not in ref_pages | taken_here:
                key = (f["page_no"], best[0])                # a character is one figure per page
                if key not in per_page or best[1]["confidence"] > per_page[key][1][1]["confidence"]:
                    per_page[key] = (f, best)
        for f, best in per_page.values():
            resolved[str(f["id"])] = (best[0], "reference", best[1])

    def eliminate() -> int:
        """The scan's SET of names on a page is usually right even when it swaps who is who.
        If every figure of a kind group is named, the names are distinct, and all but one
        figure are identified as members of that set, the last figure is the last name."""
        n = 0
        for page, fs in by_page.items():
            def who(f: dict) -> str | None:                  # identified beats the scan's guess
                return resolved[str(f["id"])][0] if str(f["id"]) in resolved else f["cid"]
            groups: dict[str, list] = {}
            for f in fs:
                if who(f):
                    groups.setdefault(ckind[who(f)], []).append(f)
            for kind, same in groups.items():
                # a figure nobody could name or identify might be of this kind too
                if kind not in GATE or any(who(f) is None and not f["group"] for f in fs):
                    continue
                names = {who(f) for f in same}
                if len(same) < 2 or len(names) != len(same):
                    continue
                open_figs = [f for f in same if str(f["id"]) not in resolved]
                left = {f["cid"] for f in open_figs}
                if len(open_figs) == 1 and len(left) == 1 and not open_figs[0]["group"]:
                    resolved[str(open_figs[0]["id"])] = (next(iter(left)), "elimination", None)
                    n += 1
        return n

    if gallery:
        await match_round(gallery)
    stats["by_elimination"] = eliminate()
    # ---- 3. a character found by elimination on two pages, whose two crops match each other,
    #         earns a reference; then one more round for the figures still open
    promoted: dict[str, dict] = {}
    by_char: dict[str, list] = {}
    for f in figs:
        got = resolved.get(str(f["id"]))
        if got and got[1] == "elimination" and got[0] not in gallery and not f["group"] \
                and f["short_px"] >= settings().min_reference_px:
            by_char.setdefault(got[0], []).append(f)
    for cid, fs in by_char.items():
        fs.sort(key=lambda f: -f["area"])
        if len(fs) >= 2:
            _, best = await match(fs[1], {cid: {"fig": fs[0]}})
            if best and best[1]["confidence"] >= 0.9:
                promoted[cid] = {"fig": fs[0], "area": fs[0]["area"], "features": best[1]["matching_features"]}
    stats["references_promoted"] = [cname[c_] for c_ in promoted]
    if promoted:
        await match_round(promoted)
        stats["by_elimination"] += eliminate()
    gallery.update(promoted)
    # ---- 4. a character who is never drawn without a rival nearby has no reference by rule 1.
    #         Independent agreement replaces it: the scan named figures as this character on
    #         three or more pages (each time with the name in the near text), the largest of
    #         them is one whole figure of the right kind, and at least two of the others match
    #         it crop to crop. Those figures are the character; the largest becomes the reference.
    consistent: dict[str, dict] = {}
    trace: dict[str, dict] = {}
    for cid in cname:
        if cid in gallery:
            continue
        taken = {(g["page_no"], resolved[str(g["id"])][0]) for g in figs if str(g["id"]) in resolved}
        own = sorted((f for f in figs if f["cid"] == cid and str(f["id"]) not in resolved and not f["group"]
                      and f["deep"] and not f["front"] and f["short_px"] >= settings().min_reference_px
                      and named_near(f["page_no"], cid) and (f["page_no"], cid) not in taken),
                     key=lambda f: -f["area"])
        own = list({f["page_no"]: f for f in reversed(own)}.values())[::-1]      # largest per page
        named = [f for f in figs if f["cid"] == cid]
        why = trace[cname[cid]] = {"scan_named_pages": sorted({f["page_no"] for f in named}),
                                   "group_crops": sorted({f["page_no"] for f in named if f["group"]}),
                                   "too_small": sorted({f["page_no"] for f in named
                                                        if f["short_px"] < settings().min_reference_px}),
                                   "eligible_pages": [f["page_no"] for f in own]}
        if len(own) < 3:
            why["outcome"] = "fewer than 3 eligible pages"
            continue
        _, _, chk = await check(own[0], cid)
        if not (chk and chk["whole_figure"] and _compatible(chk["kind"], ckind[cid])):
            stats["references_refused"] += 1
            why["outcome"] = f"largest crop refused: {chk}"
            continue
        agree = [(f, best) for f, best in await asyncio.gather(
            *(match(f, {cid: {"fig": own[0]}}) for f in own[1:])) if best and best[1]["confidence"] >= 0.9]
        why["agreeing_pages"] = [f["page_no"] for f, _ in agree]
        if len(agree) < 2:
            why["outcome"] = "fewer than 2 other pages match the largest crop"
            continue
        why["outcome"] = "reference by consistency"
        own[0]["kind"] = chk["kind"]
        consistent[cid] = {"fig": own[0], "area": own[0]["area"], "kind": chk["kind"], "features": chk["features"]}
        resolved[str(own[0]["id"])] = (cid, "consistency", None)
        for f, best in agree:
            resolved[str(f["id"])] = (cid, "consistency", best[1])
    stats["references_by_consistency"] = [cname[c_] for c_ in consistent]
    stats["without_reference_why"] = trace
    if consistent:
        await match_round(consistent)
        stats["by_elimination"] += eliminate()
    gallery.update(consistent)

    with db.tx() as c:
        # start clean (idempotent): a RESOLVED row may not lose its character alone
        c.execute("UPDATE character_mention SET character_id=NULL, resolution='UNCERTAIN', appearance ="
                  " appearance - 'identified_by' - 'is_reference' - 'matching_features' - 'match_reason'"
                  " WHERE generation_id=%s AND via='VISUAL'", (generation_id,))
        for f in figs:
            got = resolved.get(str(f["id"]))
            if not got:
                stats["left_uncertain"] += 1
                c.execute("UPDATE character_mention SET character_id=NULL, resolution='UNCERTAIN',"
                          " confidence=LEAST(confidence, 0.6) WHERE id=%s", (f["id"],))
                continue
            cid, how, out = got
            if how == "reference":
                stats["matched"] += 1
            stats["scan_name_corrected"] += bool(f["cid"] and f["cid"] != cid)
            conf = 0.95 if how == "anchor" else 0.8 if how == "elimination" else 0.85 if how == "consistency" \
                else min(float(out["confidence"]), 0.95)
            extra = {"identified_by": how, "scan_name": f["surface_name"]}
            if how == "anchor":
                extra["is_reference"] = gallery[cid]["fig"]["id"] == f["id"]
            elif cid in gallery and gallery[cid]["fig"]["id"] == f["id"]:
                extra["is_reference"] = True             # promoted after elimination or by consistency
            if out:
                extra.update(matching_features=out["matching_features"][:8], match_reason=out["reason"][:400])
            c.execute("UPDATE character_mention SET character_id=%s, resolution='RESOLVED', confidence=%s,"
                      " appearance = appearance || %s WHERE id=%s", (cid, conf, db.J(extra), f["id"]))
        for ch in chars:
            # Appearance profile from figures that are surely this character. The scan's text for
            # a box is kept only where the scan's own name agreed (its box/label pairing slips:
            # a box labelled as the professor held the girl); otherwise what the matcher saw.
            obs = c.execute("SELECT page_no, appearance FROM character_mention WHERE character_id=%s AND"
                            " via='VISUAL' AND resolution='RESOLVED' ORDER BY page_no", (ch["id"],)).fetchall()
            rows = []
            for o in obs:
                a = o["appearance"]
                agreed = unique.get(ledger.norm(a.get("scan_name") or "")) == str(ch["id"])
                if a.get("identified_by") == "anchor" or agreed:
                    rows.append({"page": o["page_no"], "by": a.get("identified_by"),
                                 **{k: v for k, v in a.items() if k in ("hair", "skin", "age_look", "clothes",
                                                                        "colors", "distinctive")}})
                else:
                    rows.append({"page": o["page_no"], "by": a.get("identified_by"),
                                 "seen": a.get("matching_features") or []})
            c.execute("UPDATE character SET appearance=%s WHERE id=%s",
                      (db.J({"reference_features": (gallery.get(str(ch["id"])) or {}).get("features", []),
                             "observations": rows}), ch["id"]))
    stats["characters_without_reference"] = [cname[c_] for c_ in cname if c_ not in gallery]
    return stats


async def scan_pages(generation_id: str, pages: list[int], depth: str, concurrency: int,
                     on_done=None) -> list[dict]:
    sem = asyncio.Semaphore(concurrency)

    async def one(p: int) -> dict:
        async with sem:
            r = await analyze_page_visual(generation_id, p, depth)
            if on_done:
                on_done(r)
            return r

    return await asyncio.gather(*(one(p) for p in pages))
