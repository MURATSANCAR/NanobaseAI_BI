"""Unit tests for Oracle metadata → Qdrant payload shaping."""

from __future__ import annotations

from query_gateway.infrastructure.oracle.metadata_scanner import to_qdrant_documents


def test_qdrant_payload_has_oracle_filters():
    scan = {
        "objects": [
            {
                "owner": "NANOBASE_REPORTING",
                "object_name": "V_INVOICE",
                "object_type": "VIEW",
                "status": "VALID",
            }
        ],
        "columns": [
            {
                "owner": "NANOBASE_REPORTING",
                "table_name": "V_INVOICE",
                "column_name": "REMAINING_AMOUNT",
                "data_type": "NUMBER",
                "data_precision": 18,
                "data_scale": 2,
                "nullable": "Y",
            }
        ],
        "table_comments": [],
        "column_comments": [],
        "synonyms": [
            {
                "document_type": "SYNONYM",
                "owner": "NANOBASE_REPORTING",
                "synonym_name": "INVOICES",
                "resolved_owner": "NANOBASE_REPORTING",
                "resolved_object": "V_INVOICE",
                "resolved_type": "VIEW",
            }
        ],
    }
    docs = to_qdrant_documents(
        scan,
        tenant_id="t1",
        datasource_id="oracle_reporting",
        database_unique_name="FINDB",
        container_name="FINPDB",
        schema_version="sha256:abc",
        semantic_version="8.0.0",
    )
    col = next(d for d in docs if d["document_type"] == "COLUMN")
    assert col["database_type"] == "ORACLE"
    assert col["owner"] == "NANOBASE_REPORTING"
    assert col["oracle_data_type"] == "NUMBER"
    assert col["status"] == "ACTIVE"
    assert col["tenant_id"] == "t1"
