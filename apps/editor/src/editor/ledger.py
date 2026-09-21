"""Evidence ledger writes. Every claim goes through `save_claim`, which refuses
a claim without evidence (the database refuses it too, at commit)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Iterable

import psycopg

from . import db, source

_WS = re.compile(r"\s+")
_HYPH = re.compile(r"(\w)[-­]\s+(\w)")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "")
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    s = _HYPH.sub(r"\1\2", s)
    s = re.sub(r"[\"'«»….,;:!?()\-–—]", " ", s)
    return _WS.sub(" ", s).strip().casefold()


def has_name(text_norm: str, name: str, allow_suffix: bool = False) -> bool:
    """Is `name` in the (normalised) text as whole words? Suffixes after an apostrophe
    ("Can'a") are already split off by `norm`; "can" inside "heyecan" is not the name.
    `allow_suffix` also accepts an inflected common noun ("dedesi" in "dedesini"); use it
    only to confirm that a word occurs in the book, never to decide who is on a page."""
    n = norm(name)
    tail = r"\w*" if allow_suffix else r"(?!\w)"
    return bool(n) and re.search(r"(?<!\w)" + re.escape(n) + tail, text_norm) is not None


def quote_found(quote: str, haystack_norm: str) -> bool:
    """Verbatim (after normalisation) or >= 85% of the quote's words in order."""
    q = norm(quote)
    if not q:
        return False
    if q in haystack_norm:
        return True
    words = q.split()
    if len(words) < 4:
        return False
    hay = haystack_norm.split()
    best = 0
    for i in range(len(hay)):
        j, k = i, 0
        while j < len(hay) and k < len(words):
            if hay[j] == words[k]:
                k += 1
            j += 1
            if j - i > len(words) * 2:
                break
        best = max(best, k)
    return best / len(words) >= 0.85


def snap_quote(quote: str, raw_page_text: str) -> str | None:
    """The model sometimes retypes a sentence with a slip ("oynu" for "oyunu", a
    line-break hyphen). Find the span of the page that the quote is a near copy of
    and return the page's own words; None when nothing on the page is that close."""
    import difflib
    q = norm(quote)
    raw = raw_page_text.split()
    toks = [(norm(w), i) for i, w in enumerate(raw)]
    toks = [(t, i) for t, i in toks if t]
    n = len(q.split())
    if n < 3 or len(toks) < n:
        return None
    best, span = 0.0, None
    for size in (n, n - 1, n + 1, n + 2):
        if size < 3:
            continue
        for a in range(0, len(toks) - size + 1):
            cand = " ".join(t for t, _ in toks[a:a + size])
            if abs(len(cand) - len(q)) > len(q) * 0.25:
                continue
            r = difflib.SequenceMatcher(None, q, cand, autojunk=False).ratio()
            if r > best:
                best, span = r, (toks[a][1], toks[a + size - 1][1])
    if span is None or best < 0.9:
        return None
    return " ".join(raw[span[0]:span[1] + 1])


@dataclass
class PageIndex:
    """Current source spans; historical paragraph rows are never reinterpreted."""
    text: dict[int, str]
    visual: dict[int, str]
    raw: dict[int, str]
    spans: dict[int, list[dict]]
    generation_id: str

    @classmethod
    def load(cls, conn: psycopg.Connection, generation_id: str) -> "PageIndex":
        pages = source.load(conn, generation_id)
        spans = {p["page_no"]: p["spans"] for p in pages}
        visual: dict[int, list[str]] = {}
        for r in conn.execute("SELECT page_no, result::text AS t FROM page_scan "
                              "WHERE generation_id=%s", (generation_id,)):
            visual.setdefault(r["page_no"], []).append(r["t"])
        raw = {p: "\n".join(s["text"] for s in ss) for p, ss in spans.items()}
        return cls({p: norm(t) for p, t in raw.items()},
                   {p: norm(" ".join(v)) for p, v in visual.items()}, raw, spans, str(generation_id))

    def matching_spans(self, page: int, quote: str, paragraph: int | None = None) -> list[dict]:
        q = source.key(quote)
        return [s for s in self.spans.get(page, []) if q and q in source.key(s["text"])
                and (not paragraph or s["idx"] == paragraph)]

    def verify(self, page: int, quote: str, kind: str, paragraph: int | None = None) -> bool:
        if kind == "TEXT":
            return bool(self.matching_spans(page, quote, paragraph))
        if kind == "VISUAL":
            return quote_found(quote, self.text.get(page, "") + " " + self.visual.get(page, ""))
        return False


def save_evidence(conn: psycopg.Connection, generation_id: str, idx: PageIndex, *,
                  page: int, quote: str, kind: str = "TEXT",
                  paragraph_idx: int | None = None, region_id: str | None = None,
                  event_id: str | None = None) -> tuple[str, bool]:
    if idx.generation_id != str(generation_id):
        raise ValueError("evidence generation mismatch")
    quote = (quote or "").strip()
    if not quote:
        raise ValueError("empty evidence quote")
    ok = idx.verify(page, quote, kind, paragraph_idx)
    refs = [{k: s[k] for k in ("span_id", "source", "source_sha256", "start", "end", "idx")}
            for s in idx.matching_spans(page, quote, paragraph_idx)] if kind == "TEXT" else []
    provenance = {"policy": source.POLICY, "generation_id": generation_id,
                  "page_no": page, "spans": refs}
    row = conn.execute(
        "INSERT INTO evidence(generation_id, page_no, paragraph_idx, region_id, event_id, kind,"
        " quote, quote_verified, source_refs) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (generation_id, page, paragraph_idx or None, region_id, event_id, kind, quote, ok, db.J(provenance)),
    ).fetchone()
    return str(row["id"]), ok


