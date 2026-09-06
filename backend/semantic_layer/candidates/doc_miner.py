"""Doc Miner — human-authored business documentation → DOC facts.

Sources: knowledge/rules/*.md, knowledge/glossary/*.md, knowledge/metrics/*.md, MDL model/column
descriptions, and portal annotations. Extracts enum glosses ("8 toptan satış"), value-set statements
("satış TRCODE IN (7,8)"), column aliases ("kanal / satış kanalı" = `CLCARD.SPECODE2`) and metric
terms. These are evidence for the engine — a doc alone never certifies a mapping.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

from semantic_layer.history.question_facts import GENERIC_S
from semantic_layer.normalize import METRIC_VOCAB_S, MODIFIERS_S, STOPWORDS_S, fold, stem, tokenize

_ENTITY_WORDS = ("INVOICE", "STLINE", "CLCARD", "ITEMS", "ORFICHE", "ORFLINE", "CLFLINE", "STFICHE", "PAYTRANS")
_ENUM_COLUMNS = ("TRCODE", "LINETYPE", "CANCELLED", "CARDTYPE", "IOCODE", "STATUS", "CLOSED", "BILLED", "GRPCODE", "TRCURR", "EINVOICE", "PROFILEID", "ACTIVE")
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
    extra: dict = field(default_factory=dict)


def _entity_in(text: str) -> Optional[str]:
    up = text.upper()
    hits = [(up.rfind(e), e) for e in _ENTITY_WORDS if e in up]
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


def _enum_facts(text: str, column: str, entity_hint: Optional[str], source: str) -> list[DocFact]:
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


def _in_list_facts(text: str, source: str) -> list[DocFact]:
    """'satış TRCODE IN (7,8)', 'iade (TRCODE IN (2,3))', 'TRCODE 7,8'."""
    out: list[DocFact] = []
    folded = fold(text)
    for m in re.finditer(r"((?:[a-z/]+\s+){0,3}[a-z/]+)\s*[\(=]?\s*\(?\s*(trcode|linetype|cardtype|iocode)\s+(?:in\s*\()?\s*(\d+(?:\s*\([^)]*\))?(?:\s*(?:,|/|ve|veya)\s*\d+(?:\s*\([^)]*\))?)*)\)?", folded):
        phrase, col, vals = m.group(1), m.group(2).upper(), m.group(3)
        values = _split_values(vals)
        if not values:
            continue
        entity = _entity_in(text[: m.start()]) or None
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


def _metric_facts(text: str, source: str) -> list[DocFact]:
    """'## net_ciro' headings and '"iade oranı (adet)" = …' definitions → METRIC term facts."""
    out: list[DocFact] = []
    for m in re.finditer(r"^##\s+([^\n]+)$", text, re.M):
        head = m.group(1).strip()
        key = " ".join(stem(x) for x in tokenize(head.replace("_", " ")) if stem(x) not in STOPWORDS_S)
        body = text[m.end(): m.end() + 400]
        if key and any(w in METRIC_VOCAB_S for w in key.split()):
            out.append(DocFact("metric", key, source, _entity_in(body), None, (), body.strip()[:160]))
    for m in re.finditer(r"[\"“]([^\"”]{2,60})[\"”]\s*=\s*(Σ|SUM|COUNT|1 −|1 -)", text):
        key = " ".join(stem(x) for x in tokenize(m.group(1)) if stem(x) not in STOPWORDS_S)
        if key:
            out.append(DocFact("metric", key, source, _entity_in(text[m.start(): m.start() + 200]), None, (), text[m.start(): m.start() + 160]))
    return out


def mine_text(text: str, source: str, entity_hint: Optional[str] = None) -> list[DocFact]:
    facts: list[DocFact] = []
    for col in _ENUM_COLUMNS:
        if col in text:
            facts.extend(_enum_facts(text, col, entity_hint, source))
    facts.extend(_in_list_facts(text, source))
    facts.extend(_column_alias_facts(text, source))
    facts.extend(_metric_facts(text, source))
    # de-dup
    seen = set()
    out = []
    for f in facts:
        k = (f.kind, f.term, f.entity, f.column, f.values)
        if k not in seen and f.term and not f.term.isdigit():
            seen.add(k)
            out.append(f)
    return out


def mine_project_docs(project_dir: Path) -> list[DocFact]:
    facts: list[DocFact] = []
    for sub in ("rules", "glossary", "metrics", "caveats"):
        for f in sorted((project_dir / "knowledge" / sub).glob("*.md")):
            facts.extend(mine_text(f.read_text(encoding="utf-8"), f"doc:{sub}/{f.name}"))
    return facts


def mine_profiles(profiles: Iterable) -> list[DocFact]:
    """MDL/column descriptions carried in SchemaProfile → facts scoped to the entity."""
    facts: list[DocFact] = []
    for p in profiles:
        if p.description:
            facts.extend(mine_text(p.description, f"model:{p.entity}", p.entity))
        for c in p.columns:
            if c.description and c.name.upper() in _ENUM_COLUMNS:
                facts.extend(mine_text(f"{c.name}: {c.description}", f"model:{p.entity}.{c.name}", p.entity))
    return facts


def mine_annotation(text: str, entity: str, column: Optional[str], source: str) -> list[DocFact]:
    """Portal annotation text ("8 = toptan satış, 7 = perakende satış" or free text)."""
    prefixed = f"{column}: {text}" if column else text
    facts = mine_text(prefixed, source, entity)
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
