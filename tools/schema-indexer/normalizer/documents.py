from __future__ import annotations

import json
from typing import Any

from fingerprint import point_id_from_key, sha256_fingerprint
from models import RelationshipMeta, SchemaDocument, TableMeta


def _rel_info(table: TableMeta) -> str:
    parts = []
    for fk in table.foreign_keys:
        parts.append(
            f"{fk.column}->{fk.target_schema}.{fk.target_table}.{fk.target_column}"
        )
    return ",".join(sorted(parts))


def normalize_documents(
    datasource_id: str,
    tables: list[TableMeta],
    relationships: list[RelationshipMeta],
) -> list[SchemaDocument]:
    """Build TABLE / COLUMN / RELATIONSHIP documents with fingerprints."""
    docs: list[SchemaDocument] = []

    for t in tables:
        fq = f"{t.schema_name}.{t.table_name}"
        table_payload: dict[str, Any] = {
            "document_type": "TABLE",
            "datasource_id": datasource_id,
            "schema_name": t.schema_name,
            "table_name": t.table_name,
            "description": t.description,
            "primary_key": t.primary_key,
            "foreign_keys": [fk.as_doc() for fk in t.foreign_keys],
            "table_type": t.table_type,
            "row_count": t.row_count,
            "date_min": t.date_min,
            "date_max": t.date_max,
            "status_dist": t.status_dist,
            "kind": "view" if t.table_type == "VIEW" else "table",
            "schema": t.schema_name,
            "table": t.table_name,
            "column": None,
        }
        col_lines = [
            f"- {c.column_name} {c.type_display or c.data_type} nullable={c.nullable}"
            + (f" samples={c.samples}" if c.samples else "")
            for c in t.columns
        ]
        text = (
            f"{'View' if t.table_type == 'VIEW' else 'Table'} {fq}\n"
            f"Description: {t.description}\n"
            f"Datasource: {datasource_id}\n"
            f"Primary key: {t.primary_key}\n"
            f"Foreign keys: {_rel_info(t)}\n"
            f"Row count: {t.row_count}\n"
            f"Date range: {t.date_min} .. {t.date_max}\n"
            f"Status dist: {json.dumps(t.status_dist, ensure_ascii=False)}\n"
            f"Columns:\n" + "\n".join(col_lines)
        )
        fp = sha256_fingerprint(
            datasource_id,
            t.schema_name,
            t.table_name,
            "",
            "",
            "",
            t.description,
            _rel_info(t),
            t.primary_key,
            t.row_count,
            t.date_min,
            t.date_max,
            json.dumps(t.status_dist, sort_keys=True, ensure_ascii=False),
        )
        key = f"{datasource_id}:TABLE:{fq}"
        table_payload["fingerprint"] = fp
        table_payload["document_key"] = key
        table_payload["text"] = text
        docs.append(
            SchemaDocument(
                document_type="TABLE",
                datasource_id=datasource_id,
                document_key=key,
                fingerprint=fp,
                text=text,
                payload=table_payload,
            )
        )

        for c in t.columns:
            col_payload: dict[str, Any] = {
                "document_type": "COLUMN",
                "datasource_id": datasource_id,
                "schema_name": t.schema_name,
                "table_name": t.table_name,
                "column_name": c.column_name,
                "data_type": c.data_type,
                "type_display": c.type_display or c.data_type,
                "max_length": c.max_length,
                "precision": c.precision,
                "scale": c.scale,
                "nullable": c.nullable,
                "description": c.description,
                "is_pk": c.is_pk,
                "samples": c.samples,
                "kind": "column",
                "schema": t.schema_name,
                "table": t.table_name,
                "column": c.column_name,
            }
            rel_for_col = next(
                (
                    f"{fk.column}->{fk.target_table}.{fk.target_column}"
                    for fk in t.foreign_keys
                    if fk.column == c.column_name
                ),
                "",
            )
            type_label = c.type_display or c.data_type
            text_c = (
                f"Column {fq}.{c.column_name} type={type_label} "
                f"nullable={c.nullable} pk={c.is_pk} "
                f"max_length={c.max_length} precision={c.precision} scale={c.scale} "
                f"description={c.description or '-'} "
                f"relationship={rel_for_col or '-'} "
                f"samples={c.samples} datasource={datasource_id}"
            )
            fp_c = sha256_fingerprint(
                datasource_id,
                t.schema_name,
                t.table_name,
                c.column_name,
                type_label,
                c.nullable,
                c.description,
                rel_for_col,
                c.samples,
                c.max_length,
                c.precision,
                c.scale,
            )
            key_c = f"{datasource_id}:COLUMN:{fq}.{c.column_name}"
            col_payload["fingerprint"] = fp_c
            col_payload["document_key"] = key_c
            col_payload["text"] = text_c
            docs.append(
                SchemaDocument(
                    document_type="COLUMN",
                    datasource_id=datasource_id,
                    document_key=key_c,
                    fingerprint=fp_c,
                    text=text_c,
                    payload=col_payload,
                )
            )

    for r in relationships:
        rel_payload: dict[str, Any] = {
            "document_type": "RELATIONSHIP",
            "datasource_id": datasource_id,
            "from_table": r.from_table,
            "from_column": r.from_column,
            "to_table": r.to_table,
            "to_column": r.to_column,
            "relationship_type": r.relationship_type,
            "from_schema": r.from_schema,
            "to_schema": r.to_schema,
            "kind": "relationship",
            "schema": r.from_schema,
            "table": r.from_table,
            "column": r.from_column,
        }
        text_r = (
            f"Relationship {r.from_schema}.{r.from_table}.{r.from_column} "
            f"→ {r.to_schema}.{r.to_table}.{r.to_column} "
            f"type={r.relationship_type} datasource={datasource_id}"
        )
        fp_r = sha256_fingerprint(
            datasource_id,
            r.from_schema,
            r.from_table,
            r.from_column,
            r.to_schema,
            r.to_table,
            r.to_column,
            r.relationship_type,
            "",
        )
        key_r = (
            f"{datasource_id}:RELATIONSHIP:"
            f"{r.from_schema}.{r.from_table}.{r.from_column}->"
            f"{r.to_schema}.{r.to_table}.{r.to_column}"
        )
        rel_payload["fingerprint"] = fp_r
        rel_payload["document_key"] = key_r
        rel_payload["text"] = text_r
        docs.append(
            SchemaDocument(
                document_type="RELATIONSHIP",
                datasource_id=datasource_id,
                document_key=key_r,
                fingerprint=fp_r,
                text=text_r,
                payload=rel_payload,
            )
        )

    for d in docs:
        d.payload["point_id"] = point_id_from_key(d.document_key)
    return docs
