#!/usr/bin/env bash
# Watchdog for the Semantic Bridge: proves the service can still answer, not just that the port is open.
# A bridge that is up but serving an empty catalog, or that lost its database connection, is production
# down — the check therefore looks at the catalog and at a real question, and restarts once before alerting.
set -uo pipefail
PORT="${SEMANTIC_BRIDGE_PORT:-8795}"
UNIT="${SEMANTIC_UNIT:-nanobase-semantic-bridge.service}"
STATE="${SEMANTIC_WATCHDOG_STATE:-/run/semantic-watchdog.state}"
LOG_TAG="semantic-watchdog"

log() { logger -t "$LOG_TAG" -- "$*"; printf '[%s] %s\n' "$LOG_TAG" "$*"; }
fail() { log "UNHEALTHY: $*"; exit 1; }

health="$(curl -fsS -m 10 "http://127.0.0.1:${PORT}/health" 2>/dev/null || true)"
[[ -n "$health" ]] || { log "no answer on :${PORT} — restarting ${UNIT}"; sudo systemctl restart "$UNIT"; sleep 5; health="$(curl -fsS -m 15 "http://127.0.0.1:${PORT}/health" || true)"; }
[[ -n "$health" ]] || fail "service does not answer after a restart"

certified="$(printf '%s' "$health" | python3 -c 'import json,sys; print((json.load(sys.stdin).get("catalog") or {}).get("CERTIFIED", 0))' 2>/dev/null || echo 0)"
profiles="$(printf '%s' "$health" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("profiles", 0))' 2>/dev/null || echo 0)"
[[ "${profiles:-0}" -gt 0 ]] || fail "no schema profiles — the pipeline has never completed"
[[ "${certified:-0}" -gt 0 ]] || fail "catalog holds no certified concept — answers would fall back to the model for everything"

# One real question end to end. Deterministic answers cost nothing; this is the actual product promise.
ask="$(curl -fsS -m 60 -H 'Content-Type: application/json' \
  -d "{\"question\":\"${SEMANTIC_WATCHDOG_QUESTION:-2026 toplam net ciro nedir?}\",\"sampleSize\":1}" \
  "http://127.0.0.1:${PORT}/api/v1/ask" 2>/dev/null || true)"
printf '%s' "$ask" | grep -q '"type": *"TEXT_TO_SQL"' || fail "the bridge could not answer a catalog question: $(printf '%s' "$ask" | head -c 200)"

log "healthy: ${profiles} profiles, ${certified} certified concepts"
date +%s > "$STATE" 2>/dev/null || true
