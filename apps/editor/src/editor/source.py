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


#: Sayfa başlığı/altlığı (yazar adı, kitap adı, bölüm adı sayfa kenarında): metin olarak korunur (ofsetler, kanıt
#: doğrulaması aynı), ama okumaya (numbered), aramaya (passages), ad sayımına ve bölüm bulmaya girmez
#: (`editor.running_head`). Rol span kimliğine girmez: eski kanıtların span bağı geçerli kalır.
RUNNING_HEAD = "running_head"
#: Baskı/üretim notu ve dizgi dosyasında kalmış özgün dil satırı (`editor.print_note`, K20): sayfa başlığı gibi metin
#: olarak korunur, okumaya/aramaya/ad sayımına/bölüm bulmaya girmez.
PRINT_NOTE = "print_note"
NOT_BODY = (RUNNING_HEAD, PRINT_NOTE)


def body_spans(page: dict) -> list[dict]:
    """Sayfanın gövde spanları (sayfa başlığı/altlığı ve baskı notu hariç)."""
    return [s for s in page["spans"] if s.get("role") not in NOT_BODY]


def shown(span: dict) -> str:
    """Spanın okumaya/aramaya giden metni: dizgi dosyasında satırdaki baskı notu parçası çıkarılmış hâli
    («KAPAK içine baskı İşte burada!» → «İşte burada!»; `display`), yoksa metnin kendisi. Kanıt doğrulaması `text`'e
    bakar: gösterilen metin onun parçasıdır."""
    return span.get("display") or span["text"]


def body_text(pages: list[dict], sep: str = "\n") -> str:
    """Kitabın yazılı metni, sayfa başlığı/altlığı olmadan (özel ad sayımı: `naming.is_proper_name`)."""
    return sep.join(shown(s) for p in pages for s in body_spans(p))


def _unreliable(page: dict) -> bool:
    return bool((page.get("layer_health") or {}).get("layer_unreliable"))


def base_source(page: dict, by_source: dict) -> str | None:
    """Sayfanın taban okuması (`project_page` ile aynı): metin katmanı; katman güvenilmez ölçülmüş ve OCR okuması
    varsa OCR."""
    if "TEXT_LAYER" in by_source and not ("OCR" in by_source and _unreliable(page)):
        return "TEXT_LAYER"
    return "OCR" if "OCR" in by_source else None


def project_page(gid: str, page: dict, sources: list[dict], legacy_role: dict | None = None,
                 running=frozenset(), notes: dict | None = None) -> dict:
    """`running`: bu sayfanın sayfa başlığı/altlığı olan kenar blokları ({"top", "bottom"}; `running_heads`).
    `notes`: kitabın baskı notu bağlamı (`print_note.book_context`; `page_marks`) — bütünüyle not olan blok
    `PRINT_NOTE` rolü alır, dizgi dosyasında notla metnin karıştığı satırın gösterilen metninden not çıkar."""
    ocr_attempted = any(s["source"] == "OCR" for s in sources)
    by_source = {s["source"]: s for s in sources if s["text"].strip()}
    layer, ocr = by_source.get("TEXT_LAYER"), by_source.get("OCR")
    spans, alternatives, issues = [], [], []
    # A digital text layer is the publisher's own text and normally the base. Where the
    # manifest measured it as unreliable (scrambled words, garbled characters, letter-spaced)
    # and the page was read from its pixels, that reading is the base instead and the layer
    # is kept only as an alternative. Without an OCR reading the unreliable layer stays —
    # it is all there is — and the page says so.
    unreliable = _unreliable(page)
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
    if running and base:
        from . import running_head
        raw = base["text"]
        edges = running_head.edge_blocks(raw[:running_head.WINDOW], raw[-running_head.WINDOW:], len(raw))
        for pos in running:
            if pos not in edges:
                continue
            lo, hi = edges[pos]
            for span in spans:
                if span["source"] == base["source"] and lo <= span["start"] and span["end"] <= hi:
                    span["role"] = RUNNING_HEAD
    if notes and base:
        _mark_notes(spans, base["source"], notes)
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


def _mark_notes(spans: list[dict], base: str, notes: dict) -> None:
    """Taban okumanın spanlarında baskı notu (`editor.print_note`): bütünüyle not olan blok `PRINT_NOTE`; dizgi
    dosyasında notla metnin aynı satırda durduğu blokta gösterilen metin (`display`) notsuz."""
    from . import print_note
    production = print_note.is_production_file(notes)
    for span in spans:
        if span["source"] != base or span.get("role") in NOT_BODY:
            continue
        if print_note.block_is_note(span["text"], notes):
            span["role"] = PRINT_NOTE
        elif production:
            lines = span["text"].split("\n")
            kept = [print_note.strip_notes(ln) if print_note.note_spans(ln) else ln for ln in lines]
            if kept != lines:
                span["display"] = "\n".join(ln for ln in kept if ln.strip())


