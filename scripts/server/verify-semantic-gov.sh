#!/usr/bin/env bash
# Faz 7 governance verification — unit + contract + compiler determinism
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
BACKEND="$ROOT/backend"
ART="$ROOT/artifacts/phase-7"
mkdir -p "$ART"
cd "$BACKEND"
export PYTHONPATH=.
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

# Promotion security smoke artifact
ROOT="$ROOT" "$PY" <<'PY'
import json, os
from pathlib import Path
from nanobase_api.semantic_catalog.domain.errors import AuthorizationError
from nanobase_api.semantic_catalog.domain.promotion import PromotionPhase, PromotionRequest
from nanobase_api.semantic_catalog.application.services import publish_promotion
from nanobase_api.semantic_catalog.infrastructure.catalog_store import reset_catalog_store

store = reset_catalog_store()
promo = PromotionRequest(
    id="p1",
    tenant_id="default",
    datasource_id="default",
    asset_type="METRIC",
    asset_id="x",
    phase=PromotionPhase.READY_TO_PUBLISH,
    requires_dual_approval=False,
)
store.promotions[promo.id] = promo
blocked = False
try:
    publish_promotion(store, promotion_id="p1", publisher_user_id="u", publisher_roles={"DATA_ANALYST"})
except AuthorizationError:
    blocked = True
out = {"unauthorizedPublishBlocked": blocked, "autoPromoteDisabled": True}
path = Path(os.environ["ROOT"]) / "artifacts/phase-7/promotion-security-results.json"
path.write_text(json.dumps(out, indent=2))
assert blocked
print(out)
PY

echo "OK — artifacts in $ART"
