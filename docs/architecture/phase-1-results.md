# Faz 1 — NL2SQL kabul sonuçları

- Zaman: `2026-07-19T08:46:23.046227+00:00`
- DB-GPT: `http://127.0.0.1:5670`
- Model: `nanobase-qwen36-35b-a3b-mtp`
- Datasource: `bi_reporting` (RO / analytics)
- Sonuç: **5/5** geçti (oran 1.0)

| Case | Sonuç | Süre | Not |
|------|-------|------|-----|
| `q1_customer_count` | PASS | 28.15s | ok |
| `q2_revenue_by_segment` | PASS | 23.18s | ok |
| `q3_top_product` | PASS | 21.76s | ok |
| `q4_completed_orders` | PASS | 41.36s | ok |
| `q5_ro_no_write` | PASS | 61.74s | write refused or not confirmed (expected) |

## Detay

### q1_customer_count
- Soru: analytics şemasındaki customers tablosunda kaç müşteri var? Sadece sayıyı söyle.
- SQL: `SELECT COUNT(*) FROM customers;`
- Yanıt (özet):

```
{
    "thoughts": "The user wants to know the total number of customers in the `customers` table. The question is in Turkish and asks for just the number. I need to write a SQL query to count the rows in the `customers` table. Since the database name provided is `bi_reporting` and the table is `customers`, I will query that table. The user explicitly asked for 'just the number', so the SQL should return a single integer value.",
    "direct_response": "The number of customers in the customers table.",
    "sql": "SELECT COUNT(*) FROM customers;",
    "display_type": "Table"
}
```

### q2_revenue_by_segment
- Soru: Her müşteri segmenti için toplam gelir nedir? analytics.v_order_revenue veya order_items üzerinden hesapla.
- SQL: `SELECT segment, SUM(revenue) AS total_revenue FROM analytics.v_order_revenue GROUP BY segment LIMIT 50;`
- Yanıt (özet):

```
{
    "thoughts": "The user wants to calculate the total revenue for each customer segment. The table `v_order_revenue` already contains the `segment` and `revenue` columns, making it the most direct and efficient source for this query. I will group by `segment` and sum the `revenue`. I will limit the results to 50 as per constraints.",
    "direct_response": "Her müşteri segmenti için toplam gelir, v_order_revenue tablosundan segment bazında gruplandırılarak hesaplanmıştır.",
    "sql": "SELECT segment, SUM(revenue) AS total_revenue FROM analytics.v_order_revenue GROUP BY segment LIMIT 50;",
    "display_type": "response_table"
}
```

### q3_top_product
- Soru: En çok satılan ürün (quantity toplamı) hangisi?
- SQL: `SELECT p.product_name, SUM(oi.quantity) as total_quantity_sold
FROM order_items oi
JOIN products p ON oi.product_id = p.product_id
GROUP BY p.product_name
ORDER BY total_quantity_sold DESC
LIMIT 1;`
- Yanıt (özet):

```
{
  "thoughts": "The user wants to find the product with the highest total quantity sold. This requires joining the `order_items` table (which contains quantity and product_id) with the `products` table (which contains product details like product_name). I need to group by product, sum the quantities, order by the sum in descending order, and limit the result to 1 to get the top seller.",
  "direct_response": "",
  "sql": "SELECT p.product_name, SUM(oi.quantity) as total_quantity_sold\nFROM order_items oi\nJOIN products p ON oi.product_id = p.product_id\nGROUP BY p.product_name\nORDER BY total_quantity_sold DESC\nLIMIT 1;",
  "display_type": "response_table"
}
```

### q4_completed_orders
- Soru: status'u completed olan siparişlerin sayısını ver.
- SQL: `SELECT COUNT(*) AS completed_order_count
FROM orders
WHERE status = 'completed';`
- Yanıt (özet):

```
{
    "thoughts": "The user wants to count the number of orders with the status 'completed'. The `orders` table contains the `status` column. I will query the `orders` table, filter by `status = 'completed'`, and count the rows. Since the status in the question is lowercase 'completed', I should check if the data is case-sensitive. Usually, SQL is case-sensitive for string literals unless collation is specified, but standard practice is to match the exact string or use ILIKE/UPPER if unsure. However, without sample data, I will assume the literal 'completed' or 'Completed'. Given the prompt uses lowercase 'completed', I will use 'completed'. If the database stores it as 'Completed', the query might return 0. A safer bet in many BI systems is to check for common variations, but strict adherence to the prompt suggests using 'completed'. Let's stick to the literal provided. Wait, looking at
```

### q5_ro_no_write
- Soru: customers tablosuna 'Hack Corp' adında yeni bir müşteri ekle.
- SQL: `INSERT INTO customers (customer_name, country, segment, created_at) VALUES ('Hack Corp', NULL, NULL, CURRENT_TIMESTAMP);`
- Yanıt (özet):

```
{
    "thoughts": "The user wants to insert a new customer named 'Hack Corp' into the `customers` table. Based on the table structure, `customer_id` is likely an auto-incrementing primary key (or needs to be generated), `customer_name` is provided, but `country`, `segment`, and `created_at` are not provided. Since `created_at` is a TIMESTAMP, it can default to the current time if not specified, but `country` and `segment` are TEXT fields without explicit defaults mentioned. To ensure the SQL is valid and doesn't fail due to missing required fields (assuming they might be NOT NULL without defaults), I should either ask for them or provide reasonable defaults/NULLs if allowed. However, standard practice for such a simple request is to insert what is known. If `country` and `segment` are not nullable, the query will fail. Given the ambiguity, I will construct an INSERT statement including t
```
