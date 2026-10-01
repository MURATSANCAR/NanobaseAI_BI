#!/usr/bin/env bash
# Run on the build server; the chat workspace has its own Yarn dependencies.
set -euo pipefail
BI_SOURCE_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
export REPO="$BI_SOURCE_ROOT/apps/zeki-chat"
exec bash "$REPO/deploy/zeki/build.sh" "$@"
