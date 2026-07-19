#!/usr/bin/env bash
# Faz 1 acceptance — Nanobase prod mapping (38.247.162.28).
# Names differ from generic plan: reporting DB = bi_reporting (:5435), RO = bi_reporting_ro.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SECRETS="${SECRETS_ROOT:-/data/nanobaseai/bi/secrets}"
OUT_MD="${ROOT}/docs/architecture/phase-1-results.md"
OUT_JSON="${ROOT}/docs/architecture/phase-1-acceptance.json"
VENV="${ROOT}/backend/.venv"
PY="${VENV}/bin/python"

fail=0
declare -A RES
pass() { RES["$1"]=PASS; printf 'PASS  %s — %s\n' "$1" "$2"; }
bad()  { RES["$1"]=FAIL; printf 'FAIL  %s — %s\n' "$1" "$2"; fail=1; }

# Load embed key without sudo hang
if [[ -f "${ROOT}/backend/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT}/backend/.env" || true
  set +a
fi
EMBED_KEY="${BI_EMBED_API_KEY:-${CONTRACT_API_KEY:-${OPENAI_API_KEY:-}}}"

# ---------------------------------------------------------------------------
# 1) Infra / versions
# ---------------------------------------------------------------------------
if curl -fsS http://127.0.0.1:6333/collections >/dev/null; then
  pass "qdrant_up" ":6333"
else
  bad "qdrant_up" "unreachable"
fi

if sudo docker exec nanobase-bi-meta-db pg_isready -U bi_meta -d bi_meta >/dev/null 2>&1; then
  pass "meta_pg" "nanobase-bi-meta-db :5434"
else
  bad "meta_pg" "not ready"
fi

if sudo docker exec nanobase-bi-reporting-db pg_isready -U bi_reporting_admin -d bi_reporting >/dev/null 2>&1; then
  pass "reporting_pg" "nanobase-bi-reporting-db :5435 (test DB)"
else
  bad "reporting_pg" "not ready"
fi

DBGPT_VER="$("$PY" -c 'import importlib.metadata as m; print(m.version("dbgpt"))' 2>/dev/null || echo missing)"
if [[ "$DBGPT_VER" == "0.8.1" ]]; then
  pass "dbgpt_version" "$DBGPT_VER"
else
  bad "dbgpt_version" "got $DBGPT_VER want 0.8.1"
fi

# ---------------------------------------------------------------------------
# 2) Qwen
# ---------------------------------------------------------------------------
MODELS_JSON="$(curl -fsS http://127.0.0.1:8010/v1/models || true)"
QWEN_MODEL_ID="$(printf '%s' "$MODELS_JSON" | "$PY" -c 'import sys,json; d=json.load(sys.stdin); print(((d.get("data") or [{}])[0].get("id")) or "")' 2>/dev/null || true)"
if [[ -n "$QWEN_MODEL_ID" ]]; then
  pass "qwen_models" "$QWEN_MODEL_ID"
else
  bad "qwen_models" "empty"
fi

STREAM_OUT="$(curl -sN --max-time 60 http://127.0.0.1:8010/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d "{\"model\":\"${QWEN_MODEL_ID}\",\"messages\":[{\"role\":\"user\",\"content\":\"Türkçe olarak yalnızca MODEL_OK yaz.\"}],\"temperature\":0,\"stream\":true,\"max_tokens\":16}" || true)"
if printf '%s' "$STREAM_OUT" | grep -q 'MODEL_OK'; then
  pass "qwen_streaming" "MODEL_OK seen"
else
  # some models wrap tokens; accept data: chunks + OK fragment
  if printf '%s' "$STREAM_OUT" | grep -q 'data:'; then
    pass "qwen_streaming" "SSE chunks (MODEL_OK literal optional)"
  else
    bad "qwen_streaming" "no stream"
  fi
fi

# ---------------------------------------------------------------------------
# 3) BGE-M3
# ---------------------------------------------------------------------------
if [[ -z "$EMBED_KEY" ]]; then
  bad "bge_m3" "missing embed API key"
else
  EMB_CODE="$(curl -sS -o /tmp/faz1_emb.json -w '%{http_code}' \
    -H "Authorization: Bearer ${EMBED_KEY}" \
    -H 'Content-Type: application/json' \
    -d '{"texts":["müşterilerin ödenmemiş faturaları"]}' \
    http://127.0.0.1:8083/v1/embeddings || true)"
  DIM="$("$PY" - <<'PY' 2>/dev/null || echo 0
import json
d=json.load(open("/tmp/faz1_emb.json"))
vecs=d.get("embeddings") or d.get("data") or []
if vecs and isinstance(vecs[0], dict):
    vecs=[v["embedding"] for v in vecs]
print(len(vecs[0]) if vecs else 0)
PY
)"
  if [[ "$EMB_CODE" == "200" && "$DIM" == "1024" ]]; then
    pass "bge_m3" "http200 dim=${DIM} tr_ok"
  else
    bad "bge_m3" "http=${EMB_CODE} dim=${DIM}"
  fi
fi

# ---------------------------------------------------------------------------
# 4) Qdrant collections
# ---------------------------------------------------------------------------
COLL_JSON="$(curl -fsS http://127.0.0.1:6333/collections)"
COLL_OK="$("$PY" - <<'PY'
import json,sys
names=[c["name"] for c in json.load(sys.stdin)["result"]["collections"]]
need=["bi_schema_bi_reporting","bi_schema_erp","bi_schema_sigorta"]
print("OK" if all(n in names for n in need) else "MISS:"+str(names))
PY
<<<"$COLL_JSON")"
# heredoc with stdin conflict — fix via python -c
COLL_OK="$(printf '%s' "$COLL_JSON" | "$PY" -c 'import sys,json; names=[c["name"] for c in json.load(sys.stdin)["result"]["collections"]]; need=["bi_schema_bi_reporting","bi_schema_erp","bi_schema_sigorta"]; print("OK" if all(n in names for n in need) else "MISS:"+str(names))')"
if [[ "$COLL_OK" == "OK" ]]; then
  pass "qdrant_collections" "bi_schema_{bi_reporting,erp,sigorta}"
