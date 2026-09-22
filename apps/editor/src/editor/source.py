"""A source-preserving reading projection, shared by readers and evidence checks.

No model calls, writes, inferred story exclusions or retroactive evidence changes.
Offsets refer to the original page_text value, never to a normalized replacement.
OCR without geometry cannot establish cross-source reading order: flag it.
"""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from difflib import SequenceMatcher

from . import db

POLICY = "source-reading-v1"


def key(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"(\w)[-\u00ad]\s+(\w)", r"\1\2", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def blocks(text: str) -> list[tuple[int, int]]:
    out = []
    for match in re.finditer(r"\S.*?(?=\n\s*\n|\Z)", text, re.S):
        end = match.end()
        while end > match.start() and text[end-1].isspace():
            end -= 1
        out.append((match.start(), end))
    return out


def _span(gid: str, page: int, source: dict, start: int, end: int, role="body") -> dict:
    raw = source["text"]
    checksum = hashlib.sha256(raw.encode()).hexdigest()
    identity = f"{POLICY}:{gid}:{page}:{source['source']}:{checksum}:{start}:{end}"
    return {"span_id": hashlib.sha256(identity.encode()).hexdigest(), "source": source["source"],
        "source_sha256": checksum, "start": start, "end": end, "text": raw[start:end],
        "model_call_id": source.get("model_call_id"), "role": role}


def project_page(gid: str, page: dict, sources: list[dict], legacy_role: dict | None = None) -> dict:
    ocr_attempted = any(s["source"] == "OCR" for s in sources)
    by_source = {s["source"]: s for s in sources if s["text"].strip()}
    layer, ocr = by_source.get("TEXT_LAYER"), by_source.get("OCR")
    spans, alternatives, issues = [], [], []
    # A digital text layer is the publisher's own text and normally the base. Where the
    # manifest measured it as unreliable (scrambled words, garbled characters, letter-spaced)
    # and the page was read from its pixels, that reading is the base instead and the layer
    # is kept only as an alternative. Without an OCR reading the unreliable layer stays —
    # it is all there is — and the page says so.
    unreliable = bool((page.get("layer_health") or {}).get("layer_unreliable"))
    if layer and ocr and unreliable:
        alternatives.append({**_span(gid, page["page_no"], layer, 0, len(layer["text"])),
                             "disposition": "TEXT_LAYER_UNRELIABLE",
                             "reasons": (page.get("layer_health") or {}).get("ocr_reasons", [])})
        layer = None
    elif layer and unreliable:
        issues.append("TEXT_LAYER_UNRELIABLE_NO_OCR")
    base = layer or ocr
    ocr_kinds = {}
    # Layout kinds come only from a reader that returns them (our block schema); an OCR
    # specialist answers in plain text, which is not an invalid answer.
    if ocr and (ocr.get("ocr_content") or "").lstrip().startswith("{"):
        try:
            response = json.loads(ocr["ocr_content"])
            ocr_kinds = {b["text"].strip(): b.get("kind", "body") for b in response["blocks"]}
        except (ValueError, KeyError, TypeError, AttributeError):
            issues.append("OCR_LAYOUT_METADATA_INVALID")
    if base:
        for start, end in blocks(base["text"]):
            text = base["text"][start:end]
            # Use OCR layout only when the heading is literally present at the
            # start of the retained layer block. Keep the layer's original words.
            headings = [h for h,kind in ocr_kinds.items() if kind=="heading" and h
                and text.startswith(h) and (len(text)==len(h) or text[len(h)].isspace())]
            heading = max(headings, key=len) if headings else None
            if heading and layer:
                spans.append(_span(gid,page["page_no"],base,start,start+len(heading),"heading"))
                body_start = start+len(heading)
                while body_start < end and base["text"][body_start].isspace():
                    body_start += 1
                if body_start < end:
                    spans.append(_span(gid,page["page_no"],base,body_start,end))
            else:
                spans.append(_span(gid,page["page_no"],base,start,end,ocr_kinds.get(text,"body") if not layer else "body"))
    if layer and ocr:
        layer_key = key(layer["text"])
        for start,end in blocks(ocr["text"]):
            candidate = _span(gid,page["page_no"],ocr,start,end,ocr_kinds.get(ocr["text"][start:end],"body"))
            candidate_key = key(candidate["text"])
            if candidate_key and candidate_key in layer_key:
                candidate["disposition"] = "CORROBORATES_TEXT_LAYER"
                alternatives.append(candidate)
                continue
            # Similarity only flags a disagreement; it never rewrites either source.
            similar = any(SequenceMatcher(None,candidate_key,key(s["text"]),autojunk=False).ratio() >= .6
                for s in spans if s["source"]=="TEXT_LAYER")
            if similar:
                # The publisher's own digital text against an 8B model's reading of pixels is
                # not two sources in conflict (an unreliable layer never reaches this branch:
                # there the OCR reading is already the base). Measured on six books, every
                # disagreement with a healthy layer was the OCR's slip ("alındaki" for
                # "alnındaki", "bağirdik", a looped phrase). The reading is kept as a variant.
                candidate["disposition"] = "OCR_VARIANT_OF_HEALTHY_TEXT_LAYER"
                alternatives.append(candidate)
            else:
                candidate["reading_order"] = "UNRESOLVED_SUPPLEMENT"
                spans.append(candidate)
                issues.append("OCR_SUPPLEMENT_ORDER_UNRESOLVED")
    for idx,span in enumerate(spans,1):
        span["idx"] = idx
    if not spans:
        issues.append("NO_READABLE_TEXT")
    if page["needs_ocr"] and not ocr_attempted:
        issues.append("OCR_REQUIRED_MISSING")
    legacy_role = legacy_role or {}
    # No model or heading heuristic can silently exclude a physical page.
    role = legacy_role.get("role") if legacy_role.get("source")=="editor" else "UNKNOWN"
    inputs = [{"source":s["source"],"sha256":hashlib.sha256(s["text"].encode()).hexdigest(),
               "model_call_id":s.get("model_call_id")} for s in sources]
    digest = hashlib.sha256(json.dumps({"policy":POLICY,"inputs":inputs,"spans":spans,
        "alternatives":alternatives,"issues":sorted(set(issues))},sort_keys=True,default=str).encode()).hexdigest()
    return {"generation_id":gid,"page_no":page["page_no"],"policy":POLICY,"reading_sha256":digest,
        "page_role":role,"legacy_role":legacy_role or None,"included_in_extraction":True,
        "text_status":"READABLE" if spans else "MISSING_OR_VISUAL_ONLY",
        "ocr_status":"TEXT_FOUND" if ocr else "COMPLETED_NO_TEXT" if ocr_attempted else "NOT_RUN",
        "reconciliation_status":"NEEDS_REVIEW" if issues else "AVAILABLE",
        "semantic_acceptance":False,"issues":sorted(set(issues)),"sources":inputs,
        "spans":spans,"alternatives":alternatives}


def load(conn, generation_id: str, page_no: int | None = None) -> list[dict]:
    gen = conn.execute("SELECT book_version_id FROM ed.generation WHERE id=%s",(generation_id,)).fetchone()
    if not gen:
        raise KeyError(generation_id)
    pages = conn.execute("SELECT page_no,needs_ocr,image_count,layer_health FROM ed.page WHERE book_version_id=%s "
        "AND (%s::int IS NULL OR page_no=%s) ORDER BY page_no",(gen["book_version_id"],page_no,page_no)).fetchall()
    if page_no is not None and not pages:
        raise KeyError(f"page {page_no}")
    data = conn.execute("SELECT p.page_no,p.source,p.text,p.model_call_id,m.response->>'content' AS ocr_content "
        "FROM ed.page_text p LEFT JOIN ed.model_call m ON m.id=p.model_call_id AND p.source='OCR' "
        "WHERE p.generation_id=%s AND (%s::int IS NULL OR p.page_no=%s) ORDER BY p.page_no,p.source",
        (generation_id,page_no,page_no)).fetchall()
    roles = {r["page_no"]:dict(r) for r in conn.execute("SELECT page_no,role,source FROM ed.page_role "
        "WHERE generation_id=%s AND (%s::int IS NULL OR page_no=%s)",(generation_id,page_no,page_no))}
    by_page = {}
    for row in data:
        by_page.setdefault(row["page_no"],[]).append(row)
    return [project_page(str(generation_id),p,by_page.get(p["page_no"],[]),roles.get(p["page_no"])) for p in pages]


def read(generation_id: str, page_no: int | None = None) -> list[dict]:
    with db.tx() as c:
        c.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        c.execute("SET LOCAL statement_timeout='15s'")
        return load(c,generation_id,page_no)


def numbered(page: dict) -> str:
    lines=[]
    for span in page["spans"]:
        tag = " [OCR eki; okuma sırası belirsiz]" if span.get("reading_order") else ""
        lines.append(f"[s{page['page_no']} p{span['idx']}]{tag} {span['text']}")
    if page["issues"]:
        lines.append("[KAYNAK UYARISI: " + ", ".join(page["issues"]) + "]")
    return "\n".join(lines) or "(metin yok)"


def coverage(generation_id: str) -> dict:
    pages=read(generation_id)
    return {"generation_id":generation_id,"policy":POLICY,"physical_pages":len(pages),
        "included_pages":[p["page_no"] for p in pages],"excluded_pages":[],
        "readable_pages":sum(bool(p["spans"]) for p in pages),
        "unresolved_pages":[{"page_no":p["page_no"],"issues":p["issues"]} for p in pages if p["issues"]],
        "classification_unresolved_pages":[p["page_no"] for p in pages if p["page_role"]=="UNKNOWN"],
        "complete_book":False,"semantic_acceptance":False,
        "pages":[{k:v for k,v in p.items() if k not in ("spans","alternatives")} for p in pages]}


def passages(generation_id: str) -> list[dict]:
    return [{"kind":"paragraph", "page_no":p["page_no"],
             "ref":f"s{p['page_no']}p{s['idx']}", "paragraph_idx":s["idx"],
             "text":s["text"], "source_policy":POLICY, "reading_sha256":p["reading_sha256"],
             "source_span":{k:s[k] for k in ("span_id","source","source_sha256","start","end")},
             "source_issues":p["issues"]}
            for p in read(generation_id) for s in p["spans"]]
