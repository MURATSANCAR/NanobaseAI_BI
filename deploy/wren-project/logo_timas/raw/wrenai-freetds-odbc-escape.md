# Upstream report — Canner/WrenAI (`core/wren`, wrenai 0.13.4)

Bu Mac'te GitHub kimliği yok; aşağıdaki iki kaydı sen açarsın. Yama: `wrenai-freetds-odbc-escape.patch`
(`git apply` ile `main` üzerine uygulanır; `core/wren/tests/unit/test_mssql_connection.py` 20/20 geçti — sunucu venv'inde koşuldu).

---

## Issue 1 — mssql: `_escape_odbc_value` braces every ODBC attribute; FreeTDS fails with HY001

**Title:** `mssql connector: unconditional `{}` quoting of ODBC values breaks FreeTDS (HY001 Memory allocation failure)`

**Environment:** wrenai 0.13.4 (`pip install 'wrenai[mssql]'`), Ubuntu 24.04, unixODBC 2.3.12, FreeTDS 1.3.17 (`tdsodbc`), SQL Server 2019.

**Repro**

```json
{"datasource":"mssql","host":"127.0.0.1","port":"14330","database":"LOGO_DB","user":"u","password":"p",
 "driver":"FreeTDS","tds_version":"7.4","kwargs":{"ClientCharset":"UTF-8"}}
```

```
$ wren query --mdl target/mdl.json --connection-file conn.json --sql 'SELECT TOP 1 "DATE_" FROM "dbo_LG_411_01_INVOICE"'
Error: ('HY001', '[HY001] [FreeTDS][SQL Server]Memory allocation failure (0) (SQLDriverConnect)')
```

The connector builds (`wren/connector/mssql.py::_connect_mssql_pyodbc`, `_escape_odbc_value` at L483):

```
DRIVER={FreeTDS};SERVER=127.0.0.1,14330;DATABASE={LOGO_DB};UID={u};PWD={p};TDS_Version={7.4};ClientCharset={UTF-8}
```

Passing the same string with `TDS_Version=7.4;ClientCharset=UTF-8` (no braces) to `pyodbc.connect` works. Microsoft's ODBC
Driver 18 strips braces on every attribute; FreeTDS only does so where it expects quoting (DRIVER/DATABASE/UID/PWD), so
`TDS_Version={7.4}` becomes an invalid version and `ClientCharset={UTF-8}` an unknown charset → HY001. Verified by
brute-force: braced DRIVER/DATABASE/UID/PWD are fine, braced TDS_Version or ClientCharset alone reproduce the failure.

**Fix (patch attached):** quote a value only when it needs it (contains `;`, `{`, `}`, or leading/trailing whitespace,
or starts with `{`), which is the ODBC rule and keeps both drivers working. Two unit tests added to
`tests/unit/test_mssql_connection.py` (`test_plain_values_are_not_braced`, `test_values_needing_quotes_are_braced`).

**Workaround until released:** a `.pth`-loaded shim that replaces `wren.connector.mssql._escape_odbc_value`
(we ship it as `tools/wren/sitecustomize.py`, installed as `nanobaseai_odbc_shim.pth`).

---

## Issue 2 — `wrenai[mcp]` extra resolves to `mcp` 2.x, `wren serve mcp` crashes at import

**Title:** `wren serve mcp: mcp>=2 (FastMCP renamed to mcpserve) breaks startup — pin mcp<2 in the [mcp] extra`

`core/wren/pyproject.toml` declares `mcp = ["mcp[cli]>=1.19"]`; a fresh install today pulls `mcp 2.x`, and
`wren serve mcp --transport http` exits with the migration notice
(`…/v2/migration/#fastmcp-renamed-to-mcpserve … or pin 'mcp<2' to keep running v1 code`). `pip install 'mcp<2'`
(1.29.1) fixes it: server starts, 17 tools listed, `run_sql` works over Streamable HTTP. Suggest `mcp[cli]>=1.19,<2`
until the server is ported to the v2 API.

---

## Issue 3 — `wren cube query` emits unsupported SQL for SQL Server (mssql)

**Title:** `cube query: DATE_TRUNC and outer-reference GROUP BY break cubes on mssql`

wrenai 0.13.4, `mssql` connector (FreeTDS/pyodbc), SQL Server 2019. Measure-only cube queries work:

```bash
$ wren cube query --cube sales_cube --measures net_ciro,satis,iade
    net_ciro        satis        iade
8.481102e+08 9.224187e+08 74308487.24     # matches raw SQL exactly
```

Adding a dimension or a time granularity fails at execution:

```bash
$ wren cube query --cube sales_cube --measures net_ciro --time-dimension fatura_tarihi:month
Error: [GENERIC_USER_ERROR] ('42000', "[42000] [FreeTDS][SQL Server]'DATE_TRUNC' is not a recognized
built-in function name. (195) (SQLExecDirectW)") phase=SQL_EXECUTION

$ wren cube query --cube sales_cube --measures net_ciro --dimensions trcode
Error: [GENERIC_USER_ERROR] ('42000', '[42000] [FreeTDS][SQL Server]Each GROUP BY expression must
contain at least one column that is not an outer reference. (164) (SQLExecDirectW)')
```

Expected: the cube query builder should translate the time granularity to a T-SQL expression
(`DATEFROMPARTS(YEAR(c), MONTH(c), 1)` for month, `CAST(c AS date)` for day, …) and emit dimension
expressions in `GROUP BY` directly rather than as outer references. Both are dialect-translation gaps,
not user errors: hand-written T-SQL with the same semantics runs fine through `wren query`.

Impact: cubes are unusable for any breakdown on SQL Server, which is the main reason to define one.
Workaround: MDL views with the grouping baked in (`v_monthly_sales`, `v_channel_net`).

---

## Issue 4 — Relationship columns are not expanded by the planner (mssql)

**Title:** `Relationship (join handle) columns are passed through verbatim instead of being expanded into joins`

wrenai 0.13.4 / wren-core-py 0.7.6, datasource `mssql`. MDL declares a relationship and a relationship column:

```yaml
# relationships.yml
- name: invoice_clcard
  models: [dbo_LG_411_01_INVOICE, dbo_LG_411_CLCARD]
  join_type: MANY_TO_ONE
  condition: '"dbo_LG_411_01_INVOICE".CLIENTREF = "dbo_LG_411_CLCARD".LOGICALREF'

# models/dbo_LG_411_01_INVOICE/metadata.yml
- name: cari
  type: dbo_LG_411_CLCARD
  relationship: invoice_clcard
```

`wren context build` keeps the column in `target/mdl.json`, but every documented navigation form fails:

| SQL | Result |
|---|---|
| `SELECT dbo_LG_411_01_INVOICE.cari.DEFINITION_ FROM dbo_LG_411_01_INVOICE` | `Schema error: No field named "dbo_LG_411_01_INVOICE".cari` (planning) |
| `SELECT cari.DEFINITION_ FROM dbo_LG_411_01_INVOICE` | passed through verbatim → SQL Server `The multi-part identifier "cari.DEFINITION_" could not be bound` |
| `SELECT i.cari.DEFINITION_ FROM dbo_LG_411_01_INVOICE i` | same planning error |

The MDL reference documents `orders.customer.first_name` as valid; here the planner's field list contains
only physical and calculated columns, never the relationship handles (this also affects handles that were
generated by the legacy wren-ui, not just hand-written ones).

Expected: the planner resolves the handle and injects the declared join. Impact: agents must hand-write
every JOIN, which is exactly what the semantic layer is supposed to remove.
