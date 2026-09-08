"""Plain dataclasses shared by every layer (no ORM objects leak across boundaries)."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Optional


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- catalog entities

class SemanticType:
    DIMENSION_VALUE = "DIMENSION_VALUE"   # toptan → INVOICE.TRCODE IN (8)
    METRIC = "METRIC"                     # net ciro → formula
    DEFAULT_FILTER = "DEFAULT_FILTER"     # CANCELLED = 0 on INVOICE
    TEMPORAL = "TEMPORAL"                 # son 30 gün → LAST_N_DAYS(30)
    ENTITY = "ENTITY"                     # fatura → INVOICE
    COLUMN = "COLUMN"                     # kanal → CLCARD.SPECODE2
    RELATIONSHIP = "RELATIONSHIP"         # STLINE.CLIENTREF → CLCARD.LOGICALREF
    ALL = (DIMENSION_VALUE, METRIC, DEFAULT_FILTER, TEMPORAL, ENTITY, COLUMN, RELATIONSHIP)


class ConceptStatus:
    DISCOVERED = "DISCOVERED"
    CANDIDATE = "CANDIDATE"
    CERTIFIED = "CERTIFIED"
    REJECTED = "REJECTED"
    SENSE_CONFLICT = "SENSE_CONFLICT"
    DEPRECATED = "DEPRECATED"
    ALL = (DISCOVERED, CANDIDATE, CERTIFIED, REJECTED, SENSE_CONFLICT, DEPRECATED)


class EvidenceType:
    VALIDATED_SQL = "VALIDATED_SQL"         # term co-occurs with predicate in a validated Q→SQL pair
    ALIAS_BINDING = "ALIAS_BINDING"         # SQL alias tokens name the term (perakende_toplam ↔ TRCODE=7)
    EXPLICIT_BINDING = "EXPLICIT_BINDING"   # question literally says "toptan (TRCODE 8)"
    DOC = "DOC"                             # rules / glossary / column description
    PROFILE = "PROFILE"                     # value exists in column profile
    HUMAN_ANNOTATION = "HUMAN_ANNOTATION"   # portal user text
    EXECUTION = "EXECUTION"                 # executed successfully / consistent results
    LLM_CANDIDATE = "LLM_CANDIDATE"         # Qwen proposal (never certifies on its own)


@dataclass
class Mapping:
    concept_id: str
    entity: str                       # INVOICE, STLINE, CLCARD, ITEMS …
    table_pattern: str                # LG_{firm}_{period}_INVOICE
    column: Optional[str] = None
    operator: Optional[str] = None    # IN, =, <>, NOT IN, BETWEEN
    values: list[str] = field(default_factory=list)
    formula: Optional[str] = None     # metric expression over ENTITY.COLUMN refs
    time_primitive: Optional[str] = None
    extra: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: new_id("map"))

    def key(self) -> str:
        if self.formula:
            return f"{self.entity}:{self.formula}"
        return f"{self.entity}.{self.column} {self.operator} {','.join(sorted(self.values))}"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Concept:
    tenant_id: str
    datasource_id: str
    term: str
    normalized_term: str
    semantic_type: str
    domain: str = "general"
    sense_id: int = 1
    status: str = ConceptStatus.DISCOVERED
    confidence: float = 0.0
    version: int = 1
    synonyms: list[str] = field(default_factory=list)
    explain: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: new_id("sem"))
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        d["updated_at"] = self.updated_at.isoformat()
        return d


@dataclass
class Evidence:
    concept_id: str
    evidence_type: str
    source_id: str
    support_count: int = 1
    weight: float = 1.0
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: new_id("ev"))
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class CounterEvidence:
    concept_id: str
    source_id: str
    conflict_type: str               # VALUE_MISMATCH | COLUMN_MISMATCH | DRIFT | HUMAN_REJECT
    payload: dict[str, Any] = field(default_factory=dict)
    severity: str = "MEDIUM"         # LOW | MEDIUM | BLOCKING
    id: str = field(default_factory=lambda: new_id("cev"))
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class Candidate:
    concept_id: str
    generated_by: str                # history_miner | profiler | doc_miner | qwen | human
    payload: dict[str, Any] = field(default_factory=dict)
    model_version: Optional[str] = None
    status: str = "OPEN"             # OPEN | ACCEPTED | REJECTED
    id: str = field(default_factory=lambda: new_id("cand"))
    created_at: datetime = field(default_factory=utcnow)


@dataclass
class Annotation:
    datasource_id: str
    table_pattern: str
    text: str
    column: Optional[str] = None
    author: str = "portal"
    status: str = "ACTIVE"
    id: str = field(default_factory=lambda: new_id("ann"))
    created_at: datetime = field(default_factory=utcnow)


# ---------------------------------------------------------------- schema profile

@dataclass
class ColumnProfile:
    name: str
    data_type: str = ""
    nullable: bool = True
    distinct_count: Optional[int] = None
    top_values: list[tuple[str, int]] = field(default_factory=list)   # (value, count)
    null_ratio: Optional[float] = None
    is_primary_key: bool = False
    ref_entity: Optional[str] = None      # a reference column and the entity it points at
    ref_column: Optional[str] = None
    # Three different people can have something to say about one column, and none of them may
    # overwrite another: the source's own comment is what the customer wrote, `derived` is what this
    # system concluded from the data, and a portal annotation lives in its own table with its author.
    description: Optional[str] = None     # the source's own words — a database comment or model export
    # What this system concluded, each entry tagged with where it came from. Two different kinds live
    # here: a reading of what the column *means* (a third-party glossary), which a person's own words
    # override, and a fact about the data (how far it is populated), which is true regardless of who
    # described the column and is therefore always reported.
    derived: list[dict[str, str]] = field(default_factory=list)
    sensitive: bool = False               # personal data: never sampled, never shown, never sent to a model
    sensitivity_reason: Optional[str] = None
    sentinel_values: list[str] = field(default_factory=list)  # values that mean "absent" (0 on a reference, …)
    unit: Optional[str] = None            # documented unit/basis ("KDV dahil", "birim maliyet"): guards mixing

    def is_enum(self) -> bool:
        return bool(self.top_values) and (self.distinct_count or 0) <= 64

    #: derived entries that describe the data rather than define the column
    FACTS = ("freshness",)

    def add_derived(self, source: str, text: str) -> None:
        if text and not any(d.get("text") == text for d in self.derived):
            self.derived.append({"source": source, "text": text})

    def meaning(self, annotation: Optional[str] = None) -> Optional[str]:
        """What this column means, and whose account of it that is.

        A person who wrote it down in the portal is the last word; failing that, whatever the database
        itself says; failing that, what this system worked out. They are never merged — one of them is
        the answer and the others stay visible elsewhere.
        """
        if annotation:
            return annotation
        if self.description:
            return self.description
        return next((d["text"] for d in self.derived if d.get("source") not in self.FACTS), None)

    def data_facts(self) -> list[str]:
        """Things measured about the data, true no matter who described the column."""
        return [d["text"] for d in self.derived if d.get("source") in self.FACTS]

    def meaningful_values(self) -> list[tuple[str, int]]:
        """Observed values with the sentinels removed — what a business term may actually mean."""
        return [(v, n) for v, n in self.top_values if v not in self.sentinel_values]


@dataclass
class SchemaProfile:
    datasource_id: str
    table_name: str                   # LG_411_01_INVOICE
    table_pattern: str                # LG_{firm}_{period}_INVOICE
    entity: str                       # INVOICE
    schema_name: str = ""
    columns: list[ColumnProfile] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)
    relationships: list[dict[str, str]] = field(default_factory=list)  # {column, ref_entity, ref_column}
    row_count: Optional[int] = None
    description: Optional[str] = None      # the source's own words about the table
    derived: list[dict[str, str]] = field(default_factory=list)   # what we concluded, tagged by source
    time_window: Optional[tuple[str, str]] = None   # measured (first, last) value of the time column
    context: dict[str, str] = field(default_factory=dict)              # placeholder values for the pattern
    scanned_at: datetime = field(default_factory=utcnow)

    def column(self, name: str) -> Optional[ColumnProfile]:
        n = (name or "").upper()
        for c in self.columns:
            if c.name.upper() == n:
                return c
        return None


# ---------------------------------------------------------------- history facts

@dataclass(frozen=True)
class Predicate:
    entity: str
    column: str
    operator: str
    values: tuple[str, ...]
    source: str = "where"             # where | case | join | having
    alias: Optional[str] = None

    def key(self) -> str:
        return f"{self.entity}.{self.column} {self.operator} ({','.join(self.values)})"


@dataclass
class Aggregate:
    alias: Optional[str]
    func: str                         # SUM | COUNT | COUNT_DISTINCT | AVG | MIN | MAX | RATIO | EXPR
    entity: Optional[str]
    formula: str                      # ENTITY.COLUMN normalised expression
    columns: list[str] = field(default_factory=list)
    conditions: list[Predicate] = field(default_factory=list)


@dataclass
class TimeRange:
    entity: str
    column: str
    start: Optional[str] = None
    end: Optional[str] = None
    grain: Optional[str] = None


@dataclass
class SqlFacts:
    tables: list[str] = field(default_factory=list)          # entities
    table_patterns: dict[str, str] = field(default_factory=dict)
    context: dict[str, str] = field(default_factory=dict)
    predicates: list[Predicate] = field(default_factory=list)
    aggregates: list[Aggregate] = field(default_factory=list)
    joins: list[tuple[str, str, str, str]] = field(default_factory=list)
    time_ranges: list[TimeRange] = field(default_factory=list)
    grain: Optional[str] = None
    group_by: list[str] = field(default_factory=list)
    projections: list[tuple[Optional[str], str, str]] = field(default_factory=list)   # (alias, entity, column)
    limit: Optional[int] = None
    parse_error: Optional[str] = None


@dataclass
class ValidatedPair:
    id: str
    nl: str
    sql: str
    source: str = "user"
    created_at: Optional[str] = None
    datasource_id: Optional[str] = None
    weight: float = 1.0
    human_verified: bool = False  # successful execution alone is not semantic approval


# ---------------------------------------------------------------- runtime

@dataclass
class TemporalSlot:
    text: str
    primitive: str                    # TODAY, LAST_N_DAYS, THIS_MONTH, YEAR, MONTH, MONTH_RANGE, AMBIGUOUS_RECENT …
    start: Optional[date] = None      # inclusive
    end: Optional[date] = None        # exclusive
    grain: Optional[str] = None       # DAY | WEEK | MONTH | QUARTER | YEAR
    ambiguous: bool = False
    params: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "primitive": self.primitive,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "grain": self.grain,
            "ambiguous": self.ambiguous,
            "params": self.params,
        }


@dataclass
class ResolvedSlot:
    term: str
    semantic_type: str
    status: str                        # CERTIFIED | EXPLICIT | CANDIDATE (informational only)
    concept_id: Optional[str] = None
    mapping: Optional[Mapping] = None
    confidence: float = 0.0
    explain: dict[str, Any] = field(default_factory=dict)
    span: tuple[int, int] = (0, 0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "term": self.term,
            "semanticType": self.semantic_type,
            "status": self.status,
            "conceptId": self.concept_id,
            "mapping": self.mapping.to_dict() if self.mapping else None,
            "confidence": round(self.confidence, 3),
            "explain": self.explain,
        }


@dataclass
class SemanticQuery:
    question: str
    tenant_id: str
    datasource_id: str
    slots: list[ResolvedSlot] = field(default_factory=list)
    unresolved: list[str] = field(default_factory=list)
    temporal: list[TemporalSlot] = field(default_factory=list)
    grain: Optional[str] = None
    group_by: list[ResolvedSlot] = field(default_factory=list)
    limit: Optional[int] = None
    order_desc: bool = True
    catalog_version: Optional[int] = None
    explanation: list[str] = field(default_factory=list)
    conflicts: list[str] = field(default_factory=list)
    ignored: list[str] = field(default_factory=list)   # ordinary language the resolver skipped
    out_of_scope: list[str] = field(default_factory=list)  # asked for a period this deployment has no data for
    # A qualifier that narrows the subject but has no certified meaning ("bekleyen siparişler",
    # "satmayan ürünler"). Dropping it would answer a wider question than the one that was asked,
    # so it blocks the deterministic path and is handed to the model spelled out.
    unhandled: list[str] = field(default_factory=list)
    modifiers: list[dict[str, Any]] = field(default_factory=list)
    clarification: list[str] = field(default_factory=list)
    # A shape the question asks for that the deterministic compiler cannot express but the model can
    # ("payı yüzde kaç" needs a denominator). Unlike `unhandled`, this is a request to write different
    # SQL, not a meaning nobody has defined — so it routes to the model instead of refusing.
    shape: Optional[str] = None
    # Çıktının biçimi soruda tarif edildiyse istenen kolonlar, sorulduğu sırayla ("1. kolon kanal
    # adı 2. kolon yıl"). Anlamı değil sunumu belirler: neyin hangi sırayla görüneceğini söyler.
    projection: list[str] = field(default_factory=list)
    # Katalogda karşılığı olmayan bir kelime için veride bulunan aday kolonlar. Karar değildir:
    # biri yeterince baskınsa slota dönüşür, değilse modele "bu kelime şuna benziyor" diye gider.
    candidates: list[dict[str, Any]] = field(default_factory=list)
    # Soru bir karşılaştırma istiyorsa: hangi dönem neye göre, ve bu istek yerine getirildi mi.
    # Karşılaştırma isteyen bir soru, karşılaştırma üretilmeden başarılı sayılamaz.
    comparison: Optional[dict[str, Any]] = None
    data_coverage: list[dict[str, Any]] = field(default_factory=list)
    temporal_binding: Optional[dict[str, str]] = None

    @property
    def metrics(self) -> list[ResolvedSlot]:
        return [s for s in self.slots if s.semantic_type == SemanticType.METRIC]

    @property
    def filters(self) -> list[ResolvedSlot]:
        return [s for s in self.slots if s.semantic_type == SemanticType.DIMENSION_VALUE]

    @property
    def fully_resolved(self) -> bool:
        return not self.unresolved and not self.unhandled and not self.clarification and not self.conflicts and not self.out_of_scope and not any(t.ambiguous for t in self.temporal)

    @property
    def state(self) -> str:
        """RESOLVED · PARTIAL · UNRESOLVED — how much of this question the catalog could place.

        The three are routed differently: what is resolved is compiled deterministically and never
        reaches a model, what is partial goes to the fallback with the resolved part pinned, and what
        is unresolved has to be found before it can be answered at all.
        """
        if self.fully_resolved and self.slots:
            return "RESOLVED"
        return "PARTIAL" if any(s.mapping for s in self.slots) else "UNRESOLVED"

    @property
    def refusal_reason(self) -> Optional[str]:
        """Why this question must not be answered — as opposed to merely not being answerable *here*.

        The distinction decides routing, and getting it wrong is how a system produces a confident
        wrong answer. A period the deployment holds no data for is not a harder question for a
        language model: any SQL it writes returns zero rows, and a zero that means "we did not load
        that year" is indistinguishable from a zero that means "you sold nothing". Contradictory
        filters are the same shape — the result is empty by construction, whoever writes it.

        Everything else is only a limit of the deterministic compiler: a join it cannot make, a metric
        nobody certified, a shape it cannot express. Those are handed on, not refused.
        """
        if self.out_of_scope:
            return "OUT_OF_SCOPE"
        if self.conflicts:
            return "AMBIGUOUS"
        if any(t.ambiguous for t in self.temporal):
            return "AMBIGUOUS"
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "slots": [s.to_dict() for s in self.slots],
            "unresolved": list(self.unresolved),
            "temporal": [t.to_dict() for t in self.temporal],
            "grain": self.grain,
            "groupBy": [s.to_dict() for s in self.group_by],
            "limit": self.limit,
            "orderDesc": self.order_desc,
            "catalogVersion": self.catalog_version,
            "conflicts": list(self.conflicts),
            "ignored": list(self.ignored),
            "outOfScope": list(self.out_of_scope),
            "unhandled": list(self.unhandled),
            "modifiers": list(self.modifiers),
            "clarification": list(self.clarification),
            "modifierTelemetry": self.modifier_telemetry,
            "shape": self.shape,
            "projection": list(self.projection),
            "candidates": [dict(c) for c in self.candidates],
            "comparison": dict(self.comparison) if self.comparison else None,
            "dataCoverage": [dict(c) for c in self.data_coverage],
            "temporalBinding": dict(self.temporal_binding) if self.temporal_binding else None,
            "fullyResolved": self.fully_resolved,
            "state": self.state,
            "refusalReason": self.refusal_reason,
            "explanation": list(self.explanation),
        }

    @property
    def modifier_telemetry(self) -> dict[str, Any]:
        silent = sum(m["token"] in self.ignored and m["decision"] == "UNKNOWN" for m in self.modifiers)
        return {
            "modifier_seen": len(self.modifiers),
            **{f"modifier_{role.lower()}": sum(m["decision"] == role for m in self.modifiers)
               for role in ("GRAMMATICAL", "SEMANTIC", "UNKNOWN", "ABSENCE")},
            "modifier_historical_confirmed": sum(m["evidence_source"] == "history" for m in self.modifiers),
            "modifier_catalog_confirmed": sum(m["evidence_source"] == "catalog" for m in self.modifiers),
            "modifier_recovered": sum(m.get("recovered", False) for m in self.modifiers),
            "modifier_silently_ignored": silent,
            "silent_modifier_drop_rate": silent / len(self.modifiers) if self.modifiers else 0.0,
        }


@dataclass
class CompiledQuery:
    sql: str
    compiler: str                      # deterministic | existing_llm
    tables: list[str] = field(default_factory=list)
    catalog_version: Optional[int] = None
    explain: list[str] = field(default_factory=list)
    llm_ms: int = 0
    certified: bool = False            # every semantic slot came from CERTIFIED catalog entries
    # What the model said when it wrote no SQL. Kept for diagnosis and never shown: a refusal it wrote
    # could be about anything at all, and a data tool that can be talked into discussing itself is no
    # longer a data tool.
    model_text: Optional[str] = None
    # Set when the answer is a refusal rather than a query: OUT_OF_SCOPE, AMBIGUOUS. A refusal is a
    # first-class result — for a question whose data this deployment does not hold, it is the *correct*
    # result, and measuring it as a failure is how a system gets pushed into answering anyway.
    refusal: Optional[str] = None
