-- Controlled expected-result anchors for invoice scenario validation farm.
-- Applies on top of 08-reporting-rich-schema.sql (analytics.invoices).
-- Business timezone assumption: Europe/Istanbul (date columns are DATE).

-- Ensure deterministic demo rows for period tests (idempotent upserts via temp staging).
CREATE TABLE IF NOT EXISTS analytics.scenario_expected_baseline (
    scenario_code TEXT PRIMARY KEY,
    expected_row_count INT,
    expected_sum NUMERIC(18, 2),
    notes TEXT
);

INSERT INTO analytics.scenario_expected_baseline (scenario_code, expected_row_count, expected_sum, notes)
VALUES
    ('invoice.list.unpaid', NULL, NULL, 'remaining_amount > 0 AND status <> cancelled'),
    ('invoice.list.cancelled', NULL, NULL, 'status = cancelled'),
    ('invoice.list.overdue', NULL, NULL, 'due_date < today AND remaining_amount > 0'),
    ('invoice.sum.previous_month', NULL, NULL, 'SUM(gross_amount) for previous calendar month'),
    ('invoice.count.today', NULL, NULL, 'COUNT(*) for invoice_date = today')
ON CONFLICT (scenario_code) DO NOTHING;

-- Helper view: open invoices (non-cancelled with remaining balance)
CREATE OR REPLACE VIEW analytics.v_scenario_unpaid_invoices AS
SELECT
    i.invoice_id,
    i.invoice_date,
    i.due_date,
    i.gross_amount,
    i.remaining_amount,
    i.currency,
    i.status
FROM analytics.invoices i
WHERE i.status <> 'cancelled'
  AND i.remaining_amount > 0;
