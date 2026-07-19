"""Oracle connection profile + username / SERVICE_NAME policy."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from query_gateway.domain.errors import GatewayError

FORBIDDEN_ORACLE_USERS = frozenset(
    {
        "SYS",
        "SYSTEM",
        "SYSBACKUP",
        "SYSDG",
        "SYSKM",
        "DBSNMP",
        "ADMIN",  # Autonomous default admin — not for Nanobase production
    }
)

FORBIDDEN_OWNERS = frozenset(
    {
        "SYS",
        "SYSTEM",
        "XDB",
        "MDSYS",
        "CTXSYS",
        "ORDSYS",
        "WMSYS",
        "DBSNMP",
        "AUDSYS",
        "GSMADMIN_INTERNAL",
    }
)

DATASOURCE_AUTHENTICATION_FAILED = "DATASOURCE_AUTHENTICATION_FAILED"
ORACLE_PROFILE_INVALID = "ORACLE_PROFILE_INVALID"


@dataclass
class OracleConnectionProfile:
    datasource_id: str
    user: str
    password: str
    host: str = ""
    port: int = 1521
    service_name: str = ""
    dsn: str = ""
    connection_mode: str = "THIN"  # THIN | THICK
    ssl_mode: str = "REQUIRE"
    wallet_secret_ref: str | None = None
    allow_sid: bool = False
    sid: str | None = None
    allowed_owners: list[str] = field(default_factory=lambda: ["NANOBASE_REPORTING"])
    size_profile: str = "medium"
    plan_user: str | None = None
    plan_password: str | None = None
    metadata_user: str | None = None
    metadata_password: str | None = None
    container_name: str | None = None
    database_unique_name: str | None = None
    call_timeout_ms: int = 15_000

    def connect_dsn(self) -> str:
        if self.dsn:
            return self.dsn
        if self.allow_sid and self.sid and self.host:
            return f"{self.host}:{self.port}/{self.sid}"
        if self.host and self.service_name:
            return f"{self.host}:{self.port}/{self.service_name}"
        raise GatewayError(
            ORACLE_PROFILE_INVALID,
            "Oracle SERVICE_NAME veya DSN zorunludur.",
            status=400,
        )


def validate_oracle_username(username: str | None) -> str:
    user = (username or "").strip()
    if not user:
        raise GatewayError(
            ORACLE_PROFILE_INVALID,
            "Oracle kullanıcı adı zorunludur.",
            status=400,
        )
    if user.upper() in FORBIDDEN_ORACLE_USERS:
        raise GatewayError(
            DATASOURCE_AUTHENTICATION_FAILED,
            "Yasak Oracle hesabı ile bağlantı kurulamaz.",
            status=400,
        )
    return user


def validate_allowed_owners(owners: list[str] | None) -> list[str]:
    result: list[str] = []
    for raw in owners or ["NANOBASE_REPORTING"]:
        owner = str(raw).strip().upper()
        if not owner:
            continue
        if owner in FORBIDDEN_OWNERS or owner == "CDB$ROOT":
            raise GatewayError(
                ORACLE_PROFILE_INVALID,
                f"Yasak Oracle owner: {owner}.",
                status=400,
            )
        result.append(owner)
    if not result:
        raise GatewayError(
            ORACLE_PROFILE_INVALID,
            "allowedOwners boş olamaz.",
            status=400,
        )
    return result


def build_profile_from_datasource(ds: dict[str, Any]) -> OracleConnectionProfile:
    user = validate_oracle_username(ds.get("user") or ds.get("username"))
    mode = str(ds.get("connection_mode") or ds.get("connectionMode") or "THIN").upper()
    if mode not in ("THIN", "THICK"):
        raise GatewayError(ORACLE_PROFILE_INVALID, "connectionMode THIN veya THICK olmalı.", status=400)

    allow_sid = bool(ds.get("allow_sid") or ds.get("allowSid") or False)
    service = (
        ds.get("service_name")
        or ds.get("serviceName")
        or ds.get("service")
        or ds.get("database")
        or ""
    )
    service = str(service).strip()
    sid = ds.get("sid")
    dsn = str(ds.get("dsn") or "").strip()

    if not allow_sid and not dsn and not service:
        raise GatewayError(
            ORACLE_PROFILE_INVALID,
            "Production Oracle bağlantısı için SERVICE_NAME zorunludur.",
            status=400,
        )
    if service.upper() == "CDB$ROOT" or str(ds.get("container_name") or "").upper() == "CDB$ROOT":
        raise GatewayError(
            ORACLE_PROFILE_INVALID,
            "CDB$ROOT bağlantısına izin verilmez.",
            status=400,
        )

    owners_raw = ds.get("allowed_owners") or ds.get("allowedOwners")
    if owners_raw is None:
        # Infer from allowed_tables schemas / default reporting owner
        tables = ds.get("allowed_tables") or []
        inferred: list[str] = []
        if isinstance(tables, (list, set)):
            for t in tables:
                if isinstance(t, str) and "." in t:
                    inferred.append(t.split(".", 1)[0].upper())
        owners_raw = sorted(set(inferred)) or ["NANOBASE_REPORTING"]

    return OracleConnectionProfile(
        datasource_id=str(ds.get("id") or ""),
        user=user,
        password=str(ds.get("password") or ""),
        host=str(ds.get("host") or ""),
        port=int(ds.get("port") or 1521),
        service_name=service,
        dsn=dsn,
        connection_mode=mode,
        ssl_mode=str(ds.get("ssl_mode") or ds.get("sslMode") or ds.get("sslmode") or "REQUIRE").upper(),
        wallet_secret_ref=ds.get("wallet_secret_ref") or ds.get("walletSecretRef"),
        allow_sid=allow_sid,
        sid=str(sid) if sid else None,
        allowed_owners=validate_allowed_owners(list(owners_raw) if owners_raw else None),
        size_profile=str(ds.get("size_profile") or "medium"),
        plan_user=ds.get("plan_user") or ds.get("planUser"),
        plan_password=ds.get("plan_password") or ds.get("planPassword"),
        metadata_user=ds.get("metadata_user") or ds.get("metadataUser"),
        metadata_password=ds.get("metadata_password") or ds.get("metadataPassword"),
        container_name=ds.get("container_name") or ds.get("containerName"),
        database_unique_name=ds.get("database_unique_name") or ds.get("databaseUniqueName"),
        call_timeout_ms=int(ds.get("call_timeout_ms") or ds.get("callTimeoutMs") or 15_000),
    )
