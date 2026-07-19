-- Additive rich reporting schema for NL2SQL quality (idempotent).
-- Apply on live bi_reporting (not only first docker init).

CREATE SCHEMA IF NOT EXISTS analytics;
SET search_path TO analytics, public;

CREATE TABLE IF NOT EXISTS analytics.companies (
    company_id   SERIAL PRIMARY KEY,
    company_name TEXT NOT NULL,
    country      TEXT NOT NULL DEFAULT 'TR'
);

CREATE TABLE IF NOT EXISTS analytics.branches (
    branch_id   SERIAL PRIMARY KEY,
    company_id  INT NOT NULL REFERENCES analytics.companies (company_id),
    city        TEXT NOT NULL,
    code        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analytics.customer_addresses (
    address_id  SERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES analytics.customers (customer_id),
    city        TEXT NOT NULL,
    line1       TEXT NOT NULL,
    is_primary  BOOLEAN NOT NULL DEFAULT false
);

CREATE TABLE IF NOT EXISTS analytics.sales_orders (
    order_id    SERIAL PRIMARY KEY,
    customer_id INT NOT NULL REFERENCES analytics.customers (customer_id),
    branch_id   INT REFERENCES analytics.branches (branch_id),
    order_date  DATE NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('pending', 'shipped', 'cancelled', 'completed', 'returned')),
    currency    TEXT NOT NULL DEFAULT 'TRY'
);

CREATE TABLE IF NOT EXISTS analytics.sales_order_items (
    item_id     SERIAL PRIMARY KEY,
    order_id    INT NOT NULL REFERENCES analytics.sales_orders (order_id),
    product_id  INT NOT NULL REFERENCES analytics.products (product_id),
    quantity    INT NOT NULL CHECK (quantity > 0),
    unit_price  NUMERIC(12, 2) NOT NULL CHECK (unit_price >= 0)
);

CREATE TABLE IF NOT EXISTS analytics.invoices (
    invoice_id       SERIAL PRIMARY KEY,
    order_id         INT NOT NULL REFERENCES analytics.sales_orders (order_id),
    invoice_date     DATE NOT NULL,
    due_date         DATE NOT NULL,
    currency         TEXT NOT NULL DEFAULT 'TRY',
    gross_amount     NUMERIC(14, 2) NOT NULL,
    remaining_amount NUMERIC(14, 2) NOT NULL,
    status           TEXT NOT NULL CHECK (status IN ('open', 'partial', 'paid', 'overdue', 'cancelled'))
);

CREATE TABLE IF NOT EXISTS analytics.payments (
    payment_id   SERIAL PRIMARY KEY,
    invoice_id   INT NOT NULL REFERENCES analytics.invoices (invoice_id),
    payment_date DATE NOT NULL,
    amount       NUMERIC(14, 2) NOT NULL CHECK (amount > 0),
    currency     TEXT NOT NULL DEFAULT 'TRY'
);

CREATE TABLE IF NOT EXISTS analytics.currency_rates (
    rate_id       SERIAL PRIMARY KEY,
    rate_date     DATE NOT NULL,
    from_currency TEXT NOT NULL,
    to_currency   TEXT NOT NULL,
    rate          NUMERIC(18, 8) NOT NULL CHECK (rate > 0),
    UNIQUE (rate_date, from_currency, to_currency)
);

CREATE TABLE IF NOT EXISTS analytics.returns (
    return_id   SERIAL PRIMARY KEY,
    order_id    INT NOT NULL REFERENCES analytics.sales_orders (order_id),
    product_id  INT NOT NULL REFERENCES analytics.products (product_id),
    quantity    INT NOT NULL CHECK (quantity > 0),
    return_date DATE NOT NULL
);

-- Seed only if empty
INSERT INTO analytics.companies (company_name, country)
SELECT * FROM (VALUES
    ('Nanobase Demo A.Ş.', 'TR'),
    ('Nanobase EU GmbH', 'DE')
) v(company_name, country)
WHERE NOT EXISTS (SELECT 1 FROM analytics.companies LIMIT 1);

INSERT INTO analytics.branches (company_id, city, code)
SELECT c.company_id, v.city, v.code
FROM analytics.companies c
JOIN (VALUES
    ('Nanobase Demo A.Ş.', 'İstanbul', 'IST'),
    ('Nanobase Demo A.Ş.', 'Ankara', 'ANK'),
    ('Nanobase EU GmbH', 'Berlin', 'BER')
) AS v(company_name, city, code) ON v.company_name = c.company_name
WHERE NOT EXISTS (SELECT 1 FROM analytics.branches LIMIT 1);

