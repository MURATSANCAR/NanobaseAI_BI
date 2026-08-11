-- Additive view for the deterministic "total_revenue" semantic metric
-- (backend/nanobase_api/semantic_catalog/application/seed_total_revenue_slice.py).
-- Precomputes quantity*unit_price alongside the owning order's status/date
-- because Metric.source must be a plain column, not an arbitrary expression.
-- Non-destructive: adds views only, touches no existing table/view.

CREATE OR REPLACE VIEW analytics.v_sales_revenue_lines AS
SELECT
    soi.order_id,
    soi.product_id,
    so.customer_id,
    so.branch_id,
    so.order_date,
    so.status,
    so.currency,
    soi.quantity,
    soi.unit_price,
    (soi.quantity * soi.unit_price) AS line_total
FROM analytics.sales_order_items soi
JOIN analytics.sales_orders so ON so.order_id = soi.order_id;

CREATE OR REPLACE VIEW public.v_sales_revenue_lines AS
SELECT * FROM analytics.v_sales_revenue_lines;
