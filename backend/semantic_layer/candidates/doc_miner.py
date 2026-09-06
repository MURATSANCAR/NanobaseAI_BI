"""Doc Miner — human-authored business documentation → DOC facts.

Sources: knowledge/rules/*.md, knowledge/glossary/*.md, knowledge/metrics/*.md, MDL model/column
descriptions, and portal annotations. Extracts enum glosses ("8 toptan satış"), value-set statements
("satış <kod kolonu> IN (…)"), column aliases ("kanal / satış kanalı" = `<TABLO>.<KOLON>`) and metric
terms. These are evidence for the engine — a doc alone never certifies a mapping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from semantic_layer.history.question_facts import GENERIC_S
from semantic_layer.normalize import METRIC_VOCAB_S, MODIFIERS_S, STOPWORDS_S, fold, stem, tokenize

_LABEL_GENERIC = frozenset(stem(w) for w in "satis satisi fatura faturasi faturalari belge belgesi kart karti satir satiri".split())


@dataclass
class DocFact:
    kind: str                      # value | column | metric | entity
    term: str
    source: str
    entity: Optional[str] = None
    column: Optional[str] = None
    values: tuple[str, ...] = ()
    snippet: str = ""
    operator: str = "IN"
    extra: dict = field(default_factory=dict)


def _entity_in(text: str, entities: Iterable[str] = ()) -> Optional[str]:
    """The entity a documentation sentence is about: the profiled entity mentioned last before it."""
    up = text.upper()
    hits = [(up.rfind(e), e) for e in entities if e and e in up]
    if not hits:
        return None
    return max(hits)[1]


def _label_terms(label: str) -> list[str]:
    """'toptan satış iadesi' → ['toptan satis iadesi', 'toptan iade']; 'perakende satış' → ['perakende satis', 'perakende']."""
    toks = [stem(t) for t in tokenize(label) if stem(t) not in STOPWORDS_S]
    if not toks:
        return []
    full = " ".join(toks)
    specific = [t for t in toks if t not in _LABEL_GENERIC and t not in MODIFIERS_S]
    out = [full]
    if specific and specific != toks:
        out.append(" ".join(specific))
    return list(dict.fromkeys(out))


def _split_values(raw: str) -> tuple[str, ...]:
    vals = re.findall(r"-?\d+", raw)
    return tuple(sorted(set(vals), key=lambda v: float(v)))


def _enum_facts(text: str, column: str, entity_hint: Optional[str], source: str, entities: Iterable[str] = ()) -> list[DocFact]:
    """After 'COLUMN' find "N label, N label = GROUP; …" lists."""
    out: list[DocFact] = []
    for m in re.finditer(rf"\b{column}\b[^:\n]{{0,40}}[:)]?\s*([^\n]+)", text):
        tail = m.group(1)
        tail = tail.split(". ")[0]
        entity = _entity_in(text[: m.start()]) or entity_hint
        for group in re.split(r";", tail):
            items = [x.strip() for x in group.split(",") if x.strip()]
            group_label = None
            parsed: list[tuple[str, str]] = []
            for item in items:
                gm = re.match(r"^(.*?)\s*=\s*([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ ]{2,})$", item)
                if gm:
                    item, group_label = gm.group(1).strip(), gm.group(2).strip()
                im = re.match(r"^(-?\d+)\s*[=:]?\s*([A-Za-zÇĞİÖŞÜçğıöşü][^()\[\]·]*?)\s*(?:\(.*\))?$", item)
                if im:
                    parsed.append((im.group(1), im.group(2).strip()))
            for value, label in parsed:
                for term in _label_terms(label):
                    out.append(DocFact("value", term, source, entity, column, (value,), f"{value} {label}"))
            if group_label and parsed:
                for term in _label_terms(group_label):
                    out.append(DocFact("value", term, source, entity, column, tuple(v for v, _ in parsed), group_label))
    return out


def _in_list_facts(text: str, source: str, enum_columns: Iterable[str] = (), entities: Iterable[str] = ()) -> list[DocFact]:
    """'<term> COLUMN IN (7,8)', '<term> (COLUMN 2,3)' for any low-cardinality column in the profile."""
    out: list[DocFact] = []
    cols = sorted({c.lower() for c in enum_columns if len(c) > 2}, key=len, reverse=True)
    if not cols:
        return out
    folded = fold(text)
    pattern = r"((?:[a-z/]+\s+){0,3}[a-z/]+)\s*[\(=]?\s*\(?\s*(" + "|".join(re.escape(c) for c in cols) + r")\s+(?:in\s*\()?\s*(\d+(?:\s*\([^)]*\))?(?:\s*(?:,|/|ve|veya)\s*\d+(?:\s*\([^)]*\))?)*)\)?"
    for m in re.finditer(pattern, folded):
        phrase, col, vals = m.group(1), m.group(2).upper(), m.group(3)
        values = _split_values(vals)
        if not values:
            continue
        entity = _entity_in(text[: m.start()], entities) or None
        words: list[str] = []
        for w in re.split(r"[\s/]+", phrase):
            w = stem(w)
            if w and w not in STOPWORDS_S and w not in MODIFIERS_S and w not in ("soru", "sorularinda", "icin", "olan"):
                words.append(w)
        specific = [w for w in words if w not in _LABEL_GENERIC]
        if len(specific) == 1:
            out.append(DocFact("value", specific[0], source, entity, col, values, m.group(0)[:80]))
        if len(words) >= 2:
            out.append(DocFact("value", " ".join(words[-2:]), source, entity, col, values, m.group(0)[:80]))
    return out


_CODE = re.compile(r"^[A-ZÇĞİÖŞÜ0-9][A-ZÇĞİÖŞÜ0-9._\-]{1,24}$")
_VALUES_LABEL = re.compile(r"\b([A-Z_][A-Z0-9_]{2,})\s*=\s*([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ ]{2,40}?)\s*\(([^)]{5,200})\)")
_VALUES_COLON = re.compile(r"\b([A-Z_][A-Z0-9_]{2,})\s*:\s*([A-ZÇĞİÖŞÜ0-9][^.\n]{5,200})")


def _code_list(raw: str) -> tuple[str, ...]:
    """'KITAPCI, E-TICARET, DAGITICI, ...' → codes; prose and ellipses are dropped."""
    out = []
    for part in re.split(r"[,;]", raw):
        token = part.strip().strip('"\u201c\u201d').rstrip(".").strip()
        if token and _CODE.match(token) and not token.isdigit():
            out.append(token)
    return tuple(dict.fromkeys(out))


def _column_values_facts(text: str, source: str, entity_hint: Optional[str] = None, entities: Iterable[str] = ()) -> list[DocFact]:
    """Documented value inventories for a text column:
       'SPECODE2 = SATIŞ KANALI (KITAPCI, E-TICARET, DAGITICI...)' and 'SPECODE2: KITAPCI, E-TICARET, ...'
    The codes become the column's documented value list (DOC evidence), so a question naming one of them
    resolves without waiting for a live value probe."""
    out: list[DocFact] = []
    for m in _VALUES_LABEL.finditer(text):
        column, label, raw = m.group(1).upper(), m.group(2).strip(), m.group(3)
        codes = _code_list(raw)
        if len(codes) < 2:
            continue
        entity = _entity_in(text[: m.start()], entities) or entity_hint
        for term in _label_terms(label):
            out.append(DocFact("column", term, source, entity, column, (), m.group(0)[:120], extra={"documented_values": list(codes)}))
    for m in _VALUES_COLON.finditer(text):
        column, raw = m.group(1).upper(), m.group(2)
        codes = _code_list(raw)
        if len(codes) < 2:
            continue
        entity = _entity_in(text[: m.start()], entities) or entity_hint
        out.append(DocFact("column_values", column.lower(), source, entity, column, (), m.group(0)[:120], extra={"documented_values": list(codes)}))
    return out


_COMPARISON = re.compile(r"`(?:([A-Z_][A-Z0-9_]*)\.)?([A-Z_][A-Z0-9_]{2,})\s*(<>|!=|=)\s*(-?\d+)`\s*\(([^)]{3,60})\)")


def _comparison_facts(text: str, source: str, entities: Iterable[str] = ()) -> list[DocFact]:
    """'`OUTCOST <> 0` (maliyetlendirilmiş satır) varsayılan' → value fact with the stated operator."""
    out: list[DocFact] = []
    for m in _COMPARISON.finditer(text):
        entity, column, op, value, label = m.groups()
        terms = _label_terms(label)
        if not terms:
            continue
        op = "<>" if op in ("<>", "!=") else "IN"
        for term in terms:
            out.append(DocFact("value", term, source, (entity or "").upper() or _entity_in(text[: m.start()], entities), column.upper(), (value,), m.group(0)[:100], operator=op))
    return out


def _column_alias_facts(text: str, source: str) -> list[DocFact]:
    """'"kanal / satış kanalı" = faturanın carisindeki `CLCARD.SPECODE2`' → COLUMN facts (terms declared together are synonyms)."""
    out: list[DocFact] = []
    pattern = re.compile(r"[\"\u201c]([^\"\u201d]{2,80})[\"\u201d]\s*=[^`\n]{0,60}?`([A-Z_][A-Z0-9_]*)\.([A-Z_][A-Z0-9_]*)`")
    for m in pattern.finditer(text):
        terms, entity, column = m.group(1), m.group(2).upper(), m.group(3).upper()
        group = []
        for t in re.split(r"\s*/\s*", terms):
            key = " ".join(stem(x) for x in tokenize(t) if stem(x) not in STOPWORDS_S)
            if key:
                group.append(key)
        for key in group:
            out.append(DocFact("column", key, source, entity, column, (), m.group(0)[:100], extra={"synonyms": [g for g in group if g != key]}))
    return out


def _metric_facts(text: str, source: str, entities: Iterable[str] = ()) -> list[DocFact]:
    """'## net_ciro' headings and '"iade oranı (adet)" = …' definitions → METRIC term facts."""
    out: list[DocFact] = []
    for m in re.finditer(r"^##\s+([^\n]+)$", text, re.M):
        head = m.group(1).strip()
        key = " ".join(stem(x) for x in tokenize(head.replace("_", " ")) if stem(x) not in STOPWORDS_S)
        body = text[m.end(): m.end() + 400]
        if key and any(w in METRIC_VOCAB_S for w in key.split()):
            out.append(DocFact("metric", key, source, _entity_in(body, entities), None, (), body.strip()[:160]))
    for m in re.finditer(r"[\"“]([^\"”]{2,60})[\"”]\s*=\s*(Σ|SUM|COUNT|1 −|1 -)", text):
        key = " ".join(stem(x) for x in tokenize(m.group(1)) if stem(x) not in STOPWORDS_S)
        if key:
            out.append(DocFact("metric", key, source, _entity_in(text[m.start(): m.start() + 200], entities), None, (), text[m.start(): m.start() + 160]))
    return out


def mine_text(text: str, source: str, entity_hint: Optional[str] = None, conventions: Any = None) -> list[DocFact]:
    """Documentation → facts. Which columns carry value glosses and which words name an entity is
    read from the profile (`conventions`), never from a built-in list of customer column names."""
    entities = list(getattr(conventions, "entities", ()) or ())
    enum_columns = {c for cols in (getattr(conventions, "enum_columns", {}) or {}).values() for c in cols}
    facts: list[DocFact] = []
    for col in sorted(enum_columns):
        if col in text:
            facts.extend(_enum_facts(text, col, entity_hint, source, entities))
    facts.extend(_in_list_facts(text, source, enum_columns, entities))
    facts.extend(_comparison_facts(text, source, entities))
    facts.extend(_column_values_facts(text, source, entity_hint, entities))
    facts.extend(_column_alias_facts(text, source))
    facts.extend(_metric_facts(text, source, entities))
    # de-dup
    seen = set()
    out = []
    for f in facts:
        k = (f.kind, f.term, f.entity, f.column, f.values, f.operator, tuple(f.extra.get("documented_values") or ()))
        if k not in seen and f.term and not f.term.isdigit():
            seen.add(k)
            out.append(f)
    return out


def mine_project_docs(project_dir: Path, conventions: Any = None) -> list[DocFact]:
    """Operator documentation shipped with the deployment (any *.md under knowledge/)."""
    facts: list[DocFact] = []
    root = project_dir / "knowledge"
    if not root.exists():
        return facts
    for f in sorted(root.rglob("*.md")):
        if f.parent.name == "sql":       # validated Q→SQL pairs are the miner's input, not prose
            continue
        facts.extend(mine_text(f.read_text(encoding="utf-8"), f"doc:{f.parent.name}/{f.name}", None, conventions))
    return facts


def mine_profiles(profiles: Iterable, conventions: Any = None) -> list[DocFact]:
    """Column/table descriptions carried by the source itself → facts scoped to the entity."""
    facts: list[DocFact] = []
    enum_columns = {c for cols in (getattr(conventions, "enum_columns", {}) or {}).values() for c in cols}
    for p in profiles:
        if p.description:
            facts.extend(mine_text(p.description, f"model:{p.entity}", p.entity, conventions))
        for c in p.columns:
            if c.description and (not enum_columns or c.name.upper() in enum_columns):
                facts.extend(mine_text(f"{c.name}: {c.description}", f"model:{p.entity}.{c.name}", p.entity, conventions))
    return facts


def mine_annotation(text: str, entity: str, column: Optional[str], source: str, conventions: Any = None) -> list[DocFact]:
    """Portal annotation text ("8 = wholesale, 7 = retail" or free prose)."""
    prefixed = f"{column}: {text}" if column else text
    facts = mine_text(prefixed, source, entity, conventions)
    for f in facts:
        f.entity = f.entity or entity
        if column and f.kind == "value" and not f.column:
            f.column = column
    if not facts and column:
        # free-text description: the column itself gets a COLUMN fact from the first noun phrase
        key = " ".join(stem(x) for x in tokenize(text)[:3] if stem(x) not in STOPWORDS_S)
        if key:
            facts.append(DocFact("column", key, source, entity, column, (), text[:120]))
    return facts
