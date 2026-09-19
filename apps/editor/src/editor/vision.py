"""book_vision tools. book-vision-fast scans every page; pages it marks
uncertain (identity, text-visual mismatch, unclear scene, important event) go to
book-vision-deep (NIHAI-KARAR.md §5 steps 5-6, §6)."""

from __future__ import annotations

import asyncio
import json
import re
from collections import Counter
from pathlib import Path

from . import db, ledger, prompts, schemas
from .config import settings
from .document import page_text_numbered, region_ink_ratio, render_page
from .llm import Llm, image_part

_NAME = re.compile(r"\b([A-ZÇĞİÖŞÜ][a-zçğıöşü]{2,})\b")
_STOP = {"Bir", "Bu", "Şu", "Ama", "Ve", "Ben", "Sen", "Biz", "Siz", "Onlar", "Evet", "Hayır",
         "Belki", "Hem", "Sonra", "Şimdi", "Neden", "Nasıl", "Ne", "Tamam", "Hadi", "Çünkü",
         "Aa", "Oh", "Of", "Peki", "Eğer", "Bugün", "Yarın", "Dün", "Hey", "Merhaba", "Haydi",
         "Ancak", "Oysa", "Bütün", "Her", "Hiç", "Kim", "Sanki", "Yine", "Artık", "Birden"}


EMPTY_SCAN = {"scene": {"setting": "", "time_of_day": "", "mood": "", "description": ""},
              "characters": [], "objects": [], "text_in_image": [], "text_visual_checks": [],
              "important_event": False, "uncertain": False, "uncertainty_reasons": []}


def known_names(generation_id: str) -> list[str]:
    """Capitalised words that recur mid-sentence in the book text: a hint list
    for the scanner, not a claim."""
    c: Counter = Counter()
    for r in db.all_rows("SELECT text FROM paragraph WHERE generation_id=%s", generation_id):
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
        if any(not chk["consistent"] for chk in out["text_visual_checks"]):
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
    """Best scan -> visual regions, visual character mentions, scene claim,
    text-visual candidate findings. Idempotent per page."""
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
        mentions = mismatches = unseen = 0
        png_path = render_page(str(c.execute("SELECT book_version_id FROM generation WHERE id=%s",
                                             (generation_id,)).fetchone()["book_version_id"]), page_no)["path"]
        front = c.execute("SELECT 1 FROM page_role WHERE generation_id=%s AND page_no=%s AND"
                          " role='FRONT_MATTER'", (generation_id, page_no)).fetchone() is not None
        near_text = " ".join(idx.text.get(p, "") for p in (page_no - 1, page_no, page_no + 1))
        for ch in res["characters"]:
            # A figure is a visual claim: its box must actually contain ink.
            if region_ink_ratio(png_path, ch["bbox"]) < settings().min_figure_ink:
                unseen += 1
                continue
            # A name needs a basis in the story text on or next to this page. Cover and
            # other front-matter art has no narrative text, so its figures stay unnamed
            # candidates; so do names the fast pass gives (it guesses from the hint list).
            named_here = bool(ch["name"]) and ledger.norm(ch["name"]) in near_text
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
        # "Görsel-metinsel uyuşmazlık doğrudan hata değil, aday bulgu olur."
        for chk in res["text_visual_checks"]:
            if chk["consistent"]:
                continue
            evs = []
            if chk["text_quote"].strip():
                ev_t = ledger.save_evidence(c, generation_id, idx, page=page_no, kind="TEXT",
                                            paragraph_idx=chk["paragraph"] or None,
                                            quote=chk["text_quote"])
                evs.append((ev_t[0], ev_t[1], page_no))
            obs = (chk["visual_observation"] or chk["note"]).strip()
            if obs:
                ev_v = ledger.save_evidence(c, generation_id, idx, page=page_no, kind="VISUAL", quote=obs)
                evs.append((ev_v[0], ev_v[1], page_no))
            claim_id = ledger.save_claim(
                c, generation_id, kind="TEXT_VISUAL_MISMATCH", subject=f"sayfa {page_no}",
                claim=f"Metin: “{chk['text_quote']}” — Görsel: {chk['visual_observation']}. {chk['note']}",
                evidence=evs,
                confidence=chk["confidence"], created_by=created_by, model_call_id=call_id)
            c.execute(
                "INSERT INTO contradiction(generation_id, kind, description, pages, claim_ids,"
                " confidence) VALUES (%s,'TEXT_VISUAL',%s,%s,%s,%s) RETURNING id",
                (generation_id, chk["note"] or chk["visual_observation"], [page_no],
                 [claim_id] if claim_id else [], chk["confidence"])).fetchone()
            mismatches += 1
    return {"page_no": page_no, "pass": pass_, "visual_mentions": mentions,
            "text_visual_candidates": mismatches, "figures_dropped_unseen": unseen}


