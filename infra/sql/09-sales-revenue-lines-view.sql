-- Additive view for the deterministic "total_revenue"/"total_quantity_sold"
-- semantic metrics (backend/nanobase_api/semantic_catalog/application/
-- seed_total_revenue_slice.py). Precomputes quantity*unit_price alongside the
-- owning order's status/date and the customer/product dimension columns used
-- for GROUP BY breakdowns, because Metric.source must be a plain column (not
-- an arbitrary expression) and MetricCompiler's group_by likewise expects
-- plain columns already present on the metric's own source table — no
-- runtime joins needed for a dimension.
-- Non-destructive: adds/redefines views only, touches no existing table.

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
    (soi.quantity * soi.unit_price) AS line_total,
    c.customer_name,
    c.segment,
    c.country AS customer_country,
    p.category AS product_category,
    p.product_name,
    -- Forecasting V1 (plan Faz 0.4): city dimension for "İstanbul satışları" series.
    -- Appended last so CREATE OR REPLACE VIEW stays valid on live databases.
    b.city AS branch_city
FROM analytics.sales_order_items soi
JOIN analytics.sales_orders so ON so.order_id = soi.order_id
JOIN analytics.customers c ON c.customer_id = so.customer_id
JOIN analytics.products p ON p.product_id = soi.product_id
LEFT JOIN analytics.branches b ON b.branch_id = so.branch_id;

CREATE OR REPLACE VIEW public.v_sales_revenue_lines AS
SELECT * FROM analytics.v_sales_revenue_lines;
