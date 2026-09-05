#!/usr/bin/env bash
# NanobaseAI BI LLM — sabit üretim profili:
#   greedy (temp 0), düşünme (thinking) kapalı, MTP taslak (draft) ile spekülatif çözümleme,
#   attention GPU'da, MoE expert ağırlıkları LLM_N_CPU_MOE kadar katman için CPU RAM'de.
set -euo pipefail

: "${LLM_MODEL_FILE:?LLM_MODEL_FILE gerekli}"
: "${LLM_ALIAS:=nanobaseai-bi-llm}"
: "${LLM_CTX:=24576}"
: "${LLM_PARALLEL:=1}"
: "${LLM_N_CPU_MOE:=999}"
: "${LLM_MTP_N_MAX:=3}"
: "${LLM_THREADS:=32}"
: "${LLM_BATCH:=4096}"
: "${LLM_UBATCH:=2048}"

args=(
  --model "$LLM_MODEL_FILE"
  --alias "$LLM_ALIAS"
  --host 0.0.0.0 --port 8080
  -ngl 999
  --n-cpu-moe "$LLM_N_CPU_MOE"
  -c "$LLM_CTX"
  -np "$LLM_PARALLEL"
  -t "$LLM_THREADS"
  -b "$LLM_BATCH" -ub "$LLM_UBATCH"
  --flash-attn on
  --cache-type-k q8_0 --cache-type-v q8_0
  --temp 0 --top-k 1
  --jinja
  --reasoning off
  --reasoning-budget 0
  --chat-template-kwargs '{"reasoning_effort":"none","enable_thinking":false}'
  --metrics
)

if [[ -n "${LLM_DRAFT_FILE:-}" && "${LLM_DRAFT_FILE}" != "/models/llm/" && -f "${LLM_DRAFT_FILE}" ]]; then
  args+=( -md "$LLM_DRAFT_FILE" --spec-type draft-mtp --spec-draft-n-max "$LLM_MTP_N_MAX" )
fi

if [[ -n "${LLM_API_KEY:-}" ]]; then
  args+=( --api-key "$LLM_API_KEY" )
fi

exec /opt/llm/bin/llama-server "${args[@]}"
