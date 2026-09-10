"""Export the CRM's own Turkish dictionary: what it calls its tables, columns and coded values.

Dynamics keeps every label it shows a user in `MetadataSchema.LocalizedLabel`, LanguageId 1055 for
Turkish. That is the business's own wording, written by the people who use the system — not a guess
and not a translation. This reads it out so `enrich_crm_metadata.py` can put it in the catalog.

Only published rows are exported (`ComponentState = 0`): an unpublished customisation is a draft
somebody is still editing, and the catalog must describe the system as it currently runs.

Run it on the server, where the database is reachable:

    python -m scripts.export_crm_metadata --out /tmp/crm-labels.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pyodbc

SECRETS = Path("/data/nanobaseai/bi/secrets/logo-mssql-connection.json")
DATABASE = "Timas_MSCRM"

ENTITIES = """
SELECT e.BaseTableName, l.LanguageId, l.ObjectColumnName, l.Label
FROM MetadataSchema.Entity e
JOIN MetadataSchema.LocalizedLabel l ON l.ObjectId = e.EntityId
WHERE e.BaseTableName IS NOT NULL AND l.ComponentState = 0
  AND l.ObjectColumnName IN ('LocalizedName', 'LocalizedCollectionName', 'Description')
"""

ATTRIBUTES = """
SELECT e.BaseTableName, a.PhysicalName, l.LanguageId, l.ObjectColumnName, l.Label
FROM MetadataSchema.Attribute a
JOIN MetadataSchema.Entity e ON e.EntityId = a.EntityId
JOIN MetadataSchema.LocalizedLabel l ON l.ObjectId = a.AttributeId
WHERE a.IsLogical = 0 AND a.PhysicalName IS NOT NULL AND e.BaseTableName IS NOT NULL
  AND l.ComponentState = 0 AND l.ObjectColumnName IN ('DisplayName', 'Description')
"""

# A picklist's numbers are meaningless on their own; this is the row that says 100000001 is "İptal
# Edildi". Joined through the attribute's option set, because the same set can serve several columns.
OPTIONS = """
SELECT e.BaseTableName, a.PhysicalName, p.Value, l.LanguageId, l.Label
FROM MetadataSchema.Attribute a
JOIN MetadataSchema.Entity e ON e.EntityId = a.EntityId
JOIN MetadataSchema.AttributePicklistValue p ON p.OptionSetId = a.OptionSetId
JOIN MetadataSchema.LocalizedLabel l ON l.ObjectId = p.AttributePicklistValueId
WHERE a.IsLogical = 0 AND a.PhysicalName IS NOT NULL AND e.BaseTableName IS NOT NULL
  AND l.ComponentState = 0 AND l.ObjectColumnName = 'DisplayName'
"""


def connect(secrets: Path, database: str, timeout: int = 900):
    c = json.loads(secrets.read_text())
    cs = (f"DRIVER={{{c['driver']}}};SERVER={c['host']};PORT={c['port']};DATABASE={database};"
          f"UID={c['user']};PWD={c['password']};"
          f"TDS_Version={c.get('tds_version', '7.4')};ClientCharset=UTF-8")
    cn = pyodbc.connect(cs, timeout=30)
    cn.timeout = timeout
    return cn


def rows(cur, sql: str) -> list[dict]:
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, (str(v) if v is not None else None for v in r))) for r in cur.fetchall()]


def export(cn) -> dict:
    cur = cn.cursor()
    return {"source": f"{DATABASE}.MetadataSchema, published ComponentState=0",
            "entityLabels": rows(cur, ENTITIES),
            "attributeLabels": rows(cur, ATTRIBUTES),
            "optionLabels": rows(cur, OPTIONS)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--secrets", type=Path, default=SECRETS)
    parser.add_argument("--database", default=DATABASE)
    args = parser.parse_args()
    data = export(connect(args.secrets, args.database))
    args.out.write_text(json.dumps(data, ensure_ascii=False))
    print(json.dumps({k: len(v) for k, v in data.items() if isinstance(v, list)}, ensure_ascii=False))
