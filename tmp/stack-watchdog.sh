#!/usr/bin/env bash
# NanobaseAI stack watchdog — restart stopped services, recover failed HTTP endpoints.
# Run via systemd timer every 2 min + @reboot cron. Safe to run repeatedly.
set -euo pipefail

MOBILE_QA="${MOBILE_QA:-/opt/nanobaseai/mobile-qa}"
MANIFEST="${STACK_MANIFEST:-$MOBILE_QA/configs/nanobase-stack-services.json}"
LOG="${STACK_WATCHDOG_LOG:-/data/logs/stack-watchdog.log}"
CLEANUP_SCRIPT="${CLEANUP_SCRIPT:-$MOBILE_QA/scripts/server/cleanup-stale-processes.sh}"
BI_API_ENV="${BI_API_ENV:-/data/nanobaseai/bi/frontend/backend/nanobase_api.env}"
ARCTIC_DISABLE_FLAG="${ARCTIC_DISABLE_FLAG:-/etc/nanobaseai/flags/arctic-text2sql.disabled}"

mkdir -p "$(dirname "$LOG")" /data/logs

log() {
  printf '%s %s\n' "$(date -Is 2>/dev/null || date)" "$*" | tee -a "$LOG"
}

unit_exists() {
  systemctl list-unit-files "$1" &>/dev/null
}

unit_active() {
  systemctl is-active --quiet "$1" 2>/dev/null
}

unit_enabled() {
  systemctl is-enabled --quiet "$1" 2>/dev/null
}

# True when host redis should stay off (Docker already binds :6379).
docker_owns_6379() {
  if command -v ss >/dev/null 2>&1; then
    ss -ltnp 2>/dev/null | grep -E ':6379\b' | grep -qi docker && return 0
  fi
  if command -v docker >/dev/null 2>&1; then
    docker ps --format '{{.Ports}}' 2>/dev/null | grep -qE '0\.0\.0\.0:6379|->6379' && return 0
  fi
  # Preserve prior behavior when ownership cannot be determined: keep host unit off.
  return 0
}

text2sql_prefer_is_chat() {
  local prefer=""
  if [[ -f "$BI_API_ENV" ]]; then
    prefer="$(grep -E '^TEXT2SQL_PREFER=' "$BI_API_ENV" 2>/dev/null | tail -1 | cut -d= -f2- | tr -d '\"\r' | tr '[:upper:]' '[:lower:]')"
  fi
  [[ -z "$prefer" ]] && prefer="chat"
  [[ "$prefer" == "chat" || "$prefer" == "qwen" ]]
}

arctic_force_disabled() {
  [[ -f "$ARCTIC_DISABLE_FLAG" ]]
}

# Return 0 if unit should stay disabled for this conditional token.
conditional_should_disable() {
  local cond="${1:-}"
  [[ -z "$cond" ]] && return 1
  case "$cond" in
    docker_owns_6379)
      docker_owns_6379
      ;;
    text2sql_prefer_chat|prefer_chat|off_when_text2sql_prefer_chat)
      text2sql_prefer_is_chat || arctic_force_disabled
      ;;
    always|off|true|1)
      return 0
      ;;
    *)
      # Unknown tokens keep historical "any non-empty => disable" behavior.
      return 0
      ;;
  esac
}

ensure_unit_enabled() {
  local unit="$1"
  unit_exists "$unit" || return 0
  if ! unit_enabled "$unit"; then
    log "ENABLE $unit"
    systemctl enable "$unit" 2>/dev/null || true
  fi
}

disable_unit() {
  local unit="$1"
  unit_exists "$unit" || return 0
  if unit_enabled "$unit" || unit_active "$unit"; then
    log "DISABLE $unit (conditional off)"
    systemctl stop "$unit" 2>/dev/null || true
    systemctl disable "$unit" 2>/dev/null || true
  fi
}

restart_unit() {
  local unit="$1"
  unit_exists "$unit" || return 1
  # Never fight an intentionally disabled/masked unit.
  if ! unit_enabled "$unit"; then
    local state
    state="$(systemctl is-enabled "$unit" 2>/dev/null || true)"
    log "SKIP restart $unit (is-enabled=$state)"
    return 1
  fi
  log "RESTART $unit"
  systemctl restart "$unit" 2>/dev/null || systemctl start "$unit" 2>/dev/null || true
  sleep 2
}

ensure_systemd_unit() {
  local unit="$1"
  local required="${2:-false}"
  local conditional="${3:-}"

  unit_exists "$unit" || {
    [ "$required" = "true" ] && log "MISSING required unit $unit"
    return 0
  }

  # Hard ops override for Arctic regardless of manifest token.
  if [[ "$unit" == "nanobase-arctic-text2sql.service" ]] && arctic_force_disabled; then
    disable_unit "$unit"
    return 0
  fi

  if [ -n "$conditional" ] && conditional_should_disable "$conditional"; then
    disable_unit "$unit"
    return 0
  fi

  ensure_unit_enabled "$unit"
  if ! unit_active "$unit"; then
    log "RECOVER inactive $unit"
    restart_unit "$unit"
  fi
}

http_ok() {
  # Default 15s: analysis overview can briefly saturate a single uvicorn worker;
  # short timeouts caused false UNHEALTHY → restart loops during heavy reads.
  local url="$1" timeout="${2:-15}"
  curl -sf --connect-timeout "$timeout" --max-time "$((timeout + 2))" "$url" >/dev/null 2>&1
}

