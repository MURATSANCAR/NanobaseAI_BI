"""book_quality tools: Critic Agent pass, claim validation, confidence,
editor queue, regression suite, analysis report (NIHAI-KARAR.md §5 13-15, §7)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import yaml

from . import db, ledger, prompts, schemas
from .config import settings
from .knowledge import DIRECTOR, _valid_pages, build_timeline, chapters
from .llm import Llm

REGRESSION_DIR = Path(__file__).resolve().parent.parent.parent / "tests" / "regression"
REVIEW_CONFIDENCE = 0.55          # below this a claim that survives the critic goes to the editor
CRITIC_FACTOR = {"SUPPORTED": 1.0, "PARTIAL": 0.6, "UNSUPPORTED": 0.1, None: 0.8}


# --------------------------------------------------------- confidence
def _claim_facts(c, claim_id: str) -> dict:
    cl = c.execute("SELECT * FROM claim WHERE id=%s", (claim_id,)).fetchone()
    if cl is None:
        raise KeyError(f"claim {claim_id} not found")
    ev = c.execute("SELECT e.kind, e.page_no, e.quote, e.quote_verified FROM claim_evidence ce JOIN"
                   " evidence e ON e.id=ce.evidence_id WHERE ce.claim_id=%s", (claim_id,)).fetchall()
    return {"claim": cl, "evidence": ev}


def confidence_from(model_conf: float, evidence: list[dict], critic: str | None) -> dict:
    """Documented formula (UYGULAMA-NOTLARI.md):
    conf = model * (0.5 + 0.5*verified_ratio) * critic_factor
           + min(0.10, 0.03*(pages-1)) + 0.05 if both text and visual evidence."""
    if not evidence:
        return {"confidence": 0.0, "parts": {"reason": "no evidence"}}
    text_ev = [e for e in evidence if e["kind"] != "VISUAL"]
    verified = sum(1 for e in text_ev if e["quote_verified"]) / len(text_ev) if text_ev else 0.7
    pages = len({e["page_no"] for e in evidence})
    cross = 0.05 if {e["kind"] for e in evidence} >= {"TEXT", "VISUAL"} else 0.0
    conf = model_conf * (0.5 + 0.5 * verified) * CRITIC_FACTOR.get(critic, 0.8) \
        + min(0.10, 0.03 * (pages - 1)) + cross
    conf = max(0.0, min(1.0, conf))
    return {"confidence": round(conf, 3), "parts": {"model": model_conf, "verified_ratio": round(verified, 2),
                                                     "pages": pages, "critic": critic, "cross_modal": cross}}


def calculate_confidence(claim_id: str) -> dict:
    with db.tx() as c:
        f = _claim_facts(c, claim_id)
    critic = (f["claim"]["payload"] or {}).get("critic")
    return {"claim_id": claim_id, **confidence_from(float(f["claim"]["confidence"]), f["evidence"], critic)}


# ---------------------------------------------------------- validation
def validate_claim(generation_id: str, claim: dict | None = None, claim_id: str | None = None) -> dict:
    """Checks a claim in the §7 shape ({claim, source_pages, evidence, confidence,
    status, needs_editor_review}) or a stored claim, against the quality rules."""
    problems: list[str] = []
    with db.tx() as c:
        pages = _valid_pages(c, generation_id)
        idx = ledger.PageIndex.load(c, generation_id)
        if claim_id:
            f = _claim_facts(c, claim_id)
            cl = f["claim"]
            claim = {"claim": cl["claim"], "source_pages": cl["source_pages"], "confidence": cl["confidence"],
                     "status": cl["status"], "needs_editor_review": cl["needs_editor_review"],
                     "evidence": [{"page": e["page_no"], "quote": e["quote"], "verified": e["quote_verified"],
                                   "kind": e["kind"]} for e in f["evidence"]],
                     "kind": cl["kind"], "payload": cl["payload"]}
        assert claim is not None
        for k in ("claim", "source_pages", "evidence", "confidence", "status", "needs_editor_review"):
            if k not in claim:
                problems.append(f"alan eksik: {k}")
        ev = claim.get("evidence") or []
        if isinstance(ev, str):
            ev = [{"page": p, "quote": ev} for p in claim.get("source_pages") or []]
        if not ev:
            problems.append("Kaynaksız iddia üretilemez: kanıt yok")
        for p in claim.get("source_pages") or []:
            if p not in pages:
                problems.append(f"sayfa {p} kitapta yok")
        verified = 0
        for e in ev:
            ok = e.get("verified")
            if ok is None:
                ok = idx.verify(int(e.get("page") or 0), e.get("quote", ""), e.get("kind", "TEXT"))
            verified += bool(ok)
            if not ok and e.get("kind", "TEXT") == "TEXT":
                problems.append(f"alıntı sayfa {e.get('page')} metninde bulunamadı: “{e.get('quote', '')[:80]}”")
        conf = float(claim.get("confidence") or 0)
        if not 0 <= conf <= 1:
            problems.append("güven 0-1 arasında olmalı")
        payload = claim.get("payload") or {}
        if claim.get("kind") == "EVENT" and payload.get("modality") not in (None, "REALIZED", "MEMORY") \
                and "gerçekleşti" in claim["claim"].lower():
            problems.append("Plan/hayal/şaka gerçekleşmiş olay gibi yazılmış")
        if claim.get("kind") == "CHARACTER_IDENTITY" and payload.get("identity_status") == "CONFIRMED" \
                and conf < 0.85:
            problems.append("Belirsiz karakter kesin kimlik olarak kaydedilemez (güven < 0.85)")
    needs_review = bool(problems) or conf < REVIEW_CONFIDENCE
    return {"valid": not problems, "problems": problems, "evidence_verified": f"{verified}/{len(ev)}",
            "needs_editor_review": needs_review}


def send_to_editor_queue(generation_id: str, reason: str, claim_id: str | None = None,
                         contradiction_id: str | None = None, priority: int = 2) -> dict:
    if not claim_id and not contradiction_id:
        raise ValueError("claim_id ya da contradiction_id gerekli")
    with db.tx() as c:
        rid = ledger.queue_review(c, generation_id, reason=reason, claim_id=claim_id,
                                  contradiction_id=contradiction_id, priority=priority)
    return {"review_item_id": rid, "status": "OPEN"}


# -------------------------------------------------------------- critic
_CLAIM_SQL = ("SELECT c.id, c.kind, c.subject, c.claim, c.confidence, c.payload, c.source_pages,"
              " (SELECT json_agg(json_build_object('id', e.id, 'page', e.page_no, 'kind', e.kind,"
              " 'quote', e.quote, 'verified', e.quote_verified)) FROM claim_evidence ce JOIN evidence e"
              " ON e.id=ce.evidence_id WHERE ce.claim_id=c.id) AS ev FROM claim c WHERE ")


async def _judge(generation_id: str, claims: list[dict], batch: int = 30) -> list[tuple[dict, dict]]:
    """Critic verdict per claim, from the claim's own evidence only."""
    async def run(chunk: list[dict]) -> list[tuple[dict, dict]]:
        short = {f"c{i}": x for i, x in enumerate(chunk)}
        lines = [f"{k} [{x['kind']}{'/' + x['payload'].get('modality') if x['payload'].get('modality') else ''}]"
                 f" İDDİA: {x['claim']}\n   KANITLAR: " + " | ".join(
                     f"s{e['page']} ({e['kind']}{'' if e['verified'] else ', alıntı metinde yok'}): “{e['quote']}”"
                     for e in (x["ev"] or [])) for k, x in short.items()]
        ref, body = prompts.render("critic", claims="\n".join(lines))
        out, _ = await Llm(generation_id).chat(DIRECTOR, [{"role": "user", "content": body}],
                                               prompt=ref, schema=schemas.CRITIC, max_tokens=8000,
                                               temperature=0.0, thinking=False)
        seen, res = set(), []
        for v in out["verdicts"]:
            if v["claim_id"] in short and v["claim_id"] not in seen:
                seen.add(v["claim_id"])
                res.append((short[v["claim_id"]], v))
        return res

    parts = await asyncio.gather(*(run(claims[i:i + batch]) for i in range(0, len(claims), batch)))
    return [x for p in parts for x in p]


