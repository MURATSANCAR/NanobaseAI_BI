#!/usr/bin/env bash
# Faz 7 governance verification — unit + contract + 300/150 suites + perf/chaos/soak
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND="$ROOT/backend"
ART="$ROOT/artifacts/phase-7"
mkdir -p "$ART"
cd "$BACKEND"
export PYTHONPATH=.
export SEMANTIC_CATALOG_BACKEND=memory
PY="${BACKEND}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then PY=python3; fi

echo "== semantic_catalog pytest =="
"$PY" -m pytest nanobase_api/semantic_catalog/tests -q --tb=line \
  --junitxml="$ART/unit-tests.xml" | tee "$ART/pytest-stdout.txt"

echo "== compiler determinism =="
ROOT="$ROOT" "$PY" <<'PY'
import json, os
from pathlib import Path
from nanobase_api.semantic_catalog.infrastructure.catalog_store import reset_catalog_store
from nanobase_api.semantic_catalog.application.seed_unpaid_slice import seed_unpaid_invoice_slice
from nanobase_api.semantic_catalog.infrastructure.metric_compiler import MetricCompiler, CompileRequest

store = reset_catalog_store()
ids = seed_unpaid_invoice_slice(store, published=True)
metric = store.metrics[ids["metric_id"]]
filt = store.filters[ids["filter_id"]]
c = MetricCompiler()
req = CompileRequest(metric=metric, filters=[filt])
base = c.compile(req).ast_fingerprint
ok = all(c.compile(req).ast_fingerprint == base for _ in range(1000))
sql = c.compile(req).sql
out = {
    "deterministic": ok,
    "astFingerprint": base,
    "mandatoryFilterApplied": "NOT IN" in sql and "CANCELLED" in sql,
    "sqlPreview": sql[:500],
}
path = Path(os.environ["ROOT"]) / "artifacts/phase-7/compiler-determinism.json"
path.write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
assert ok and out["mandatoryFilterApplied"]
PY

echo "== benchmark 300 + verified 150 + perf/chaos/soak =="
"$PY" -m nanobase_api.semantic_catalog.infrastructure.benchmark_runner \
  --out "$ART" \
  --soak-seconds "${SOAK_SECONDS:-5}"

echo "OK — artifacts in $ART"
"$PY" -c "import json; print(json.load(open('$ART/build-metadata.json'))['verdict'])"
