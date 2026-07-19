"""PostgreSQL persistence for sc_* semantic catalog tables."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from nanobase_api.semantic_catalog.domain.business_term import BusinessTerm
from nanobase_api.semantic_catalog.domain.filter_rule import FilterExpression, FilterRule
from nanobase_api.semantic_catalog.domain.metric import (
    CurrencySemantics,
    Metric,
    SourceExpression,
    TimeSemantics,
)
from nanobase_api.semantic_catalog.domain.promotion import (
    PromotionPhase,
    PromotionRequest,
    PromotionReview,
)
from nanobase_api.semantic_catalog.domain.semantic_version import ManifestAsset, SemanticVersion
from nanobase_api.semantic_catalog.domain.status import AssetStatus
from nanobase_api.semantic_catalog.domain.verified_query import VerifiedQuery, VerifiedQueryCandidate


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


class SqlCatalogRepository:
    """Write-through repository for semantic catalog entities."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def tables_ready(self) -> bool:
        try:
            with self._engine.connect() as conn:
                row = conn.execute(
                    text("SELECT to_regclass('public.sc_metric_definition') IS NOT NULL")
                ).scalar()
                return bool(row)
        except Exception:
            return False

    # --- metrics ---

    def upsert_metric(self, m: Metric) -> None:
        currency_json = json.dumps(m.currency.to_dict()) if m.currency else None
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sc_metric_definition (
                      id, code, name, description, aggregation, source_table, source_column,
                      null_policy, time_field, timezone, calendar_type, default_granularity,
                      is_financial, multi_currency, currency_json,
                      tenant_id, datasource_id, created_by, updated_by, version, status, updated_at
                    ) VALUES (
                      :id, :code, :name, :description, :aggregation, :source_table, :source_column,
                      :null_policy, :time_field, :timezone, :calendar_type, :default_granularity,
                      :is_financial, :multi_currency, :currency_json,
                      :tenant_id, :datasource_id, :created_by, :updated_by, :version, :status, :now
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      code = EXCLUDED.code,
                      name = EXCLUDED.name,
                      description = EXCLUDED.description,
                      aggregation = EXCLUDED.aggregation,
                      source_table = EXCLUDED.source_table,
                      source_column = EXCLUDED.source_column,
                      null_policy = EXCLUDED.null_policy,
                      time_field = EXCLUDED.time_field,
                      timezone = EXCLUDED.timezone,
                      calendar_type = EXCLUDED.calendar_type,
                      default_granularity = EXCLUDED.default_granularity,
                      is_financial = EXCLUDED.is_financial,
                      multi_currency = EXCLUDED.multi_currency,
                      currency_json = EXCLUDED.currency_json,
                      version = EXCLUDED.version,
                      status = EXCLUDED.status,
                      updated_by = EXCLUDED.updated_by,
                      updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "id": m.id,
                    "code": m.code,
                    "name": m.name,
                    "description": m.description,
                    "aggregation": m.aggregation,
                    "source_table": m.source.table,
                    "source_column": m.source.column,
                    "null_policy": m.null_policy,
                    "time_field": m.time.time_field if m.time else None,
                    "timezone": m.time.timezone if m.time else "Europe/Istanbul",
                    "calendar_type": m.time.calendar_type if m.time else "CALENDAR",
                    "default_granularity": m.time.default_granularity if m.time else "MONTH",
                    "is_financial": m.is_financial,
                    "multi_currency": m.multi_currency_datasource,
                    "currency_json": currency_json,
                    "tenant_id": m.tenant_id,
                    "datasource_id": m.datasource_id,
                    "created_by": None,
                    "updated_by": None,
                    "version": m.version,
                    "status": m.status.value,
                    "now": _now(),
                },
            )
            conn.execute(
                text("DELETE FROM sc_metric_default_filter WHERE metric_id = :mid"),
                {"mid": m.id},
            )
            for code in m.default_filter_codes:
                conn.execute(
                    text(
                        """
                        INSERT INTO sc_metric_default_filter (
                          id, metric_id, filter_code, tenant_id, datasource_id, status, updated_at
                        ) VALUES (:id, :mid, :code, :tenant, :ds, :status, :now)
                        """
                    ),
                    {
                        "id": _id("mdf"),
                        "mid": m.id,
                        "code": code,
                        "tenant": m.tenant_id,
                        "ds": m.datasource_id,
                        "status": m.status.value,
                        "now": _now(),
                    },
                )

    def load_metrics(self) -> list[Metric]:
        with self._engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM sc_metric_definition")).mappings().all()
            out: list[Metric] = []
            for r in rows:
                filters = conn.execute(
                    text(
                        "SELECT filter_code FROM sc_metric_default_filter WHERE metric_id = :id ORDER BY filter_code"
                    ),
                    {"id": r["id"]},
                ).scalars().all()
                currency = None
                if r.get("currency_json"):
                    raw = json.loads(r["currency_json"])
                    currency = CurrencySemantics(
                        amount_field=raw.get("amountField") or r["source_table"] + "." + r["source_column"],
                        currency_field=raw.get("currencyField"),
                        base_currency=raw.get("baseCurrency") or "TRY",
                        conversion_policy=raw.get("conversionPolicy") or "DOCUMENT_CURRENCY",
                        rate_source=raw.get("rateSource"),
                        rate_date_policy=raw.get("rateDatePolicy"),
                        rounding_scale=int(raw.get("roundingScale") or 2),
                    )
                time = None
                if r.get("time_field"):
                    time = TimeSemantics(
                        time_field=r["time_field"],
                        timezone=r.get("timezone") or "Europe/Istanbul",
                        calendar_type=r.get("calendar_type") or "CALENDAR",
                        default_granularity=r.get("default_granularity") or "MONTH",
                    )
                out.append(
                    Metric(
                        id=r["id"],
                        tenant_id=r["tenant_id"],
                        datasource_id=r["datasource_id"],
                        code=r["code"],
                        name=r["name"],
                        description=r["description"] or "",
                        aggregation=r["aggregation"],
                        source=SourceExpression(r["source_table"], r["source_column"]),
                        default_filter_codes=list(filters),
                        null_policy=r.get("null_policy") or "ZERO",
                        time=time,
                        currency=currency,
                        is_financial=bool(r.get("is_financial")),
                        multi_currency_datasource=bool(r.get("multi_currency")),
                        status=AssetStatus(r["status"]),
                        version=int(r.get("version") or 1),
                    )
                )
            return out

    # --- filters ---

    def upsert_filter(self, f: FilterRule) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sc_filter_rule (
                      id, code, description, expression_json, mandatory,
                      tenant_id, datasource_id, version, status, updated_at
                    ) VALUES (
                      :id, :code, :description, :expr, :mandatory,
                      :tenant_id, :datasource_id, :version, :status, :now
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      code = EXCLUDED.code,
                      description = EXCLUDED.description,
                      expression_json = EXCLUDED.expression_json,
                      mandatory = EXCLUDED.mandatory,
                      version = EXCLUDED.version,
                      status = EXCLUDED.status,
                      updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "id": f.id,
                    "code": f.code,
                    "description": f.description,
                    "expr": json.dumps(f.expression.to_dict()),
                    "mandatory": f.mandatory,
                    "tenant_id": f.tenant_id,
                    "datasource_id": f.datasource_id,
                    "version": f.version,
                    "status": f.status.value,
                    "now": _now(),
                },
            )

    def load_filters(self) -> list[FilterRule]:
        with self._engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM sc_filter_rule")).mappings().all()
            out: list[FilterRule] = []
            for r in rows:
                expr = json.loads(r["expression_json"] or "{}")
                out.append(
                    FilterRule(
                        id=r["id"],
                        tenant_id=r["tenant_id"],
                        datasource_id=r["datasource_id"],
                        code=r["code"],
                        description=r["description"] or "",
                        expression=FilterExpression(
                            field=expr.get("field", ""),
                            operator=expr.get("operator", "="),
                            values=list(expr.get("values") or []),
                        ),
                        mandatory=bool(r.get("mandatory")),
                        status=AssetStatus(r["status"]),
                        version=int(r.get("version") or 1),
                    )
                )
            return out

    # --- business terms ---

    def upsert_term(self, t: BusinessTerm) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sc_business_term (
                      id, name, normalized_name, description, language,
                      tenant_id, datasource_id, version, status, updated_at
                    ) VALUES (
                      :id, :name, :normalized_name, :description, :language,
                      :tenant_id, :datasource_id, :version, :status, :now
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      name = EXCLUDED.name,
                      normalized_name = EXCLUDED.normalized_name,
                      description = EXCLUDED.description,
                      language = EXCLUDED.language,
                      version = EXCLUDED.version,
                      status = EXCLUDED.status,
                      updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "id": t.id,
                    "name": t.name,
                    "normalized_name": t.normalized_name,
                    "description": t.description,
                    "language": t.language,
                    "tenant_id": t.tenant_id,
                    "datasource_id": t.datasource_id,
                    "version": t.version,
                    "status": t.status.value,
                    "now": _now(),
                },
            )
            conn.execute(
                text("DELETE FROM sc_business_term_synonym WHERE business_term_id = :id"),
                {"id": t.id},
            )
            for syn, norm in zip(t.synonyms, t.normalized_synonyms):
                conn.execute(
                    text(
                        """
                        INSERT INTO sc_business_term_synonym (
                          id, business_term_id, synonym, normalized_synonym, tenant_id, datasource_id
                        ) VALUES (:id, :tid, :syn, :norm, :tenant, :ds)
                        ON CONFLICT (tenant_id, datasource_id, normalized_synonym) DO NOTHING
                        """
                    ),
                    {
                        "id": _id("syn"),
                        "tid": t.id,
                        "syn": syn,
                        "norm": norm,
                        "tenant": t.tenant_id,
                        "ds": t.datasource_id,
                    },
                )

    def load_terms(self) -> list[BusinessTerm]:
        with self._engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM sc_business_term")).mappings().all()
            out: list[BusinessTerm] = []
            for r in rows:
                syns = conn.execute(
                    text(
                        "SELECT synonym FROM sc_business_term_synonym WHERE business_term_id = :id ORDER BY synonym"
                    ),
                    {"id": r["id"]},
                ).scalars().all()
                out.append(
                    BusinessTerm(
                        id=r["id"],
                        tenant_id=r["tenant_id"],
                        datasource_id=r["datasource_id"],
                        name=r["name"],
                        description=r["description"] or "",
                        synonyms=list(syns),
                        language=r.get("language") or "tr",
                        status=AssetStatus(r["status"]),
                        version=int(r.get("version") or 1),
                    )
                )
            return out

    # --- candidates ---

    def upsert_candidate(self, c: VerifiedQueryCandidate) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sc_verified_query_candidate (
                      id, question, logical_plan_json, source, sql_fingerprint, execution_id,
                      candidate_score, tenant_id, datasource_id, version, status, updated_at
                    ) VALUES (
                      :id, :question, :plan, :source, :sql_fp, :exec_id,
                      :score, :tenant_id, :datasource_id, :version, :status, :now
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      question = EXCLUDED.question,
                      logical_plan_json = EXCLUDED.logical_plan_json,
                      source = EXCLUDED.source,
                      sql_fingerprint = EXCLUDED.sql_fingerprint,
                      execution_id = EXCLUDED.execution_id,
                      candidate_score = EXCLUDED.candidate_score,
                      version = EXCLUDED.version,
                      status = EXCLUDED.status,
                      updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "id": c.id,
                    "question": c.question,
                    "plan": json.dumps(c.logical_plan),
                    "source": c.source,
                    "sql_fp": c.sql_fingerprint,
                    "exec_id": c.execution_id,
                    "score": c.candidate_score,
                    "tenant_id": c.tenant_id,
                    "datasource_id": c.datasource_id,
                    "version": c.version,
                    "status": c.status.value,
                    "now": _now(),
                },
            )

    def load_candidates(self) -> list[VerifiedQueryCandidate]:
        with self._engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM sc_verified_query_candidate")).mappings().all()
            return [
                VerifiedQueryCandidate(
                    id=r["id"],
                    tenant_id=r["tenant_id"],
                    datasource_id=r["datasource_id"],
                    question=r["question"],
                    logical_plan=json.loads(r["logical_plan_json"] or "{}"),
                    source=r["source"],
                    sql_fingerprint=r.get("sql_fingerprint"),
                    execution_id=r.get("execution_id"),
                    candidate_score=float(r.get("candidate_score") or 0),
                    status=AssetStatus(r["status"]),
                    version=int(r.get("version") or 1),
                )
                for r in rows
            ]

    # --- verified queries ---

    def upsert_verified_query(self, v: VerifiedQuery) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sc_verified_query (
                      id, verified_question_id, semantic_version, schema_version, dialect,
                      logical_plan_json, compiled_sql, expected_result_fingerprint,
                      tenant_id, datasource_id, version, status, updated_at
                    ) VALUES (
                      :id, :vqid, :semver, :schema_ver, :dialect,
                      :plan, :sql, :fp,
                      :tenant_id, :datasource_id, :version, :status, :now
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      semantic_version = EXCLUDED.semantic_version,
                      schema_version = EXCLUDED.schema_version,
                      dialect = EXCLUDED.dialect,
                      logical_plan_json = EXCLUDED.logical_plan_json,
                      compiled_sql = EXCLUDED.compiled_sql,
                      expected_result_fingerprint = EXCLUDED.expected_result_fingerprint,
                      version = EXCLUDED.version,
                      status = EXCLUDED.status,
                      updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "id": v.id,
                    "vqid": v.verified_question_id,
                    "semver": v.semantic_version,
                    "schema_ver": v.schema_version,
                    "dialect": v.dialect,
                    "plan": json.dumps(v.logical_plan),
                    "sql": v.compiled_sql,
                    "fp": v.expected_result_fingerprint,
                    "tenant_id": v.tenant_id,
                    "datasource_id": v.datasource_id,
                    "version": v.version,
                    "status": v.status.value,
                    "now": _now(),
                },
            )

    def load_verified_queries(self) -> list[VerifiedQuery]:
        with self._engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM sc_verified_query")).mappings().all()
            return [
                VerifiedQuery(
                    id=r["id"],
                    tenant_id=r["tenant_id"],
                    datasource_id=r["datasource_id"],
                    verified_question_id=r["verified_question_id"],
                    semantic_version=r["semantic_version"],
                    schema_version=r["schema_version"],
                    dialect=r["dialect"],
                    logical_plan=json.loads(r["logical_plan_json"] or "{}"),
                    compiled_sql=r.get("compiled_sql"),
                    expected_result_fingerprint=r.get("expected_result_fingerprint"),
                    status=AssetStatus(r["status"]),
                    version=int(r.get("version") or 1),
                )
                for r in rows
            ]

    # --- promotions ---

    def upsert_promotion(self, p: PromotionRequest) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO sc_promotion_request (
                      id, asset_type, asset_id, phase, requires_dual_approval,
                      tenant_id, datasource_id, created_by, version, status, updated_at
                    ) VALUES (
                      :id, :asset_type, :asset_id, :phase, :dual,
                      :tenant_id, :datasource_id, :created_by, :version, :status, :now
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      phase = EXCLUDED.phase,
                      requires_dual_approval = EXCLUDED.requires_dual_approval,
                      version = EXCLUDED.version,
                      status = EXCLUDED.status,
                      updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "id": p.id,
                    "asset_type": p.asset_type,
                    "asset_id": p.asset_id,
                    "phase": p.phase.value,
                    "dual": p.requires_dual_approval,
                    "tenant_id": p.tenant_id,
                    "datasource_id": p.datasource_id,
                    "created_by": p.created_by,
                    "version": 1,
                    "status": p.status.value,
                    "now": _now(),
                },
            )
            conn.execute(
                text("DELETE FROM sc_promotion_review WHERE promotion_request_id = :id"),
                {"id": p.id},
            )
            for rev in p.reviews:
                conn.execute(
                    text(
                        """
                        INSERT INTO sc_promotion_review (
                          id, promotion_request_id, reviewer_user_id, role, decision, comment,
                          tenant_id, datasource_id, status, updated_at
                        ) VALUES (
                          :id, :pid, :uid, :role, :decision, :comment,
                          :tenant_id, :datasource_id, 'DRAFT', :now
                        )
                        """
                    ),
                    {
                        "id": _id("rev"),
                        "pid": p.id,
                        "uid": rev.reviewer_user_id,
                        "role": rev.role,
                        "decision": rev.decision,
                        "comment": rev.comment,
                        "tenant_id": p.tenant_id,
                        "datasource_id": p.datasource_id,
                        "now": _now(),
                    },
                )

    def load_promotions(self) -> list[PromotionRequest]:
        with self._engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM sc_promotion_request")).mappings().all()
            out: list[PromotionRequest] = []
            for r in rows:
                reviews = conn.execute(
                    text(
                        "SELECT * FROM sc_promotion_review WHERE promotion_request_id = :id ORDER BY created_at"
                    ),
                    {"id": r["id"]},
                ).mappings().all()
                promo = PromotionRequest(
                    id=r["id"],
                    tenant_id=r["tenant_id"],
                    datasource_id=r["datasource_id"],
                    asset_type=r["asset_type"],
                    asset_id=r["asset_id"],
                    requires_dual_approval=bool(r.get("requires_dual_approval")),
                    phase=PromotionPhase(r["phase"]),
                    reviews=[
                        PromotionReview(
                            reviewer_user_id=x["reviewer_user_id"],
                            role=x["role"],
                            decision=x["decision"],
                            comment=x.get("comment") or "",
                        )
                        for x in reviews
                    ],
                    status=AssetStatus(r["status"]),
                    created_by=r.get("created_by"),
                )
                out.append(promo)
            return out

    # --- versions ---

    def upsert_version(self, v: SemanticVersion) -> None:
        with self._engine.begin() as conn:
            if v.is_active:
                conn.execute(
                    text(
                        """
                        UPDATE sc_semantic_version
                        SET is_active = false, updated_at = :now
                        WHERE tenant_id = :tenant AND datasource_id = :ds AND is_active = true
                        """
                    ),
                    {"now": _now(), "tenant": v.tenant_id, "ds": v.datasource_id},
                )
            manifest = json.dumps(v.build_manifest()) if not v.manifest_sha256 else None
            if manifest is None and v.manifest_sha256:
                # rebuild for storage
                body = v.build_manifest()
                manifest = json.dumps(body)
            conn.execute(
                text(
                    """
                    INSERT INTO sc_semantic_version (
                      id, version, schema_version, manifest_json, manifest_sha256, is_active,
                      published_at, published_by, tenant_id, datasource_id, status, updated_at
                    ) VALUES (
                      :id, :version, :schema_version, :manifest, :sha, :is_active,
                      :published_at, :published_by, :tenant_id, :datasource_id, :status, :now
                    )
                    ON CONFLICT (id) DO UPDATE SET
                      manifest_json = EXCLUDED.manifest_json,
                      manifest_sha256 = EXCLUDED.manifest_sha256,
                      is_active = EXCLUDED.is_active,
                      published_at = EXCLUDED.published_at,
                      published_by = EXCLUDED.published_by,
                      status = EXCLUDED.status,
                      updated_at = EXCLUDED.updated_at
                    """
                ),
                {
                    "id": v.id,
                    "version": v.version,
                    "schema_version": v.schema_version,
                    "manifest": manifest,
                    "sha": v.manifest_sha256,
                    "is_active": v.is_active,
                    "published_at": datetime.fromisoformat(v.published_at) if v.published_at else None,
                    "published_by": v.published_by,
                    "tenant_id": v.tenant_id,
                    "datasource_id": v.datasource_id,
                    "status": v.status.value,
                    "now": _now(),
                },
            )
            conn.execute(
                text("DELETE FROM sc_semantic_version_asset WHERE semantic_version_id = :id"),
                {"id": v.id},
            )
            for a in v.assets:
                conn.execute(
                    text(
                        """
                        INSERT INTO sc_semantic_version_asset (
                          id, semantic_version_id, asset_type, asset_code, asset_version, sha256,
                          tenant_id, datasource_id, status, updated_at
                        ) VALUES (
                          :id, :vid, :atype, :code, :aver, :sha,
                          :tenant_id, :datasource_id, 'PUBLISHED', :now
                        )
                        """
                    ),
                    {
                        "id": _id("sva"),
                        "vid": v.id,
                        "atype": a.type,
                        "code": a.code,
                        "aver": a.version,
                        "sha": a.sha256,
                        "tenant_id": v.tenant_id,
                        "datasource_id": v.datasource_id,
                        "now": _now(),
                    },
                )

    def load_versions(self) -> list[SemanticVersion]:
        with self._engine.connect() as conn:
            rows = conn.execute(text("SELECT * FROM sc_semantic_version")).mappings().all()
            out: list[SemanticVersion] = []
            for r in rows:
                assets = conn.execute(
                    text(
                        "SELECT * FROM sc_semantic_version_asset WHERE semantic_version_id = :id"
                    ),
                    {"id": r["id"]},
                ).mappings().all()
                published_at = r.get("published_at")
                out.append(
                    SemanticVersion(
                        id=r["id"],
                        tenant_id=r["tenant_id"],
                        datasource_id=r["datasource_id"],
                        version=r["version"],
                        schema_version=r["schema_version"],
                        assets=[
                            ManifestAsset(
                                type=a["asset_type"],
                                code=a["asset_code"],
                                version=int(a["asset_version"]),
                                sha256=a["sha256"],
                            )
                            for a in assets
                        ],
                        status=AssetStatus(r["status"]),
                        published_by=r.get("published_by"),
                        published_at=published_at.isoformat() if published_at else None,
                        manifest_sha256=r.get("manifest_sha256"),
                        is_active=bool(r.get("is_active")),
                    )
                )
            return out

    def hydrate_store_dicts(self) -> dict[str, Any]:
        """Load all entities for CatalogStore hydration."""
        metrics = {m.id: m for m in self.load_metrics()}
        filters = {f.id: f for f in self.load_filters()}
        terms = {t.id: t for t in self.load_terms()}
        candidates = {c.id: c for c in self.load_candidates()}
        verified = {v.id: v for v in self.load_verified_queries()}
        promotions = {p.id: p for p in self.load_promotions()}
        versions = {v.id: v for v in self.load_versions()}
        active: dict[tuple[str, str], str] = {}
        for v in versions.values():
            if v.is_active:
                active[(v.tenant_id, v.datasource_id)] = v.id
        return {
            "metrics": metrics,
            "filters": filters,
            "business_terms": terms,
            "candidates": candidates,
            "verified_queries": verified,
            "promotions": promotions,
            "versions": versions,
            "active_version": active,
        }