def _apply_verdict(c, generation_id: str, x: dict, v: dict, stats: dict) -> None:
    f = _claim_facts(c, str(x["id"]))
    conf = confidence_from(float(x["confidence"]), f["evidence"], v["supported"])["confidence"]
    note = f"{v['supported']}: {v['note']}"
    if v["supported"] == "UNSUPPORTED":
        status, review = "REJECTED", False
        stats["rejected"] += 1
    elif not v["modality_ok"] or not v["identity_ok"]:
        status, review = "NEEDS_REVIEW", True
    elif v["supported"] == "PARTIAL":
        status, review = "CANDIDATE", conf < REVIEW_CONFIDENCE
        stats["partial"] += 1
    else:
        status, review = "VERIFIED", conf < REVIEW_CONFIDENCE
        stats["verified"] += 1
    c.execute("UPDATE claim SET status=%s, confidence=%s, critic_note=%s, needs_editor_review=%s"
              " WHERE id=%s", (status, conf, note, review, x["id"]))
    if review:
        why = []
        if not v["modality_ok"]:
            why.append("kip (plan/hayal/şaka) gerçekleşmiş gibi")
        if not v["identity_ok"]:
            why.append("belirsiz kimlik kesin gibi")
        if conf < REVIEW_CONFIDENCE:
            why.append(f"düşük güven {conf:.2f}")
        ledger.queue_review(c, generation_id, claim_id=str(x["id"]),
                            priority=1 if not (v["modality_ok"] and v["identity_ok"]) else 3,
                            reason="Critic: " + "; ".join(why) + f" — {v['note']}")
        stats["to_review"] += 1


