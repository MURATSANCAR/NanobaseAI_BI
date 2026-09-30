"""Remote-only published CRM metadata evidence for the closed CRM query module.

No legacy catalog reads and no source writes. This establishes field/relationship
identity, not API answer acceptance; the latter belongs to composable_live.py.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from schema import collect
from live import connect, query
from datetime import datetime, timezone


REQUIRED = {
    "new_kitapBase": ["new_kitapId", "new_stokkodu", "new_name", "new_yazartext", "new_isbn13", "new_yayineviid", "CreatedOn", "ModifiedOn", "statecode", "statuscode"],
    "new_markaBase": ["new_markaId", "new_name", "statecode", "statuscode"],
    "ContactBase": ["ContactId", "FullName", "new_yazarmi", "CreatedOn", "ModifiedOn", "statecode", "statuscode"],
    "AccountBase": ["AccountId", "Name", "CreatedOn", "ModifiedOn", "statecode", "statuscode"],
}


def inventory():
    """All physical tables/columns and all published entity edges; no business rows."""
    conn = connect("/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
    sqls = {
        "tables": "SELECT TABLE_SCHEMA,TABLE_NAME,TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES ORDER BY TABLE_SCHEMA,TABLE_NAME",
        "columns": "SELECT TABLE_SCHEMA,TABLE_NAME,COLUMN_NAME,ORDINAL_POSITION,DATA_TYPE,IS_NULLABLE,CHARACTER_MAXIMUM_LENGTH,NUMERIC_PRECISION,NUMERIC_SCALE FROM INFORMATION_SCHEMA.COLUMNS ORDER BY TABLE_SCHEMA,TABLE_NAME,ORDINAL_POSITION",
        "keys": "SELECT S.name schema_name,T.name table_name,I.name index_name,I.is_unique,I.is_primary_key,C.name column_name,K.key_ordinal FROM sys.tables T JOIN sys.schemas S ON S.schema_id=T.schema_id JOIN sys.indexes I ON I.object_id=T.object_id AND I.is_unique=1 JOIN sys.index_columns K ON K.object_id=I.object_id AND K.index_id=I.index_id AND K.key_ordinal>0 JOIN sys.columns C ON C.object_id=K.object_id AND C.column_id=K.column_id ORDER BY S.name,T.name,I.name,K.key_ordinal",
        "foreignKeys": "SELECT F.name relationship,OBJECT_SCHEMA_NAME(F.parent_object_id) source_schema,OBJECT_NAME(F.parent_object_id) source_table,PC.name source_column,OBJECT_SCHEMA_NAME(F.referenced_object_id) target_schema,OBJECT_NAME(F.referenced_object_id) target_table,RC.name target_column FROM sys.foreign_keys F JOIN sys.foreign_key_columns K ON K.constraint_object_id=F.object_id JOIN sys.columns PC ON PC.object_id=K.parent_object_id AND PC.column_id=K.parent_column_id JOIN sys.columns RC ON RC.object_id=K.referenced_object_id AND RC.column_id=K.referenced_column_id",
        "entities": "SELECT DISTINCT E.LogicalName entity,E.BaseTableName table_name,E.ObjectTypeCode,L.Label label FROM MetadataSchema.Entity E LEFT JOIN MetadataSchema.LocalizedLabel L ON L.ObjectId=E.EntityId AND L.ComponentState=0 AND L.LanguageId=1055 AND L.ObjectColumnName='LocalizedName' WHERE E.ComponentState=0",
        "fields": "SELECT DISTINCT E.LogicalName entity,E.BaseTableName table_name,A.LogicalName attribute,A.PhysicalName physical_name,A.ColumnNumber,A.ReferencedEntityObjectTypeCode,L.Label label FROM MetadataSchema.Entity E JOIN MetadataSchema.Attribute A ON A.EntityId=E.EntityId AND A.ComponentState=0 LEFT JOIN MetadataSchema.LocalizedLabel L ON L.ObjectId=A.AttributeId AND L.ComponentState=0 AND L.LanguageId=1055 AND L.ObjectColumnName='DisplayName' WHERE E.ComponentState=0",
        "relationships": "SELECT DISTINCT R.Name relationship,E.LogicalName source_entity,A.PhysicalName source_column,T.LogicalName target_entity,B.PhysicalName target_column FROM MetadataSchema.Relationship R JOIN MetadataSchema.Entity E ON E.EntityId=R.ReferencingEntityId AND E.ComponentState=0 JOIN MetadataSchema.Attribute A ON A.AttributeId=R.ReferencingAttributeId AND A.ComponentState=0 JOIN MetadataSchema.Entity T ON T.EntityId=R.ReferencedEntityId AND T.ComponentState=0 JOIN MetadataSchema.Attribute B ON B.AttributeId=R.ReferencedAttributeId AND B.ComponentState=0 WHERE R.ComponentState=0",
        "statusLabels": "SELECT DISTINCT E.LogicalName entity,M.AttributeName attribute,M.AttributeValue code,M.Value label FROM dbo.StringMapBase M JOIN MetadataSchema.Entity E ON E.ObjectTypeCode=M.ObjectTypeCode AND E.ComponentState=0 WHERE M.AttributeName IN ('statecode','statuscode') AND M.LangId=1055",
    }
    result = {"collectedAt": datetime.now(timezone.utc).isoformat(), "sourceWrites": 0, "businessRowsRead": 0, "apiAcceptance": False, "sources": {}}
    try:
        for name, sql in sqls.items():
            result["sources"][name] = query(conn, sql)
        try:
            query(conn, "SELECT TOP (0) AuditId,AttributeMask,ChangeData,CreatedOn,ObjectId,ObjectTypeCode FROM AuditBase")
            result["auditAvailability"] = {"physicalReadPermission": True, "rowsRead": 0, "oldNewValueDecoderVerified": False,
                "stageEntryHistoryVerified": False, "reason": "Audit columns readable; permission and schema do not establish old/new decoding or complete event coverage"}
        except Exception as exc:
            result["auditAvailability"] = {"physicalReadPermission": False, "rowsRead": 0, "reason": str(exc)[:250]}
    finally:
        conn.close()
    seeds = {"new_kitap", "new_eserkatilim", "new_katilimcitipi", "new_marka", "new_yaynevialtmarka", "contact", "account", "task", "appointment", "activityparty", "new_sozlesme", "new_sozlesmetarafi", "new_hak", "new_dil", "new_blge", "new_isplani", "new_proje", "audit"}
    # Connected closure records every reachable entity, including intervening N:N
    # entities. Traversal is metadata only; this is not an instruction to scan data.
    closure = set(seeds)
    edges = result["sources"]["relationships"]
    while True:
        expanded = closure | {r[side] for r in edges if r["source_entity"] in closure or r["target_entity"] in closure for side in ("source_entity", "target_entity")}
        if expanded == closure: break
        closure = expanded
    result["connectedEntityClosure"] = sorted(closure)
    cols = result["sources"]["columns"]
    bytable = {}
    for row in cols:
        bytable.setdefault(row["TABLE_NAME"].lower(), set()).add(row["COLUMN_NAME"].lower())
    used = {"new_kitapbase", "new_markabase", "new_yaynevialtmarkabase", "contactbase", "accountbase", "new_eserkatilimbase", "new_katilimcitipibase", "new_contact_accountbase", "new_sozlesmebase", "new_sozlesmetarafibase", "new_sozlesmetaraftipibase", "new_new_sozlesme_new_kitapbase", "new_new_hak_new_sozlesmebase", "new_new_sozlesme_new_dilbase", "new_new_sozlesme_new_blgebase", "new_new_sozlesme_new_ulkebase", "new_hakbase", "new_dilbase", "new_blgebase", "new_ulkebase", "new_isplanibase", "new_projebase", "new_new_proje_new_kitapbase", "new_projeasamalaribase", "activitypointerbase", "activitypartybase", "taskbase", "appointmentbase", "new_kitapgecmisibase", "systemuserbase", "customeraddressbase", "territorybase"}
    result["reportTableBindings"] = {
        "book_quality_duplicate_publication": ["new_kitapBase","new_markaBase","new_yaynevialtmarkaBase","new_eserkatilimBase","new_katilimcitipiBase","ContactBase"],
        "author_identity_coverage": ["ContactBase","new_eserkatilimBase","new_katilimcitipiBase","new_kitapBase"],
        "customer_identity_geography": ["AccountBase","ContactBase","new_contact_accountBase","CustomerAddressBase","TerritoryBase"],
        "contract_scope_and_parties": ["new_sozlesmeBase","new_new_sozlesme_new_kitapBase","new_sozlesmetarafiBase","new_sozlesmetaraftipiBase","new_new_hak_new_sozlesmeBase","new_hakBase","new_new_sozlesme_new_dilBase","new_dilBase","new_new_sozlesme_new_blgeBase","new_blgeBase","new_new_sozlesme_new_ulkeBase","new_ulkeBase"],
        "book_assignments": ["new_kitapBase","SystemUserBase"],
        "work_due_stage": ["new_isplaniBase","new_projeBase","new_projeasamalariBase","new_new_proje_new_kitapBase","new_kitapBase"],
        "author_meeting_actions": ["ActivityPointerBase","ActivityPartyBase","TaskBase","AppointmentBase","ContactBase"],
        "history_partial": ["new_kitapgecmisiBase","AuditBase"],
    }
    matrix = []
    entitytables = {r["table_name"].lower() for r in result["sources"]["entities"] if r["entity"] in closure and r["table_name"]}
    for t in result["sources"]["tables"]:
        name = t["TABLE_NAME"].lower()
        state = "USED_BY_CLOSED_REPORT" if name in used else "NEEDED_HISTORY_EVIDENCE" if name == "auditbase" else "RELATED_NOT_YET_BOUND" if name in entitytables else "INVENTORIED_NOT_USED"
        matrix.append({**t, "coverage": state, "statecodePresent": "statecode" in bytable.get(name, set()), "statuscodePresent": "statuscode" in bytable.get(name, set()),
                       "reason": "Physical inventory only; no business semantics or row coverage inferred" if state != "USED_BY_CLOSED_REPORT" else "Fields still verified at execution; API/full-answer acceptance separate"})
    result["tableCoverage"] = matrix
    result["missingRequiredTables"] = sorted(used - set(bytable))
    result["counts"] = {k:len(v) for k,v in result["sources"].items()}
    return result


def main():
    if sys.platform != "linux" or not Path("/proc").is_dir():
        raise SystemExit("Run only on the real test server")
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    parser.add_argument("--inventory", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    if args.inventory:
        evidence = inventory()
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(evidence, ensure_ascii=False, default=str, indent=2))
        print(json.dumps({"counts":evidence["counts"],"missingRequiredTables":evidence["missingRequiredTables"],"closureEntities":len(evidence["connectedEntityClosure"]),"sha256":hashlib.sha256(target.read_bytes()).hexdigest()}, ensure_ascii=False))
        return 1 if evidence["missingRequiredTables"] else 0
    evidence = collect(("crm",))
    source = evidence["sources"]["crm"]
    physical = {(r["TABLE_NAME"].lower(), r["COLUMN_NAME"].lower()) for r in source["columns"]}
    missing = [t + "." + c for t, cols in REQUIRED.items() for c in cols if (t.lower(), c.lower()) not in physical]
    labels = sorted({str(r["Label"]) for r in source["fieldLabels"] if str(r["attribute"]).lower() == "new_isbn13" and r["LanguageId"] == 1055 and r["Label"]})
    relationships = [r for r in source["relationships"] if r["sourceEntity"] == "new_kitap" and r["sourceAttribute"].lower() == "new_yayineviid" and r["targetEntity"] == "new_marka" and r["targetAttribute"].lower() == "new_markaid"]
    checks = {"requiredPhysicalColumns": not missing, "currentIsbnLabel": any("ISBN" in label for label in labels),
              "publisherRelationship": bool(relationships)}
    evidence.update(checks=checks, missingColumns=missing, currentIsbnLabels=labels,
                    relationshipEvidence=relationships, sourceWrites=0, apiAcceptance=False)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(evidence, ensure_ascii=False, default=str, indent=2))
    print(json.dumps({"checks": checks, "missingColumns": missing, "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                      "apiAcceptance": False}, ensure_ascii=False))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
