#!/usr/bin/env bash
# WrenAI MCP server for agents / the LLM tool layer: `wren serve mcp --transport http` (Streamable HTTP, loopback only).
# Tools: run_sql, dry_run, dry_plan, get_mdl, list_models, describe_model, describe_schema, get_instructions, recall_queries, get_context ...
set -euo pipefail
export SYSTEMD_BUS_TIMEOUT="${SYSTEMD_BUS_TIMEOUT:-300}"
VENV="${WREN_VENV:-/data/nanobaseai/bi/wren-venv}"
PROJECT="${WREN_PROJECT:-/data/nanobaseai/bi/wren-project/logo_timas}"
PROFILE="${WREN_PROFILE:-logo-tunnel}"
# Ajanların doğrulanmış NL→SQL çiftini geri yazabilmesi için store_query aracı (öğrenme döngüsü).
ALLOW_WRITE="${WREN_MCP_ALLOW_WRITE:-1}"
PORT="${WREN_MCP_PORT:-8090}"
UNIT=/etc/systemd/system/nanobase-wren-mcp.service
log() { printf '[deploy-wren-mcp] %s\n' "$*"; }
# wrenai 0.13.4 FastMCP v1 API'sini bekler; mcp 2.x sunucuyu import aşamasında düşürür (bkz. docs/upstream Issue 2).
"${VENV}/bin/python" -c "import mcp.server.fastmcp" 2>/dev/null || { log "installing wrenai[mcp] (mcp<2)"; "${VENV}/bin/python" -m pip install -q "wrenai[mcp]" "mcp<2"; }
"${VENV}/bin/python" -c "import importlib.metadata as m; v=m.version('mcp'); assert int(v.split('.')[0]) < 2, v; print('  mcp', v)" || { log "pinning mcp<2"; "${VENV}/bin/python" -m pip install -q "mcp<2"; }
[[ -f "${PROJECT}/target/mdl.json" ]] || { echo "missing ${PROJECT}/target/mdl.json (wren context build)" >&2; exit 1; }
WRITE_FLAG=""; [[ "$ALLOW_WRITE" == "1" ]] && WRITE_FLAG="--allow-write"
sudo -E tee "$UNIT" >/dev/null <<UNIT
[Unit]
Description=NanobaseAI BI — WrenAI MCP server (:${PORT}, loopback)
After=network.target

[Service]
Type=simple
User=administrator
WorkingDirectory=${PROJECT}
Environment=PATH=${VENV}/bin:/usr/bin
Environment=HOME=/home/administrator
ExecStart=${VENV}/bin/wren serve mcp --transport http --host 127.0.0.1 --port ${PORT} --project ${PROJECT} --profile ${PROFILE} ${WRITE_FLAG} --quiet
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
sudo -E systemctl daemon-reload || log "WARN: daemon-reload timed out — continuing"
sudo -E systemctl enable nanobase-wren-mcp >/dev/null 2>&1 || true
sudo -E systemctl restart nanobase-wren-mcp
sleep 4
systemctl is-active nanobase-wren-mcp
log "MCP initialize + tools/list smoke"
"${VENV}/bin/python" - "$PORT" <<'PY'
import json, sys, urllib.request
port = sys.argv[1]
H = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
def call(payload, sid=None):
    h = dict(H)
    if sid: h["Mcp-Session-Id"] = sid
    req = urllib.request.Request(f"http://127.0.0.1:{port}/mcp", data=json.dumps(payload).encode(), headers=h)
    r = urllib.request.urlopen(req, timeout=60)
    body = r.read().decode()
    sid = r.headers.get("Mcp-Session-Id") or sid
    if not body.strip():  # notifications → 202, empty body
        return {}, sid
    # streamable http answers as SSE ("event: message\ndata: {...}")
    data = [json.loads(l[5:]) for l in body.splitlines() if l.startswith("data:")] or [json.loads(body)]
    return data[-1], sid
init, sid = call({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "nanobaseai-smoke", "version": "0"}}})
print("  server:", init.get("result", {}).get("serverInfo"))
call({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
tools, _ = call({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, sid)
names = [t["name"] for t in tools.get("result", {}).get("tools", [])]
print("  tools:", names)
res, _ = call({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "run_sql", "arguments": {"sql": 'SELECT COUNT(*) AS n FROM "dbo_LG_411_01_INVOICE" WHERE "CANCELLED" = 0', "limit": 1}}}, sid)
print("  run_sql:", json.dumps(res.get("result", res), ensure_ascii=False)[:200])
PY
log "nanobase-wren-mcp active on 127.0.0.1:${PORT}/mcp"
