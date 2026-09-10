#!/usr/bin/env bash
# The three steps left after the prompt budget went live, in the order they depend on each other.
#
#   1. name the tables the vendor's documents never named  — routing matches on table text
#   2. rebuild the vector index                            — the one in Qdrant predates the naming
#   3. turn the router on                                  — only worth doing once 1 and 2 are true
#
# Each step is reversible and none of them touches what a person wrote in the portal. Step 3 is the
# only one that changes what the model sees at question time; `--no-router` stops before it.
#
#   ssh nanobase-direct
#   cd /data/nanobaseai/bi/frontend && ./scripts/server/finish-semantic-routing.sh
set -euo pipefail

ROOT=/data/nanobaseai/bi/frontend
VENV=/data/nanobaseai/bi/semantic-venv/bin/python
ENVF=/etc/nanobase/semantic-bridge.env
BRIDGE=http://127.0.0.1:8795
WITH_ROUTER=1
[[ "${1:-}" == "--no-router" ]] && WITH_ROUTER=0

log() { printf '\n[%s] %s\n' "$(date +%H:%M:%S)" "$*"; }

cd "$ROOT/backend"
set -a; sudo cat "$ENVF" > /tmp/semantic.env; . /tmp/semantic.env; set +a
export PYTHONPATH=.
export QDRANT_URL="${QDRANT_URL:-http://127.0.0.1:6333}"
export BI_EMBED_URL="${BI_EMBED_URL:-http://172.17.0.1:8021/v1/embeddings}"
export BI_EMBED_API_KEY="${BI_EMBED_API_KEY:-$(sudo cat /data/nanobaseai/bi/secrets/embed-api.key | tr -d '\n')}"
export SEMANTIC_ROUTER_COLLECTION="${SEMANTIC_ROUTER_COLLECTION:-semantic_catalog_logo}"
export BI_EMBED_BATCH="${BI_EMBED_BATCH:-64}"

log "0/3 katalog yedeği"
D=$(echo "${SEMANTIC_STORE_DSN:-$NANOBASE_META_DSN}" | sed 's#postgresql+psycopg2://#postgresql://#;s#postgresql+psycopg://#postgresql://#')
pg_dump "$D" -t sl_schema_profile -f "/data/nanobaseai/bi/backups/sl_profiles-$(date +%Y%m%d-%H%M%S).sql"

log "1/3 belgesiz tabloları adlandır"
"$VENV" scripts/describe_undocumented_tables.py --apply

log "2/3 vektör indeksini yeniden kur"
# The embedder is on the GPU host, reached through a tunnel that is not always up.
sudo systemctl start a40-embed-tunnel.service || true
sleep 3
"$VENV" scripts/index_catalog_qdrant.py --dictionary

log "3/3 köprüyü tazele"
if [[ $WITH_ROUTER -eq 1 ]]; then
  for kv in "QDRANT_URL=$QDRANT_URL" "BI_EMBED_URL=$BI_EMBED_URL" \
            "SEMANTIC_ROUTER_COLLECTION=$SEMANTIC_ROUTER_COLLECTION" "BI_EMBED_API_KEY=$BI_EMBED_API_KEY"; do
    k=${kv%%=*}
    sudo grep -q "^$k=" "$ENVF" || echo "$kv" | sudo tee -a "$ENVF" >/dev/null
  done
  sudo systemctl restart nanobase-semantic-bridge.service
  sleep 8
  echo "router açık — kapatmak için: $ENVF içinden QDRANT_URL satırını silip servisi yeniden başlatın"
else
  curl -s -X POST "$BRIDGE/api/v1/semantic/reload" >/dev/null
  echo "router kapalı bırakıldı"
fi

log "durum"
systemctl is-active nanobase-semantic-bridge.service
curl -s -m 20 "$BRIDGE/health" | head -c 220; echo