def evidence_from_model(conn: psycopg.Connection, generation_id: str, idx: PageIndex,
                        items: Iterable[dict], *, valid_pages: set[int],
                        default_kind: str = "TEXT") -> list[tuple[str, bool, int]]:
    """Model evidence [{page, paragraph, quote}] -> ledger rows. Items pointing
    at pages outside the book are dropped (they are not evidence)."""
    out = []
    for e in items or []:
        page = int(e.get("page") or 0)
        quote = (e.get("quote") or "").strip()
        if page not in valid_pages or not quote:
            continue
        paragraph = int(e.get("paragraph") or 0) or None
        # Do not silently rewrite an attributed quote or resolve a bad paragraph
        # against a different span. Unmatched evidence remains unverified.
        kind = "VISUAL" if paragraph is None and default_kind == "TEXT" \
            and not idx.verify(page, quote, "TEXT") else default_kind
        eid, ok = save_evidence(conn, generation_id, idx, page=page, quote=quote, kind=kind,
                                paragraph_idx=int(e.get("paragraph") or 0) or None)
        out.append((eid, ok, page))
    return out


def save_claim(conn: psycopg.Connection, generation_id: str, *, kind: str, claim: str,
               evidence: list[tuple[str, bool, int]], confidence: float, created_by: str,
               subject: str | None = None, payload: dict | None = None,
               model_call_id: int | None = None, status: str = "CANDIDATE",
               needs_review: bool = False) -> str | None:
    """Insert a claim with its evidence links. Returns None (and writes
    nothing) when there is no evidence: "Kaynaksız iddia üretilemez"."""
    if not evidence or not claim.strip():
        return None
    pages = sorted({p for _, _, p in evidence})
    verified = sum(1 for _, ok, _ in evidence if ok)
    payload = dict(payload or {})
    payload.setdefault("evidence_verified", f"{verified}/{len(evidence)}")
    row = conn.execute(
        "INSERT INTO claim(generation_id, kind, subject, claim, source_pages, payload, confidence,"
        " status, needs_editor_review, created_by, model_call_id)"
        " VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (generation_id, kind, subject, claim.strip(), pages, db.J(payload),
         max(0.0, min(1.0, float(confidence))), status, needs_review, created_by, model_call_id),
    ).fetchone()
    cid = str(row["id"])
    for eid, _, _ in evidence:
        conn.execute("INSERT INTO claim_evidence(claim_id, evidence_id) VALUES (%s,%s) "
                     "ON CONFLICT DO NOTHING", (cid, eid))
    return cid


def supersede_claim(conn: psycopg.Connection, generation_id: str, old_claim_id: str, *,
                    payload_update: dict, created_by: str, note: str, claim: str | None = None,
                    model_call_id: int | None = None) -> str | None:
    """Claims are immutable: a correction the application makes itself is a new claim with
    the same evidence, and the old one is kept, marked SUPERSEDED."""
    old = conn.execute("SELECT * FROM claim WHERE id=%s", (old_claim_id,)).fetchone()
    if old is None:
        return None
    evs = [(str(r["evidence_id"]), r["quote_verified"], r["page_no"]) for r in conn.execute(
        "SELECT ce.evidence_id, e.quote_verified, e.page_no FROM claim_evidence ce JOIN evidence e ON"
        " e.id=ce.evidence_id WHERE ce.claim_id=%s", (old_claim_id,)).fetchall()]
    new_id = save_claim(conn, generation_id, kind=old["kind"], subject=old["subject"],
                        claim=claim or old["claim"], evidence=evs, confidence=float(old["confidence"]),
                        created_by=created_by, model_call_id=model_call_id,
                        payload={**(old["payload"] or {}), **payload_update, "supersedes": old_claim_id})
    conn.execute("UPDATE claim SET status='SUPERSEDED', critic_note=%s WHERE id=%s",
                 (f"{note} → yerine {new_id}", old_claim_id))
    return new_id


def queue_review(conn: psycopg.Connection, generation_id: str, *, reason: str,
                 claim_id: str | None = None, contradiction_id: str | None = None,
                 priority: int = 2) -> str:
    if claim_id:
        conn.execute("UPDATE claim SET status='NEEDS_REVIEW', needs_editor_review=true "
                     "WHERE id=%s AND status IN ('CANDIDATE','VERIFIED','NEEDS_REVIEW')",
                     (claim_id,))
    if contradiction_id:
        conn.execute("UPDATE contradiction SET status='NEEDS_REVIEW' WHERE id=%s "
                     "AND status='CANDIDATE'", (contradiction_id,))
    existing = conn.execute(
        "SELECT id FROM review_item WHERE generation_id=%s AND status='OPEN' AND "
        "claim_id IS NOT DISTINCT FROM %s AND contradiction_id IS NOT DISTINCT FROM %s",
        (generation_id, claim_id, contradiction_id)).fetchone()
    if existing:
        return str(existing["id"])
    row = conn.execute(
        "INSERT INTO review_item(generation_id, claim_id, contradiction_id, reason, priority)"
        " VALUES (%s,%s,%s,%s,%s) RETURNING id",
        (generation_id, claim_id, contradiction_id, reason[:2000], priority)).fetchone()
    return str(row["id"])


def corrections_for_book(conn: psycopg.Connection, book_id: str) -> list[dict[str, Any]]:
    """Editor corrections carried into every later run of the same book."""
    return conn.execute(
        "SELECT target_kind, target_key, correction, editor, created_at FROM editor_correction "
        "WHERE book_id=%s ORDER BY created_at", (book_id,)).fetchall()
