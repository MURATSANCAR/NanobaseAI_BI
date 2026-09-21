"""Authenticated, read-only Editor control API; never starts a model or worker."""
from __future__ import annotations

import hmac
import os
from typing import Literal
from uuid import UUID

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Path

from . import foundation, source, knowledge, ledger, outputs, read_model, jobs, catalog
from .config import settings


def authorize(authorization: str = Header(default="")) -> None:
    expected = settings().gateway_internal_key
    given = authorization.removeprefix("Bearer ").strip()
    if not expected or not hmac.compare_digest(given, expected):
        raise HTTPException(401, "unauthorized")


app = FastAPI(title="Editor control", docs_url=None, redoc_url=None,
    openapi_url=None, dependencies=[Depends(authorize)])


@app.get("/health")
def health():
    result = foundation.runtime_status()
    return {"ok": True, "maintenance": result["control"]["maintenance"],
        "code_version": os.environ.get("EDITOR_CODE_VERSION", "unknown"),
        "mode": "foundation_only"}


@app.get("/v1/runtime")
def runtime():
    return foundation.runtime_status()


@app.get("/v1/generations")
def generations(limit: int = Query(default=100, ge=1, le=100)):
    return foundation.generations(limit)


@app.get("/v1/generations/{generation_id}/readiness")
def readiness(generation_id: UUID):
    try:
        return foundation.readiness(str(generation_id))
    except KeyError:
        raise HTTPException(404, "generation not found") from None


@app.get("/v1/generations/{generation_id}/records/{kind}")
def records(generation_id: UUID, kind: Literal["claims", "events", "emotions"],
            limit: int = Query(default=50, ge=1, le=100), offset: int = Query(default=0, ge=0)):
    try:
        return foundation.read_records(str(generation_id),kind,limit,offset)
    except KeyError:
        raise HTTPException(404, "generation not found") from None


@app.get("/v1/generations/{generation_id}/source/coverage")
def source_coverage(generation_id: UUID):
    try:
        return source.coverage(str(generation_id))
    except KeyError:
        raise HTTPException(404, "generation not found") from None


@app.get("/v1/generations/{generation_id}/source/pages/{page_no}")
def source_page(generation_id: UUID, page_no: int = Path(ge=1)):
    try:
        page = source.read(str(generation_id), page_no)[0]
        return {**page, "numbered_text": source.numbered(page)}
    except KeyError:
        raise HTTPException(404, "generation or page not found") from None


@app.get("/v1/generations/{generation_id}/source/plan")
def source_plan(generation_id: UUID):
    try:
        gid = str(generation_id)
        chapters = knowledge.chapters(gid)
        return {"policy": source.POLICY, "chapters": chapters,
                "text_chunks": knowledge.text_chunks(gid),
                "complete_book": False, "semantic_acceptance": False}
    except KeyError:
        raise HTTPException(404, "generation not found") from None


@app.get("/v1/generations/{generation_id}/source/passages")
def source_passages(generation_id: UUID):
    try:
        return {"policy": source.POLICY, "passages": source.passages(str(generation_id)),
                "indexed": False, "semantic_acceptance": False}
    except KeyError:
        raise HTTPException(404, "generation not found") from None


@app.get("/v1/generations/{generation_id}/source/quote-check")
def source_quote(generation_id: UUID, page_no: int = Query(ge=1),
                 paragraph: int = Query(ge=1), quote: str = Query(min_length=1, max_length=2000)):
    try:
        with foundation.read_snapshot() as c:
            idx = ledger.PageIndex.load(c, str(generation_id))
        spans = idx.matching_spans(page_no, quote, paragraph)
        return {"verified": bool(spans), "policy": source.POLICY,
                "span_ids": [s["span_id"] for s in spans], "semantic_acceptance": False}
    except KeyError:
        raise HTTPException(404, "generation not found") from None


@app.get("/v1/generations/{generation_id}/output-plan")
def output_plan(generation_id: UUID):
    try:
        return outputs.preview(str(generation_id))
    except KeyError:
        raise HTTPException(404, "generation not found") from None


@app.get("/v1/generations/{generation_id}/artifacts/{kind}")
def current_output(generation_id: UUID,
                   kind: Literal["chapter_summaries","book_summary","search_index","report","catalog"]):
    try:
        return outputs.current(str(generation_id), kind)
    except KeyError:
        raise HTTPException(404, "generation not found") from None


@app.get('/v1/generations/{generation_id}/timeline')
def timeline(generation_id: UUID):
    try:
        return knowledge.build_timeline(str(generation_id))
    except read_model.Unavailable as exc:
        raise HTTPException(409, str(exc)) from None
    except KeyError:
        raise HTTPException(404, 'generation not found') from None


@app.get('/v1/generations/{generation_id}/actors')
def actors(generation_id: UUID):
    try:
        return knowledge.event_actors(str(generation_id))
    except read_model.Unavailable as exc:
        raise HTTPException(409, str(exc)) from None
    except KeyError:
        raise HTTPException(404, 'generation not found') from None


@app.get('/v1/generations/{generation_id}/characters/history')
def character_history(generation_id: UUID, name: str = Query(min_length=1, max_length=300)):
    try:
        return read_model.character_history(str(generation_id), name)
    except read_model.Unavailable as exc:
        raise HTTPException(409, str(exc)) from None
    except KeyError:
        raise HTTPException(404, 'generation not found') from None


@app.get('/v1/generations/{generation_id}/report')
def report(generation_id: UUID, kind: str = 'ANALYSIS'):
    try:
        return jobs.get_report(str(generation_id), kind)
    except KeyError:
        raise HTTPException(404, 'generation not found') from None


@app.get('/v1/books/{book_id}/card')
def book_card(book_id: UUID):
    result = catalog.get_book_card(str(book_id))
    if result is None:
        raise HTTPException(404, 'book not found')
    return result
