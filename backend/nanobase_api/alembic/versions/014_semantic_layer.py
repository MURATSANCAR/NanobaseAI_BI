"""014 — Semantic Layer V1: sl_* tables (catalog, evidence, candidates, versions, query log, profile, annotations)."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "014_semantic_layer"
down_revision: Union[str, None] = "013_forecast_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sl_concept (
            id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL,
            datasource_id VARCHAR(128) NOT NULL,
            term TEXT NOT NULL,
            normalized_term VARCHAR(256) NOT NULL,
            semantic_type VARCHAR(32) NOT NULL,
            domain VARCHAR(64) NOT NULL DEFAULT 'general',
            sense_id INTEGER NOT NULL DEFAULT 1,
            status VARCHAR(32) NOT NULL DEFAULT 'DISCOVERED',
            confidence DOUBLE PRECISION NOT NULL DEFAULT 0,
            version INTEGER NOT NULL DEFAULT 1,
            synonyms_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            explain_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_sl_concept_lookup ON sl_concept (tenant_id, datasource_id, normalized_term, status);
        CREATE INDEX IF NOT EXISTS ix_sl_concept_type ON sl_concept (tenant_id, datasource_id, semantic_type);

        CREATE TABLE IF NOT EXISTS sl_mapping (
            id VARCHAR(64) PRIMARY KEY,
            concept_id VARCHAR(64) NOT NULL REFERENCES sl_concept(id) ON DELETE CASCADE,
            entity VARCHAR(128) NOT NULL,
            table_pattern VARCHAR(256) NOT NULL,
            column_name VARCHAR(128),
            operator VARCHAR(16),
            values_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            formula TEXT,
            time_primitive VARCHAR(64),
            extra_json JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE INDEX IF NOT EXISTS ix_sl_mapping_concept ON sl_mapping (concept_id);
        CREATE INDEX IF NOT EXISTS ix_sl_mapping_column ON sl_mapping (entity, column_name);

        CREATE TABLE IF NOT EXISTS sl_evidence (
            id VARCHAR(64) PRIMARY KEY,
            concept_id VARCHAR(64) NOT NULL REFERENCES sl_concept(id) ON DELETE CASCADE,
            evidence_type VARCHAR(32) NOT NULL,
            source_id VARCHAR(256) NOT NULL,
            support_count INTEGER NOT NULL DEFAULT 1,
            weight DOUBLE PRECISION NOT NULL DEFAULT 1,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_sl_evidence_src UNIQUE (concept_id, evidence_type, source_id)
        );
        CREATE INDEX IF NOT EXISTS ix_sl_evidence_concept ON sl_evidence (concept_id, evidence_type);

        CREATE TABLE IF NOT EXISTS sl_counter_evidence (
            id VARCHAR(64) PRIMARY KEY,
            concept_id VARCHAR(64) NOT NULL REFERENCES sl_concept(id) ON DELETE CASCADE,
            source_id VARCHAR(256) NOT NULL,
            conflict_type VARCHAR(32) NOT NULL,
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            severity VARCHAR(16) NOT NULL DEFAULT 'MEDIUM',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_sl_counter_src UNIQUE (concept_id, conflict_type, source_id)
        );
        CREATE INDEX IF NOT EXISTS ix_sl_counter_concept ON sl_counter_evidence (concept_id);

        CREATE TABLE IF NOT EXISTS sl_candidate (
            id VARCHAR(64) PRIMARY KEY,
            concept_id VARCHAR(64) NOT NULL REFERENCES sl_concept(id) ON DELETE CASCADE,
            generated_by VARCHAR(64) NOT NULL,
            model_version VARCHAR(128),
            payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            status VARCHAR(16) NOT NULL DEFAULT 'OPEN',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_sl_candidate_concept ON sl_candidate (concept_id);

        CREATE TABLE IF NOT EXISTS sl_catalog_version (
            id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL,
            datasource_id VARCHAR(128) NOT NULL,
            version INTEGER NOT NULL,
            certified_count INTEGER NOT NULL DEFAULT 0,
            snapshot_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            note TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_sl_catalog_version UNIQUE (tenant_id, datasource_id, version)
        );

        CREATE TABLE IF NOT EXISTS sl_query_log (
            id VARCHAR(64) PRIMARY KEY,
            tenant_id VARCHAR(64) NOT NULL,
            datasource_id VARCHAR(128) NOT NULL,
            question TEXT NOT NULL,
            normalized_question TEXT NOT NULL,
            sql_text TEXT,
            compiler VARCHAR(32),
            catalog_version INTEGER,
            resolved_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            executed BOOLEAN NOT NULL DEFAULT FALSE,
            row_count INTEGER,
            validated BOOLEAN,
            result_fingerprint VARCHAR(64),
            latency_ms INTEGER,
            error TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_sl_query_log_validated ON sl_query_log (tenant_id, datasource_id, validated);

        CREATE TABLE IF NOT EXISTS sl_schema_profile (
            id VARCHAR(64) PRIMARY KEY,
            datasource_id VARCHAR(128) NOT NULL,
            schema_name VARCHAR(128) NOT NULL DEFAULT 'dbo',
            table_name VARCHAR(256) NOT NULL,
            table_pattern VARCHAR(256) NOT NULL,
            entity VARCHAR(128) NOT NULL,
            columns_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            primary_key_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            relationships_json JSONB NOT NULL DEFAULT '[]'::jsonb,
            context_json JSONB NOT NULL DEFAULT '{}'::jsonb,
            row_count INTEGER,
            description TEXT,
            scanned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_sl_schema_profile UNIQUE (datasource_id, table_pattern)
        );

        CREATE TABLE IF NOT EXISTS sl_schema_annotation (
            id VARCHAR(64) PRIMARY KEY,
            datasource_id VARCHAR(128) NOT NULL,
            table_pattern VARCHAR(256) NOT NULL,
            column_name VARCHAR(128),
            text TEXT NOT NULL,
            author VARCHAR(128) NOT NULL DEFAULT 'portal',
            status VARCHAR(16) NOT NULL DEFAULT 'ACTIVE',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE INDEX IF NOT EXISTS ix_sl_annotation_lookup ON sl_schema_annotation (datasource_id, table_pattern, column_name, status);
        """
    )


def downgrade() -> None:
    for t in ("sl_schema_annotation", "sl_schema_profile", "sl_query_log", "sl_catalog_version", "sl_candidate", "sl_counter_evidence", "sl_evidence", "sl_mapping", "sl_concept"):
        op.execute(f"DROP TABLE IF EXISTS {t}")
