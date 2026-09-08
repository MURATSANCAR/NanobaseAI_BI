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
