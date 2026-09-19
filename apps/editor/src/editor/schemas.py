"""JSON schemas for structured model output (vLLM json_schema response_format)."""

from __future__ import annotations


def obj(props: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": props,
            "required": required if required is not None else list(props),
            "additionalProperties": False}


def arr(items: dict, min_items: int = 0, max_items: int = 120) -> dict:
    """Every list is bounded. An unbounded list is where a schema-guided decode spins
    ("SCENE","SCENE",... until max_tokens, seen on real pages); the bound is far above
    anything a page or a book chunk can really hold, so it only ever stops a loop."""
    s: dict = {"type": "array", "items": items, "maxItems": max_items}
    if min_items:
        s["minItems"] = min_items
    return s


STR = {"type": "string", "maxLength": 1200}   # a runaway string cannot eat the token budget
INT = {"type": "integer"}
NUM = {"type": "number", "minimum": 0, "maximum": 1}
BOOL = {"type": "boolean"}
BBOX = arr({"type": "integer", "minimum": 0, "maximum": 1000}, 4, 4)
MODALITY = {"type": "string", "enum": ["REALIZED", "PLAN", "DREAM", "IMAGINATION", "JOKE",
                                       "LIE", "HYPOTHETICAL", "MEMORY", "UNCERTAIN"]}
EVIDENCE = arr(obj({"page": INT, "paragraph": INT, "quote": STR}), 1, 8)

OCR = obj({"blocks": arr(obj({
    "text": {"type": "string", "maxLength": 8000},   # a full page of body text can be one block
    "kind": {"type": "string", "enum": ["body", "heading", "speech_bubble", "sign",
                                        "caption", "screen", "other"]}}), 0, 200)})

PAGE_SCAN = obj({
    "scene": obj({"setting": STR, "time_of_day": STR, "mood": STR, "description": STR}),
    "characters": arr(obj({
        "label": STR, "name": STR, "name_basis": STR, "identity_uncertain": BOOL,
        "appearance": obj({"hair": STR, "skin": STR, "age_look": STR, "clothes": STR,
                           "colors": STR, "distinctive": STR}),
        "action": STR, "visible_emotion": STR, "bbox": BBOX, "confidence": NUM}), 0, 40),
    "objects": arr(obj({"label": STR, "bbox": BBOX, "note": STR}), 0, 60),
    "text_in_image": arr(STR, 0, 60),
    "text_visual_checks": arr(obj({
        "paragraph": INT, "text_quote": STR, "visual_observation": STR,
        "consistent": BOOL, "note": STR, "confidence": NUM}), 0, 40),
    "important_event": BOOL,
    "uncertain": BOOL,
    "uncertainty_reasons": arr({"type": "string",
                                "enum": ["IDENTITY", "TEXT_VISUAL", "SCENE", "IMPORTANT_EVENT"]}, 0, 4),
})

KNOWLEDGE = obj({
    "character_mentions": arr(obj({
        "surface_name": STR, "page": INT, "via": {"type": "string", "enum": ["TEXT", "VISUAL", "BOTH"]},
        "description": STR, "confidence": NUM, "evidence": EVIDENCE})),
    "events": arr(obj({
        "summary": STR, "modality": MODALITY, "page_from": INT, "page_to": INT,
        "participants": arr(STR), "importance": NUM, "confidence": NUM, "evidence": EVIDENCE})),
    "emotions": arr(obj({
        "character": STR, "page": INT, "emotion": STR, "intensity": NUM, "trigger": STR,
        "confidence": NUM, "evidence": EVIDENCE})),
    "themes": arr(obj({"theme": STR, "confidence": NUM, "evidence": EVIDENCE})),
    # pages in this chunk that are not story (reader activities, information pages,
    # imprint, biographies, advertisements): nothing is extracted from them
    "non_story_pages": arr(INT),
})

IDENTITY = obj({
    "characters": arr(obj({
        "canonical_name": STR, "aliases": arr(STR), "description": STR,
        "mention_ids": arr(STR, 1), "merge_basis": STR, "identity_confidence": NUM})),
    "unresolved_mention_ids": arr(STR),
    "conflicts": arr(obj({"mention_id": STR, "candidates": arr(STR), "note": STR})),
})

MERGE_EVENTS = obj({
    "groups": arr(obj({"event_ids": arr(STR, 2), "summary": STR})),
    "story_order": arr(STR),
})

SUMMARY = obj({
    "title": STR,
    "sentences": arr(obj({"text": STR, "evidence": EVIDENCE, "confidence": NUM}), 1),
})

BOOK_SUMMARY = obj({
    "summary": arr(obj({"text": STR, "evidence": EVIDENCE, "confidence": NUM}), 1),
    "themes": arr(obj({"theme": STR, "text": STR, "evidence": EVIDENCE, "confidence": NUM})),
    "arcs": arr(obj({"character": STR, "text": STR, "evidence": EVIDENCE, "confidence": NUM})),
})

CRITIC = obj({"verdicts": arr(obj({
    "claim_id": STR,
    "supported": {"type": "string", "enum": ["SUPPORTED", "PARTIAL", "UNSUPPORTED"]},
    "modality_ok": BOOL, "identity_ok": BOOL, "note": STR}))})

APPEARANCE = obj({
    "same_character_everywhere": BOOL,
    "differences": arr(obj({"attribute": STR, "pages": arr(INT), "description": STR,
                            "explained_by_story": BOOL, "continuity_candidate": BOOL,
                            "confidence": NUM})),
    "summary": STR,
})

MODALITY_CHECK = obj({"events": arr(obj({
    "event_id": STR, "modality": MODALITY, "confidence": NUM, "reason": STR}))})

THEMES = obj({"themes": arr(obj({
    "theme": STR, "text": STR, "source_ids": arr(STR, 1), "confidence": NUM}))})

NARRATIVE_ROLES = obj({"events": arr(obj({
    "event_id": STR,
    "role": {"type": "string", "enum": ["SETUP", "INCITING", "TURNING_POINT", "CLIMAX",
                                        "RESOLUTION", "ORDINARY"]},
    "reason": STR}))})

CLAIM_REPAIR = obj({
    "action": {"type": "string", "enum": ["ADD_EVIDENCE", "NARROW", "NONE"]},
    "claim": STR,
    "evidence": arr(obj({"page": INT, "paragraph": INT, "quote": STR})),
})

BOOK_METADATA = obj({"fields": arr(obj({
    "field": {"type": "string", "enum": ["TITLE", "AUTHOR", "ILLUSTRATOR", "PUBLISHER", "SERIES",
                                         "ISBN", "AGE_RANGE", "GENRE", "EDITION"]},
    "value": STR, "page": INT, "quote": STR}))})

MATCH_FIGURES = obj({"matches": arr(obj({
    "figure": STR, "reference": STR, "confidence": NUM, "reason": STR}))})

CONTRADICTIONS = obj({"candidates": arr(obj({
    "kind": {"type": "string", "enum": ["TIMELINE", "CHARACTER", "TEXT_VISUAL",
                                        "CONTINUITY", "IDENTITY"]},
    "pages": arr(INT, 1), "description": STR, "confidence": NUM,
    "evidence": EVIDENCE}))})
