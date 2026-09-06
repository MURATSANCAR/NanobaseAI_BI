"""CatalogStore — the only object that touches sl_* tables.

Thread-safe (one SQLAlchemy engine, short transactions). Concepts are addressed by
(tenant, datasource, normalized_term, semantic_type, sense_id); mappings/evidence hang off the id.
"""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

import sqlalchemy as sa
from sqlalchemy.engine import Engine

from semantic_layer.models import (
    Annotation,
    Candidate,
    ColumnProfile,
    Concept,
    ConceptStatus,
    CounterEvidence,
    Evidence,
    Mapping,
    SchemaProfile,
    SemanticType,
    new_id,
    utcnow,
)
from semantic_layer.normalize import normalize_term
from semantic_layer.store import schema as S


def _dt(v: Any) -> datetime:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, str):
        return datetime.fromisoformat(v)
    return utcnow()


def _json(v: Any) -> Any:
    """SQLite returns JSON columns as str under some drivers; normalise."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:  # noqa: BLE001
            return v
    return v


def open_store(dsn: str, *, create: bool = True) -> "CatalogStore":
    kwargs: dict[str, Any] = {"pool_pre_ping": True}
    if dsn.startswith("sqlite"):
        kwargs = {"connect_args": {"check_same_thread": False}}
        if dsn in ("sqlite://", "sqlite:///:memory:"):
            from sqlalchemy.pool import StaticPool

            kwargs["poolclass"] = StaticPool
    engine = sa.create_engine(dsn, **kwargs)
    if dsn.startswith("sqlite"):
        @sa.event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _rec):  # pragma: no cover - trivial
            dbapi_conn.execute("PRAGMA foreign_keys=ON")
    store = CatalogStore(engine)
    if create:
        store.create_all()
    return store


class CatalogStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._lock = threading.RLock()
        self._index_cache: dict[tuple[str, str], tuple[int, dict[str, list[tuple[Concept, list[Mapping]]]]]] = {}

    # ------------------------------------------------------------------ infra
    def create_all(self) -> None:
        S.create_all(self.engine)

    def _rows(self, stmt) -> list[dict[str, Any]]:
        with self.engine.connect() as conn:
            return [dict(r._mapping) for r in conn.execute(stmt)]

    def _row_to_concept(self, r: dict[str, Any]) -> Concept:
        return Concept(
            id=r["id"],
            tenant_id=r["tenant_id"],
            datasource_id=r["datasource_id"],
            term=r["term"],
            normalized_term=r["normalized_term"],
            semantic_type=r["semantic_type"],
            domain=r["domain"],
            sense_id=int(r["sense_id"]),
            status=r["status"],
            confidence=float(r["confidence"] or 0),
            version=int(r["version"]),
            synonyms=list(_json(r["synonyms_json"]) or []),
            explain=dict(_json(r["explain_json"]) or {}),
            created_at=_dt(r["created_at"]),
            updated_at=_dt(r["updated_at"]),
        )

    @staticmethod
    def _row_to_mapping(r: dict[str, Any]) -> Mapping:
        return Mapping(
            id=r["id"],
            concept_id=r["concept_id"],
            entity=r["entity"],
            table_pattern=r["table_pattern"],
            column=r["column_name"],
            operator=r["operator"],
            values=[str(v) for v in (_json(r["values_json"]) or [])],
            formula=r["formula"],
            time_primitive=r["time_primitive"],
            extra=dict(_json(r["extra_json"]) or {}),
        )

    # ------------------------------------------------------------------ concepts
    def get_concept(self, concept_id: str) -> Optional[Concept]:
        rows = self._rows(sa.select(S.sl_concept).where(S.sl_concept.c.id == concept_id))
        return self._row_to_concept(rows[0]) if rows else None

    def find_concepts(
        self,
        tenant_id: str,
        datasource_id: str,
        *,
        normalized_term: Optional[str] = None,
        semantic_type: Optional[str] = None,
        status: Optional[str | Iterable[str]] = None,
        limit: int = 500,
    ) -> list[Concept]:
        stmt = sa.select(S.sl_concept).where(
            S.sl_concept.c.tenant_id == tenant_id, S.sl_concept.c.datasource_id == datasource_id
        )
        if normalized_term is not None:
            stmt = stmt.where(S.sl_concept.c.normalized_term == normalized_term)
        if semantic_type:
            stmt = stmt.where(S.sl_concept.c.semantic_type == semantic_type)
        if status:
            statuses = [status] if isinstance(status, str) else list(status)
            stmt = stmt.where(S.sl_concept.c.status.in_(statuses))
        stmt = stmt.order_by(S.sl_concept.c.normalized_term, S.sl_concept.c.sense_id).limit(limit)
        return [self._row_to_concept(r) for r in self._rows(stmt)]

    def search_concepts(self, tenant_id: str, datasource_id: str, q: str, limit: int = 100) -> list[Concept]:
        key = normalize_term(q)
        stmt = (
            sa.select(S.sl_concept)
            .where(S.sl_concept.c.tenant_id == tenant_id, S.sl_concept.c.datasource_id == datasource_id)
            .where(sa.or_(S.sl_concept.c.normalized_term.like(f"%{key}%"), S.sl_concept.c.term.like(f"%{q}%")))
            .limit(limit)
        )
        return [self._row_to_concept(r) for r in self._rows(stmt)]

    def upsert_concept(
        self,
        tenant_id: str,
        datasource_id: str,
        term: str,
        semantic_type: str,
        *,
        mapping: Optional[Mapping] = None,
        domain: str = "general",
        status: str = ConceptStatus.DISCOVERED,
        synonyms: Optional[list[str]] = None,
    ) -> tuple[Concept, bool]:
        """Find the concept whose mapping matches (same term+type+physical key) or create a new sense.
        Returns (concept, created)."""
        norm = normalize_term(term)
        with self._lock:
            existing = self.find_concepts(tenant_id, datasource_id, normalized_term=norm, semantic_type=semantic_type)
            if mapping is not None:
                for c in existing:
                    for m in self.list_mappings(c.id):
                        if m.key() == mapping.key():
                            return c, False
            elif existing:
                return existing[0], False
            sense = (max((c.sense_id for c in existing), default=0) + 1) if existing else 1
            concept = Concept(
                tenant_id=tenant_id,
                datasource_id=datasource_id,
                term=term,
                normalized_term=norm,
                semantic_type=semantic_type,
                domain=domain,
                sense_id=sense,
                status=status,
                synonyms=list(synonyms or []),
            )
            with self.engine.begin() as conn:
                conn.execute(
                    S.sl_concept.insert().values(
                        id=concept.id,
                        tenant_id=tenant_id,
                        datasource_id=datasource_id,
                        term=term,
                        normalized_term=norm,
                        semantic_type=semantic_type,
                        domain=domain,
                        sense_id=sense,
                        status=status,
                        confidence=0.0,
                        version=1,
                        synonyms_json=list(synonyms or []),
                        explain_json={},
                        created_at=concept.created_at,
                        updated_at=concept.updated_at,
                    )
                )
                if mapping is not None:
                    mapping.concept_id = concept.id
                    conn.execute(S.sl_mapping.insert().values(**self._mapping_values(mapping)))
            self._invalidate(tenant_id, datasource_id)
            return concept, True

    def update_concept(
        self,
        concept_id: str,
        *,
        status: Optional[str] = None,
        confidence: Optional[float] = None,
        explain: Optional[dict[str, Any]] = None,
        synonyms: Optional[list[str]] = None,
        bump_version: bool = False,
    ) -> Optional[Concept]:
        c = self.get_concept(concept_id)
        if c is None:
            return None
        values: dict[str, Any] = {"updated_at": utcnow()}
        if status is not None:
            values["status"] = status
        if confidence is not None:
            values["confidence"] = float(confidence)
        if explain is not None:
            merged = dict(c.explain)
            merged.update(explain)
            values["explain_json"] = merged
        if synonyms is not None:
            values["synonyms_json"] = sorted(set(synonyms))
        if bump_version or (status is not None and status != c.status):
            values["version"] = c.version + 1
        with self.engine.begin() as conn:
            conn.execute(S.sl_concept.update().where(S.sl_concept.c.id == concept_id).values(**values))
        self._invalidate(c.tenant_id, c.datasource_id)
        return self.get_concept(concept_id)

    def add_synonym(self, concept_id: str, synonym: str) -> None:
        c = self.get_concept(concept_id)
        if c is None:
            return
        syns = set(c.synonyms)
        key = normalize_term(synonym)
        if key and key != c.normalized_term:
            syns.add(key)
            self.update_concept(concept_id, synonyms=sorted(syns))

    def delete_concept(self, concept_id: str) -> None:
        c = self.get_concept(concept_id)
        with self.engine.begin() as conn:
            for t in (S.sl_mapping, S.sl_evidence, S.sl_counter_evidence, S.sl_candidate):
                conn.execute(t.delete().where(t.c.concept_id == concept_id))
            conn.execute(S.sl_concept.delete().where(S.sl_concept.c.id == concept_id))
        if c:
            self._invalidate(c.tenant_id, c.datasource_id)

    # ------------------------------------------------------------------ mappings
    @staticmethod
    def _mapping_values(m: Mapping) -> dict[str, Any]:
        return {
            "id": m.id,
            "concept_id": m.concept_id,
            "entity": m.entity,
            "table_pattern": m.table_pattern,
            "column_name": m.column,
            "operator": m.operator,
            "values_json": [str(v) for v in m.values],
            "formula": m.formula,
            "time_primitive": m.time_primitive,
            "extra_json": dict(m.extra or {}),
        }

    def list_mappings(self, concept_id: str) -> list[Mapping]:
        return [self._row_to_mapping(r) for r in self._rows(sa.select(S.sl_mapping).where(S.sl_mapping.c.concept_id == concept_id))]

    def replace_mappings(self, concept_id: str, mappings: list[Mapping]) -> None:
        c = self.get_concept(concept_id)
        with self.engine.begin() as conn:
            conn.execute(S.sl_mapping.delete().where(S.sl_mapping.c.concept_id == concept_id))
            for m in mappings:
                m.concept_id = concept_id
                conn.execute(S.sl_mapping.insert().values(**self._mapping_values(m)))
        if c:
            self._invalidate(c.tenant_id, c.datasource_id)

    def mappings_for_column(self, tenant_id: str, datasource_id: str, entity: str, column: str) -> list[tuple[Concept, Mapping]]:
        result: list[tuple[Concept, Mapping]] = []
        stmt = sa.select(S.sl_mapping).where(S.sl_mapping.c.entity == entity, S.sl_mapping.c.column_name == column)
        for m in self._rows(stmt):
            c = self.get_concept(m["concept_id"])
            if c and c.tenant_id == tenant_id and c.datasource_id == datasource_id:
                result.append((c, self._row_to_mapping(m)))
        return result

    # ------------------------------------------------------------------ evidence
    def add_evidence(self, ev: Evidence) -> Evidence:
        """Idempotent on (concept, type, source): repeated mining updates support/payload in place."""
        with self._lock, self.engine.begin() as conn:
            row = conn.execute(
                sa.select(S.sl_evidence.c.id).where(
                    S.sl_evidence.c.concept_id == ev.concept_id,
                    S.sl_evidence.c.evidence_type == ev.evidence_type,
                    S.sl_evidence.c.source_id == ev.source_id,
                )
            ).first()
            if row:
                conn.execute(
                    S.sl_evidence.update()
                    .where(S.sl_evidence.c.id == row[0])
                    .values(support_count=ev.support_count, weight=ev.weight, payload_json=ev.payload)
                )
                ev.id = row[0]
            else:
                conn.execute(
                    S.sl_evidence.insert().values(
                        id=ev.id,
                        concept_id=ev.concept_id,
                        evidence_type=ev.evidence_type,
                        source_id=ev.source_id,
                        support_count=ev.support_count,
                        weight=ev.weight,
                        payload_json=ev.payload,
                        created_at=ev.created_at,
                    )
                )
        return ev

    def list_evidence(self, concept_id: str) -> list[Evidence]:
        return [
            Evidence(
                id=r["id"],
                concept_id=r["concept_id"],
                evidence_type=r["evidence_type"],
                source_id=r["source_id"],
                support_count=int(r["support_count"]),
                weight=float(r["weight"]),
                payload=dict(_json(r["payload_json"]) or {}),
                created_at=_dt(r["created_at"]),
            )
            for r in self._rows(sa.select(S.sl_evidence).where(S.sl_evidence.c.concept_id == concept_id))
        ]

    def add_counter_evidence(self, ce: CounterEvidence) -> CounterEvidence:
        with self._lock, self.engine.begin() as conn:
            row = conn.execute(
                sa.select(S.sl_counter_evidence.c.id).where(
                    S.sl_counter_evidence.c.concept_id == ce.concept_id,
                    S.sl_counter_evidence.c.conflict_type == ce.conflict_type,
                    S.sl_counter_evidence.c.source_id == ce.source_id,
                )
            ).first()
            if row:
                conn.execute(
                    S.sl_counter_evidence.update()
                    .where(S.sl_counter_evidence.c.id == row[0])
                    .values(payload_json=ce.payload, severity=ce.severity)
                )
                ce.id = row[0]
            else:
                conn.execute(
                    S.sl_counter_evidence.insert().values(
                        id=ce.id,
                        concept_id=ce.concept_id,
                        source_id=ce.source_id,
                        conflict_type=ce.conflict_type,
                        payload_json=ce.payload,
                        severity=ce.severity,
                        created_at=ce.created_at,
                    )
                )
        return ce

    def list_counter_evidence(self, concept_id: str) -> list[CounterEvidence]:
        return [
            CounterEvidence(
                id=r["id"],
                concept_id=r["concept_id"],
                source_id=r["source_id"],
                conflict_type=r["conflict_type"],
                payload=dict(_json(r["payload_json"]) or {}),
                severity=r["severity"],
                created_at=_dt(r["created_at"]),
            )
            for r in self._rows(sa.select(S.sl_counter_evidence).where(S.sl_counter_evidence.c.concept_id == concept_id))
        ]

    def clear_counter_evidence(self, concept_id: str, conflict_type: Optional[str] = None) -> None:
        stmt = S.sl_counter_evidence.delete().where(S.sl_counter_evidence.c.concept_id == concept_id)
        if conflict_type:
            stmt = stmt.where(S.sl_counter_evidence.c.conflict_type == conflict_type)
        with self.engine.begin() as conn:
            conn.execute(stmt)

    # ------------------------------------------------------------------ candidates
    def add_candidate(self, cand: Candidate) -> Candidate:
        with self.engine.begin() as conn:
            conn.execute(
                S.sl_candidate.insert().values(
                    id=cand.id,
                    concept_id=cand.concept_id,
                    generated_by=cand.generated_by,
                    model_version=cand.model_version,
                    payload_json=cand.payload,
                    status=cand.status,
                    created_at=cand.created_at,
                )
            )
        return cand

    def list_candidates(self, concept_id: Optional[str] = None, status: Optional[str] = None, limit: int = 500) -> list[Candidate]:
        stmt = sa.select(S.sl_candidate)
        if concept_id:
            stmt = stmt.where(S.sl_candidate.c.concept_id == concept_id)
        if status:
            stmt = stmt.where(S.sl_candidate.c.status == status)
        stmt = stmt.order_by(S.sl_candidate.c.created_at.desc()).limit(limit)
        return [
            Candidate(
                id=r["id"],
                concept_id=r["concept_id"],
                generated_by=r["generated_by"],
                model_version=r["model_version"],
                payload=dict(_json(r["payload_json"]) or {}),
                status=r["status"],
                created_at=_dt(r["created_at"]),
            )
            for r in self._rows(stmt)
        ]

    # ------------------------------------------------------------------ versions
    def latest_version(self, tenant_id: str, datasource_id: str) -> Optional[dict[str, Any]]:
        rows = self._rows(
            sa.select(S.sl_catalog_version)
            .where(S.sl_catalog_version.c.tenant_id == tenant_id, S.sl_catalog_version.c.datasource_id == datasource_id)
            .order_by(S.sl_catalog_version.c.version.desc())
            .limit(1)
        )
        if not rows:
            return None
        r = rows[0]
        return {"id": r["id"], "version": int(r["version"]), "certified_count": int(r["certified_count"]), "snapshot": _json(r["snapshot_json"]), "note": r["note"], "created_at": _dt(r["created_at"]).isoformat()}

    def create_version(self, tenant_id: str, datasource_id: str, snapshot: dict[str, Any], note: str = "") -> int:
        with self._lock:
            latest = self.latest_version(tenant_id, datasource_id)
            version = (latest["version"] + 1) if latest else 1
            with self.engine.begin() as conn:
                conn.execute(
                    S.sl_catalog_version.insert().values(
                        id=new_id("cv"),
                        tenant_id=tenant_id,
                        datasource_id=datasource_id,
                        version=version,
                        certified_count=int(snapshot.get("certified_count") or 0),
                        snapshot_json=snapshot,
                        note=note,
                        created_at=utcnow(),
                    )
                )
            self._invalidate(tenant_id, datasource_id)
            return version

    # ------------------------------------------------------------------ query log
    def log_query(
        self,
        tenant_id: str,
        datasource_id: str,
        question: str,
        *,
        sql: Optional[str],
        compiler: Optional[str],
        catalog_version: Optional[int],
        resolved: dict[str, Any],
        executed: bool,
        row_count: Optional[int] = None,
        latency_ms: Optional[int] = None,
        error: Optional[str] = None,
        result_fingerprint: Optional[str] = None,
    ) -> str:
        qid = new_id("q")
        with self.engine.begin() as conn:
            conn.execute(
                S.sl_query_log.insert().values(
                    id=qid,
                    tenant_id=tenant_id,
                    datasource_id=datasource_id,
                    question=question,
                    normalized_question=normalize_term(question),
                    sql_text=sql,
                    compiler=compiler,
                    catalog_version=catalog_version,
                    resolved_json=resolved,
                    executed=bool(executed),
                    row_count=row_count,
                    latency_ms=latency_ms,
                    error=error,
                    result_fingerprint=result_fingerprint,
                    created_at=utcnow(),
                )
            )
        return qid

    def mark_validated(self, query_id: str, validated: bool) -> bool:
        with self.engine.begin() as conn:
            res = conn.execute(S.sl_query_log.update().where(S.sl_query_log.c.id == query_id).values(validated=bool(validated)))
        return bool(res.rowcount)

    def list_validated_queries(self, tenant_id: str, datasource_id: str, limit: int = 2000) -> list[dict[str, Any]]:
        stmt = (
            sa.select(S.sl_query_log)
            .where(S.sl_query_log.c.tenant_id == tenant_id, S.sl_query_log.c.datasource_id == datasource_id)
            .where(S.sl_query_log.c.validated.is_(True))
            .order_by(S.sl_query_log.c.created_at.desc())
            .limit(limit)
        )
        return self._rows(stmt)

    def list_unresolved_terms(self, tenant_id: str, datasource_id: str, limit: int = 500) -> dict[str, int]:
        """Terms the runtime could not resolve (from resolved_json.unresolved) with counts."""
        stmt = (
            sa.select(S.sl_query_log.c.resolved_json)
            .where(S.sl_query_log.c.tenant_id == tenant_id, S.sl_query_log.c.datasource_id == datasource_id)
            .order_by(S.sl_query_log.c.created_at.desc())
            .limit(limit)
        )
        counts: dict[str, int] = {}
        for r in self._rows(stmt):
            for term in (_json(r["resolved_json"]) or {}).get("unresolved") or []:
                counts[term] = counts.get(term, 0) + 1
        return dict(sorted(counts.items(), key=lambda kv: -kv[1]))

    def query_stats(self, tenant_id: str, datasource_id: str) -> dict[str, Any]:
        with self.engine.connect() as conn:
            base = sa.select(sa.func.count()).select_from(S.sl_query_log).where(
                S.sl_query_log.c.tenant_id == tenant_id, S.sl_query_log.c.datasource_id == datasource_id
            )
            total = conn.execute(base).scalar() or 0
            validated = conn.execute(base.where(S.sl_query_log.c.validated.is_(True))).scalar() or 0
            det = conn.execute(base.where(S.sl_query_log.c.compiler == "deterministic")).scalar() or 0
        return {"total": int(total), "validated": int(validated), "deterministic": int(det)}

    # ------------------------------------------------------------------ profiles
    def upsert_profile(self, p: SchemaProfile) -> None:
        values = {
            "datasource_id": p.datasource_id,
            "schema_name": p.schema_name,
            "table_name": p.table_name,
            "table_pattern": p.table_pattern,
            "entity": p.entity,
            "columns_json": [self._col_to_json(c) for c in p.columns],
            "primary_key_json": list(p.primary_key),
            "relationships_json": list(p.relationships),
            "context_json": dict(p.context),
            "row_count": p.row_count,
            "description": p.description,
            "scanned_at": p.scanned_at,
        }
        with self._lock, self.engine.begin() as conn:
            row = conn.execute(
                sa.select(S.sl_schema_profile.c.id).where(
                    S.sl_schema_profile.c.datasource_id == p.datasource_id, S.sl_schema_profile.c.table_pattern == p.table_pattern
                )
            ).first()
            if row:
                conn.execute(S.sl_schema_profile.update().where(S.sl_schema_profile.c.id == row[0]).values(**values))
            else:
                conn.execute(S.sl_schema_profile.insert().values(id=new_id("prof"), **values))

    @staticmethod
    def _col_to_json(c: ColumnProfile) -> dict[str, Any]:
        d = asdict(c)
        d["top_values"] = [[str(v), int(n)] for v, n in c.top_values]
        return d

    @staticmethod
    def _col_from_json(d: dict[str, Any]) -> ColumnProfile:
        return ColumnProfile(
            name=d["name"],
            data_type=d.get("data_type") or "",
            nullable=bool(d.get("nullable", True)),
            distinct_count=d.get("distinct_count"),
            top_values=[(str(v), int(n)) for v, n in (d.get("top_values") or [])],
            null_ratio=d.get("null_ratio"),
            is_primary_key=bool(d.get("is_primary_key")),
            ref_entity=d.get("ref_entity"),
            ref_column=d.get("ref_column"),
            description=d.get("description"),
        )

    def prune_profiles(self, datasource_id: str, keep_patterns: list[str]) -> int:
        """Drop profile rows for tables the current scope no longer covers, so the runtime never compiles
        against a table that is out of scope or gone."""
        if not keep_patterns:
            return 0
        with self.engine.begin() as conn:
            res = conn.execute(
                S.sl_schema_profile.delete()
                .where(S.sl_schema_profile.c.datasource_id == datasource_id)
                .where(S.sl_schema_profile.c.table_pattern.notin_(keep_patterns))
            )
        return int(res.rowcount or 0)

    def list_profiles(self, datasource_id: str) -> list[SchemaProfile]:
        rows = self._rows(sa.select(S.sl_schema_profile).where(S.sl_schema_profile.c.datasource_id == datasource_id).order_by(S.sl_schema_profile.c.table_name))
        out = []
        for r in rows:
            out.append(
                SchemaProfile(
                    datasource_id=r["datasource_id"],
                    table_name=r["table_name"],
                    table_pattern=r["table_pattern"],
                    entity=r["entity"],
                    schema_name=r["schema_name"],
                    columns=[self._col_from_json(c) for c in (_json(r["columns_json"]) or [])],
                    primary_key=list(_json(r["primary_key_json"]) or []),
                    relationships=list(_json(r["relationships_json"]) or []),
                    row_count=r["row_count"],
                    description=r["description"],
                    context=dict(_json(r["context_json"]) or {}),
                    scanned_at=_dt(r["scanned_at"]),
                )
            )
        return out

    def get_profile(self, datasource_id: str, entity_or_pattern: str) -> Optional[SchemaProfile]:
        key = (entity_or_pattern or "").upper()
        for p in self.list_profiles(datasource_id):
            if p.entity.upper() == key or p.table_pattern.upper() == key or p.table_name.upper() == key:
                return p
        return None

    # ------------------------------------------------------------------ annotations (portal layer)
    def add_annotation(self, ann: Annotation) -> Annotation:
        with self.engine.begin() as conn:
            conn.execute(
                S.sl_schema_annotation.insert().values(
                    id=ann.id,
                    datasource_id=ann.datasource_id,
                    table_pattern=ann.table_pattern,
                    column_name=ann.column,
                    text=ann.text,
                    author=ann.author,
                    status=ann.status,
                    created_at=ann.created_at,
                )
            )
        return ann

    def list_annotations(self, datasource_id: str, table_pattern: Optional[str] = None, *, active_only: bool = True) -> list[Annotation]:
        stmt = sa.select(S.sl_schema_annotation).where(S.sl_schema_annotation.c.datasource_id == datasource_id)
        if table_pattern:
            stmt = stmt.where(S.sl_schema_annotation.c.table_pattern == table_pattern)
        if active_only:
            stmt = stmt.where(S.sl_schema_annotation.c.status == "ACTIVE")
        stmt = stmt.order_by(S.sl_schema_annotation.c.created_at.desc())
        return [
            Annotation(
                id=r["id"],
                datasource_id=r["datasource_id"],
                table_pattern=r["table_pattern"],
                column=r["column_name"],
                text=r["text"],
                author=r["author"],
                status=r["status"],
                created_at=_dt(r["created_at"]),
            )
            for r in self._rows(stmt)
        ]

    def retire_annotation(self, annotation_id: str) -> bool:
        with self.engine.begin() as conn:
            res = conn.execute(S.sl_schema_annotation.update().where(S.sl_schema_annotation.c.id == annotation_id).values(status="RETIRED"))
        return bool(res.rowcount)

    # ------------------------------------------------------------------ certified index (runtime)
    def _invalidate(self, tenant_id: str, datasource_id: str) -> None:
        self._index_cache.pop((tenant_id, datasource_id), None)

    def certified_index(self, tenant_id: str, datasource_id: str) -> dict[str, list[tuple[Concept, list[Mapping]]]]:
        """normalized term (and synonyms) → [(concept, mappings)] for CERTIFIED concepts only.
        Cached per catalog version; the resolver never sees CANDIDATE rows."""
        key = (tenant_id, datasource_id)
        latest = self.latest_version(tenant_id, datasource_id)
        ver = latest["version"] if latest else 0
        cached = self._index_cache.get(key)
        if cached and cached[0] == ver:
            return cached[1]
        index: dict[str, list[tuple[Concept, list[Mapping]]]] = {}
        for c in self.find_concepts(tenant_id, datasource_id, status=ConceptStatus.CERTIFIED, limit=100000):
            maps = self.list_mappings(c.id)
            for k in [c.normalized_term, *c.synonyms]:
                if k:
                    index.setdefault(k, []).append((c, maps))
        self._index_cache[key] = (ver, index)
        return index

    def status_counts(self, tenant_id: str, datasource_id: str) -> dict[str, int]:
        stmt = (
            sa.select(S.sl_concept.c.status, sa.func.count())
            .where(S.sl_concept.c.tenant_id == tenant_id, S.sl_concept.c.datasource_id == datasource_id)
            .group_by(S.sl_concept.c.status)
        )
        out = {s: 0 for s in ConceptStatus.ALL}
        with self.engine.connect() as conn:
            for status, n in conn.execute(stmt):
                out[str(status)] = int(n)
        return out

    def type_counts(self, tenant_id: str, datasource_id: str, status: str = ConceptStatus.CERTIFIED) -> dict[str, int]:
        stmt = (
            sa.select(S.sl_concept.c.semantic_type, sa.func.count())
            .where(S.sl_concept.c.tenant_id == tenant_id, S.sl_concept.c.datasource_id == datasource_id, S.sl_concept.c.status == status)
            .group_by(S.sl_concept.c.semantic_type)
        )
        out = {t: 0 for t in SemanticType.ALL}
        with self.engine.connect() as conn:
            for typ, n in conn.execute(stmt):
                out[str(typ)] = int(n)
        return out

    # ------------------------------------------------------------------ helpers
    def concept_bundle(self, concept_id: str) -> Optional[dict[str, Any]]:
        c = self.get_concept(concept_id)
        if c is None:
            return None
        return {
            "concept": c.to_dict(),
            "mappings": [m.to_dict() for m in self.list_mappings(concept_id)],
            "evidence": [asdict(e) | {"created_at": e.created_at.isoformat()} for e in self.list_evidence(concept_id)],
            "counterEvidence": [asdict(e) | {"created_at": e.created_at.isoformat()} for e in self.list_counter_evidence(concept_id)],
            "candidates": [asdict(x) | {"created_at": x.created_at.isoformat()} for x in self.list_candidates(concept_id)],
        }


def result_fingerprint(columns: list[str], rows: list[dict[str, Any]]) -> str:
    h = hashlib.sha256()
    h.update("|".join(columns).encode())
    for r in rows[:50]:
        h.update(json.dumps(r, sort_keys=True, default=str).encode())
    return h.hexdigest()[:32]
