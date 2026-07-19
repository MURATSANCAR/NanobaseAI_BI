# S/4HANA OData Design

## Logical plan (AWEL never emits raw URLs)

```json
{
  "sourceType": "SAP_ODATA",
  "service": "APPROVED_FINANCE_SERVICE",
  "entitySet": "JournalEntryItem",
  "select": ["CompanyCode", "FiscalYear", "AmountInCompanyCodeCurrency"],
  "filters": [{"field": "CompanyCode", "operator": "EQ", "value": "1000"}],
  "top": 101
}
```

## Allowed options

`$select` (required), `$filter`, `$orderby`, `$top`, controlled `$count` / `$expand`.

## Denied

POST/PUT/PATCH/DELETE, actions, function imports, `$batch`, `$apply`, `$search`,
host/path escape, absolute URL injection, uncontrolled expand.

## Limits

Interactive rows 100, max 1000, expand depth ≤1, max navigation 2.
Next-link must preserve host, service root, entity set, and query options.
