-- Forecasting V1 plan Faz 0.3 — synthetic 48-month sales history (2022-09 .. 2026-08)
-- for the reporting DEMO database only. Customer installs use their remote DB.
--
-- Shape: per branch, monthly order count = base × linear trend × yearly
-- seasonality × noise (setseed → reproducible). Orders get 1-3 lines with real
-- product prices, so monthly revenue follows the same profile.
--
-- Idempotent: skips entirely when any sales_orders row exists before 2026-01-01
-- (the rich-schema seed only inserts 2026 rows). Additive: touches no existing rows.

DO $$
DECLARE
    n_existing  int;
    cust_ids    int[];
    prod_ids    int[];
    n_cust      int;
    n_prod      int;
BEGIN
    SELECT count(*) INTO n_existing FROM analytics.sales_orders WHERE order_date < DATE '2026-01-01';
    IF n_existing > 0 THEN
        RAISE NOTICE 'forecast history seed: % pre-2026 orders already present, skipping', n_existing;
        RETURN;
    END IF;

    PERFORM setseed(0.42);
    cust_ids := ARRAY(SELECT customer_id FROM analytics.customers ORDER BY customer_id);
    prod_ids := ARRAY(SELECT product_id FROM analytics.products ORDER BY product_id);
    n_cust := coalesce(array_length(cust_ids, 1), 0);
    n_prod := coalesce(array_length(prod_ids, 1), 0);
    IF n_cust = 0 OR n_prod = 0 OR NOT EXISTS (SELECT 1 FROM analytics.branches) THEN
        RAISE EXCEPTION 'forecast history seed needs customers, products and branches (apply 01 + 08 seeds first)';
    END IF;

    CREATE TEMP TABLE tmp_fc_plan ON COMMIT DROP AS
    SELECT
        m::date AS month_start,
        b.branch_id,
        GREATEST(2, round(
            (CASE b.city WHEN 'İstanbul' THEN 14 WHEN 'Ankara' THEN 9 ELSE 6 END)
            * (1 + 0.018 * ((extract(year FROM m) - 2022) * 12 + extract(month FROM m) - 9))
            * (1 + 0.18 * sin(2 * pi() * (extract(month FROM m) - 1) / 12.0 - pi() / 2))
            * (0.90 + 0.20 * random())
        ))::int AS n_orders
    FROM generate_series(DATE '2022-09-01', DATE '2026-08-01', interval '1 month') AS m
    CROSS JOIN analytics.branches b;

    CREATE TEMP TABLE tmp_fc_orders ON COMMIT DROP AS
    SELECT
        cust_ids[1 + floor(random() * n_cust)::int]                          AS customer_id,
        p.branch_id,
        (p.month_start + (floor(random() * 27))::int)::date                   AS order_date,
        CASE WHEN r < 0.87 THEN 'completed'
             WHEN r < 0.93 THEN 'shipped'
             WHEN r < 0.97 THEN 'cancelled'
             ELSE 'returned' END                                              AS status,
        'TRY'                                                                 AS currency
    FROM tmp_fc_plan p
    CROSS JOIN LATERAL generate_series(1, p.n_orders) AS g(i)
    CROSS JOIN LATERAL (SELECT random() AS r) AS rr;

    WITH ins AS (
        INSERT INTO analytics.sales_orders (customer_id, branch_id, order_date, status, currency)
        SELECT customer_id, branch_id, order_date, status, currency FROM tmp_fc_orders
        RETURNING order_id
    )
    INSERT INTO analytics.sales_order_items (order_id, product_id, quantity, unit_price)
    SELECT
        i.order_id,
        pr.product_id,
        1 + floor(random() * 5)::int,
        pr.unit_price
    FROM ins i
    CROSS JOIN LATERAL generate_series(1, 1 + floor(random() * 3)::int) AS li(n)
    CROSS JOIN LATERAL (
        SELECT product_id, unit_price
        FROM analytics.products
        WHERE product_id = prod_ids[1 + floor(random() * n_prod)::int]
    ) AS pr;

    RAISE NOTICE 'forecast history seed: inserted % orders', (SELECT count(*) FROM tmp_fc_orders);
END $$;