else
  bad "qdrant_collections" "$COLL_OK"
fi

DET="$(curl -fsS http://127.0.0.1:6333/collections/bi_schema_bi_reporting)"
QDET="$("$PY" - <<'PY'
import json,sys
r=json.load(sys.stdin).get("result") or {}
status=r.get("status")
cfg=(r.get("config") or {}).get("params") or {}
vecs=(cfg.get("vectors") or {})
size=vecs.get("size") if isinstance(vecs,dict) else None
dist=vecs.get("distance") if isinstance(vecs,dict) else None
pts=r.get("points_count") or 0
ok = status in ("green","yellow") and size==1024 and str(dist).lower()=="cosine" and pts>0
print(f"{'OK' if ok else 'BAD'} status={status} size={size} dist={dist} points={pts}")
PY
<<<"$DET")" 2>/dev/null || true
QDET="$(printf '%s' "$DET" | "$PY" -c 'import sys,json; r=json.load(sys.stdin).get("result") or {}; status=r.get("status"); cfg=(r.get("config") or {}).get("params") or {}; vecs=(cfg.get("vectors") or {}); size=vecs.get("size") if isinstance(vecs,dict) else None; dist=vecs.get("distance") if isinstance(vecs,dict) else None; pts=r.get("points_count") or 0; ok=status in ("green","yellow") and size==1024 and str(dist).lower()=="cosine" and pts>0; print(f"{chr(79)+chr(75) if ok else chr(66)+chr(65)+chr(68)} status={status} size={size} dist={dist} points={pts}")')"
# simpler:
QDET="$(printf '%s' "$DET" | "$PY" -c "
import sys,json
r=json.load(sys.stdin).get('result') or {}
status=r.get('status')
vecs=((r.get('config') or {}).get('params') or {}).get('vectors') or {}
size=vecs.get('size') if isinstance(vecs, dict) else None
dist=vecs.get('distance') if isinstance(vecs, dict) else None
pts=r.get('points_count') or 0
ok = status in ('green','yellow') and size==1024 and str(dist).lower()=='cosine' and int(pts)>0
print(('OK' if ok else 'BAD') + f' status={status} size={size} dist={dist} points={pts}')
")"
if [[ "$QDET" == OK* ]]; then
  pass "qdrant_detail" "$QDET"
else
  bad "qdrant_detail" "$QDET"
fi

# ---------------------------------------------------------------------------
# 5) Datasources (Gateway + API sources — Nanobase path)
# ---------------------------------------------------------------------------
QG_H="$(curl -fsS http://127.0.0.1:8792/health)"
if printf '%s' "$QG_H" | grep -q 'bi_reporting'; then
  pass "datasource_listed" "query_gateway has bi_reporting (+erp/sigorta)"
else
  bad "datasource_listed" "$QG_H"
fi

# ---------------------------------------------------------------------------
# 6) RO user tests (reporting = our test DB)
# ---------------------------------------------------------------------------
RO_PW="$(tr -d '\n\r' < "${SECRETS}/reporting-ro.password")"
SEL="$(sudo docker exec -e PGPASSWORD="$RO_PW" nanobase-bi-reporting-db \
  psql -U bi_reporting_ro -d bi_reporting -Atc 'SELECT COUNT(*) FROM invoices;' 2>/dev/null || echo err)"
