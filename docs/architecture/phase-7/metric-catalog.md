# Metric catalog

First production metric: `unpaid_invoice_amount`

- Aggregation: SUM
- Source: `reporting.invoice.remaining_amount`
- Mandatory filter: `exclude_cancelled_invoices` (CANCELLED, VOID)
- Time field: `reporting.invoice.invoice_date`
- Null policy: ZERO (COALESCE)
- Currency: DOCUMENT_CURRENCY

Second metric must not be added until this slice passes GO gates.
