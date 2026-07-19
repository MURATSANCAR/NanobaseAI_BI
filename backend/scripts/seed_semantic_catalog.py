#!/usr/bin/env python3
"""Seed semantic catalog + verified SQL for bi_reporting (Faz 7)."""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

SECRETS = Path(os.environ.get("SECRETS_ROOT", "/data/nanobaseai/bi/secrets"))
META_PW = (SECRETS / "bi-meta-db.password").read_text(encoding="utf-8").strip()
TENANT = "default"
NOW = datetime.now(timezone.utc)


def norm_q(q: str) -> str:
    q = q.lower().strip()
    q = re.sub(r"\s+", " ", q)
    q = re.sub(r"[^\w\sçğıöşüâîû]", "", q, flags=re.I)
    return q


def connect():
    return psycopg2.connect(
        host="127.0.0.1",
        port=5434,
        dbname="bi_meta",
        user="bi_meta",
        password=META_PW,
    )


def main() -> None:
    sql_path = Path(__file__).resolve().parents[2] / "infra" / "sql" / "07-semantic-verified.sql"
    # on server synced path may differ
    for candidate in (
        sql_path,
        Path("/data/nanobaseai/bi/frontend/infra/sql/07-semantic-verified.sql"),
        Path("/data/nanobaseai/bi/infra/sql/07-semantic-verified.sql"),
    ):
        if candidate.is_file():
            sql_path = candidate
            break

    conn = connect()
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute(sql_path.read_text(encoding="utf-8"))

    glossary = [
        ("müşteri", "customers", "customer_name", "Müşteri adı"),
        ("segment", "customers", "segment", "Müşteri segmenti: enterprise|smb|consumer"),
        ("ciro", "v_order_revenue", "revenue", "Sipariş geliri (quantity*unit_price)"),
        ("sipariş", "orders", "order_id", "Sipariş kaydı"),
        ("ürün", "products", "product_name", "Ürün adı"),
        ("sku", "products", "sku", "Stok kodu"),
        ("adet", "order_items", "quantity", "Satış adedi"),
        ("durum", "orders", "status", "pending|shipped|cancelled|completed"),
    ]
    for term, table, col, definition in glossary:
        gid = f"gl-{term}"
        payload = json.dumps({"datasource_id": "bi_reporting"}, ensure_ascii=False)
        cur.execute("SELECT pk FROM bi_glossary_entries WHERE id=%s", (gid,))
        if cur.fetchone():
            cur.execute(
                """
                UPDATE bi_glossary_entries
                SET term=%s, table_name=%s, column_name=%s, definition=%s, status='approved',
                    payload_json=%s, updated_at=%s
                WHERE id=%s
                """,
                (term, table, col, definition, payload, NOW, gid),
            )
        else:
            cur.execute(
                """
                INSERT INTO bi_glossary_entries
                  (id, tenant_id, term, table_name, column_name, definition, status, payload_json, updated_at)
                VALUES (%s,%s,%s,%s,%s,%s,'approved',%s,%s)
                """,
                (gid, TENANT, term, table, col, definition, payload, NOW),
            )

    # metrics
    metrics = [
        (
            "customer_count",
            "Müşteri sayısı",
            "COUNT(*)",
            "customers",
            "SELECT COUNT(*) AS n FROM customers",
        ),
        (
            "order_revenue",
            "Sipariş cirosu",
            "SUM(revenue)",
            "v_order_revenue",
            "SELECT SUM(revenue) AS revenue FROM v_order_revenue",
        ),
        (
            "completed_orders",
            "Tamamlanan sipariş",
            "COUNT(*)",
            "orders",
            "SELECT COUNT(*) AS n FROM orders WHERE status = 'completed'",
        ),
    ]
    for mid, label, expr, table, golden in metrics:
        cur.execute(
            """
            INSERT INTO bi_metrics (
              metric_id, tenant_id, label, expression, source_table, grain, time_dimension,
              mandatory_filters_json, allowed_dimensions_json, owner, status, payload_json,
              updated_at, version, golden_sql
            ) VALUES (
              %s,%s,%s,%s,%s,'row','order_date','[]','[]','nanobase','certified',%s,%s,1,%s
            )
            ON CONFLICT (tenant_id, metric_id) DO UPDATE SET
              label=EXCLUDED.label,
              expression=EXCLUDED.expression,
              source_table=EXCLUDED.source_table,
              status='certified',
              golden_sql=EXCLUDED.golden_sql,
              payload_json=EXCLUDED.payload_json,
              updated_at=EXCLUDED.updated_at
            """,
            (
                mid,
                TENANT,
                label,
                expr,
                table,
                json.dumps({"datasource_id": "bi_reporting"}, ensure_ascii=False),
                NOW,
                golden,
            ),
        )

    joins = [
        ("orders_customers", "orders", "customers", "customer_id", "customer_id"),
        ("order_items_orders", "order_items", "orders", "order_id", "order_id"),
        ("order_items_products", "order_items", "products", "product_id", "product_id"),
    ]
    for jid, lt, rt, lk, rk in joins:
        cur.execute(
            """
            INSERT INTO bi_joins (
              join_id, tenant_id, left_table, right_table, left_key, right_key,
              cardinality, bridge_flag, causes_fanout, payload_json, updated_at
            ) VALUES (%s,%s,%s,%s,%s,%s,'many_to_one',false,false,%s,%s)
            ON CONFLICT (tenant_id, join_id) DO UPDATE SET
              left_table=EXCLUDED.left_table,
              right_table=EXCLUDED.right_table,
              left_key=EXCLUDED.left_key,
              right_key=EXCLUDED.right_key,
              updated_at=EXCLUDED.updated_at
            """,
            (
                jid,
                TENANT,
                lt,
                rt,
                lk,
                rk,
                json.dumps({"datasource_id": "bi_reporting"}, ensure_ascii=False),
                NOW,
            ),
        )

    verified = [
        ("Kaç müşteri var?", "SELECT COUNT(*) AS n FROM customers"),
        ("Completed sipariş sayısı", "SELECT COUNT(*) AS n FROM orders WHERE status = 'completed'"),
        (
            "Segment bazında toplam gelir",
            "SELECT segment, SUM(revenue) AS revenue FROM v_order_revenue GROUP BY segment",
        ),
    ]
    for q, sql in verified:
        vid = f"vsql-{uuid.uuid5(uuid.NAMESPACE_URL, norm_q(q) + sql).hex[:12]}"
        cur.execute(
            """
            INSERT INTO bi_verified_sql
              (id, tenant_id, datasource_id, question_norm, question_display, sql_text, status, created_by, created_at, updated_at)
            VALUES (%s,%s,'bi_reporting',%s,%s,%s,'verified','seed',%s,%s)
            ON CONFLICT (id) DO UPDATE SET
              sql_text=EXCLUDED.sql_text,
              question_display=EXCLUDED.question_display,
              status='verified',
              updated_at=EXCLUDED.updated_at
            """,
            (vid, TENANT, norm_q(q), q, sql, NOW, NOW),
        )

    cur.execute("SELECT count(*) FROM bi_glossary_entries")
    g = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM bi_metrics WHERE tenant_id=%s", (TENANT,))
    m = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM bi_verified_sql WHERE datasource_id='bi_reporting'")
    v = cur.fetchone()[0]
    cur.close()
    conn.close()
    print(f"seeded glossary={g} metrics={m} verified_sql={v}")


if __name__ == "__main__":
    main()
