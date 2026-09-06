"""NanobaseAI shim for the WrenAI venv (installed as <venv>/lib/python3.x/site-packages/sitecustomize.py).

wrenai 0.13.4 `wren.connector.mssql._escape_odbc_value` wraps EVERY ODBC attribute value in braces
(`TDS_Version={7.4}`, `ClientCharset={UTF-8}`). Microsoft's driver tolerates that; FreeTDS does not and
fails SQLDriverConnect with "HY001 Memory allocation failure". The ODBC rule is to brace only values that
need it (contain ';', '{', '}' or leading/trailing whitespace). Applied at interpreter start so the CLI,
`wren serve mcp` and backend/wren_bridge all use the same connector behaviour. Remove once upstream fixes it.
"""

from __future__ import annotations


def _escape_odbc_value_minimal(value: str) -> str:
    v = str(value)
    if v.startswith("{") or any(ch in v for ch in ";{}") or v != v.strip():
        return "{" + v.replace("}", "}}") + "}"
    return v


def _patch() -> None:
    try:
        import wren.connector.mssql as m  # noqa: PLC0415
    except Exception:  # noqa: BLE001 — wren not importable (pip, other tools): nothing to do
        return
    if getattr(m, "_escape_odbc_value", None) is not _escape_odbc_value_minimal:
        m._escape_odbc_value = _escape_odbc_value_minimal  # noqa: SLF001
        m._NANOBASEAI_ODBC_SHIM = True  # noqa: SLF001


_patch()
