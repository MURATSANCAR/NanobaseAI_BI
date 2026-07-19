#!/usr/bin/env bash
# Final Production Release Gate — local vertical slice entrypoint.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
RELEASE="${1:-1.0.0-rc.1}"
CONNECTORS="${2:-postgres}"
cd "$ROOT"
exec python3 tools/release-gate/run_vertical_slice.py \
  --release "$RELEASE" \
  --claimed-connectors "$CONNECTORS" \
  --freeze
