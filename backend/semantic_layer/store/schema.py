"""sl_* tables (SQLAlchemy Core). Works on PostgreSQL (production, bi_meta) and SQLite (tests/CLI).

Production DDL lives in nanobase_api/alembic/versions/014_semantic_layer.py (JSONB); this metadata is
used for SQLite `create_all` and for typed Core statements.
"""

from __future__ import annotations

import sqlalchemy as sa

metadata = sa.MetaData()

sl_concept = sa.Table(
    "sl_concept",
    metadata,
    sa.Column("id", sa.String(64), primary_key=True),
    sa.Column("tenant_id", sa.String(64), nullable=False),
    sa.Column("datasource_id", sa.String(128), nullable=False),
    sa.Column("term", sa.Text(), nullable=False),
    sa.Column("normalized_term", sa.String(256), nullable=False),
    sa.Column("semantic_type", sa.String(32), nullable=False),
    sa.Column("domain", sa.String(64), nullable=False, server_default="general"),
    sa.Column("sense_id", sa.Integer(), nullable=False, server_default="1"),
    sa.Column("status", sa.String(32), nullable=False, server_default="DISCOVERED"),
    sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
    sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    sa.Column("synonyms_json", sa.JSON(), nullable=False, default=list),
    sa.Column("explain_json", sa.JSON(), nullable=False, default=dict),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Index("ix_sl_concept_lookup", "tenant_id", "datasource_id", "normalized_term", "status"),
    sa.Index("ix_sl_concept_type", "tenant_id", "datasource_id", "semantic_type"),
    # One row per sense. The store looks a concept up before inserting it, which holds inside one
    # process and not between two: the nightly timer and a hand-run pipeline can both pass the lookup.
    # The evidence for a term would then split across two rows and neither would reach the gate.
    sa.Index("uq_sl_concept_sense", "tenant_id", "datasource_id", "normalized_term", "semantic_type", "sense_id", unique=True),
)

sl_mapping = sa.Table(
    "sl_mapping",
    metadata,
    sa.Column("id", sa.String(64), primary_key=True),
    sa.Column("concept_id", sa.String(64), sa.ForeignKey("sl_concept.id", ondelete="CASCADE"), nullable=False),
    sa.Column("entity", sa.String(128), nullable=False),
    sa.Column("table_pattern", sa.String(256), nullable=False),
    sa.Column("column_name", sa.String(128)),
    sa.Column("operator", sa.String(16)),
    sa.Column("values_json", sa.JSON(), nullable=False, default=list),
    sa.Column("formula", sa.Text()),
    sa.Column("time_primitive", sa.String(64)),
    sa.Column("extra_json", sa.JSON(), nullable=False, default=dict),
    sa.Index("ix_sl_mapping_concept", "concept_id"),
    sa.Index("ix_sl_mapping_column", "entity", "column_name"),
)

sl_evidence = sa.Table(
    "sl_evidence",
    metadata,
    sa.Column("id", sa.String(64), primary_key=True),
    sa.Column("concept_id", sa.String(64), sa.ForeignKey("sl_concept.id", ondelete="CASCADE"), nullable=False),
    sa.Column("evidence_type", sa.String(32), nullable=False),
    sa.Column("source_id", sa.String(256), nullable=False),
    sa.Column("support_count", sa.Integer(), nullable=False, server_default="1"),
    sa.Column("weight", sa.Float(), nullable=False, server_default="1"),
    sa.Column("payload_json", sa.JSON(), nullable=False, default=dict),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Index("ix_sl_evidence_concept", "concept_id", "evidence_type"),
    sa.UniqueConstraint("concept_id", "evidence_type", "source_id", name="uq_sl_evidence_src"),
)