async def _repair(generation_id: str, x: dict, v: dict) -> str | None:
    """The application's own fix for a PARTIAL claim: find the missing evidence on the
    claim's pages, or narrow the claim to what its evidence says. Claims are immutable,
    so the repair is a new claim that supersedes the old one. Returns the new claim id."""
    from .document import page_text_numbered
    pages = sorted({p + d for p in x["source_pages"] for d in (-1, 0, 1) if p + d > 0})
    ref, body = prompts.render(
        "claim_repair", kind=x["kind"], claim=x["claim"], note=v["note"],
        evidence=" | ".join(f"s{e['page']}: “{e['quote']}”" for e in (x["ev"] or [])),
        pages_text="\n".join(page_text_numbered(generation_id, p) for p in pages))
    try:
        out, call_id = await Llm(generation_id).chat(DIRECTOR, [{"role": "user", "content": body}],
                                                     prompt=ref, schema=schemas.CLAIM_REPAIR,
                                                     pages=pages, max_tokens=3000, temperature=0.0,
                                                     thinking=False)
    except Exception:  # noqa: BLE001 - an unrepaired claim simply keeps its first verdict
        return None
    if out["action"] == "NONE":
        return None
    with db.tx() as c:
        idx = ledger.PageIndex.load(c, generation_id)
        added = [e for e in ledger.evidence_from_model(c, generation_id, idx, out["evidence"],
                                                       valid_pages=_valid_pages(c, generation_id))
                 if e[1]]                       # only quotes found verbatim on the page count
        text = out["claim"].strip() if out["action"] == "NARROW" and out["claim"].strip() else x["claim"]
        if not added and text == x["claim"]:
            return None                         # nothing actually changed
        old = [(str(e["id"]), e["verified"], e["page"]) for e in (x["ev"] or [])]
        new_id = ledger.save_claim(
            c, generation_id, kind=x["kind"], subject=x["subject"], claim=text, evidence=old + added,
            confidence=float(x["confidence"]), created_by="critic:repair", model_call_id=call_id,
            payload={**(x["payload"] or {}), "supersedes": str(x["id"]), "repair": out["action"]})
        c.execute("UPDATE claim SET status='SUPERSEDED', critic_note=%s WHERE id=%s",
                  (f"PARTIAL: {v['note']} → {out['action']}, yerine {new_id}", x["id"]))
        for table in ("event", "emotion", "character"):
            c.execute(f"UPDATE {table} SET claim_id=%s WHERE claim_id=%s", (new_id, x["id"]))
    return new_id


