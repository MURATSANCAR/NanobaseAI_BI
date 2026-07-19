"""Ensure bi_meta budget satellite tables exist (idempotent DDL)."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

_DDL = [
    """
    CREATE TABLE IF NOT EXISTS bi_budget_periods (
      pk SERIAL PRIMARY KEY,
      tenant_id VARCHAR(64) NOT NULL,
      budget_id VARCHAR(64) NOT NULL,
      period_index INTEGER NOT NULL DEFAULT 1,
      allocated DOUBLE PRECISION NOT NULL DEFAULT 0,
      actual DOUBLE PRECISION,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT uq_bi_budget_period UNIQUE (tenant_id, budget_id, period_index)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_bi_budget_period_budget
      ON bi_budget_periods (tenant_id, budget_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS bi_budget_commitments (
      pk SERIAL PRIMARY KEY,
      id VARCHAR(64) NOT NULL,
      tenant_id VARCHAR(64) NOT NULL,
      budget_id VARCHAR(64) NOT NULL,
      description VARCHAR(256) NOT NULL DEFAULT '',
      amount DOUBLE PRECISION NOT NULL DEFAULT 0,
      currency VARCHAR(8) NOT NULL DEFAULT 'TRY',
      status VARCHAR(32) NOT NULL DEFAULT 'open',
      due_date VARCHAR(32),
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_bi_budget_commit_budget
      ON bi_budget_commitments (tenant_id, budget_id)
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_bi_budget_commit_id
      ON bi_budget_commitments (id)
    """,
    """
    CREATE TABLE IF NOT EXISTS bi_fx_rates (
      pk SERIAL PRIMARY KEY,
      tenant_id VARCHAR(64) NOT NULL,
      from_currency VARCHAR(8) NOT NULL DEFAULT 'USD',
      to_currency VARCHAR(8) NOT NULL DEFAULT 'TRY',
      rate DOUBLE PRECISION NOT NULL DEFAULT 1,
      as_of TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT uq_bi_fx_rate UNIQUE (tenant_id, from_currency, to_currency, as_of)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_bi_fx_tenant_pair
      ON bi_fx_rates (tenant_id, from_currency, to_currency)
    """,
    """
    CREATE TABLE IF NOT EXISTS bi_budget_change_log (
      pk SERIAL PRIMARY KEY,
      tenant_id VARCHAR(64) NOT NULL,
      budget_id VARCHAR(64) NOT NULL,
      action VARCHAR(32) NOT NULL DEFAULT 'update',
      actor VARCHAR(128) NOT NULL DEFAULT 'system',
      field VARCHAR(64),
      old_value TEXT,
      new_value TEXT,
      payload_json TEXT NOT NULL DEFAULT '{}',
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_bi_budget_clog_tenant_budget
      ON bi_budget_change_log (tenant_id, budget_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS bi_cost_centers (
      pk SERIAL PRIMARY KEY,
      id VARCHAR(64) NOT NULL,
      tenant_id VARCHAR(64) NOT NULL,
      code VARCHAR(64) NOT NULL DEFAULT '',
      name VARCHAR(256) NOT NULL DEFAULT '',
      parent_id VARCHAR(64),
      active BOOLEAN NOT NULL DEFAULT TRUE,
      created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      CONSTRAINT uq_bi_cost_center_code UNIQUE (tenant_id, code)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bi_budget_actuals_history (
      pk SERIAL PRIMARY KEY,
      tenant_id VARCHAR(64) NOT NULL,
      budget_id VARCHAR(64) NOT NULL,
      actual DOUBLE PRECISION,
      source VARCHAR(64) NOT NULL DEFAULT 'refresh',
      recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
      payload_json TEXT NOT NULL DEFAULT '{}'
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_bi_budget_hist_budget
      ON bi_budget_actuals_history (tenant_id, budget_id, recorded_at DESC)
    """,
]

_ensured = False


def ensure_budget_tables(engine: Engine) -> None:
    """Idempotent CREATE TABLE / INDEX for budget satellite tables."""
    global _ensured
    if _ensured:
        return
    with engine.begin() as conn:
        for stmt in _DDL:
            conn.execute(text(stmt))
    _ensured = True