sl_counter_evidence = sa.Table(
    "sl_counter_evidence",
    metadata,
    sa.Column("id", sa.String(64), primary_key=True),
    sa.Column("concept_id", sa.String(64), sa.ForeignKey("sl_concept.id", ondelete="CASCADE"), nullable=False),
    sa.Column("source_id", sa.String(256), nullable=False),
    sa.Column("conflict_type", sa.String(32), nullable=False),
    sa.Column("payload_json", sa.JSON(), nullable=False, default=dict),
    sa.Column("severity", sa.String(16), nullable=False, server_default="MEDIUM"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Index("ix_sl_counter_concept", "concept_id"),
    sa.UniqueConstraint("concept_id", "conflict_type", "source_id", name="uq_sl_counter_src"),
)

sl_candidate = sa.Table(
    "sl_candidate",
    metadata,
    sa.Column("id", sa.String(64), primary_key=True),
    sa.Column("concept_id", sa.String(64), sa.ForeignKey("sl_concept.id", ondelete="CASCADE"), nullable=False),
    sa.Column("generated_by", sa.String(64), nullable=False),
    sa.Column("model_version", sa.String(128)),
    sa.Column("payload_json", sa.JSON(), nullable=False, default=dict),
    sa.Column("status", sa.String(16), nullable=False, server_default="OPEN"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Index("ix_sl_candidate_concept", "concept_id"),
)

sl_catalog_version = sa.Table(
    "sl_catalog_version",
    metadata,
    sa.Column("id", sa.String(64), primary_key=True),
    sa.Column("tenant_id", sa.String(64), nullable=False),
    sa.Column("datasource_id", sa.String(128), nullable=False),
    sa.Column("version", sa.Integer(), nullable=False),
    sa.Column("certified_count", sa.Integer(), nullable=False, server_default="0"),
    sa.Column("snapshot_json", sa.JSON(), nullable=False, default=dict),
    sa.Column("note", sa.Text()),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("tenant_id", "datasource_id", "version", name="uq_sl_catalog_version"),
)

sl_query_log = sa.Table(
    "sl_query_log",
    metadata,
    sa.Column("id", sa.String(64), primary_key=True),
    sa.Column("tenant_id", sa.String(64), nullable=False),
    sa.Column("datasource_id", sa.String(128), nullable=False),
    sa.Column("question", sa.Text(), nullable=False),
    sa.Column("normalized_question", sa.Text(), nullable=False),
    sa.Column("sql_text", sa.Text()),
    sa.Column("compiler", sa.String(32)),
    sa.Column("catalog_version", sa.Integer()),
    sa.Column("resolved_json", sa.JSON(), nullable=False, default=dict),
    sa.Column("executed", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    sa.Column("row_count", sa.Integer()),
    sa.Column("validated", sa.Boolean()),          # NULL = no feedback, True = user confirmed, False = rejected
    sa.Column("result_fingerprint", sa.String(64)),
    sa.Column("latency_ms", sa.Integer()),
    sa.Column("error", sa.Text()),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Index("ix_sl_query_log_validated", "tenant_id", "datasource_id", "validated"),
)

sl_schema_profile = sa.Table(
    "sl_schema_profile",
    metadata,
    sa.Column("id", sa.String(64), primary_key=True),
    sa.Column("datasource_id", sa.String(128), nullable=False),
    sa.Column("schema_name", sa.String(128), nullable=False, server_default=""),
    sa.Column("table_name", sa.String(256), nullable=False),
    sa.Column("table_pattern", sa.String(256), nullable=False),
    sa.Column("entity", sa.String(128), nullable=False),
    sa.Column("columns_json", sa.JSON(), nullable=False, default=list),
    sa.Column("primary_key_json", sa.JSON(), nullable=False, default=list),
    sa.Column("relationships_json", sa.JSON(), nullable=False, default=list),
    sa.Column("context_json", sa.JSON(), nullable=False, default=dict),
    sa.Column("row_count", sa.Integer()),
    sa.Column("description", sa.Text()),
    sa.Column("time_window_json", sa.JSON()),
    sa.Column("scanned_at", sa.DateTime(timezone=True), nullable=False),
    # One row per physical table, not per pattern. A logical entity often lives in several tables that
    # share a pattern and differ only in context — one fiscal period each, say — and keying on the
    # pattern made them overwrite one another, leaving only whichever was profiled last.
    sa.UniqueConstraint("datasource_id", "table_name", name="uq_sl_schema_profile_table"),
)

sl_schema_annotation = sa.Table(
    "sl_schema_annotation",
    metadata,
    sa.Column("id", sa.String(64), primary_key=True),
    sa.Column("datasource_id", sa.String(128), nullable=False),
    sa.Column("table_pattern", sa.String(256), nullable=False),
    sa.Column("column_name", sa.String(128)),
    sa.Column("text", sa.Text(), nullable=False),
    sa.Column("author", sa.String(128), nullable=False, server_default="portal"),
    sa.Column("status", sa.String(16), nullable=False, server_default="ACTIVE"),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Index("ix_sl_annotation_lookup", "datasource_id", "table_pattern", "column_name", "status"),
)


sl_llm_queue = sa.Table(
    "sl_llm_queue",
    metadata,
    sa.Column("id", sa.String(64), primary_key=True),
    sa.Column("tenant_id", sa.String(64), nullable=False),
    sa.Column("datasource_id", sa.String(128), nullable=False),
    sa.Column("user_id", sa.String(128)),
    sa.Column("purpose", sa.String(64), nullable=False),
    sa.Column("question", sa.Text()),
    sa.Column("status", sa.String(16), nullable=False, server_default="WAITING"),  # WAITING | RUNNING | DONE | ABANDONED
    sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("started_at", sa.DateTime(timezone=True)),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
    sa.Column("heartbeat_at", sa.DateTime(timezone=True)),
    sa.Column("worker", sa.String(128)),
    sa.Index("ix_sl_llm_queue_order", "status", "enqueued_at"),
)


def create_all(engine: sa.Engine) -> None:
    metadata.create_all(engine)
