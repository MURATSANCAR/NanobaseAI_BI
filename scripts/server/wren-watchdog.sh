#!/usr/bin/env bash
# WrenAI hattı sağlık bekçisi (2 dk'da bir timer): sağlıksız servisi yeniden başlatır, durumu loglar.
# Uyarı kanalı: WREN_ALERT_WEBHOOK (Slack/Teams uyumlu JSON) tanımlıysa oraya da yazar.
set -uo pipefail
LOG="${WREN_WATCHDOG_LOG:-/data/logs/wren-watchdog.log}"
STATE="${WREN_WATCHDOG_STATE:-/data/logs/wren-watchdog.state}"
WEBHOOK="${WREN_ALERT_WEBHOOK:-}"
export SYSTEMD_BUS_TIMEOUT=120
mkdir -p "$(dirname "$LOG")"
log() { printf '%s %s\n' "$(date -Is)" "$*" >> "$LOG"; }
alert() {
  log "ALERT $*"
  [[ -n "$WEBHOOK" ]] && curl -s -m 8 -X POST "$WEBHOOK" -H 'Content-Type: application/json' -d "{\"text\":\"[nanobase wren] $*\"}" >/dev/null 2>&1 || true
}
fail=0; report=()
check() {  # check <ad> <unit> <test-komutu...>
  local name="$1" unit="$2"; shift 2
  if "$@" >/dev/null 2>&1; then report+=("$name:ok"); return 0; fi
  fail=$((fail+1)); report+=("$name:FAIL")
  alert "$name sağlıksız → $unit yeniden başlatılıyor"
  sudo -n systemctl restart "$unit" 2>/dev/null || true
}
mcp_ok() { curl -s -m 8 -X POST http://127.0.0.1:8090/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"watchdog","version":"0"}}}' | grep -q '"serverInfo"'; }
bridge_ok() { curl -fsS -m 8 http://127.0.0.1:8794/health | grep -q '"status":"ok"'; }
bridge_query_ok() { curl -fsS -m 30 -X POST http://127.0.0.1:8794/api/v1/run_sql -H 'Content-Type: application/json' -d '{"sql":"SELECT COUNT(*) AS n FROM \"dbo_LG_411_01_INVOICE\"","limit":1}' | grep -q '"n"'; }
forecast_ok() { curl -fsS -m 8 http://127.0.0.1:8793/health | grep -q '"ready":true'; }
watch_ok() { systemctl is-active --quiet nanobase-wren-memory-watch; }
nginx_ok() { [[ "$(curl -s -o /dev/null -w '%{http_code}' -m 10 https://portal.nanobase.ai/timas/)" == "401" ]]; }
tunnel_ok() { ss -ltn 2>/dev/null | grep -q '127.0.0.1:14330'; }

check bridge         nanobase-wren-bridge        bridge_ok
check bridge-query   nanobase-wren-bridge        bridge_query_ok
check mcp            nanobase-wren-mcp           mcp_ok
check forecast       nanobase-forecast           forecast_ok
check memory-watch   nanobase-wren-memory-watch  watch_ok
if ! nginx_ok; then fail=$((fail+1)); report+=("nginx-timas:FAIL"); alert "portal /timas 401 dönmüyor (nginx/auth)"; else report+=("nginx-timas:ok"); fi
if ! tunnel_ok; then fail=$((fail+1)); report+=("logo-tunnel:FAIL"); alert "Logo tüneli (127.0.0.1:14330) kapalı — veritabanı erişilemez"; else report+=("logo-tunnel:ok"); fi

printf '%s fail=%d %s\n' "$(date -Is)" "$fail" "${report[*]}" > "$STATE"
[[ $fail -eq 0 ]] && log "ok ${report[*]}" || log "fail=$fail ${report[*]}"
exit 0