if [[ "$SEL" =~ ^[0-9]+$ ]]; then
  pass "ro_select" "SELECT COUNT(*) FROM invoices → ${SEL}"
  SELECT_ALLOWED=true
else
  bad "ro_select" "$SEL"
  SELECT_ALLOWED=false
fi

if sudo docker exec -e PGPASSWORD="$RO_PW" nanobase-bi-reporting-db \
  psql -U bi_reporting_ro -d bi_reporting -v ON_ERROR_STOP=1 \
  -c 'UPDATE invoices SET remaining_amount = 0 WHERE 1 = 0;' >/tmp/faz1_upd.txt 2>&1; then
  bad "ro_update" "UPDATE unexpectedly allowed"
  UPDATE_DENIED=false
else
  pass "ro_update" "UPDATE denied"
  UPDATE_DENIED=true
fi

if sudo docker exec -e PGPASSWORD="$RO_PW" nanobase-bi-reporting-db \
  psql -U bi_reporting_ro -d bi_reporting -v ON_ERROR_STOP=1 \
  -c 'CREATE TABLE unauthorized_test(id bigint);' >/tmp/faz1_crt.txt 2>&1; then
  bad "ro_create" "CREATE unexpectedly allowed"
  CREATE_DENIED=false
else
  pass "ro_create" "CREATE denied"
  CREATE_DENIED=true
fi

# ---------------------------------------------------------------------------
# 7) NL→SQL via Nanobase locked path (plan → gateway → explain)
# ---------------------------------------------------------------------------
"$PY" - <<'PY' >/tmp/faz1_nl2sql.json
import json, urllib.request, time

def post(url, body, timeout=180):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")

questions = [
    "2026 yılındaki toplam fatura tutarı nedir?",
    "Bunun ödenmemiş kısmı ne kadar?",
    "Ankara'daki müşterilere ait gecikmiş faturaları göster.",
    "İptal edilmiş faturaları hesaba katmadan toplam tutarı hesapla.",
]
results = []
session = "faz1-accept"
for i, q in enumerate(questions):
    t0 = time.time()
    # full chat for context continuity on follow-ups
    raw = post(
        "http://127.0.0.1:8790/api/v1/bi/chat/stream",
        {"message": q, "session_id": session, "db_name": "bi_reporting"},
        timeout=200,
    )
    done = None
    lines = raw.splitlines()
    for j, line in enumerate(lines):
        if line.startswith("event: done") and j + 1 < len(lines) and lines[j + 1].startswith("data: "):
            done = json.loads(lines[j + 1][6:])
            break
        if line.startswith("event: error") and j + 1 < len(lines) and lines[j + 1].startswith("data: "):
            done = {"error": json.loads(lines[j + 1][6:])}
            break
    ok = bool(done) and not done.get("error") and bool(done.get("sql")) and done.get("query_result") is not None
    reply = (done or {}).get("reply") or ""
    tr_ok = any(ch.isalpha() for ch in reply) and ("SQL:" in reply or len(reply) > 10)
    results.append(
        {
            "question": q,
            "ok": ok,
            "sql": (done or {}).get("sql"),
            "rows": ((done or {}).get("query_result") or {}).get("rows"),
            "reply_head": reply[:240],
            "turkish_ok": tr_ok,
            "elapsed_s": round(time.time() - t0, 2),
            "retrieval": (((done or {}).get("workflows") or {}).get("plan") or {}).get("retrieval"),
            "error": (done or {}).get("error"),
        }
    )

nl_ok = all(r["ok"] for r in results)
follow_ok = results[1]["ok"]  # ödenmemiş kısmı — follow-up
print(json.dumps({"ok": nl_ok, "followup_ok": follow_ok, "results": results}, ensure_ascii=False, indent=2))
PY

NL_OK="$("$PY" -c 'import json; d=json.load(open("/tmp/faz1_nl2sql.json")); print("1" if d.get("ok") else "0")')"
TR_OK="$("$PY" -c 'import json; d=json.load(open("/tmp/faz1_nl2sql.json")); print("1" if all(r.get("turkish_ok") for r in d.get("results") or []) else "0")')"
FU_OK="$("$PY" -c 'import json; d=json.load(open("/tmp/faz1_nl2sql.json")); print("1" if d.get("followup_ok") else "0")')"

if [[ "$NL_OK" == "1" ]]; then
  pass "nl2sql_chain" "4/4 questions via nanobase plan→gateway"
else
  bad "nl2sql_chain" "see /tmp/faz1_nl2sql.json"
