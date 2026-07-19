"""Table and column semantic roles."""

from __future__ import annotations

from enum import Enum


class TableRole(str, Enum):
    ENTITY = "ENTITY"
    TRANSACTION = "TRANSACTION"
    TRANSACTION_DETAIL = "TRANSACTION_DETAIL"
    DIMENSION = "DIMENSION"
    FACT = "FACT"
    LOOKUP = "LOOKUP"
    RELATIONSHIP = "RELATIONSHIP"
    AUDIT = "AUDIT"
    TECHNICAL = "TECHNICAL"
    HISTORY = "HISTORY"
    SNAPSHOT = "SNAPSHOT"
    REPORTING_VIEW = "REPORTING_VIEW"


class ColumnRole(str, Enum):
    IDENTIFIER = "IDENTIFIER"
    BUSINESS_IDENTIFIER = "BUSINESS_IDENTIFIER"
    NAME = "NAME"
    DESCRIPTION = "DESCRIPTION"
    DATE = "DATE"
    DATETIME = "DATETIME"
    BUSINESS_DATE = "BUSINESS_DATE"
    CREATED_AT = "CREATED_AT"
    UPDATED_AT = "UPDATED_AT"
    DUE_DATE = "DUE_DATE"
    POSTING_DATE = "POSTING_DATE"
    STATUS = "STATUS"
    CATEGORY = "CATEGORY"
    AMOUNT = "AMOUNT"
    QUANTITY = "QUANTITY"
    CURRENCY = "CURRENCY"
    UNIT = "UNIT"
    PERCENTAGE = "PERCENTAGE"
    BOOLEAN = "BOOLEAN"
    FOREIGN_KEY = "FOREIGN_KEY"
    TENANT_KEY = "TENANT_KEY"
    COMPANY_CODE = "COMPANY_CODE"
    LEDGER = "LEDGER"
    TECHNICAL = "TECHNICAL"
    SENSITIVE = "SENSITIVE"


# Tables that never produce end-user scenarios
NON_SCENARIO_TABLE_ROLES = frozenset(
    {TableRole.AUDIT, TableRole.TECHNICAL, TableRole.HISTORY}
)

# Columns never projected by default
BLOCKED_COLUMN_ROLES = frozenset({ColumnRole.TECHNICAL, ColumnRole.SENSITIVE})

MEASURE_ROLES = frozenset({ColumnRole.AMOUNT, ColumnRole.QUANTITY, ColumnRole.PERCENTAGE})
DATE_ROLES = frozenset(
    {
        ColumnRole.DATE,
        ColumnRole.DATETIME,
        ColumnRole.BUSINESS_DATE,
        ColumnRole.CREATED_AT,
        ColumnRole.UPDATED_AT,
        ColumnRole.DUE_DATE,
        ColumnRole.POSTING_DATE,
    }
)
DIMENSION_ROLES = frozenset(
    {ColumnRole.STATUS, ColumnRole.CATEGORY, ColumnRole.NAME, ColumnRole.BOOLEAN, ColumnRole.CURRENCY}
)
