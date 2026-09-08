"""Compose explicit follow-up edits from the last successful semantic plan.

Re-resolve the composed question so coverage, catalog provenance and obligations
are calculated afresh. Never inherit context for a new standalone question.
"""
import re
from semantic_layer.normalize import fold
from semantic_layer.runtime.temporal import parse_temporal


def compose_followup(question, previous):
    text = fold(question).strip(" ?.! ")
    text = re.sub(r"^(?:peki|ya)\s+", "", text)
    periods, _ = parse_temporal(text)
    remainder = text
    for period in periods:
        remainder = remainder.replace(fold(period.text), " ")
    temporal_only = bool(periods) and not remainder.strip(" ?.! ")
    filter_only = text.startswith("sadece ")
    if not (temporal_only or filter_only):
        return question, None
    if previous is None:
        return None, "Önceki sorunun bağlamı yok. Ölçüyü ve kırılımı da içeren tam soruyu yazar mısınız?"
    base = fold(previous.question)
    if temporal_only:
        for period in previous.temporal:
            base = re.sub(r"(?<!\w)" + re.escape(fold(period.text)) + r"(?!\w)", " ", base)
        # A single-period follow-up replaces a comparison, rather than leaving its cue behind.
        base = re.sub(r"\b(?:gore|kiyasla|karsi|nazaran|oranla)\b", " ", base) if previous.comparison else base
        return " ".join((base + " " + text).split()), None
    return " ".join((base + " " + text).split()), None


def bind_followup_value(question, sq, previous, probe, columns, conventions):
    """An exact, unique value in the previous plan's entities may fill a filter.

    A substring hit or competing column is not evidence of one specific filter.
    This is an inferred query binding, never a catalog certification.
    """
    from semantic_layer.models import Mapping, ResolvedSlot
    text = fold(question).strip(" ?.! ")
    if not text.startswith("sadece ") or previous is None or probe is None:
        return
    term = text[len("sadece "):].strip()
    if term not in [fold(w) for w in sq.unresolved]:
        return
    entities = sorted({s.mapping.entity for s in previous.slots if s.mapping})
    try:
        hits = probe.find(term, entities, columns, sq.question)
    except Exception:
        sq.clarification.append("Filtre değeri doğrulanamadı. Hangi alanı filtrelemek istediğinizi belirtir misiniz?")
        return
    exact = {(h.entity,h.column,h.value) for h in hits if fold(h.value) == term and h.entity in entities}
    if len(exact) != 1:
        sq.clarification.append(f"'{term}' hangi alanın değeri? Tek bir kesin eşleşme doğrulanamadı.")
        return
    entity,column,value = next(iter(exact))
    sq.slots = [s for s in sq.slots if not (s.semantic_type == "DIMENSION_VALUE" and s.mapping and
                s.mapping.entity == entity and s.mapping.column == column)]
    sq.slots.append(ResolvedSlot(term,"DIMENSION_VALUE","INFERRED",mapping=Mapping("",entity,
                    conventions.patterns[entity],column=column,operator="=",values=[value]),
                    explain={"source":"exact_scoped_value_probe","value":value}))
    sq.unresolved = [w for w in sq.unresolved if fold(w) != term]
    sq.explanation.append(f"'{term}' önceki planın {entity}.{column} alanında tek tam değer eşleşmesiyle bağlandı.")
