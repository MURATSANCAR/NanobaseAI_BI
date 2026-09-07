#!/usr/bin/env bash
# Build the semantic catalog on this machine, from the knowledge pack — no customer database.
#
# The pack under configs/semantic/knowledge/<source> carries an exported profile of the source
# (models/*/metadata.yml) and the documentation written about it, so the whole pipeline — profile,
# mine, certify — runs offline. That is what makes this safe to run here: it reads files in this
# repository and nothing else. Pointing it at a live source is a separate, deliberate act
# (SEMANTIC_CONNECTION_FILE), not something this script does.
#
#   ./scripts/build-semantic-catalog.sh            # the logo pack
#   ./scripts/build-semantic-catalog.sh sigorta    # another pack under configs/semantic/knowledge
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PACK="${1:-logo}"
[[ $# -gt 0 ]] && shift    # anything after the pack name is passed through to `pipeline`
KNOWLEDGE="$ROOT/../configs/semantic/knowledge/$PACK"
if [[ ! -d "$KNOWLEDGE/knowledge" ]]; then
  echo "error: no knowledge pack at $KNOWLEDGE" >&2
  exit 1
fi

PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "error: no venv — run ./scripts/setup.sh --semantic-only first" >&2
  exit 1
fi

mkdir -p "$ROOT/var"
export SEMANTIC_STORE_DSN="${SEMANTIC_STORE_DSN:-sqlite:///$ROOT/var/semantic_layer.db}"
export SEMANTIC_KNOWLEDGE_DIR="$KNOWLEDGE"
export SEMANTIC_DATASOURCE_ID="${SEMANTIC_DATASOURCE_ID:-$PACK}"

echo "pack:  $SEMANTIC_KNOWLEDGE_DIR"
echo "store: $SEMANTIC_STORE_DSN"
echo
"$PY" -m semantic_layer.cli init-db
"$PY" -m semantic_layer.cli pipeline "$@"
echo
"$PY" -m semantic_layer.cli status
