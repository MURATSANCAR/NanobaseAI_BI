# SAP Semantic Model

## Mandatory FI fields

ledger, ledger_group, accounting_principle, company_code, fiscal_year, fiscal_period, posting_status.

Financial metrics without ledger cannot be published.

## Currency / unit

Amount + currency (or quantity + unit) travel together via binding/annotation.
Mismatch tolerance is zero.

## Reversal

Cancellation/reversal filters are Semantic Catalog mandatory rules, not LLM suggestions.
Cannot be stripped from the query plan.

## LLM may not invent

Ledger, reversal handling, company code scope, fiscal year variant, posting vs document date,
currency conversion method, unit conversion, client/MANDT scope.
