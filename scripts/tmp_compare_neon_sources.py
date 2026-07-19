#!/usr/bin/env python3
"""Compare live Neon erp/sigorta vs what Nanobase BI system surfaces."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import psycopg2
import psycopg2.extras

SECRETS = Path("/data/nanobaseai/bi/secrets")
API = "http://127.0.0.1:8790"
QG = "http://127.0.0.1:8792"
QDRANT = "http://127.0.0.1:6333"


def http_json(method: str, url: str, body=None, timeout: int = 60):
    data = None if body is None else json.dumps(body).encode()
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:500]}
    except Exception as e:
        return 0, {"error": str(e)}


def pg_tables(cfg: dict) -> dict:
    pw = ""
    if cfg.get("password_file"):
        pw = Path(cfg["password_file"]).read_text(encoding="utf-8").strip()
    elif cfg.get("password"):
        pw = str(cfg["password"])
    conn = psycopg2.connect(
        host=cfg["host"],
        port=int(cfg.get("port") or 5432),
        dbname=cfg.get("database") or "neondb",
        user=cfg["user"],
        password=pw,
        sslmode=cfg.get("sslmode") or "require",
        connect_timeout=15,
    )
    conn.set_session(readonly=True, autocommit=True)
    out: dict = {}
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
              AND table_type IN ('BASE TABLE', 'VIEW')
            ORDER BY 1, 2
            """
        )
        rels = list(cur.fetchall())
        for rel in rels:
            sch, name = rel["table_schema"], rel["table_name"]
            fq = f"{sch}.{name}" if sch != "public" else name
            cur.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
                ORDER BY ordinal_position
                """,
                (sch, name),
            )
            cols = [c["column_name"] for c in cur.fetchall()]
            try:
                cur.execute(f'SELECT COUNT(*) AS n FROM "{sch}"."{name}"')
                n = cur.fetchone()["n"]
            except Exception as e:
                n = f"ERR:{type(e).__name__}:{e}"
            out[fq] = {
                "schema": sch,
                "name": name,
                "type": rel["table_type"],
                "cols": cols,
                "col_count": len(cols),
                "n": n,
            }
    conn.close()
    return out


def qdrant_info(name: str) -> dict:
    code, d = http_json("GET", f"{QDRANT}/collections/{name}")
    if code != 200:
        return {"http": code, "error": d}
    r = d.get("result") or {}
    return {"points": r.get("points_count"), "status": r.get("status")}


def qdrant_scroll_sample(name: str, limit: int = 10) -> list:
    code, d = http_json(
        "POST",
        f"{QDRANT}/collections/{name}/points/scroll",
        {"limit": limit, "with_payload": True, "with_vector": False},
    )
    pts = ((d.get("result") or {}).get("points") or [])
    sample = []
    for p in pts:
        pl = p.get("payload") or {}
        sample.append(
            {
                "table": pl.get("table") or pl.get("table_name") or pl.get("name"),
                "kind": pl.get("kind") or pl.get("doc_type") or pl.get("type"),
                "schema": pl.get("schema"),
                "payload_keys": sorted(pl.keys())[:16],
            }
        )
    return sample


def qdrant_unique_tables(name: str, max_points: int = 2000) -> set[str]:
    tables: set[str] = set()
    offset = None
    fetched = 0
    while fetched < max_points:
        body = {
            "limit": 100,
            "with_payload": True,
            "with_vector": False,
            "offset": offset,
        }
        code, d = http_json("POST", f"{QDRANT}/collections/{name}/points/scroll", body)
        result = d.get("result") or {}
        pts = result.get("points") or []
        if not pts:
            break
        for p in pts:
            pl = p.get("payload") or {}
            t = pl.get("table") or pl.get("table_name") or pl.get("name")
            if t:
                tables.add(str(t))
        fetched += len(pts)
        offset = result.get("next_page_offset")
        if offset is None:
            break
    return tables


def catalog_names(path: str) -> set[str]:
    p = Path(path)
    if not p.is_file():
        return set()
    cat = json.loads(p.read_text(encoding="utf-8"))
    names: set[str] = set()
    tables = cat.get("tables") or cat.get("relations") or cat.get("entities") or []
    if isinstance(tables, dict):
        names |= set(tables.keys())
    else:
        for t in tables:
            if isinstance(t, str):
                names.add(t)
            elif isinstance(t, dict):
                n = t.get("name") or t.get("table") or t.get("id")
                if n:
                    names.add(str(n))
    return {n for n in names if n}


def main() -> None:
    neon = json.loads((SECRETS / "neon-ro.datasources.json").read_text(encoding="utf-8"))
    report: dict = {}

    for sid in ("erp", "sigorta"):
        cfg = neon["sources"][sid]
        allow = set(cfg.get("allowed_tables") or [])
        allow_simple = {t for t in allow if "." not in t}
        live = pg_tables(cfg)
        live_names = set(live.keys())
        live_public = {k for k in live_names if "." not in k}
        live_all_simple = {k.split(".")[-1] for k in live_names}

        http_json("POST", f"{API}/api/v1/bi/sources/{sid}/activate")
        _, sys_schema = http_json("GET", f"{API}/api/v1/bi/schema")
        sys_tables = sys_schema.get("tables") or []
        sys_names = {(t.get("full_name") or t.get("name")) for t in sys_tables}
        sys_simple = {n.split(".")[-1] for n in sys_names if n}
        sys_source = sys_schema.get("source_id")

        # Prove query-param ignore while this source is active
        other = "sigorta" if sid == "erp" else "erp"
        _, asked_other = http_json("GET", f"{API}/api/v1/bi/schema?datasource_id={other}")
        asked_other_source = asked_other.get("source_id")

        tcode, tbody = http_json("POST", f"{API}/api/v1/bi/sources/{sid}/test")
        _, qh = http_json("GET", f"{QG}/health")
        qg_has = sid in (qh.get("datasources") or [])

        probe_table = None
        for cand in sorted(live_public):
            if isinstance(live[cand]["n"], int) and live[cand]["n"] > 0:
                probe_table = cand
                break
        if not probe_table and live_public:
            probe_table = sorted(live_public)[0]
        qg_probe = None
        if probe_table:
            qcode, qbody = http_json(
                "POST",
                f"{QG}/api/v1/query/execute",
                {
                    "datasource_id": sid,
                    "sql": f"SELECT COUNT(*) AS n FROM {probe_table}",
                },
            )
            qg_probe = {
                "table": probe_table,
                "http": qcode,
                "ok": qbody.get("ok"),
                "rows": qbody.get("rows"),
                "error": qbody.get("error") or qbody.get("detail") or qbody.get("message"),
            }

        coll = f"bi_schema_{sid}"
        qd = qdrant_info(coll)
        qd_tables = qdrant_unique_tables(coll)
        qd_sample = qdrant_scroll_sample(coll, 8)

        cat_path = f"/data/nanobaseai/bi/frontend/configs/schemas/{sid}.catalog.json"
        cat = catalog_names(cat_path)

        nonempty = sorted(
            [(k, v["n"]) for k, v in live.items() if isinstance(v["n"], int) and v["n"] > 0],
            key=lambda x: -x[1],
        )[:20]
        empty = sorted([k for k, v in live.items() if v["n"] == 0])
        err_counts = sorted([k for k, v in live.items() if isinstance(v["n"], str)])

        # column sample mismatch: pick a nonempty table and compare sys columns
        col_mismatch = []
        sys_by_name = {(t.get("full_name") or t.get("name")): t for t in sys_tables}
        for fq in list(sorted(live_public))[:30]:
            live_cols = set(live[fq]["cols"])
            st = sys_by_name.get(fq)
            if not st:
                continue
            sys_cols = {c.get("name") for c in (st.get("columns") or [])}
            only_live = sorted(live_cols - sys_cols)
            only_sys = sorted(sys_cols - live_cols)
            if only_live or only_sys:
                col_mismatch.append(
                    {
                        "table": fq,
                        "only_in_live_db": only_live[:20],
                        "only_in_sys_api": only_sys[:20],
                        "live_col_count": len(live_cols),
                        "sys_col_count": len(sys_cols),
                    }
                )

        report[sid] = {
            "connection": {
                "user": cfg.get("user"),
                "host": (cfg.get("host") or "")[:56],
                "database": cfg.get("database"),
                "test_ok": bool(tbody.get("ok") or tbody.get("success")),
                "test_latency_ms": tbody.get("latencyMs"),
                "qg_registered": qg_has,
                "qg_probe": qg_probe,
            },
            "counts": {
                "allowlist": len(allow_simple),
                "live_db_all": len(live),
                "live_db_public": len(live_public),
                "system_schema_api": len(sys_tables),
                "qdrant_points": qd.get("points"),
                "qdrant_unique_table_payloads": len(qd_tables),
                "catalog_file": len(cat) if cat else 0,
            },
            "system_schema_api": {
                "source_id_returned": sys_source,
                "asked_other_datasource_id": other,
                "got_source_id_for_other_query": asked_other_source,
                "query_param_honored": asked_other_source == other,
            },
            "schemas_in_live_db": sorted({v["schema"] for v in live.values()}),
            "diffs": {
                "in_live_db_not_allowlist": sorted(live_public - allow_simple),
                "in_allowlist_not_live_db": sorted(allow_simple - live_all_simple),
                "in_live_db_not_system_schema_api": sorted(live_public - sys_simple),
                "in_system_schema_api_not_live_db": sorted(sys_simple - live_all_simple),
                "in_live_db_not_qdrant": sorted(live_public - qd_tables)[:50],
                "in_qdrant_not_live_db": sorted(qd_tables - live_all_simple)[:50],
                "in_live_db_not_catalog": sorted(live_public - cat)[:50] if cat else ["<catalog missing or empty>"],
                "in_catalog_not_live_db": sorted(cat - live_all_simple)[:50] if cat else [],
            },
            "data": {
                "top_nonempty": nonempty,
                "empty_count": len(empty),
                "empty_sample": empty[:25],
                "count_errors": err_counts[:15],
            },
            "column_mismatches_sample": col_mismatch[:10],
            "qdrant": {"collection": coll, **qd, "payload_sample": qd_sample},
        }

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
