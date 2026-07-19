-- BI reporting seed (idempotent-ish; runs only on first Postgres init)
-- Schema: sales analytics for NL2SQL acceptance tests

CREATE SCHEMA IF NOT EXISTS analytics;
SET search_path TO analytics, public;

CREATE TABLE IF NOT EXISTS customers (
    customer_id   SERIAL PRIMARY KEY,
    customer_name TEXT NOT NULL,
    country       TEXT NOT NULL,
    segment       TEXT NOT NULL CHECK (segment IN ('enterprise', 'smb', 'consumer')),
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS products (
    product_id   SERIAL PRIMARY KEY,
    sku          TEXT NOT NULL UNIQUE,
    product_name TEXT NOT NULL,
    category     TEXT NOT NULL,
    unit_price   NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0)
);

CREATE TABLE IF NOT EXISTS orders (
    order_id     SERIAL PRIMARY KEY,
    customer_id  INT NOT NULL REFERENCES customers (customer_id),
    order_date   DATE NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('pending', 'shipped', 'cancelled', 'completed')),
    currency     TEXT NOT NULL DEFAULT 'TRY'
);

CREATE TABLE IF NOT EXISTS order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_id      INT NOT NULL REFERENCES orders (order_id),
    product_id    INT NOT NULL REFERENCES products (product_id),
    quantity      INT NOT NULL CHECK (quantity > 0),
    unit_price    NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0)
);

CREATE INDEX IF NOT EXISTS idx_orders_customer ON orders (customer_id);
CREATE INDEX IF NOT EXISTS idx_orders_date ON orders (order_date);
CREATE INDEX IF NOT EXISTS idx_order_items_order ON order_items (order_id);
CREATE INDEX IF NOT EXISTS idx_products_category ON products (category);

INSERT INTO customers (customer_name, country, segment) VALUES
    ('Acme Holding', 'TR', 'enterprise'),
    ('Beta Lojistik', 'TR', 'smb'),
    ('Gamma Retail', 'DE', 'consumer'),
    ('Delta Enerji', 'TR', 'enterprise'),
    ('Epsilon Soft', 'NL', 'smb');

INSERT INTO products (sku, product_name, category, unit_price) VALUES
    ('SKU-100', 'Analytics License', 'software', 12000.00),
    ('SKU-200', 'Support Pack', 'services', 3500.00),
    ('SKU-300', 'Sensor Kit', 'hardware', 890.50),
    ('SKU-400', 'Dashboard Addon', 'software', 2100.00),
    ('SKU-500', 'Training Day', 'services', 1500.00)
ON CONFLICT (sku) DO NOTHING;

INSERT INTO orders (customer_id, order_date, status, currency) VALUES
    (1, '2025-11-03', 'completed', 'TRY'),
    (1, '2026-01-15', 'completed', 'TRY'),
    (2, '2026-02-01', 'shipped', 'TRY'),
    (3, '2026-02-20', 'completed', 'EUR'),
    (4, '2026-03-05', 'pending', 'TRY'),
    (5, '2026-03-12', 'completed', 'EUR'),
    (2, '2026-04-01', 'cancelled', 'TRY'),
    (1, '2026-05-10', 'completed', 'TRY'),
    (4, '2026-06-01', 'shipped', 'TRY'),
    (3, '2026-06-18', 'completed', 'EUR');

INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
    (1, 1, 2, 12000.00),
    (1, 2, 1, 3500.00),
    (2, 4, 3, 2100.00),
    (3, 3, 10, 890.50),
    (3, 5, 2, 1500.00),
    (4, 1, 1, 12000.00),
    (5, 2, 4, 3500.00),
    (6, 4, 2, 2100.00),
    (7, 3, 5, 890.50),
    (8, 1, 1, 12000.00),
    (8, 5, 3, 1500.00),
    (9, 2, 2, 3500.00),
    (10, 3, 8, 890.50);

CREATE OR REPLACE VIEW analytics.v_order_revenue AS
SELECT
    o.order_id,
    o.order_date,
    o.status,
    o.currency,
    c.customer_name,
    c.country,
    c.segment,
    SUM(oi.quantity * oi.unit_price) AS revenue
FROM orders o
JOIN customers c ON c.customer_id = o.customer_id
JOIN order_items oi ON oi.order_id = o.order_id
GROUP BY o.order_id, o.order_date, o.status, o.currency,
         c.customer_name, c.country, c.segment;

-- Public aliases so DB-GPT schema discovery (public-only) works
CREATE OR REPLACE VIEW public.customers AS SELECT * FROM analytics.customers;
CREATE OR REPLACE VIEW public.products AS SELECT * FROM analytics.products;
CREATE OR REPLACE VIEW public.orders AS SELECT * FROM analytics.orders;
CREATE OR REPLACE VIEW public.order_items AS SELECT * FROM analytics.order_items;
CREATE OR REPLACE VIEW public.v_order_revenue AS SELECT * FROM analytics.v_order_revenue;
