#!/usr/bin/env bash
# M50 Zeki AI kalitesi: kapı koşuları ve bildirimler (timas-model-quality@<tur>.service çağırır).
#
#   model-quality-run.sh sira    ekrandan istenen koşuları al ve koştur (10 dakikada bir)
#   model-quality-run.sh gece    okuma kapısı (resolver-gate, modelsiz, ~2 dk) — her gece katalog taramasından sonra
#   model-quality-run.sh hafta   cevap kapısı (answer-gate --repeat 3, referans SQL doğrudan Logo/CRM'de, ~35 dk) — pazar
#   model-quality-run.sh ozet    günlük geri bildirim özeti + yarıda kalan koşuyu kapat
#
# Mantık köprüde; betikler sonuçlarını `--report` ile köprüye yazar. Aynı anda tek kapı koşar (flock). Kapı
# betikleri köprüyü yeniden başlatmaz; kurulum ölçüm penceresine girerse koşu satırı «kirli» işaretlenir.
# Ortam: /etc/nanobase/semantic-bridge.env (SEMANTIC_CALLER_TOKEN, SEMANTIC_STORE_DSN, bağlantı dosyaları).
set -uo pipefail
TUR="${1:-sira}"
ROOT="${MQ_ROOT:-/data/nanobaseai/bi/frontend}"
PY="${MQ_PYTHON:-/data/nanobaseai/bi/semantic-venv/bin/python}"
BRIDGE="${MQ_BRIDGE:-http://127.0.0.1:${SEMANTIC_BRIDGE_PORT:-8795}}"
QUESTIONS="${MQ_QUESTIONS:-tests/text2sql/set100.jsonl}"
BASELINE="${MQ_RESOLVER_BASELINE:-tests/text2sql/resolver-baseline-set100.json}"
GOLD="${MQ_ANSWER_GOLD:-tests/text2sql/answers-set100.json}"
REPEAT="${MQ_ANSWER_REPEAT:-3}"
LOCK="${MQ_LOCK:-/tmp/timas-model-quality.lock}"

# Köprü yeniden başlarken beklenir, yalnız «iş başlamadı» hatalarında yeniden denenir (kopru-cagir.sh).
due() { KOPRU_AD="model-quality-$1" "$ROOT/scripts/server/kopru-cagir.sh" -m 300 -X POST "${BRIDGE}/api/v1/model-quality/run-due?kind=$1"; }

resolver() {  # $1: istek kimliği (boş olabilir)
  local req=(); [[ -n "${1:-}" ]] && req=(--request "$1")
  (cd "$ROOT" && PYTHONPATH="$ROOT/backend" "$PY" tests/text2sql/resolver-gate.py "$QUESTIONS" --baseline "$BASELINE" \
     --url "$BRIDGE" --report "$BRIDGE" "${req[@]}")
}

answer() {
  local req=(); [[ -n "${1:-}" ]] && req=(--request "$1")
  (cd "$ROOT" && PYTHONPATH="$ROOT/backend" "$PY" tests/text2sql/answer-gate.py --gold "$GOLD" --repeat "$REPEAT" \
     --url "$BRIDGE" --backend "$ROOT/backend" --report "$BRIDGE" "${req[@]}")
}

gate() {  # tek seferde tek kapı
  exec 9>"$LOCK"
  if ! flock -n 9; then echo "başka bir kalite koşusu sürüyor; bu tur atlandı"; return 0; fi
  "$@"
}

case "$TUR" in
  sira)
    jobs="$(due claim)" || { echo "UYARI: sıra okunamadı"; exit 1; }
    echo "$jobs" | python3 -c 'import json,sys; [print(j["id"], j["suite"]) for j in json.load(sys.stdin).get("jobs", [])]' |
      while read -r id suite; do
        echo "== istek ${id}: ${suite}"
        case "$suite" in
          resolver) gate resolver "$id" ;;
          answer) gate answer "$id" ;;
          *) echo "bilinmeyen takım: ${suite}" ;;
        esac
      done ;;
  gece) gate resolver "" ;;
  hafta) gate answer "" ;;
  ozet) due digest; echo; due stale; echo ;;
  *) echo "kullanım: $0 sira|gece|hafta|ozet"; exit 2 ;;
esac
exit 0