async def critic_pass(generation_id: str) -> dict:
    """Step 13. The Critic Agent re-reads every claim against its evidence only. What it
    finds PARTIAL the application first tries to repair itself (missing evidence added
    from the page, or the claim narrowed) and judges again; only what is still weak
    after that goes to the editor."""
    claims = db.all_rows(_CLAIM_SQL + "c.generation_id=%s AND c.status='CANDIDATE'", generation_id)
    stats = {"checked": 0, "verified": 0, "partial": 0, "rejected": 0, "to_review": 0,
             "repair_tried": 0, "repaired": 0, "no_verdict": 0}
    first = await _judge(generation_id, claims)
    stats["no_verdict"] = len(claims) - len(first)
    repairable = [(x, v) for x, v in first
                  if v["supported"] == "PARTIAL" and v["modality_ok"] and v["identity_ok"]]
    rep_ids = {str(x["id"]) for x, _ in repairable}
    with db.tx() as c:
        for x, v in first:
            stats["checked"] += 1
            if str(x["id"]) not in rep_ids:
                _apply_verdict(c, generation_id, x, v, stats)
    stats["repair_tried"] = len(repairable)
    new_ids = await asyncio.gather(*(_repair(generation_id, x, v) for x, v in repairable))
    fresh = [i for i in new_ids if i]
    stats["repaired"] = len(fresh)
    second = await _judge(generation_id, db.all_rows(_CLAIM_SQL + "c.id = ANY(%s::uuid[])", fresh)) \
        if fresh else []
    judged = {str(x["id"]) for x, _ in second}
    with db.tx() as c:
        for x, v in second:
            _apply_verdict(c, generation_id, x, v, stats)
        for (x, v), nid in zip(repairable, new_ids):
            if nid is None:                     # could not be repaired: first verdict stands
                _apply_verdict(c, generation_id, x, v, stats)
        for nid in fresh:
            if nid not in judged:
                ledger.queue_review(c, generation_id, claim_id=nid, priority=3,
                                    reason="Critic: onarılan iddia yeniden denetlenemedi")
    return stats


def contradictions_to_queue(generation_id: str, min_conf: float = 0.4) -> dict:
    """Step 14: contradiction candidates -> NEEDS_REVIEW in the editor queue."""
    n = 0
    with db.tx() as c:
        for x in c.execute("SELECT id, kind, description, pages, confidence FROM contradiction WHERE"
                           " generation_id=%s AND status='CANDIDATE' AND confidence >= %s",
                           (generation_id, min_conf)).fetchall():
            ledger.queue_review(c, generation_id, contradiction_id=str(x["id"]),
                                priority=1 if x["confidence"] >= 0.75 else 2,
                                reason=f"{x['kind']} aday çelişki (s{x['pages']}): {x['description']}")
            n += 1
    return {"queued": n}


# ----------------------------------------------------------- regression
def _check(name: str, ok: bool, detail: Any = None) -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


def _aliases_in_text(generation_id: str) -> bool:
    with db.tx() as c:
        text = " ".join(ledger.PageIndex.load(c, generation_id).text.values())
    return all(ledger.norm(n) in text for r in db.all_rows(
        "SELECT canonical_name, aliases FROM character WHERE generation_id=%s", generation_id)
        for n in [r["canonical_name"], *r["aliases"]])