INSERT INTO analytics.customer_addresses (customer_id, city, line1, is_primary)
SELECT c.customer_id, v.city, v.line1, v.is_primary
FROM analytics.customers c
JOIN (VALUES
    ('Acme Holding', 'İstanbul', 'Maslak Cad. 1', true),
    ('Acme Holding', 'Ankara', 'Çankaya Sk. 4', false),
    ('Beta Lojistik', 'Ankara', 'OSB 12', true),
    ('Gamma Retail', 'Berlin', 'Unter den Linden 5', true),
    ('Delta Enerji', 'İstanbul', 'Kadıköy 9', true),
    ('Epsilon Soft', 'Amsterdam', 'Damrak 2', true)
) AS v(customer_name, city, line1, is_primary)
  ON v.customer_name = c.customer_name
WHERE NOT EXISTS (SELECT 1 FROM analytics.customer_addresses LIMIT 1);

INSERT INTO analytics.sales_orders (customer_id, branch_id, order_date, status, currency)
SELECT c.customer_id, b.branch_id, v.order_date::date, v.status, v.currency
FROM (VALUES
    ('Acme Holding', 'İstanbul', '2026-01-10', 'completed', 'TRY'),
    ('Acme Holding', 'Ankara', '2026-02-05', 'completed', 'TRY'),
    ('Beta Lojistik', 'Ankara', '2026-02-20', 'shipped', 'TRY'),
    ('Gamma Retail', 'Berlin', '2026-03-01', 'completed', 'EUR'),
    ('Delta Enerji', 'İstanbul', '2026-03-15', 'cancelled', 'TRY'),
    ('Epsilon Soft', 'Berlin', '2026-04-01', 'completed', 'EUR'),
    ('Beta Lojistik', 'Ankara', '2026-04-18', 'returned', 'TRY'),
    ('Acme Holding', 'İstanbul', '2026-05-01', 'completed', 'USD'),
    ('Delta Enerji', 'Ankara', '2026-05-20', 'pending', 'TRY'),
    ('Gamma Retail', 'Berlin', '2026-06-02', 'completed', 'EUR')
) AS v(customer_name, city, order_date, status, currency)
JOIN analytics.customers c ON c.customer_name = v.customer_name
JOIN analytics.branches b ON b.city = v.city
WHERE NOT EXISTS (SELECT 1 FROM analytics.sales_orders LIMIT 1);

INSERT INTO analytics.sales_order_items (order_id, product_id, quantity, unit_price)
SELECT o.order_id, p.product_id, v.qty, v.price
FROM (VALUES
    (1, 'SKU-100', 2, 12000.00),
    (1, 'SKU-200', 1, 3500.00),
    (2, 'SKU-400', 3, 2100.00),
    (3, 'SKU-300', 10, 890.50),
    (4, 'SKU-100', 1, 12000.00),
    (5, 'SKU-200', 2, 3500.00),
    (6, 'SKU-400', 2, 2100.00),
    (7, 'SKU-300', 4, 890.50),
    (8, 'SKU-100', 1, 12000.00),
    (9, 'SKU-500', 5, 1500.00),
    (10, 'SKU-300', 6, 890.50)
) AS v(ord_n, sku, qty, price)
JOIN analytics.sales_orders o ON o.order_id = v.ord_n
JOIN analytics.products p ON p.sku = v.sku
WHERE NOT EXISTS (SELECT 1 FROM analytics.sales_order_items LIMIT 1);

INSERT INTO analytics.invoices (order_id, invoice_date, due_date, currency, gross_amount, remaining_amount, status)
SELECT o.order_id, v.inv_date::date, v.due_date::date, o.currency, v.gross, v.remaining, v.status
FROM (VALUES
    (1, '2026-01-12', '2026-02-12', 27500.00, 0.00, 'paid'),
    (2, '2026-02-06', '2026-03-06', 6300.00, 0.00, 'paid'),
    (3, '2026-02-21', '2026-03-21', 11905.00, 5000.00, 'partial'),
    (4, '2026-03-02', '2026-04-01', 12000.00, 12000.00, 'overdue'),
    (6, '2026-04-02', '2026-05-02', 4200.00, 0.00, 'paid'),
    (8, '2026-05-02', '2026-06-01', 12000.00, 4000.00, 'partial'),
    (9, '2026-05-21', '2026-06-20', 7500.00, 7500.00, 'open'),
    (10, '2026-06-03', '2026-07-03', 5343.00, 0.00, 'paid')
) AS v(ord_n, inv_date, due_date, gross, remaining, status)
JOIN analytics.sales_orders o ON o.order_id = v.ord_n
WHERE NOT EXISTS (SELECT 1 FROM analytics.invoices LIMIT 1);

