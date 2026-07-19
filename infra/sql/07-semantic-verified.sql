-- Faz 7: verified SQL cache + feedback feedback (bi_meta)
CREATE TABLE IF NOT EXISTS bi_verified_sql (
    pk              SERIAL PRIMARY KEY,
    id              VARCHAR(64) NOT NULL UNIQUE,
    tenant_id       VARCHAR(64) NOT NULL DEFAULT 'default',
    datasource_id   VARCHAR(64) NOT NULL,
    question_norm   TEXT NOT NULL,
    question_display TEXT NOT NULL,
    sql_text        TEXT NOT NULL,
    status          VARCHAR(32) NOT NULL DEFAULT 'verified',
    hit_count       INTEGER NOT NULL DEFAULT 0,
    created_by      VARCHAR(128),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bi_verified_sql_tenant ON bi_verified_sql (tenant_id);
CREATE INDEX IF NOT EXISTS ix_bi_verified_sql_ds ON bi_verified_sql (datasource_id);
CREATE INDEX IF NOT EXISTS ix_bi_verified_sql_qnorm ON bi_verified_sql (question_norm);

CREATE TABLE IF NOT EXISTS bi_query_feedback (
    pk              SERIAL PRIMARY KEY,
    id              VARCHAR(64) NOT NULL UNIQUE,
    tenant_id       VARCHAR(64) NOT NULL DEFAULT 'default',
    datasource_id   VARCHAR(64) NOT NULL,
    session_id      VARCHAR(128),
    question        TEXT NOT NULL,
    sql_text        TEXT,
    rating          SMALLINT NOT NULL CHECK (rating IN (-1, 0, 1)),
    comment         TEXT,
    promote_verified BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_bi_query_feedback_tenant ON bi_query_feedback (tenant_id);
CREATE INDEX IF NOT EXISTS ix_bi_query_feedback_ds ON bi_query_feedback (datasource_id);
