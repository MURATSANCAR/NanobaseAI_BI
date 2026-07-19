"""Metric definition entity + validation invariants."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from nanobase_api.semantic_catalog.domain.errors import ValidationError
from nanobase_api.semantic_catalog.domain.status import AssetStatus, transition

Aggregation = Literal["SUM", "COUNT", "AVG", "MIN", "MAX", "COUNT_DISTINCT"]
NullPolicy = Literal["ZERO", "IGNORE", "REJECT"]
CurrencyPolicy = Literal[
    "DOCUMENT_CURRENCY",
    "BASE_CURRENCY",
    "TRANSACTION_DATE_RATE",
    "NONE",
]


@dataclass
class SourceExpression:
    table: str
    column: str

    def to_dict(self) -> dict[str, Any]:
        return {"table": self.table, "column": self.column}

    @property
    def qualified(self) -> str:
        return f"{self.table}.{self.column}"


@dataclass
class CurrencySemantics:
    amount_field: str
    currency_field: str | None = None
    base_currency: str = "TRY"
    conversion_policy: CurrencyPolicy = "DOCUMENT_CURRENCY"
    rate_source: str | None = None
    rate_date_policy: str | None = None
    rounding_scale: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "amountField": self.amount_field,
            "currencyField": self.currency_field,
            "baseCurrency": self.base_currency,
            "conversionPolicy": self.conversion_policy,
            "rateSource": self.rate_source,
            "rateDatePolicy": self.rate_date_policy,
            "roundingScale": self.rounding_scale,
        }


@dataclass
class TimeSemantics:
    time_field: str
    timezone: str = "Europe/Istanbul"
    calendar_type: str = "CALENDAR"
    default_granularity: str = "MONTH"

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeField": self.time_field,
            "timezone": self.timezone,
            "calendarType": self.calendar_type,
            "defaultGranularity": self.default_granularity,
        }


@dataclass
class Metric:
    id: str
    tenant_id: str
    datasource_id: str
    code: str
    name: str
    description: str
    aggregation: Aggregation
    source: SourceExpression
    default_filter_codes: list[str] = field(default_factory=list)
    null_policy: NullPolicy = "ZERO"
    time: TimeSemantics | None = None
    currency: CurrencySemantics | None = None
    is_financial: bool = False
    multi_currency_datasource: bool = False
    status: AssetStatus = AssetStatus.DRAFT
    version: int = 1

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValidationError("Metric code zorunludur.")
        if isinstance(self.status, str):
            self.status = AssetStatus(self.status)

    def transition_to(self, target: AssetStatus) -> None:
        self.status = transition(self.status, target)

    def validate_for_publish(self, *, known_filter_codes: set[str] | None = None) -> None:
        """Raise ValidationError if metric cannot be published."""
        if not self.source.table or not self.source.column:
            raise ValidationError("Metric source table/column zorunludur.")
        if self.time is None or not self.time.time_field:
            raise ValidationError("Metric time field zorunludur.")
        if self.null_policy not in ("ZERO", "IGNORE", "REJECT"):
            raise ValidationError("Geçersiz null policy.")
        if self.is_financial or self.multi_currency_datasource:
            if self.currency is None:
                raise ValidationError("Finansal / çoklu para birimli metric için currency policy zorunludur.")
            if self.multi_currency_datasource and self.currency.conversion_policy == "NONE":
                raise ValidationError("Çoklu para birimli datasource'ta currency policy NONE olamaz.")
        if known_filter_codes is not None:
            missing = set(self.default_filter_codes) - known_filter_codes
            if missing:
                raise ValidationError(f"Bilinmeyen filter kodları: {sorted(missing)}")
        if self.aggregation == "SUM" and self._looks_non_numeric_hint():
            # Domain-level hint only; physical type check is application/infra.
            pass

    def _looks_non_numeric_hint(self) -> bool:
        col = self.source.column.lower()
        return any(x in col for x in ("name", "status", "code", "id", "email", "city"))

    def reject_sum_on_string_column(self, physical_type: str) -> None:
        t = (physical_type or "").lower()
        if self.aggregation == "SUM" and any(x in t for x in ("char", "text", "uuid", "bool", "date", "timestamp")):
            raise ValidationError(f"SUM aggregation numeric olmayan tip ile uyumsuz: {physical_type}")

    def to_logical_plan(self, *, extra_filters: list[str] | None = None) -> dict[str, Any]:
        filters = list(self.default_filter_codes)
        if extra_filters:
            filters.extend(extra_filters)
        return {
            "metric": self.code,
            "aggregation": self.aggregation,
            "field": self.source.qualified,
            "filters": filters,
            "timeField": self.time.time_field if self.time else None,
            "nullPolicy": self.null_policy,
            "currencyPolicy": self.currency.conversion_policy if self.currency else None,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "tenantId": self.tenant_id,
            "datasourceId": self.datasource_id,
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "aggregation": self.aggregation,
            "sourceExpression": self.source.to_dict(),
            "defaultFilters": list(self.default_filter_codes),
            "nullPolicy": self.null_policy,
            "time": self.time.to_dict() if self.time else None,
            "currency": self.currency.to_dict() if self.currency else None,
            "isFinancial": self.is_financial,
            "status": self.status.value,
            "version": self.version,
        }