async def check_text_visual_consistency(generation_id: str, page_no: int) -> dict:
    s = await _ensure_scan(generation_id, page_no)
    persist_page_visual(generation_id, page_no)
    checks = s["result"]["text_visual_checks"]
    return {"page_no": page_no, "pass": s["pass"],
            "candidates": [c for c in checks if not c["consistent"]],
            "consistent": sum(1 for c in checks if c["consistent"])}


async def compare_character_appearances(generation_id: str, character: str,
                                        pages: list[int]) -> dict:
    """Deep model looks at up to 6 pages of one character; differences become
    VISUAL_CONTINUITY claims and CONTINUITY contradiction candidates."""
    pages = sorted(set(pages))[:6]
    gen = db.one("SELECT book_version_id FROM generation WHERE id=%s", generation_id)
    parts = []
    for p in pages:
        png = Path(render_page(str(gen["book_version_id"]), p, 1200)["path"]).read_bytes()
        parts += [{"type": "text", "text": f"Sayfa {p}:"}, image_part(png)]
    known = []
    for r in db.all_rows("SELECT page_no, appearance FROM character_mention cm WHERE generation_id=%s"
                         " AND (surface_name ILIKE %s OR character_id IN (SELECT id FROM character"
                         " WHERE generation_id=%s AND (canonical_name ILIKE %s OR %s = ANY(aliases))))"
                         " ORDER BY page_no LIMIT 30", generation_id, character, generation_id,
                         character, character):
        known.append(f"s{r['page_no']}: {json.dumps(r['appearance'], ensure_ascii=False)}")
    ref, body = prompts.render("compare_appearance", pages=", ".join(map(str, pages)),
                               character=character, known="\n".join(known) or "-")
    out, call_id = await Llm(generation_id).chat(
        "book-vision-deep", [{"role": "user", "content": parts + [{"type": "text", "text": body}]}],
        prompt=ref, schema=schemas.APPEARANCE, pages=pages, max_tokens=16384, temperature=0.1)
    with db.tx() as c:
        idx = ledger.PageIndex.load(c, generation_id)
        for d in out["differences"]:
            evs = [(*ledger.save_evidence(c, generation_id, idx, page=p, kind="VISUAL",
                                          quote=f"{character} — {d['attribute']}: {d['description']}"), p)
                   for p in d["pages"] if p in pages]
            if not evs:
                continue
            cid = ledger.save_claim(
                c, generation_id, kind="VISUAL_CONTINUITY", subject=character,
                claim=f"{character}: {d['attribute']} sayfalar arasında farklı — {d['description']}",
                evidence=evs, confidence=d["confidence"], created_by="vision:deep",
                payload={"explained_by_story": d["explained_by_story"]}, model_call_id=call_id)
            if d["continuity_candidate"] and not d["explained_by_story"]:
                c.execute("INSERT INTO contradiction(generation_id, kind, description, pages,"
                          " claim_ids, confidence) VALUES (%s,'CONTINUITY',%s,%s,%s,%s)",
                          (generation_id, f"{character}: {d['description']}", d["pages"],
                           [cid] if cid else [], d["confidence"]))
    return {"character": character, "pages": pages, **out}


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