ensure_http() {
  local url="$1" unit="$2" timeout="${3:-8}" required="${4:-false}" fallback="${5:-}"

  if http_ok "$url" "$timeout"; then
    if [[ "$url" == *":8787/health"* ]]; then
      local redis_ok
      redis_ok=$(curl -sf --connect-timeout "$timeout" --max-time "$((timeout + 2))" "$url" 2>/dev/null \
        | python3 -c "import json,sys; print(json.load(sys.stdin).get('redis_ok',''))" 2>/dev/null || echo "")
      if [[ "$redis_ok" == "False" ]]; then
        log "UNHEALTHY redis_ok=false on $url"
        if unit_exists redis-server.service && ! unit_active redis-server.service; then
          restart_unit redis-server.service
          sleep 2
        fi
        restart_unit nanobase-mobile-runner-api.service
        sleep 3
        http_ok "$url" "$timeout" && { log "OK after redis/runner recover"; return 0; }
      fi
    fi
    return 0
  fi

  log "UNHEALTHY $url"

  if [ -n "$unit" ] && unit_exists "$unit"; then
    if ! unit_enabled "$unit"; then
      log "SKIP http-recover $unit for $url (unit intentionally disabled)"
      [ "$required" = "true" ] && return 1
      return 0
    fi
    restart_unit "$unit"
    sleep 3
    http_ok "$url" "$timeout" && { log "OK after restart $unit"; return 0; }
  fi

  if [ "$required" = "true" ]; then
    log "FAIL required check still down: $url"
    return 1
  fi
  log "WARN optional check still down: $url"
  return 0
}

ensure_docker_stack() {
  local compose_dir="$1" health_url="$2"
  [ -d "$compose_dir" ] || return 0
  http_ok "$health_url" 8 && return 0
  if ! systemctl is-active --quiet docker 2>/dev/null; then
    restart_unit docker.service
    sleep 3
  fi
  log "DOCKER stack recover $compose_dir"
  if [ -f "$compose_dir/docker-compose.yml" ] || [ -f "$compose_dir/compose.yml" ]; then
    (cd "$compose_dir" && docker compose up -d >>"$LOG" 2>&1) || true
  fi
}

cleanup_stale_processes() {
  if [ -x "$CLEANUP_SCRIPT" ]; then
    "$CLEANUP_SCRIPT" || true
  fi
}

emit_manifest_actions() {
  python3 - "$MANIFEST" <<'PY'
import json, sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    sys.exit(0)
data = json.loads(path.read_text())
for u in data.get("systemd_units", []):
    req = "true" if u.get("required") else "false"
    cond = u.get("conditional") or ""
    print(f"UNIT|{u['name']}|{req}|{cond}")
for h in data.get("http_checks", []):
    req = "true" if h.get("required") else "false"
    fb = h.get("fallback_script") or ""
    print(f"HTTP|{h['url']}|{h.get('restart_unit','')}|{h.get('timeout_sec',8)}|{req}|{fb}")
for d in data.get("docker_stacks", []):
    fb = d.get("fallback_script") or ""
    print(f"DOCKER|{d.get('compose_dir','')}|{d.get('health_url','')}|{fb}")
PY
}

run_defaults() {
  ensure_systemd_unit docker.service true
  ensure_systemd_unit cron.service true
  ensure_systemd_unit nginx.service true
  ensure_systemd_unit nanobase-mobile-runner-api.service true
  ensure_systemd_unit nanobase-qwen36-35b-a3b-mtp.service false
  ensure_systemd_unit nanobase-llm-8015-proxy.service false
  ensure_systemd_unit nanobase-arctic-text2sql.service false text2sql_prefer_chat
  ensure_http "http://127.0.0.1:8787/health" nanobase-mobile-runner-api.service 15 true ""
  ensure_http "http://127.0.0.1:8010/v1/models" nanobase-qwen36-35b-a3b-mtp.service 15 false ""
  ensure_http "http://127.0.0.1:8015/v1/models" nanobase-llm-8015-proxy.service 10 false ""
  # Arctic HTTP recover only when unit is enabled (prefer!=chat).
  ensure_http "http://127.0.0.1:8091/v1/models" nanobase-arctic-text2sql.service 15 false ""
}

main() {
  log "=== stack-watchdog start ==="

  cleanup_stale_processes

  ensure_systemd_unit docker.service true
  ensure_systemd_unit cron.service true

  if [ -f "$MANIFEST" ]; then
    while IFS= read -r line; do
      kind="${line%%|*}"
      rest="${line#*|}"
      case "$kind" in
        UNIT)
          IFS='|' read -r name req cond <<< "$rest"
          ensure_systemd_unit "$name" "$req" "$cond"
          ;;
        HTTP)
          IFS='|' read -r url unit timeout req fallback <<< "$rest"
          ensure_http "$url" "$unit" "$timeout" "$req" "$fallback"
          ;;
        DOCKER)
          IFS='|' read -r compose_dir health_url fallback <<< "$rest"
          ensure_docker_stack "$compose_dir" "$health_url"
          ;;
      esac
    done < <(emit_manifest_actions)
  else
    log "WARN manifest missing: $MANIFEST"
    run_defaults
  fi

  log "=== stack-watchdog done ==="
}

main "$@"