INSERT INTO analytics.payments (invoice_id, payment_date, amount, currency)
SELECT i.invoice_id, v.pay_date::date, v.amount, i.currency
FROM (VALUES
    (1, '2026-01-20', 27500.00),
    (2, '2026-02-28', 6300.00),
    (3, '2026-03-10', 6905.00),
    (6, '2026-04-15', 4200.00),
    (8, '2026-05-15', 8000.00),
    (10, '2026-06-10', 5343.00)
) AS v(inv_n, pay_date, amount)
JOIN analytics.invoices i ON i.invoice_id = v.inv_n
WHERE NOT EXISTS (SELECT 1 FROM analytics.payments LIMIT 1);

INSERT INTO analytics.currency_rates (rate_date, from_currency, to_currency, rate)
SELECT v.rate_date::date, v.fc, v.tc, v.rate
FROM (VALUES
    ('2026-01-10', 'USD', 'TRY', 34.50000000),
    ('2026-01-10', 'EUR', 'TRY', 37.20000000),
    ('2026-03-01', 'EUR', 'TRY', 37.80000000),
    ('2026-05-01', 'USD', 'TRY', 35.10000000),
    ('2026-06-02', 'EUR', 'TRY', 38.05000000)
) AS v(rate_date, fc, tc, rate)
WHERE NOT EXISTS (SELECT 1 FROM analytics.currency_rates LIMIT 1);

INSERT INTO analytics.returns (order_id, product_id, quantity, return_date)
SELECT 7, p.product_id, 2, '2026-04-25'::date
FROM analytics.products p
WHERE p.sku = 'SKU-300'
  AND NOT EXISTS (SELECT 1 FROM analytics.returns LIMIT 1);

CREATE OR REPLACE VIEW analytics.v_invoice_open AS
SELECT
    i.invoice_id,
    i.invoice_date,
    i.due_date,
    i.currency,
    i.gross_amount,
    i.remaining_amount,
    i.status,
    c.customer_name,
    ca.city AS customer_city,
    o.order_date,
    o.status AS order_status
FROM analytics.invoices i
JOIN analytics.sales_orders o ON o.order_id = i.order_id
JOIN analytics.customers c ON c.customer_id = o.customer_id
LEFT JOIN analytics.customer_addresses ca
  ON ca.customer_id = c.customer_id AND ca.is_primary = true;

-- Public aliases for discovery + Gateway
CREATE OR REPLACE VIEW public.companies AS SELECT * FROM analytics.companies;
CREATE OR REPLACE VIEW public.branches AS SELECT * FROM analytics.branches;
CREATE OR REPLACE VIEW public.customer_addresses AS SELECT * FROM analytics.customer_addresses;
CREATE OR REPLACE VIEW public.sales_orders AS SELECT * FROM analytics.sales_orders;
CREATE OR REPLACE VIEW public.sales_order_items AS SELECT * FROM analytics.sales_order_items;
CREATE OR REPLACE VIEW public.invoices AS SELECT * FROM analytics.invoices;
CREATE OR REPLACE VIEW public.payments AS SELECT * FROM analytics.payments;
CREATE OR REPLACE VIEW public.currency_rates AS SELECT * FROM analytics.currency_rates;
CREATE OR REPLACE VIEW public.returns AS SELECT * FROM analytics.returns;
CREATE OR REPLACE VIEW public.v_invoice_open AS SELECT * FROM analytics.v_invoice_open;

-- RO grants (role may already exist)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bi_reporting_ro') THEN
    GRANT USAGE ON SCHEMA analytics TO bi_reporting_ro;
    GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO bi_reporting_ro;
    GRANT SELECT ON ALL TABLES IN SCHEMA public TO bi_reporting_ro;
    ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO bi_reporting_ro;
  END IF;
END $$;
