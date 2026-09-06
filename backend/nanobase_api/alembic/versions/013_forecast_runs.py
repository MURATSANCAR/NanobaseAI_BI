"""013 — forecast provenance: fc_forecast_run / fc_forecast_point (plan Faz 5.5, 6.1)."""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "013_forecast_runs"
down_revision: Union[str, None] = "012_scenario_prod_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fc_forecast_run (
            id                 VARCHAR(64) PRIMARY KEY,
            tenant_id          VARCHAR(64) NOT NULL,
            datasource_id      VARCHAR(128) NOT NULL,
            metric_code        VARCHAR(128) NOT NULL,
            metric_version     INTEGER,
            dimension_filters  JSONB NOT NULL DEFAULT '{}'::jsonb,
            frequency          VARCHAR(2) NOT NULL,
            horizon            INTEGER NOT NULL,
            history_points     INTEGER NOT NULL,
            bundle_hash        VARCHAR(80) NOT NULL,
            engine             VARCHAR(64) NOT NULL,
            engine_version     VARCHAR(32) NOT NULL,
            checkpoint_sha     VARCHAR(80),
            benchmark_ref      VARCHAR(160),
            question           TEXT,
            session_id         VARCHAR(128),
            warnings           JSONB NOT NULL DEFAULT '[]'::jsonb,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS ix_fc_forecast_run_lookup
        ON fc_forecast_run (tenant_id, datasource_id, metric_code, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS fc_forecast_point (
            run_id      VARCHAR(64) NOT NULL REFERENCES fc_forecast_run (id) ON DELETE CASCADE,
            ts          DATE NOT NULL,
            p10         NUMERIC(20, 4) NOT NULL,
            p50         NUMERIC(20, 4) NOT NULL,
            p90         NUMERIC(20, 4) NOT NULL,
            actual      NUMERIC(20, 4),
            violation   VARCHAR(16),
            reconciled_at TIMESTAMPTZ,
            PRIMARY KEY (run_id, ts)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_fc_forecast_point_pending ON fc_forecast_point (ts) WHERE actual IS NULL")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS fc_forecast_point")
    op.execute("DROP TABLE IF EXISTS fc_forecast_run")
