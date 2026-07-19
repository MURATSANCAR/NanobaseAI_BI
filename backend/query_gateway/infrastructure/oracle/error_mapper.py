"""Map Oracle errors to GatewayError codes (no raw ORA text to clients)."""

from __future__ import annotations

from query_gateway.domain.errors import (
    DATABASE_UNAVAILABLE,
    QUERY_TIMEOUT,
    GatewayError,
)

DATASOURCE_AUTHENTICATION_FAILED = "DATASOURCE_AUTHENTICATION_FAILED"
DATABASE_PERMISSION_DENIED = "DATABASE_PERMISSION_DENIED"
TABLE_OR_VIEW_NOT_FOUND = "TABLE_OR_VIEW_NOT_FOUND"
COLUMN_NOT_FOUND = "COLUMN_NOT_FOUND"
QUERY_RESOURCE_LIMIT_EXCEEDED = "QUERY_RESOURCE_LIMIT_EXCEEDED"
DATABASE_CONNECTION_LOST = "DATABASE_CONNECTION_LOST"
QUERY_TYPE_CONVERSION_FAILED = "QUERY_TYPE_CONVERSION_FAILED"
QUERY_CONSISTENCY_ERROR = "QUERY_CONSISTENCY_ERROR"
DATABASE_CONTAINER_UNAVAILABLE = "DATABASE_CONTAINER_UNAVAILABLE"
ORACLE_PLAN_VALIDATION_UNAVAILABLE = "ORACLE_PLAN_VALIDATION_UNAVAILABLE"
EXECUTION_OUTCOME_UNKNOWN = "EXECUTION_OUTCOME_UNKNOWN"


def map_oracle_error(exc: BaseException) -> GatewayError:
    msg = str(exc).upper()
    code = getattr(exc, "code", None) or getattr(exc, "args", [None])[0]

    # python-oracledb often exposes .code as int ORA number
    ora = None
    if isinstance(code, int):
        ora = code
    else:
        for part in str(exc).replace(" ", "").split(":"):
            if part.upper().startswith("ORA-") and part[4:].isdigit():
                ora = int(part[4:])
                break

    if ora in (1017, 1005, 28000, 28001) or "INVALID USERNAME/PASSWORD" in msg:
        return GatewayError(
            DATASOURCE_AUTHENTICATION_FAILED,
            "Veri kaynağı kimlik doğrulaması başarısız.",
            status=401,
        )
    if ora in (12514, 12541, 12543, 12505, 12545) or "TNS" in msg or "LISTENER" in msg:
        return GatewayError(
            DATABASE_UNAVAILABLE,
            "Veritabanı servisi kullanılamıyor.",
            status=503,
            retryable=True,
        )
    if ora in (942,) or "TABLE OR VIEW DOES NOT EXIST" in msg:
        return GatewayError(TABLE_OR_VIEW_NOT_FOUND, "Tablo veya view bulunamadı.", status=400)
    if ora in (904,) or "INVALID IDENTIFIER" in msg:
        return GatewayError(COLUMN_NOT_FOUND, "Kolon bulunamadı.", status=400)
    if ora in (1031, 1045) or "INSUFFICIENT PRIVILEGES" in msg:
        return GatewayError(
            DATABASE_PERMISSION_DENIED,
            "Veritabanı yetkisi yetersiz.",
            status=403,
        )
    if ora in (1013,) or "CANCEL" in msg or "TIMEOUT" in msg or "TIMED OUT" in msg:
        return GatewayError(QUERY_TIMEOUT, "Sorgu zaman aşımına uğradı.", status=408, retryable=True)
    if "RESOURCE MANAGER" in msg or ora in (3700, 3701):
        return GatewayError(
            QUERY_RESOURCE_LIMIT_EXCEEDED,
            "Sorgu kaynak limiti aşıldı.",
            status=429,
            retryable=True,
        )
    if ora in (3113, 3114, 28, 1012) or "NOT CONNECTED" in msg:
        return GatewayError(
            DATABASE_CONNECTION_LOST,
            "Veritabanı bağlantısı koptu.",
            status=503,
            retryable=True,
        )
    if ora in (1722, 1861, 1830) or "INVALID NUMBER" in msg or "DATE FORMAT" in msg:
        return GatewayError(
            QUERY_TYPE_CONVERSION_FAILED,
            "Veri tipi dönüşümü başarısız.",
            status=400,
        )
    if ora in (1555,) or "SNAPSHOT" in msg:
        return GatewayError(
            QUERY_CONSISTENCY_ERROR,
            "Sorgu tutarlılık hatası.",
            status=409,
            retryable=True,
        )
    if "CONTAINER" in msg or ora in (65040, 65011):
        return GatewayError(
            DATABASE_CONTAINER_UNAVAILABLE,
            "Veritabanı container kullanılamıyor.",
            status=503,
            retryable=True,
        )
    return GatewayError(
        DATABASE_UNAVAILABLE,
        "Oracle sorgu yürütülemedi.",
        status=400,
    )