def running_heads(conn, generation_id: str, book_version_id) -> dict[int, set[str]]:
    """{sayfa: {"top"/"bottom"}} — kitabın sayfa başlığı/altlığı olan kenar blokları (`editor.running_head`).
    Bütün kitaba bakar ama sayfa metinlerinin yalnız kenarlarını okur (tek sayfalık sorguda da ucuz)."""
    return page_marks(conn, generation_id, book_version_id)[0]


def page_marks(conn, generation_id: str, book_version_id) -> tuple[dict[int, set[str]], dict]:
    """(`running_heads`, baskı notu bağlamı) — ikisi de sayfa metinlerinin yalnız kenarlarından (ilk/son
    `running_head.WINDOW` karakter): notlar dizgi dosyasında sayfanın kenar bloklarıdır, kitabın dili de bu
    örnekten sayılır (`print_note.book_context`)."""
    from . import print_note, running_head
    w = running_head.WINDOW
    health = {r["page_no"]: r for r in conn.execute(
        "SELECT page_no,layer_health FROM ed.page WHERE book_version_id=%s", (book_version_id,))}
    rows = conn.execute("SELECT page_no,source,left(text,%s) AS head,right(text,%s) AS tail,length(text) AS n "
                        "FROM ed.page_text WHERE generation_id=%s AND btrim(text)<>''",
                        (w, w, generation_id)).fetchall()
    by_page: dict[int, dict] = {}
    for r in rows:
        by_page.setdefault(r["page_no"], {})[r["source"]] = r
    edges, lines = {}, []
    for p, srcs in by_page.items():
        base = base_source(health.get(p) or {}, srcs)
        if base is None:
            continue
        r = srcs[base]
        edges[p] = running_head.edge_texts(r["head"], r["tail"], r["n"])
        sample = r["head"] if r["n"] <= len(r["head"]) else r["head"] + "\n" + r["tail"]
        lines += [ln for ln in sample.splitlines() if ln.strip()]
    heads = running_head.detect(edges, len(edges), book_names(conn, generation_id))
    return heads, print_note.book_context(lines)


def book_names(conn, generation_id: str) -> list[str]:
    """Kitabın kayıt adı ve künyenin doğrulanmış ad/yazar/çizer iddiaları (sayfa başlığı bulmak için)."""
    names = [r["title"] for r in conn.execute(
        "SELECT b.title FROM ed.generation g JOIN ed.book_version bv ON bv.id=g.book_version_id"
        " JOIN ed.book b ON b.id=bv.book_id WHERE g.id=%s", (generation_id,)) if r["title"]]
    names += [r["claim"] for r in conn.execute(
        "SELECT claim FROM ed.claim WHERE generation_id=%s AND kind='METADATA' AND subject IN"
        " ('TITLE','AUTHOR','ILLUSTRATOR') AND status IN ('VERIFIED','EDITOR_APPROVED','EDITOR_CORRECTED')",
        (generation_id,)) if r["claim"]]
    return [n.strip() for x in names for n in re.split(r"[,;/&]| ve ", x) if n.strip()]


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
    heads, notes = page_marks(conn, generation_id, gen["book_version_id"])
    return [project_page(str(generation_id),p,by_page.get(p["page_no"],[]),roles.get(p["page_no"]),
                         heads.get(p["page_no"], frozenset()), notes) for p in pages]


def read(generation_id: str, page_no: int | None = None) -> list[dict]:
    from .foundation import read_snapshot  # denetim bağlamını işlemin dışında tutar (foundation.read_snapshot)
    with read_snapshot() as c:
        return load(c,generation_id,page_no)


def numbered(page: dict) -> str:
    """Okumaya giden sayfa metni; sayfa başlığı/altlığı yazılmaz (paragraf numaraları değişmez)."""
    lines=[]
    for span in body_spans(page):
        tag = " [OCR eki; okuma sırası belirsiz]" if span.get("reading_order") else ""
        lines.append(f"[s{page['page_no']} p{span['idx']}]{tag} {shown(span)}")
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
             "text":shown(s), "source_policy":POLICY, "reading_sha256":p["reading_sha256"],
             "source_span":{k:s[k] for k in ("span_id","source","source_sha256","start","end")},
             "source_issues":p["issues"]}
            for p in read(generation_id) for s in body_spans(p)]
