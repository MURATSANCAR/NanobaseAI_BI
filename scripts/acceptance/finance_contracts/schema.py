"""Read live physical schema and Dynamics' own field labels; never infer from old catalog.

Run on the real test server. Contains no business-row sampling or source writes.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone

from live import connect, query


def collect(sources=("logo", "crm")):
    evidence = {"collectedAt": datetime.now(timezone.utc).isoformat(), "sources": {}}
    for source in sources:
        conn = connect(f"/data/nanobaseai/bi/secrets/{source}-mssql-connection.json")
        try:
            if source == "logo":
                predicate = "TABLE_NAME IN ('L_CAPIPERIOD','L_CAPIFIRM') OR TABLE_NAME LIKE 'LG[_]%[_]STLINE' OR TABLE_NAME LIKE 'LG[_]%[_]INVOICE' OR TABLE_NAME LIKE 'LG[_]%[_]CLFLINE' OR TABLE_NAME LIKE 'LG[_]%[_]ITEMS' OR TABLE_NAME LIKE 'LG[_]%[_]CLCARD'"
            else:
                predicate = "TABLE_NAME IN ('new_kitapBase','ContactBase','AccountBase','new_markaBase','new_satishedefleriBase')"
            rows = query(conn, "SELECT TABLE_SCHEMA,TABLE_NAME,COLUMN_NAME,ORDINAL_POSITION,DATA_TYPE,IS_NULLABLE,CHARACTER_MAXIMUM_LENGTH,NUMERIC_PRECISION,NUMERIC_SCALE FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA='dbo' AND (" + predicate + ") ORDER BY TABLE_NAME,ORDINAL_POSITION")
            item = {"columns": rows}
            if source == "crm":
                item["statusLabels"] = query(conn, "SELECT DISTINCT E.LogicalName entity,M.AttributeName attribute,M.AttributeValue code,M.Value label,M.LangId language FROM dbo.StringMapBase M JOIN MetadataSchema.Entity E ON E.ObjectTypeCode=M.ObjectTypeCode AND E.ComponentState=0 WHERE E.LogicalName IN ('new_kitap','contact','account','new_marka') AND M.AttributeName IN ('statecode','statuscode') AND M.LangId=1055 ORDER BY E.LogicalName,M.AttributeName,M.AttributeValue")
                # ComponentState=0 is published metadata, separate from business-record statecode.
                item["fieldLabels"] = query(conn, "SELECT E.LogicalName entity,E.BaseTableName,A.LogicalName attribute,A.PhysicalName,A.ReferencedEntityObjectTypeCode,L.LanguageId,L.ObjectColumnName,L.Label FROM MetadataSchema.Entity E JOIN MetadataSchema.Attribute A ON A.EntityId=E.EntityId AND A.ComponentState=0 LEFT JOIN MetadataSchema.LocalizedLabel L ON L.ObjectId=A.AttributeId AND L.ComponentState=0 AND L.LanguageId IN (1055,1033) WHERE E.ComponentState=0 AND E.LogicalName IN ('new_kitap','contact','account','new_marka','new_satishedefleri') ORDER BY E.LogicalName,A.LogicalName,L.LanguageId,L.ObjectColumnName")
                item["relationships"] = query(conn, "SELECT R.Name relationship,E.LogicalName sourceEntity,A.LogicalName sourceAttribute,T.LogicalName targetEntity,B.LogicalName targetAttribute FROM MetadataSchema.Relationship R JOIN MetadataSchema.Entity E ON E.EntityId=R.ReferencingEntityId AND E.ComponentState=0 JOIN MetadataSchema.Attribute A ON A.AttributeId=R.ReferencingAttributeId AND A.ComponentState=0 JOIN MetadataSchema.Entity T ON T.EntityId=R.ReferencedEntityId AND T.ComponentState=0 JOIN MetadataSchema.Attribute B ON B.AttributeId=R.ReferencedAttributeId AND B.ComponentState=0 WHERE R.ComponentState=0 AND E.LogicalName IN ('new_kitap','contact','account','new_marka','new_satishedefleri') ORDER BY E.LogicalName,A.LogicalName")
            else:
                item["periods"] = query(conn, "SELECT FIRMNR,NR,BEGDATE,ENDDATE,ACTIVE FROM L_CAPIPERIOD ORDER BY FIRMNR,NR")
                item["fieldDescriptions"] = query(conn, "SELECT T.name tableName,C.name columnName,CAST(P.value AS nvarchar(4000)) description FROM sys.extended_properties P JOIN sys.tables T ON T.object_id=P.major_id LEFT JOIN sys.columns C ON C.object_id=P.major_id AND C.column_id=P.minor_id WHERE P.class=1 AND P.name='MS_Description' AND (T.name LIKE 'LG[_]%[_]STLINE' OR T.name LIKE 'LG[_]%[_]INVOICE' OR T.name LIKE 'LG[_]%[_]CLFLINE')")
            item["sha256"] = hashlib.sha256(json.dumps(item, sort_keys=True, default=str).encode()).hexdigest()
            evidence["sources"][source] = item
        finally:
            conn.close()
    return evidence


if __name__ == "__main__":
    if sys.platform != "linux":
        raise SystemExit("Run only on the real test server")
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--source", choices=("logo", "crm"))
    args = parser.parse_args()
    os.umask(0o077)
    evidence = collect((args.source,) if args.source else ("logo", "crm"))
    Path(args.out).write_text(json.dumps(evidence, ensure_ascii=False, default=str, indent=2))
    print(json.dumps({s: {"columns": len(v["columns"]), "sha256": v["sha256"]} for s,v in evidence["sources"].items()}))
