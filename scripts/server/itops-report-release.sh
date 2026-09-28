#!/usr/bin/env bash
# M48 sürüm kaydı: bir kurulumun sonunda kod sürümünü, imajı ve Mac artığı (._*) sayısını Sistem durumu'na bildirir.
# Bildirim düşerse kurulum durmaz (yalnız uyarı yazar); ama kabul, kaydın gelmesini ister (CLAUDE.md dağıtım kuralı).
#
#   ENV=test ROOT=/data/nanobaseai/bi/frontend CODE_SHA=$(git rev-parse main) bash scripts/server/itops-report-release.sh
#   ENV=vm APPLEDOUBLE=0 IMAGE=nanobase-bi-bridge:latest CODE_SHA=… BRIDGE=http://127.0.0.1:8795 bash …
#
# ENV       test | vm | gpu
# ROOT      ._* sayılacak kök (APPLEDOUBLE verilmişse sayılmaz; uzak hedefte sayım çağıranın işidir)
# CODE_SHA  kurulan main sürümü; yoksa ROOT bir git ağacıysa HEAD, o da yoksa ROOT/.code-sha, yoksa «bilinmiyor»
# IMAGE     kalkan kapsayıcının imajı (varsa)
# BRIDGE    bildirimin gideceği köprü (varsayılan yerel köprü)
set -uo pipefail
ENV="${ENV:?ENV=test|vm|gpu}"
ROOT="${ROOT:-$(pwd)}"
BRIDGE="${BRIDGE:-http://127.0.0.1:${SEMANTIC_BRIDGE_PORT:-8795}}"
IMAGE="${IMAGE:-}"
NOTE="${NOTE:-}"

if [[ -z "${APPLEDOUBLE:-}" ]]; then
  APPLEDOUBLE="$(find "$ROOT" -name '._*' -type f -not -path '*/node_modules/*' 2>/dev/null | wc -l | tr -d ' ')"
fi
if [[ -z "${CODE_SHA:-}" ]]; then
  CODE_SHA="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || cat "$ROOT/.code-sha" 2>/dev/null || echo bilinmiyor)"
fi

body="$(E="$ENV" S="$CODE_SHA" I="$IMAGE" A="$APPLEDOUBLE" N="$NOTE" U="${USER:-kurulum}" python3 -c '
import json, os
print(json.dumps({"env": os.environ["E"], "codeSha": os.environ["S"].strip(), "image": os.environ["I"] or None,
                  "appledoubleCount": int(os.environ["A"] or 0), "note": os.environ["N"] or None,
                  "reportedBy": "kurulum:" + os.environ["U"]}))')"

echo "== sürüm kaydı: ${ENV} · ${CODE_SHA:0:12} · imaj ${IMAGE:-—} · ._* ${APPLEDOUBLE}"
[[ "$APPLEDOUBLE" == "0" ]] || echo "UYARI: hedefte ${APPLEDOUBLE} Mac artığı (._*) var; kural: kurulum sonrası 0 olmalı"
curl -fsS -m 20 -X POST -H 'Content-Type: application/json' -H "X-Semantic-Caller: ${SEMANTIC_CALLER_TOKEN:-}" \
  -d "$body" "${BRIDGE}/api/v1/it-ops/report-release" || echo "UYARI: sürüm kaydı ${BRIDGE} köprüsüne yazılamadı"
echo
