"""Oracle Thin Mode adapter for hardened Query Gateway path."""

from query_gateway.infrastructure.oracle.executor import execute_oracle_ro
from query_gateway.infrastructure.oracle.profile import (
    FORBIDDEN_ORACLE_USERS,
    OracleConnectionProfile,
    build_profile_from_datasource,
    validate_oracle_username,
)

__all__ = [
    "FORBIDDEN_ORACLE_USERS",
    "OracleConnectionProfile",
    "build_profile_from_datasource",
    "execute_oracle_ro",
    "validate_oracle_username",
]