def run_regression_suite(generation_id: str) -> dict:
    """Invariants of the quality rules + per-book golden expectations
    (tests/regression/books/<sha16>.yaml) + drift against the previous
    generation of the same content version."""
    one = lambda sql, *a: (db.one(sql, *a) or {}).get("n", 0)  # noqa: E731
    gen = db.one("SELECT g.*, bv.sha256, bv.book_id FROM generation g JOIN book_version bv ON"
                 " bv.id=g.book_version_id WHERE g.id=%s", generation_id)
    res = [
        _check("her iddianın kanıtı var", one("SELECT count(*) n FROM claim c WHERE generation_id=%s AND"
               " NOT EXISTS (SELECT 1 FROM claim_evidence ce WHERE ce.claim_id=c.id)", generation_id) == 0),
        _check("zaman çizelgesinde yalnız gerçekleşmiş olay", one(
            "SELECT count(*) n FROM event WHERE generation_id=%s AND story_order IS NOT NULL AND"
            " modality NOT IN ('REALIZED','MEMORY')", generation_id) == 0),
        _check("kesin kimlik güveni >= 0.85", one(
            "SELECT count(*) n FROM character WHERE generation_id=%s AND identity_status='CONFIRMED'"
            " AND identity_confidence < 0.85", generation_id) == 0),
        _check("çözülmüş anma güveni >= 0.75", one(
            "SELECT count(*) n FROM character_mention WHERE generation_id=%s AND resolution='RESOLVED'"
            " AND confidence < 0.75", generation_id) == 0),
        _check("görsel-metinsel uyuşmazlık aday, hata değil", one(
            "SELECT count(*) n FROM contradiction WHERE generation_id=%s AND status NOT IN"
            " ('CANDIDATE','NEEDS_REVIEW','EDITOR_CONFIRMED','EDITOR_DISMISSED')", generation_id) == 0),
        _check("her sayfa görsel taramadan geçti ya da resimsiz kaydedildi", one(
            "SELECT count(*) n FROM page p WHERE p.book_version_id=%s AND NOT EXISTS (SELECT 1 FROM"
            " page_scan s WHERE s.generation_id=%s AND s.page_no=p.page_no AND s.pass='FAST')",
            gen["book_version_id"], generation_id) == 0),
        _check("belirsiz sayfalar derin incelendi", one(
            "SELECT count(*) n FROM page_scan f WHERE f.generation_id=%s AND f.pass='FAST' AND"
            " f.uncertain AND NOT EXISTS (SELECT 1 FROM page_scan d WHERE d.generation_id=f.generation_id"
            " AND d.page_no=f.page_no AND d.pass='DEEP')", generation_id) == 0),
        _check("model kayıtlarında gerçek model ve sürüm var", one(
            "SELECT count(*) n FROM model_call WHERE generation_id=%s AND ok AND (revision IN ('?',"
            "'unknown') OR real_model='?')", generation_id) == 0),
        _check("prompt manifesti kayıtlı", bool(gen["prompt_manifest"])),
        # Self-checks for defects first seen in a real run; each one is a general
        # invariant, none names a book, a page or a character.
        _check("resimsiz sayfada görsel figür yok", one(
            "SELECT count(*) n FROM character_mention cm JOIN page p ON p.book_version_id=%s AND"
            " p.page_no=cm.page_no WHERE cm.generation_id=%s AND cm.via<>'TEXT' AND"
            " p.nontext_ink IS NOT NULL AND p.nontext_ink < %s",
            gen["book_version_id"], generation_id, settings().min_illustration_ink) == 0),
        _check("hikâye dışı sayfadan olay/duygu çıkarılmadı", one(
            "SELECT (SELECT count(*) FROM event e JOIN page_role r ON r.generation_id=e.generation_id AND"
            " r.page_no BETWEEN e.page_from AND e.page_to AND r.role<>'STORY' WHERE e.generation_id=%s)"
            " + (SELECT count(*) FROM emotion m JOIN page_role r ON r.generation_id=m.generation_id AND"
            " r.page_no=m.page_no AND r.role<>'STORY' WHERE m.generation_id=%s) AS n",
            generation_id, generation_id) == 0),
        _check("ön sayfa figürleri kesin kimlik almadı", one(
            "SELECT count(*) n FROM character_mention cm JOIN page_role r ON r.generation_id=cm.generation_id"
            " AND r.page_no=cm.page_no AND r.role='FRONT_MATTER' WHERE cm.generation_id=%s AND"
            " cm.via<>'TEXT' AND cm.resolution='RESOLVED'", generation_id) == 0),
        _check("hızlı taramanın verdiği ad tek başına kesin kimlik değil", one(
            "SELECT count(*) n FROM character_mention cm WHERE cm.generation_id=%s AND cm.via<>'TEXT' AND"
            " cm.resolution='RESOLVED' AND NOT EXISTS (SELECT 1 FROM page_scan d WHERE"
            " d.generation_id=cm.generation_id AND d.page_no=cm.page_no AND d.pass='DEEP')",
            generation_id) == 0),
        _check("her eş ad kitabın metninde geçiyor", _aliases_in_text(generation_id)),
        _check("kesin görsel kimlik yalnız çapa ya da referans eşleşmesiyle", one(
            "SELECT count(*) n FROM character_mention WHERE generation_id=%s AND via='VISUAL' AND"
            " resolution='RESOLVED' AND coalesce(appearance->>'identified_by','') NOT IN"
            " ('anchor','reference')", generation_id) == 0),
        _check("sınırına takılan model çağrısı kalmadı (her biri sonradan başarıldı)", one(
            "SELECT count(*) n FROM (SELECT prompt_name, pages, bool_or(ok) AS any_ok FROM model_call"
            " WHERE generation_id=%s GROUP BY 1,2) x WHERE NOT any_ok", generation_id) == 0),
    ]
    tv = db.one("SELECT count(*) FILTER (WHERE quote_verified) AS ok, count(*) AS n FROM evidence"
                " WHERE generation_id=%s AND kind='TEXT'", generation_id)
    ratio = (tv["ok"] / tv["n"]) if tv["n"] else 1.0
    res.append(_check("metin alıntılarının >= %80'i sayfada birebir", ratio >= 0.8,
                      f"{tv['ok']}/{tv['n']} = {ratio:.2f}"))
    prev = db.one("SELECT g.id FROM generation g WHERE g.book_version_id=%s AND g.id<>%s AND"
                  " g.sealed_at IS NOT NULL ORDER BY g.created_at DESC LIMIT 1",
                  gen["book_version_id"], generation_id)
    if prev:
        sealed = db.one("SELECT results FROM regression_run WHERE generation_id=%s ORDER BY created_at"
                        " DESC LIMIT 1", prev["id"])
        before = ((sealed or {}).get("results") or {}).get("counts", {}).get("claims")
        now_prev = one("SELECT count(*) n FROM claim WHERE generation_id=%s", prev["id"])
        res.append(_check("önceki nesil değişmedi", before is None or before == now_prev,
                          {"at_seal": before, "now": now_prev}))
    for corr in gen["corrections_applied"] or []:
        if corr["target_kind"] == "CHARACTER_IDENTITY":
            want = corr["correction"].get("canonical_name")
            ok = one("SELECT count(*) n FROM character WHERE generation_id=%s AND canonical_name=%s",
                     generation_id, want) > 0 if want else True
            res.append(_check(f"editör düzeltmesi uygulandı: {corr['target_key']}", ok))
    golden = REGRESSION_DIR / "books" / f"{gen['sha256'][:16]}.yaml"
    if golden.exists():
        g = yaml.safe_load(golden.read_text()) or {}
        names = {r["canonical_name"].casefold() for r in db.all_rows(
            "SELECT canonical_name FROM character WHERE generation_id=%s", generation_id)}
        aliases = {a.casefold() for r in db.all_rows("SELECT aliases FROM character WHERE generation_id=%s",
                                                     generation_id) for a in r["aliases"]}
        for want in g.get("characters", []):
            res.append(_check(f"altın: karakter {want}", want.casefold() in names | aliases))
        for e in g.get("events", []):
            hit = db.one("SELECT modality FROM event WHERE generation_id=%s AND merged_into IS NULL AND"
                         " summary ILIKE %s ORDER BY confidence DESC LIMIT 1", generation_id, f"%{e['contains']}%")
            res.append(_check(f"altın: olay '{e['contains']}' = {e['modality']}",
                              bool(hit) and hit["modality"] == e["modality"], hit))
    counts = {k: one(f"SELECT count(*) n FROM {t} WHERE generation_id=%s", generation_id) for k, t in
              (("claims", "claim"), ("evidence", "evidence"), ("characters", "character"),
               ("events", "event"), ("emotions", "emotion"), ("contradictions", "contradiction"),
               ("review_items", "review_item"), ("model_calls", "model_call"))}
    passed = all(r["passed"] for r in res)
    results = {"checks": res, "counts": counts, "golden_file": golden.name if golden.exists() else None}
    db.one("INSERT INTO regression_run(generation_id, suite, passed, results) VALUES (%s,%s,%s,%s)"
           " RETURNING id", generation_id, "quality-rules-v1", passed, db.J(results))
    return {"passed": passed, **results}


