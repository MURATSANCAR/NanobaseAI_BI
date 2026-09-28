#!/usr/bin/env bash
# M50 sürüm kaydı: kurulumun sonunda köprüye «şu kod kuruldu» der; köprü o anki katalog sürümünü, bilgi paketi ve kural
# özetini, gündelik terim havuzu özetini ve model kimliğini aynı satıra yazar (Zeki AI kalitesi → Sürümler). Bu satır,
# o sırada koşan bir kalite ölçümünün «penceresine kurulum girdi» uyarısının da kaynağıdır.
#
#   ENV=test ROOT=/data/nanobaseai/bi/frontend CODE_SHA=$(git rev-parse main) bash scripts/server/model-quality-version.sh
#   ENV=vm BRIDGE=http://127.0.0.1:8795 CODE_SHA=… bash …
#
# ENV       test | vm
# CODE_SHA  kurulan main sürümü; yoksa ROOT bir git ağacıysa HEAD, o da yoksa ROOT/.code-sha, yoksa boş (köprü son
#           bilinen sürümü taşır)
# BRIDGE    köprü (varsayılan yerel köprü); SEMANTIC_CALLER_TOKEN ortamdan
# Kayıt düşerse kurulum durmaz, yalnız uyarı yazılır.
set -uo pipefail
ENV="${ENV:-test}"
ROOT="${ROOT:-$(pwd)}"
BRIDGE="${BRIDGE:-http://127.0.0.1:${SEMANTIC_BRIDGE_PORT:-8795}}"
NOTE="${NOTE:-}"
if [[ -z "${CODE_SHA:-}" ]]; then
  CODE_SHA="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || cat "$ROOT/.code-sha" 2>/dev/null || true)"
fi
body="$(E="$ENV" S="${CODE_SHA:-}" N="$NOTE" U="${USER:-kurulum}" python3 -c '
import json, os
print(json.dumps({"env": os.environ["E"], "codeSha": os.environ["S"].strip() or None, "note": os.environ["N"] or None,
                  "by": "kurulum:" + os.environ["U"]}))')"
echo "== M50 sürüm kaydı: ${ENV} · ${CODE_SHA:0:12}"
curl -fsS -m 60 -X POST -H 'Content-Type: application/json' -H "X-Semantic-Caller: ${SEMANTIC_CALLER_TOKEN:-}" \
  -d "$body" "${BRIDGE}/api/v1/model-quality/versions" || echo "UYARI: M50 sürüm kaydı ${BRIDGE} köprüsüne yazılamadı"
echo
