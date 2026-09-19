"""Automatic approval for generated vocabulary — only for a term that has been measured to work.

A proposed term is added to the resolver *in memory only* and then questioned:

1. **It leads to its own field.** Every example sentence generated with the term that actually
   contains it is resolved; each must produce a slot on the term's entity (and column). At least one
   such example must exist — a term never tried is not a term that works.
2. **It takes nothing away.** Every question already asked on this deployment that contains the term
   is resolved before and after. Everything the question resolved to before must still be there
   after; the term may only add meaning to words that had none.
3. **It means one thing.** A term proposed or approved for more than one field, or already the name
   of a certified concept somewhere else, is never decided by a machine.
4. **It is a machine's to decide at all** (`not_for_a_machine`). One word, a term its generator
   flagged as confusable, a name for a table's own key, and a name on a table with no rows are a
   person's decision however well they measure. Measured on 1,100 labelled questions (2026-09-19):
   335 one-word approvals out of 7,751 carried 41 of the 62 ERP questions that were read against the
   CRM — "tahsil edilmemiş alacak" went to a contact's education column, "ödeme" to one CRM table —
   because the examples a term is measured on are written for the term, and ordinary speech is not.

A term that passes is approved through `vocabulary.decide`, the same path a person's yes takes, with
the measurement as the note. Everything else stays PROPOSED for a person, with the reason written on
the row. Nothing here names a table, a column or a word: the fields, the examples and the questions
all come from the catalog and the query log.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date
from functools import lru_cache
from typing import Any, Iterable, Optional

import sqlalchemy as sa

from semantic_layer import vocabulary as V
from semantic_layer.models import Concept, ConceptStatus, Mapping, SemanticType
from semantic_layer.normalize import normalize_term
from semantic_layer.store import schema as S

log = logging.getLogger(__name__)

AUTO = "otomatik-yoklama"
#: A reason written by a probe, not by the generator: the row is measured again on the next run.
PREFIX = "yoklama: "


class _WithTerm:
    """The catalog store, with one extra certified entry visible to the resolver."""

    def __init__(self, store, extra: dict[str, list]):
        self._store, self._extra = store, extra

    def __getattr__(self, name):
        return getattr(self._store, name)

    def certified_index(self, tenant_id: str, datasource_id: str):
        base = self._store.certified_index(tenant_id, datasource_id)
        if not self._extra:
            return base
        merged = dict(base)
        for key, entries in self._extra.items():
            merged[key] = list(base.get(key, [])) + entries
        return merged


def _entry(settings, profiles, row: dict[str, Any]) -> tuple[str, list]:
    entity, column = row["entity"], row["column_name"]
    norm = row["normalized"]
    prof = next((p for p in profiles if p.entity == entity), None)
    semantic_type = SemanticType.COLUMN if column else SemanticType.ENTITY
    concept = Concept(settings.tenant_id, settings.datasource_id, row["term"], norm, semantic_type,
                      status=ConceptStatus.CERTIFIED, confidence=1.0)
    mapping = Mapping(concept.id, entity, prof.table_pattern if prof else entity, column=column,
                      operator="COLUMN" if column else None)
    return norm, [(concept, [mapping])]


def _mapped(sq) -> set[tuple[str, Optional[str]]]:
    out = set()
    for slot in list(sq.slots) + list(sq.group_by):
        m = slot.mapping
        if m is not None:
            out.add((m.entity, (m.column or "").upper() or None))
    return out


def _leads_to_field(sq, entity: str, column: Optional[str]) -> bool:
    for (e, c) in _mapped(sq):
        if e == entity and (column is None or c == column.upper()):
            return True
    return False


@lru_cache(maxsize=None)
def _padded(text: str) -> str:
    # every pending row is looked for in every question ever asked: normalise each question once
    return f" {normalize_term(text)} "


def _contains(text: str, norm: str) -> bool:
    return f" {norm} " in _padded(text)


def not_for_a_machine(row: dict[str, Any], profiles) -> Optional[str]:
    """Why this row is a person's decision whatever the measurement says, or None. Row and profile
    only — no resolver — so the same rule re-judges approvals a machine has already made."""
    if len((row.get("normalized") or "").split()) < 2:
        return "tek kelime: gündelik dilde başka anlamlara da gelir; kararı bir kişi verir"
    note = row.get("generator_note")
    if note:
        return f"üretici karışabileceğini yazdı ({note}); kararı bir kişi verir"
    prof = next((p for p in profiles if p.entity == row["entity"]), None)
    if prof is not None:
        column = (row.get("column_name") or "").upper()
        if column and column in {k.upper() for k in (prof.primary_key or [])}:
            return "tablonun kendi anahtarı: sorulan bir iş alanı değil; kararı bir kişi verir"
        if prof.row_count == 0:
            return "tabloda satır yok: kullanılmayan alanın adı ölçülemez; kararı bir kişi verir"
    return None


def _generator_note(row: dict[str, Any]) -> Optional[str]:
    """What the generator wrote beside a pending row. A probe's own reason (PREFIX) is not one."""
    reason = str(row.get("reason") or "").strip()
    return None if not reason or reason.startswith(PREFIX) or reason.startswith("{") else reason