# --------------------------------------------------------------- report
def _cite(pages: list[int]) -> str:
    return "[" + ", ".join(f"s.{p}" for p in pages) + "]"


def create_analysis_report(generation_id: str, kind: str = "ANALYSIS",
                           sections: list[dict] | None = None) -> dict:
    """Builds the cited report from the ledger. `sections` (from a Hermes skill
    such as age_group_assessment) are validated claim by claim and saved as
    claims first; a section claim without verified evidence is refused."""
    saved = []
    if sections:
        with db.tx() as c:
            idx = ledger.PageIndex.load(c, generation_id)
            pages = _valid_pages(c, generation_id)
            claim_kind = {"AGE_GROUP": "AGE_GROUP", "PUBLISHER": "PUBLISHER_DECISION"}.get(kind, "ANSWER")
            for s in sections:
                for cl in s.get("claims", []):
                    for e in cl.get("evidence", []):
                        k = "VISUAL" if int(e.get("paragraph") or 0) == 0 else "TEXT"
                        if not idx.verify(int(e.get("page") or 0), e.get("quote", ""), k):
                            raise ValueError(f"kanıt doğrulanamadı: s{e.get('page')} “{e.get('quote')}”")
                    evs = ledger.evidence_from_model(c, generation_id, idx, cl.get("evidence", []),
                                                     valid_pages=pages)
                    cid = ledger.save_claim(c, generation_id, kind=claim_kind, subject=s.get("title"),
                                            claim=cl["claim"], evidence=evs,
                                            confidence=float(cl.get("confidence", 0.5)),
                                            created_by="hermes", payload={"section": s.get("title")},
                                            needs_review=bool(cl.get("needs_editor_review")))
                    if cid is None:
                        raise ValueError(f"kanıtsız iddia reddedildi: {cl['claim'][:80]}")
                    saved.append(cid)
    gen = db.one("SELECT g.*, b.title, bv.sha256, bv.page_count FROM generation g JOIN book_version bv"
                 " ON bv.id=g.book_version_id JOIN book b ON b.id=bv.book_id WHERE g.id=%s", generation_id)
    q = lambda sql, *a: db.all_rows(sql, generation_id, *a)  # noqa: E731
    live = "status NOT IN ('REJECTED','EDITOR_REJECTED','SUPERSEDED')"
    md: list[str] = [f"# {gen['title']} — {'Analiz raporu' if kind == 'ANALYSIS' else kind}",
                     f"Nesil `{generation_id}` · içerik `{gen['sha256'][:16]}` · {gen['page_count']} sayfa · "
                     f"{gen['created_at']:%Y-%m-%d %H:%M} UTC", ""]
    content: dict[str, Any] = {"generation_id": generation_id, "title": gen["title"]}

    book = q(f"SELECT claim, source_pages, status, confidence FROM claim WHERE generation_id=%s AND"
             f" kind='SUMMARY' AND payload->>'level'='book' AND {live} ORDER BY (payload->>'order')::int")
    md += ["## Kitap özeti", *[f"- {r['claim']} {_cite(r['source_pages'])}"
                               + (" _(doğrulanmadı)_" if r["status"] != "VERIFIED" else "") for r in book], ""]
    content["book_summary"] = book
    md.append("## Bölümler")
    content["chapters"] = []
    for ch in chapters(generation_id):
        rows = q(f"SELECT claim, source_pages, status FROM claim WHERE generation_id=%s AND kind='SUMMARY'"
                 f" AND payload->>'level'='chapter' AND subject=%s AND {live} ORDER BY (payload->>'order')::int",
                 ch["title"])
        if rows:
            md += [f"### {ch['title']} (s.{ch['page_from']}–{ch['page_to']})",
                   *[f"- {r['claim']} {_cite(r['source_pages'])}" for r in rows], ""]
            content["chapters"].append({**ch, "sentences": rows})
    chars = q("SELECT canonical_name, aliases, description, identity_status, identity_confidence, first_page"
              " FROM character WHERE generation_id=%s ORDER BY first_page")
    md += ["## Karakterler", "| Karakter | Diğer adlar | Kimlik | Güven | İlk sayfa |", "|---|---|---|---|---|",
           *[f"| {c['canonical_name']} | {', '.join(c['aliases'])} | {c['identity_status']} | "
             f"{c['identity_confidence']:.2f} | {c['first_page']} |" for c in chars], ""]
    content["characters"] = chars
    tl = build_timeline(generation_id)
    md += ["## Zaman çizelgesi (yalnız gerçekleşmiş olaylar)",
           *[f"{e['story_order'] or '-'}. {e['summary']} [s.{e['page_from']}]"
             + (f" — **{e['narrative_role']}**" if e.get("narrative_role") not in (None, "ORDINARY") else "")
             for e in tl], ""]
    content["timeline"] = tl
    other = q("SELECT modality, summary, page_from FROM event WHERE generation_id=%s AND merged_into IS NULL"
              " AND modality NOT IN ('REALIZED','MEMORY') ORDER BY page_from")
    md += ["## Plan, hayal, şaka ve belirsiz olaylar (gerçekleşmiş sayılmaz)",
           *[f"- **{e['modality']}** — {e['summary']} [s.{e['page_from']}]" for e in other], ""]
    content["non_realized_events"] = other
    themes = q(f"SELECT subject, claim, source_pages FROM claim WHERE generation_id=%s AND kind='THEME' AND"
               f" payload->>'level'='book' AND {live}")
    md += ["## Temalar", *[f"- **{t['subject']}**: {t['claim']} {_cite(t['source_pages'])}" for t in themes], ""]
    emo = q("SELECT coalesce(ch.canonical_name, e.character_name) AS who, e.page_no, e.emotion, e.intensity,"
            " e.trigger FROM emotion e LEFT JOIN character ch ON ch.id=e.character_id WHERE"
            " e.generation_id=%s ORDER BY who, e.page_no")
    md += ["## Duygu akışı", *[f"- {e['who']} s.{e['page_no']}: {e['emotion']} ({e['intensity']:.1f})"
                               + (f" — {e['trigger']}" if e["trigger"] else "") for e in emo], ""]
    content["emotions"] = emo
    cons = q("SELECT kind, description, pages, status, confidence FROM contradiction WHERE generation_id=%s"
             " ORDER BY confidence DESC")
    md += ["## Aday bulgular (hata değil, editör incelemesi için)",
           *[f"- {x['kind']} {_cite(x['pages'])} ({x['confidence']:.2f}, {x['status']}): {x['description']}"
             for x in cons], ""]
    content["contradictions"] = cons
    if kind != "ANALYSIS":
        sec = q("SELECT subject, claim, source_pages, confidence FROM claim WHERE generation_id=%s AND"
                " id = ANY(%s::uuid[])", saved)
        md += [f"## {kind}", *[f"- ({s['subject']}) {s['claim']} {_cite(s['source_pages'])} "
                               f"— güven {s['confidence']:.2f}" for s in sec], ""]
        content["sections"] = sec
    rq = q("SELECT r.priority, r.reason FROM review_item r WHERE r.generation_id=%s AND r.status='OPEN'"
           " ORDER BY r.priority, r.created_at")
    md += [f"## Editör kuyruğu ({len(rq)} açık)", *[f"- P{r['priority']}: {r['reason']}" for r in rq[:60]], ""]
    st = q("SELECT status, count(*) n FROM claim WHERE generation_id=%s GROUP BY status ORDER BY status")
    reg = db.one("SELECT passed, results FROM regression_run WHERE generation_id=%s ORDER BY created_at"
                 " DESC LIMIT 1", generation_id)
    md += ["## Kalite", "İddia durumları: " + ", ".join(f"{s['status']} {s['n']}" for s in st)]
    if reg:
        md += [f"Regresyon: {'GEÇTİ' if reg['passed'] else 'KALDI'}",
               *[f"- {'✓' if r['passed'] else '✗'} {r['check']}" + (f" ({r['detail']})" if r["detail"] else "")
                 for r in reg["results"]["checks"]]]
    md += ["", "## Kaynak kaydı", "Modeller: " + ", ".join(
        f"{a} → {m['real_model']}@{m['revision'][:10]}" for a, m in (gen["model_manifest"] or {}).items()),
        "Promptlar: " + ", ".join(f"{n} v{p['version']}" for n, p in (gen["prompt_manifest"] or {}).items())]
    text = "\n".join(md)
    content["review_open"] = len(rq)
    row = db.one("INSERT INTO report(generation_id, kind, content, markdown) VALUES (%s,%s,%s,%s) RETURNING id",
                 generation_id, kind, db.J(json.loads(json.dumps(content, default=str))), text)
    return {"report_id": str(row["id"]), "kind": kind, "saved_claims": saved, "markdown": text}
