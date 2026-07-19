#!/usr/bin/env bash
# Record image digests for Final Gate (build-once promotion).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
OUT="$ROOT/artifacts/final-release-gate/image-digests.txt"
mkdir -p "$(dirname "$OUT")"

{
  echo "# Nanobase image digests — generated $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "# Format: component=registry/name@sha256:..."
  echo "# pending-build until docker buildx / CI produces digests"
  echo "frontend=pending-build"
  echo "backend=pending-build"
  echo "queryGateway=pending-build"
  echo "dbgpt=pending-build"
  echo "modelHash=pin-before-freeze"
  echo "embeddingHash=pin-before-freeze"
  echo "llamaCppBuild=pin-before-freeze"
} >"$OUT"

# If local query_gateway image exists, capture digest
if command -v docker >/dev/null 2>&1; then
  if docker image inspect nanobase/query-gateway:local >/dev/null 2>&1; then
    DIGEST="$(docker image inspect nanobase/query-gateway:local --format '{{index .RepoDigests 0}}' 2>/dev/null || true)"
    ID="$(docker image inspect nanobase/query-gateway:local --format '{{.Id}}')"
    if [[ -n "${DIGEST:-}" && "$DIGEST" != "<no value>" ]]; then
      sed -i.bak "s|^queryGateway=.*|queryGateway=${DIGEST}|" "$OUT" 2>/dev/null \
        || sed -i '' "s|^queryGateway=.*|queryGateway=${DIGEST}|" "$OUT"
    else
      sed -i.bak "s|^queryGateway=.*|queryGateway=nanobase/query-gateway:local@${ID}|" "$OUT" 2>/dev/null \
        || sed -i '' "s|^queryGateway=.*|queryGateway=nanobase/query-gateway:local@${ID}|" "$OUT"
    fi
    rm -f "$OUT.bak"
  fi
fi

echo "Wrote $OUT"
cat "$OUT"