def ambiguous_terms(store, settings) -> dict[str, int]:
    """normalized term → how many different fields it is proposed or approved for."""
    stmt = (sa.select(S.sl_vocabulary.c.normalized, S.sl_vocabulary.c.entity, S.sl_vocabulary.c.column_name)
            .where(S.sl_vocabulary.c.tenant_id == settings.tenant_id, S.sl_vocabulary.c.datasource_id == settings.datasource_id,
                   S.sl_vocabulary.c.status.in_((V.PROPOSED, V.APPROVED))))
    fields: dict[str, set] = defaultdict(set)
    with store.engine.connect() as conn:
        for norm, entity, column in conn.execute(stmt):
            fields[norm].add((entity, column))
    return {k: len(v) for k, v in fields.items()}


def asked_questions(store, settings) -> list[str]:
    stmt = (sa.select(S.sl_query_log.c.question).distinct()
            .where(S.sl_query_log.c.tenant_id == settings.tenant_id, S.sl_query_log.c.datasource_id == settings.datasource_id))
    with store.engine.connect() as conn:
        return [q for (q,) in conn.execute(stmt) if q]


def probe(store, settings, profiles, row: dict[str, Any], *, resolver_factory, questions: Iterable[str],
          fields_per_term: dict[str, int], today: Optional[date] = None) -> dict[str, Any]:
    """Measure one proposed row. Returns {"ok": bool, "reason": str, "evidence": {...}}."""
    entity, column, norm = row["entity"], row["column_name"], row["normalized"]
    if row["source"] != V.GENERATED or row["status"] != V.PROPOSED:
        return {"ok": False, "reason": "yalnız bekleyen üretilmiş öneriler ölçülür", "evidence": {}}
    unfit = not_for_a_machine({**row, "generator_note": _generator_note(row)}, profiles)
    if unfit:
        return {"ok": False, "reason": unfit, "evidence": {}}
    if fields_per_term.get(norm, 0) > 1:
        return {"ok": False, "reason": f"aynı terim {fields_per_term[norm]} farklı alana önerildi; seçimi bir kişi yapar", "evidence": {}}
    why = V.refute(row["term"], entity, column, index=store.certified_index(settings.tenant_id, settings.datasource_id), profiles=profiles)
    if why:
        return {"ok": False, "reason": why, "evidence": {}}

    key, entries = _entry(settings, profiles, row)
    plain = resolver_factory(store)
    augmented = resolver_factory(_WithTerm(store, {key: entries}))

    examples = [e for e in (row.get("examples_json") or []) if isinstance(e, str) and _contains(e, norm)]
    if not examples:
        return {"ok": False, "reason": "terimi içeren örnek soru yok; ölçülemedi", "evidence": {}}
    misses = []
    for text in examples:
        if not _leads_to_field(augmented.resolve(text, today=today), entity, column):
            misses.append(text)
    if misses:
        return {"ok": False, "reason": f"örnek soru alana gitmedi: {misses[0]}",
                "evidence": {"examples": len(examples), "missed": misses}}

    broke = []
    checked = 0
    for q in questions:
        if not _contains(q, norm):
            continue
        checked += 1
        before, after = _mapped(plain.resolve(q, today=today)), _mapped(augmented.resolve(q, today=today))
        if not before <= after:
            broke.append({"question": q, "lost": sorted(f"{e}.{c or ''}" for e, c in before - after)})
    if broke:
        return {"ok": False, "reason": f"geçmiş bir sorunun anlamını değiştiriyor: {broke[0]['question']}",
                "evidence": {"examples": len(examples), "askedChecked": checked, "broke": broke}}
    return {"ok": True, "reason": "", "evidence": {"examples": len(examples), "askedChecked": checked}}


