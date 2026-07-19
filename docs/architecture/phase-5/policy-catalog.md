# Policy catalog

YAML under `backend/query_gateway/config/policies/`:

- `postgres-functions.yaml` — allowed / controlled / denied
- `postgres-statements.yaml` — forbidden AST node types
- `default-limits.yaml` — rows, timeouts, joins, wildcard flag

Datasource allowlists + `column_policies` come from secrets JSON / built-in `bi_reporting` registry.
