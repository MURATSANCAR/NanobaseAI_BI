# Faz 9 Rollback

## Primary

```text
SAP_EXECUTION_MODE → PLAN_ONLY
```

or `SAP_EXECUTION_ENABLED=0`.

## Forbidden rollback

CDS/OData → raw SAP table SQL. Generic DB-GPT execution must not open.
OData write and HANA raw table access must not open.

## Preserved

Datasource metadata, semantic catalog, conversations.

## Roll-backable components

SAP adapter image, OData/HANA policy versions, AWEL SAP prompt versions,
semantic catalog / source binding versions.
