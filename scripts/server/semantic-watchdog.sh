#!/usr/bin/env bash
# Watchdog for the Semantic Bridge: proves the service can still answer, not just that the port is open.
# A bridge that is up but serving an empty catalog, or that lost its database connection, is production
# down — the check therefore looks at the catalog and at a real question, and restarts once before alerting.
set -uo pipefail
PORT="${SEMANTIC_BRIDGE_PORT:-8795}"
UNIT="${SEMANTIC_UNIT:-nanobase-semantic-bridge.service}"
STATE="${SEMANTIC_WATCHDOG_STATE:-/run/nanobase-semantic/watchdog.state}"
LOG_TAG="semantic-watchdog"

log() { logger -t "$LOG_TAG" -- "$*"; printf '[%s] %s\n' "$LOG_TAG" "$*"; }
# M48: sonucu Sistem durumu'nun iş tablosuna da yaz (bildirim yolu; düşerse bekçi etkilenmez). Metin JSON'a python ile
# kaçırılır; köprü kapalıysa zaten yazılamaz — o durumda iş satırı eskir ve ekranda görünür.
report() {
  local ok="$1" detail="$2" body
  body="$(OK="$ok" DETAIL="$detail" python3 -c 'import json,os; print(json.dumps({"job": "kopru-saglik", "label": "Sorgu motoru sağlık denetimi", "ok": os.environ["OK"] == "true", "detail": os.environ["DETAIL"][:500], "every": "5 dk", "source": "watchdog"}))' 2>/dev/null)" || return 0
  curl -fsS -m 10 -o /dev/null -X POST -H 'Content-Type: application/json' -H "X-Semantic-Caller: ${SEMANTIC_CALLER_TOKEN:-}" \
    -d "$body" "http://127.0.0.1:${PORT}/api/v1/it-ops/watchdog" 2>/dev/null || true
}
fail() {
  # How long has it been since this bridge last answered? A single failed check is noise; hours of
  # them is an outage nobody noticed, and that difference belongs in the alert line.
  local since=""
  if [[ -r "$STATE" ]]; then
    local last now
    last="$(cat "$STATE" 2>/dev/null || echo 0)"
    now="$(date +%s)"
    [[ "${last:-0}" -gt 0 ]] && since=" (son sağlıklı yanıt $(( (now - last) / 60 )) dk önce)"
  fi
  log "UNHEALTHY: $*${since}"
  report false "$*${since}"
  exit 1
}

health="$(curl -fsS -m 10 "http://127.0.0.1:${PORT}/health" 2>/dev/null || true)"
[[ -n "$health" ]] || { log "no answer on :${PORT} — restarting ${UNIT}"; sudo systemctl restart "$UNIT"; sleep 5; health="$(curl -fsS -m 15 "http://127.0.0.1:${PORT}/health" || true)"; }
[[ -n "$health" ]] || fail "service does not answer after a restart"

# Açılış arkada sürer (semantic_bridge/boot.py): süreç hemen cevap verir, katalog birkaç on saniye içinde yüklenir.
# O sürede profil sayısı henüz yoktur; bu bir arıza değildir. Hazırlık SEMANTIC_WATCHDOG_WARM_MAX_SEC'i aşarsa arızadır.
warming="$(printf '%s' "$health" | python3 -c 'import json,sys; d=json.load(sys.stdin); b=d.get("boot") or {}; print("%s %d" % ("0" if d.get("ready", True) else "1", int(float(b.get("uptimeSec") or 0))))' 2>/dev/null || echo "0 0")"
if [[ "${warming%% *}" == "1" ]]; then
  up="${warming##* }"
  if (( up < ${SEMANTIC_WATCHDOG_WARM_MAX_SEC:-900} )); then
    log "bridge is starting (${up}s) — check skipped this round"
    exit 0
  fi
  fail "bridge has been preparing for ${up}s — catalog load does not finish"
fi

certified="$(printf '%s' "$health" | python3 -c 'import json,sys; print((json.load(sys.stdin).get("catalog") or {}).get("CERTIFIED", 0))' 2>/dev/null || echo 0)"
profiles="$(printf '%s' "$health" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("profiles", 0))' 2>/dev/null || echo 0)"
[[ "${profiles:-0}" -gt 0 ]] || fail "no schema profiles — the pipeline has never completed"
[[ "${certified:-0}" -gt 0 ]] || fail "catalog holds no certified concept — answers would fall back to the model for everything"

# One real question end to end. Deterministic answers cost nothing; this is the actual product promise.
ask="$(curl -fsS -m 60 -H 'Content-Type: application/json' \
  -d "{\"question\":\"${SEMANTIC_WATCHDOG_QUESTION:-2026 toplam net ciro nedir?}\",\"sampleSize\":1}" \
  "http://127.0.0.1:${PORT}/api/v1/ask" 2>/dev/null || true)"
# An unreachable data source is an outage, but not this service's: restarting the bridge would not
# bring the database back, and reporting it as a bridge fault sends whoever reads this to the wrong
# machine. Say which one is down.
if printf '%s' "$ask" | grep -q '"type": *"DATA_SOURCE_UNAVAILABLE"'; then
  fail "the data source is unreachable — the bridge is healthy, the database it reads is not"
fi
printf '%s' "$ask" | grep -q '"type": *"TEXT_TO_SQL"' || fail "the bridge could not answer a catalog question: $(printf '%s' "$ask" | head -c 200)"

log "healthy: ${profiles} profiles, ${certified} certified concepts"
report true "sağlıklı: ${profiles} tablo profili, ${certified} sertifikalı terim"
mkdir -p "$(dirname "$STATE")" 2>/dev/null || true
if ! date +%s > "$STATE" 2>/dev/null; then
  log "warning: cannot record health state at $STATE — an outage's duration will not be reported"
fi
