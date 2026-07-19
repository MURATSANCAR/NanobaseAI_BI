"""011 — precompiled query scenario engine tables."""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "011_scenario_engine"
down_revision: Union[str, None] = "010_feedback_rating_partial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sc_scenario_family",
        sa.Column("code", sa.String(64), primary_key=True),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
    )

    op.create_table(
        "sc_scenario_template",
        sa.Column("code", sa.String(128), primary_key=True),
        sa.Column("family", sa.String(64), sa.ForeignKey("sc_scenario_family.code"), nullable=False),
        sa.Column("required_slots_json", sa.Text(), nullable=False),
        sa.Column("optional_slots_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
    )
    op.create_index("ix_sc_scenario_template_family", "sc_scenario_template", ["family"])

    op.create_table(
        "sc_scenario_template_slot",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("template_code", sa.String(128), sa.ForeignKey("sc_scenario_template.code"), nullable=False),
        sa.Column("slot_name", sa.String(64), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("slot_type", sa.String(64), nullable=False, server_default="string"),
    )

    op.create_table(
        "sc_scenario_instance",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("datasource_id", sa.String(64), nullable=False),
        sa.Column("scenario_code", sa.String(256), nullable=False),
        sa.Column("family", sa.String(64), nullable=False),
        sa.Column("logical_plan_json", sa.Text(), nullable=False),
        sa.Column("schema_version", sa.String(128), nullable=False),
        sa.Column("semantic_version", sa.String(64), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False, server_default="2026.07.1"),
        sa.Column("risk_tier", sa.String(8), nullable=False, server_default="A"),
        sa.Column("status", sa.String(32), nullable=False, server_default="GENERATED"),
        sa.Column("category", sa.String(128), nullable=False, server_default=""),
        sa.Column("canonical_question", sa.Text(), nullable=False, server_default=""),
        sa.Column("generator_version", sa.String(32), nullable=False, server_default="1.0.0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index(
        "ix_sc_scenario_instance_tds_status",
        "sc_scenario_instance",
        ["tenant_id", "datasource_id", "status"],
    )
    op.create_index(
        "ix_sc_scenario_instance_tds_code",
        "sc_scenario_instance",
        ["tenant_id", "datasource_id", "scenario_code"],
        unique=True,
    )
    op.create_index(
        "ix_sc_scenario_instance_versions",
        "sc_scenario_instance",
        ["schema_version", "semantic_version"],
    )
    op.create_index("ix_sc_scenario_instance_family", "sc_scenario_instance", ["family"])

    op.create_table(
        "sc_scenario_parameter_definition",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scenario_id", sa.String(64), sa.ForeignKey("sc_scenario_instance.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("param_type", sa.String(64), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("default_json", sa.Text()),
    )

    op.create_table(
        "sc_scenario_paraphrase",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scenario_id", sa.String(64), sa.ForeignKey("sc_scenario_instance.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("datasource_id", sa.String(64), nullable=False),
        sa.Column("language", sa.String(16), nullable=False, server_default="tr"),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("normalized_text", sa.Text(), nullable=False),
        sa.Column("normalized_question_hash", sa.String(64), nullable=False),
        sa.Column("embedding_id", sa.String(128)),
        sa.Column("status", sa.String(32), nullable=False, server_default="GENERATED"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index(
        "ix_sc_scenario_paraphrase_hash",
        "sc_scenario_paraphrase",
        ["tenant_id", "datasource_id", "normalized_question_hash"],
    )
    op.create_index("ix_sc_scenario_paraphrase_scenario", "sc_scenario_paraphrase", ["scenario_id"])

    op.create_table(
        "sc_scenario_compilation",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scenario_id", sa.String(64), sa.ForeignKey("sc_scenario_instance.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dialect", sa.String(32), nullable=False),
        sa.Column("sql_template", sa.Text(), nullable=False),
        sa.Column("ast_fingerprint", sa.String(128), nullable=False),
        sa.Column("validation_status", sa.String(32), nullable=False, server_default="PENDING"),
        sa.Column("bind_params_json", sa.Text(), nullable=False, server_default="[]"),
        sa.UniqueConstraint("scenario_id", "dialect", name="uq_sc_scenario_compilation_dialect"),
    )

    op.create_table(
        "sc_scenario_dependency",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scenario_id", sa.String(64), sa.ForeignKey("sc_scenario_instance.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dep_kind", sa.String(32), nullable=False),
        sa.Column("dep_ref", sa.String(256), nullable=False),
    )
    op.create_index("ix_sc_scenario_dependency_ref", "sc_scenario_dependency", ["dep_kind", "dep_ref"])

    op.create_table(
        "sc_scenario_validation_run",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scenario_id", sa.String(64), sa.ForeignKey("sc_scenario_instance.id", ondelete="CASCADE"), nullable=False),
        sa.Column("layer", sa.String(64), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("detail_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )

    op.create_table(
        "sc_scenario_execution_baseline",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scenario_id", sa.String(64), sa.ForeignKey("sc_scenario_instance.id", ondelete="CASCADE"), nullable=False),
        sa.Column("result_fingerprint", sa.String(128), nullable=False),
        sa.Column("row_count", sa.Integer()),
        sa.Column("expected_json", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )

    op.create_table(
        "sc_scenario_performance_profile",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scenario_id", sa.String(64), sa.ForeignKey("sc_scenario_instance.id", ondelete="CASCADE"), nullable=False),
        sa.Column("classification", sa.String(32), nullable=False, server_default="LOW"),
        sa.Column("max_rows", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("timeout_ms", sa.Integer(), nullable=False, server_default="5000"),
        sa.Column("max_payload_bytes", sa.Integer(), nullable=False, server_default="1048576"),
        sa.Column("estimated_rows", sa.Integer()),
        sa.Column("join_count", sa.Integer(), nullable=False, server_default="0"),
    )

    op.create_table(
        "sc_scenario_publish_batch",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("datasource_id", sa.String(64), nullable=False),
        sa.Column("schema_version", sa.String(128), nullable=False),
        sa.Column("semantic_version", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="PREPARING"),
        sa.Column("scenario_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("checksum", sa.String(128)),
        sa.Column("error", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )
    op.create_index(
        "ix_sc_scenario_publish_batch_tds",
        "sc_scenario_publish_batch",
        ["tenant_id", "datasource_id", "status"],
    )

    op.create_table(
        "sc_scenario_usage_stat",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scenario_id", sa.String(64), sa.ForeignKey("sc_scenario_instance.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("datasource_id", sa.String(64), nullable=False),
        sa.Column("match_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("execution_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("gateway_rejection_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fallback_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("avg_latency_ms", sa.Float()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )

    op.create_table(
        "sc_scenario_failure",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scenario_id", sa.String(64)),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("datasource_id", sa.String(64), nullable=False),
        sa.Column("failure_kind", sa.String(64), nullable=False),
        sa.Column("detail", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )

    op.create_table(
        "sc_scenario_review",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("scenario_id", sa.String(64), sa.ForeignKey("sc_scenario_instance.id", ondelete="CASCADE"), nullable=False),
        sa.Column("reviewer", sa.String(128), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
    )

    op.create_table(
        "sc_scenario_version",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("tenant_id", sa.String(64), nullable=False),
        sa.Column("datasource_id", sa.String(64), nullable=False),
        sa.Column("active_batch_id", sa.String(64)),
        sa.Column("schema_version", sa.String(128), nullable=False),
        sa.Column("semantic_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
        sa.UniqueConstraint("tenant_id", "datasource_id", name="uq_sc_scenario_version_tds"),
    )


def downgrade() -> None:
    for table in (
        "sc_scenario_version",
        "sc_scenario_review",
        "sc_scenario_failure",
        "sc_scenario_usage_stat",
        "sc_scenario_publish_batch",
        "sc_scenario_performance_profile",
        "sc_scenario_execution_baseline",
        "sc_scenario_validation_run",
        "sc_scenario_dependency",
        "sc_scenario_compilation",
        "sc_scenario_paraphrase",
        "sc_scenario_parameter_definition",
        "sc_scenario_instance",
        "sc_scenario_template_slot",
        "sc_scenario_template",
        "sc_scenario_family",
    ):
        op.drop_table(table)
