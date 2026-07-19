"""HANA SQL policy unit tests."""

from __future__ import annotations

import pytest

from query_gateway.domain.errors import GatewayError
from query_gateway.infrastructure.sap.hana.parser_policy import enforce_hana_sql_policy
from query_gateway.infrastructure.sap.hana.profile import validate_hana_username


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO NANOBASE_REPORTING.CV_FINANCE VALUES (1)",
        "UPDATE NANOBASE_REPORTING.CV_FINANCE SET X=1",
        "DELETE FROM NANOBASE_REPORTING.CV_FINANCE",
        "CALL MY_PROC()",
        "DO BEGIN SELECT 1; END;",
        "SELECT * FROM ACDOCA",
        "SELECT * FROM SYS.TABLES",
        "CREATE TABLE EVIL (ID INT)",
        "DROP VIEW NANOBASE_REPORTING.CV_FINANCE",
    ],
)
def test_forbidden_sql(sql: str):
    with pytest.raises(GatewayError):
        enforce_hana_sql_policy(sql)


def test_select_ok():
    warnings = enforce_hana_sql_policy(
        "SELECT COMPANY_CODE, OPEN_AMOUNT FROM NANOBASE_REPORTING.CV_OPEN_RECEIVABLE LIMIT 100"
    )
    assert isinstance(warnings, list)


def test_forbid_system_user():
    with pytest.raises(GatewayError):
        validate_hana_username("SYSTEM")
