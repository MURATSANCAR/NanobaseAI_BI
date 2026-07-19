"""Oracle private synonym resolution with allowlist / cycle / db-link checks."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from query_gateway.domain.errors import GatewayError

ORACLE_SYNONYM_REJECTED = "ORACLE_SYNONYM_REJECTED"

ALLOWED_TARGET_TYPES = frozenset({"TABLE", "VIEW", "MATERIALIZED VIEW"})


@dataclass
class SynonymResolution:
    owner: str
    synonym_name: str
    resolved_owner: str
    resolved_object: str
    resolved_type: str
    chain: list[str]


FetchSynonym = Callable[[str, str], dict[str, Any] | None]
FetchObjectType = Callable[[str, str], str | None]


def resolve_synonym(
    owner: str,
    synonym_name: str,
    *,
    allowed_owners: set[str],
    allow_public: bool = False,
    fetch_synonym: FetchSynonym,
    fetch_object_type: FetchObjectType,
    max_depth: int = 8,
) -> SynonymResolution:
    owner_u = owner.upper()
    name_u = synonym_name.upper()
    allowed = {o.upper() for o in allowed_owners}

    if owner_u == "PUBLIC" and not allow_public:
        raise GatewayError(
            ORACLE_SYNONYM_REJECTED,
            "Public synonym varsayılan olarak reddedilir.",
            status=400,
        )
    if owner_u not in allowed and owner_u != "PUBLIC":
        raise GatewayError(
            ORACLE_SYNONYM_REJECTED,
            "Synonym owner allowlist dışında.",
            status=400,
        )

    chain: list[str] = []
    cur_owner, cur_name = owner_u, name_u
    for _ in range(max_depth):
        key = f"{cur_owner}.{cur_name}"
        if key in chain:
            raise GatewayError(
                ORACLE_SYNONYM_REJECTED,
                "Circular synonym reddedildi.",
                status=400,
            )
        chain.append(key)
        row = fetch_synonym(cur_owner, cur_name)
        if row is None:
            # Maybe already a real object
            otype = fetch_object_type(cur_owner, cur_name)
            if otype and otype.upper() in ALLOWED_TARGET_TYPES:
                if cur_owner not in allowed:
                    raise GatewayError(
                        ORACLE_SYNONYM_REJECTED,
                        "Hedef owner allowlist dışında.",
                        status=400,
                    )
                return SynonymResolution(
                    owner=owner_u,
                    synonym_name=name_u,
                    resolved_owner=cur_owner,
                    resolved_object=cur_name,
                    resolved_type=otype.upper(),
                    chain=chain,
                )
            raise GatewayError(
                ORACLE_SYNONYM_REJECTED,
                "Synonym çözülemedi.",
                status=400,
            )

        db_link = (row.get("db_link") or row.get("DB_LINK") or "").strip()
        if db_link:
            raise GatewayError(
                ORACLE_SYNONYM_REJECTED,
                "Database link içeren synonym reddedildi.",
                status=400,
            )
        table_owner = str(row.get("table_owner") or row.get("TABLE_OWNER") or "").upper()
        table_name = str(row.get("table_name") or row.get("TABLE_NAME") or "").upper()
        if not table_owner or not table_name:
            raise GatewayError(ORACLE_SYNONYM_REJECTED, "Synonym hedefi boş.", status=400)
        if table_owner not in allowed:
            raise GatewayError(
                ORACLE_SYNONYM_REJECTED,
                "Hedef owner allowlist dışında.",
                status=400,
            )
        otype = fetch_object_type(table_owner, table_name)
        if otype and otype.upper() in ALLOWED_TARGET_TYPES:
            return SynonymResolution(
                owner=owner_u,
                synonym_name=name_u,
                resolved_owner=table_owner,
                resolved_object=table_name,
                resolved_type=otype.upper(),
                chain=chain,
            )
        # Follow synonym chain
        cur_owner, cur_name = table_owner, table_name

    raise GatewayError(
        ORACLE_SYNONYM_REJECTED,
        "Synonym zinciri çok uzun.",
        status=400,
    )
