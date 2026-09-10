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
    # These are explicit editing commands, not a semantic vocabulary or a fuzzy intent match.
    edit = re.sub(r"^(?:bunu|bunu da)\s+", "", text)
    monthly = edit in {"aylara bol", "aylik goster", "ay bazinda goster"}
    ranking = re.fullmatch(r"ilk (\d{1,3})(?:'?[ui])? goster", edit)
    compare = edit in {"gecen yilla karsilastir", "gecen yila gore karsilastir"}
    if monthly or ranking or compare:
        if previous is None:
            return None, "Önce bir analiz çalıştırın; hangi sonucu değiştireceğim belli değil."
        base = fold(previous.question)
        if monthly:
            base = re.sub(r"\b(?:gunluk|haftalik|yillik|aylik)\b", " ", base)
            return " ".join((base + " aylık").split()), None
        if ranking:
            limit = int(ranking.group(1))
            if not 1 <= limit <= 100:
                return None, "İlk kaç kayıt gösterilsin? 1 ile 100 arasında bir sayı belirtin."
            base = re.sub(r"\b(?:ilk|top)\s+\d+\b", " ", base)
            return " ".join((base + f" ilk {limit}").split()), None
        periods = [p for p in previous.temporal if p.start and p.end]
        if len(periods) != 1 or periods[0].primitive != "YEAR":
            return None, "Yıllık karşılaştırma için önce tek bir yılı içeren analiz seçin."
        period = periods[0]
        if period.start.month != 1 or period.start.day != 1 or period.end.year != period.start.year + 1:
            return None, "Hangi iki dönemi karşılaştırmak istediğinizi açıkça belirtin."
        base = re.sub(r"(?<!\w)" + re.escape(fold(period.text)) + r"(?!\w)", " ", base)
        year = period.start.year
        return " ".join((base + f" {year} ve {year - 1} karşılaştır").split()), None
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