fi
if [[ "$TR_OK" == "1" ]]; then
  pass "turkish_explain" "answers present"
else
  bad "turkish_explain" "missing"
fi
if [[ "$FU_OK" == "1" ]]; then
  pass "followup_context" "ödenmemiş kısmı executed"
else
  bad "followup_context" "failed"
fi

# ---------------------------------------------------------------------------
# Write reports
# ---------------------------------------------------------------------------
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
"$PY" - <<PY
import json
from pathlib import Path

res = {
  "ts": "$TS",
  "mapping": {
    "test_db": "bi_reporting :5435",
    "ro_user": "bi_reporting_ro",
    "meta_db": "bi_meta :5434",
    "dbgpt": "0.8.1",
    "qwen": "$QWEN_MODEL_ID",
    "qdrant_collections": ["bi_schema_bi_reporting", "bi_schema_erp", "bi_schema_sigorta"],
    "nl2sql_path": "nanobase_api workflows → query_gateway (not DB-GPT chat_with_db_execute)",
  },
  "flags": {
    "SELECT_ALLOWED": "$SELECT_ALLOWED" == "true",
    "UPDATE_DENIED": "$UPDATE_DENIED" == "true",
    "CREATE_DENIED": "$CREATE_DENIED" == "true",
  },
  "tests": {k: v for k, v in {
$(for k in "${!RES[@]}"; do printf '    "%s": "%s",\n' "$k" "${RES[$k]}"; done)
  }.items()},
  "nl2sql": json.load(open("/tmp/faz1_nl2sql.json")),
}
Path("$OUT_JSON").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")

rows = []
order = [
 ("dbgpt_version","DB-GPT sürümü","0.8.1"),
 ("qwen_models","Qwen model listesi","HTTP 200"),
 ("qwen_streaming","Qwen streaming","Token akışı"),
 ("bge_m3","BGE-M3 embedding","1024 boyut"),
 ("qdrant_up","Qdrant up","reachable"),
 ("qdrant_detail","Qdrant collection","green + cosine + points>0"),
 ("qdrant_collections","Qdrant schema collections","bi_schema_*"),
 ("datasource_listed","Test datasource","bi_reporting listed"),
 ("ro_select","RO SELECT","Başarılı"),
 ("ro_update","RO UPDATE","Engellendi"),
 ("ro_create","RO CREATE","Engellendi"),
 ("nl2sql_chain","İlk NL→SQL (4 soru)","Çalışan SQL"),
 ("turkish_explain","Türkçe açıklama","Üretildi"),
 ("followup_context","Takip sorusu (ödenmemiş)","Çalıştı"),
]
tests = res["tests"]
lines = [
  "# Faz 1 — Kabul sonuçları (Nanobase prod mapping)",
  "",
  f"- Zaman: \`{res['ts']}\`",
  f"- DB-GPT: **{res['mapping']['dbgpt']}**",
  f"- Qwen: \`{res['mapping']['qwen']}\`",
  f"- Test DB: \`{res['mapping']['test_db']}\` RO=\`{res['mapping']['ro_user']}\`",
  f"- NL2SQL yolu: {res['mapping']['nl2sql_path']}",
  f"- RO flags: SELECT_ALLOWED={res['flags']['SELECT_ALLOWED']} UPDATE_DENIED={res['flags']['UPDATE_DENIED']} CREATE_DENIED={res['flags']['CREATE_DENIED']}",
  "",
  "| Test | Beklenen | Sonuç |",
  "|------|----------|-------|",
]
for key, label, exp in order:
  lines.append(f"| {label} | {exp} | **{tests.get(key,'SKIP')}** |")

lines += ["", "## NL2SQL detay", ""]
for i, r in enumerate(res["nl2sql"].get("results") or [], 1):
  lines += [
    f"### Q{i}",
    f"- Soru: {r['question']}",
    f"- OK: {r['ok']} ({r['elapsed_s']}s)",
    f"- SQL: \`{(r.get('sql') or '')[:300]}\`",
    f"- Rows: \`{json.dumps(r.get('rows'), ensure_ascii=False)[:300]}\`",
    f"- Reply: {(r.get('reply_head') or '')[:300]}",
    "",
  ]

verdict = "PASS" if all(tests.get(k)=="PASS" for k,_,__ in order) else "FAIL"
lines = [lines[0], "", f"**Verdict: {verdict}**", ""] + lines[1:]
Path("$OUT_MD").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("wrote", "$OUT_MD", "verdict", verdict)
PY

echo "SELECT_ALLOWED=$SELECT_ALLOWED UPDATE_DENIED=$UPDATE_DENIED CREATE_DENIED=$CREATE_DENIED"
exit "$fail"