def auto_decide(store, settings, profiles, engine, *, resolver_factory, entities: Optional[Iterable[str]] = None,
                apply: bool = True, today: Optional[date] = None, shard: tuple[int, int] = (0, 1)) -> dict[str, Any]:
    """Probe every pending generated row (optionally only these entities); approve the ones that pass.
    Rows that fail keep PROPOSED and get the measured reason, so the screen shows why a person is asked."""
    V.ensure_table(store.engine)
    wanted = set(entities) if entities else None
    stmt = sa.select(S.sl_vocabulary).where(
        S.sl_vocabulary.c.tenant_id == settings.tenant_id, S.sl_vocabulary.c.datasource_id == settings.datasource_id,
        S.sl_vocabulary.c.status == V.PROPOSED, S.sl_vocabulary.c.source == V.GENERATED)
    with store.engine.connect() as conn:
        rows = [dict(r._mapping) for r in conn.execute(stmt)]
    if wanted:
        rows = [r for r in rows if r["entity"] in wanted]
    index, count = shard
    if count > 1:
        # split by the row's own id so several processes measure disjoint rows; each still sees the
        # whole vocabulary when it asks whether a term means more than one thing.
        rows = [r for r in rows if int(r["id"][-8:], 16) % count == index]
    fields_per_term = ambiguous_terms(store, settings)
    questions = asked_questions(store, settings)
    summary = {"probed": 0, "approved": 0, "toPerson": 0, "reasons": defaultdict(int)}
    for row in rows:
        summary["probed"] += 1
        result = probe(store, settings, profiles, row, resolver_factory=resolver_factory, questions=questions,
                       fields_per_term=fields_per_term, today=today)
        if result["ok"]:
            summary["approved"] += 1
            if apply:
                note = json.dumps({"yoklama": result["evidence"]}, ensure_ascii=False)
                V.decide(store, settings, profiles, engine, row["id"], "APPROVE", AUTO, note)
            continue
        summary["toPerson"] += 1
        summary["reasons"][result["reason"].split(":")[0]] += 1
        measured = PREFIX + result["reason"]
        generator_said = row.get("reason") and not str(row["reason"]).startswith(PREFIX)
        if apply and not generator_said and measured != (row.get("reason") or ""):
            with store.engine.begin() as conn:
                conn.execute(S.sl_vocabulary.update().where(S.sl_vocabulary.c.id == row["id"])
                             .values(reason=measured[:500], updated_at=V._now()))
    summary["reasons"] = dict(summary["reasons"])
    return summary


def recheck(store, settings, profiles, *, apply: bool = True) -> dict[str, Any]:
    """Approvals a machine made, judged again by `not_for_a_machine`; the ones it may not make are taken
    back to PROPOSED with the reason, for a person. A person's approvals are never read here."""
    V.ensure_table(store.engine)
    stmt = sa.select(S.sl_vocabulary).where(
        S.sl_vocabulary.c.tenant_id == settings.tenant_id, S.sl_vocabulary.c.datasource_id == settings.datasource_id,
        S.sl_vocabulary.c.status == V.APPROVED, S.sl_vocabulary.c.decided_by == AUTO)
    with store.engine.connect() as conn:
        rows = [dict(r._mapping) for r in conn.execute(stmt)]
    summary: dict[str, Any] = {"checked": len(rows), "withdrawn": 0, "reasons": defaultdict(int), "concepts": defaultdict(int)}
    for row in rows:
        # the generator's note was overwritten by the measurement when the row was approved
        why = not_for_a_machine({**row, "generator_note": None}, profiles)
        if not why:
            continue
        summary["withdrawn"] += 1
        summary["reasons"][why.split(":")[0]] += 1
        if apply:
            out = V.withdraw(store, settings, row["id"], PREFIX + why)
            summary["concepts"][out["concept"]] += 1
    summary["reasons"], summary["concepts"] = dict(summary["reasons"]), dict(summary["concepts"])
    return summary


__all__ = ["probe", "auto_decide", "recheck", "not_for_a_machine", "ambiguous_terms", "AUTO"]
