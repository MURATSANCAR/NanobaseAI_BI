#!/usr/bin/env bash
# Zamanlayıcı turlarının köprü çağrısı (timas-*.service). Köprü yeniden başlarken tek deneme yapan `curl -fsS` turu
# düşüyordu (2026-09-29 03:30: timas-schools ve timas-supply, köprü o an istek kabul etmiyordu).
#
# Kullanım:  kopru-cagir.sh -m <deneme süre sınırı sn> [-X POST] "http://127.0.0.1:8795/api/v1/<modül>/run-due?..."
#
# 1. Köprü hazır olana kadar bekler: /health cevap verir ve çalışma ortamı kurulmuştur (`boot.runtimeReady`; eski
#    köprüde `status: ok`). Katalog isteyen uç, katalog hazır olana kadar köprünün kendisinde bekler.
# 2. Çağırır. Başarı (2xx): gövde yazılır, çıkış 0.
# 3. Yalnız işin HİÇ başlamadığı ya da köprüyle birlikte öldüğü durumlarda yeniden dener — aynı iş iki kez koşmaz:
#      - bağlanamadı (curl 7)
#      - HTTP 502 / 503 (köprü hazırlanıyor, «WARMING_UP»)
#      - boş cevap / bağlantı koptu (curl 52 / 56) ve köprünün süreç kimliği (pid) değişmiş: köprü yeniden başladı,
#        yarıdaki iş onunla öldü. pid aynıysa iş sürüyor olabilir → yeniden denenmez.
#    4xx, 500, 504 ve zaman aşımı (curl 28) yeniden denenmez: iş başlamış olabilir ya da istek yanlıştır.
# 4. Aralık artar (5, 10, 20, 40, 60, 60 … sn; ilk aralık KOPRU_ARALIK_SN). Toplam bekleme bütçesi KOPRU_BEKLE_SN (varsayılan 900 sn; hazır olma
#    beklemesi + yeniden denemeler, denemenin kendi süresi hariç). Bütçe biterse son hata koduyla çıkar.
#
# Jeton: SEMANTIC_CALLER_TOKEN (birimin EnvironmentFile'ı); hiçbir çıktıya yazılmaz.
# Müşteri VM'inde aynı kurallar infra/docker/bi/jobs.py içinde (bu birim dosyalarını okur, `-m` ve adresi alır).
set -uo pipefail

MAX=1700
METHOD=POST
URL=""
while (($#)); do
  case "$1" in
    -m) MAX="$2"; shift 2 ;;
    -X) METHOD="$2"; shift 2 ;;
    -*) echo "kopru-cagir: bilinmeyen seçenek: $1" >&2; exit 2 ;;
    *) URL="$1"; shift ;;
  esac
done
[[ -n "$URL" ]] || { echo "kopru-cagir: adres verilmedi" >&2; exit 2; }

BASE="${URL%%/api/*}"
BUDGET="${KOPRU_BEKLE_SN:-900}"
START="$(date +%s)"
UNIT="${KOPRU_AD:-$(basename "${URL%%\?*}")}"

say() { printf 'kopru-cagir[%s]: %s\n' "$UNIT" "$*" >&2; }
spent() { echo $(( $(date +%s) - START )); }

# Köprünün süreç kimliği; hazır değilse boş.
bridge_pid() {
  local h
  h="$(curl -sS -m 5 "$BASE/health" 2>/dev/null)" || return 0
  if printf '%s' "$h" | grep -q '"boot"'; then
    printf '%s' "$h" | grep -Eq '"runtimeReady": ?true' || return 0
  else
    printf '%s' "$h" | grep -Eq '"status": ?"ok"' || return 0
  fi
  printf '%s' "$h" | sed -nE 's/.*"pid": ?([0-9]+).*/\1/p'
}

wait_ready() {
  local pause=2 pid
  while :; do
    pid="$(bridge_pid)"
    if [[ -n "$pid" ]]; then
      echo "$pid"
      return 0
    fi
    if (( $(spent) >= BUDGET )); then
      return 1
    fi
    sleep "$pause"
    pause=$(( pause < 10 ? pause + 2 : 10 ))
  done
}

pid="$(wait_ready)" || { say "köprü ${BUDGET} sn içinde hazır olmadı"; exit 7; }
(( $(spent) > 5 )) && say "köprü $(spent) sn sonra hazır"

delay="${KOPRU_ARALIK_SN:-5}"
attempt=1
body="$(mktemp)"
trap 'rm -f "$body"' EXIT
while :; do
  code="$(curl -sS -m "$MAX" -X "$METHOD" -H "X-Semantic-Caller: ${SEMANTIC_CALLER_TOKEN:-}" -o "$body" -w '%{http_code}' "$URL")"
  rc=$?
  if (( rc == 0 )) && [[ "$code" == 2* ]]; then
    cat "$body"; echo
    (( attempt > 1 )) && say "deneme ${attempt}: başarılı"
    exit 0
  fi
  retry=0
  why="curl ${rc}, HTTP ${code:-000}"
  if (( rc == 7 )); then
    retry=1
  elif (( rc == 0 )) && [[ "$code" == 502 || "$code" == 503 ]]; then
    retry=1
  elif (( rc == 52 || rc == 56 )); then
    # Köprü yeniden başladıysa iş onunla öldü; başlamadıysa iş sürüyor olabilir.
    now_pid="$(wait_ready)" || now_pid=""
    if [[ -n "$now_pid" && "$now_pid" != "$pid" ]]; then
      retry=1
      why="${why}; köprü yeniden başladı (pid ${pid} → ${now_pid})"
      pid="$now_pid"
    fi
  fi
  if (( !retry )); then
    [[ -s "$body" ]] && { head -c 2000 "$body" >&2; echo >&2; }
    say "başarısız (${why}) — yeniden denenmez"
    (( rc == 0 )) && exit 22 || exit "$rc"
  fi
  if (( $(spent) + delay > BUDGET )); then
    say "başarısız (${why}); bekleme bütçesi (${BUDGET} sn) bitti"
    (( rc == 0 )) && exit 22 || exit "$rc"
  fi
  say "deneme ${attempt}: ${why} — ${delay} sn sonra yeniden"
  sleep "$delay"
  new_pid="$(wait_ready)" || { say "köprü ${BUDGET} sn içinde hazır olmadı"; exit 7; }
  pid="$new_pid"
  delay=$(( delay * 2 > 60 ? 60 : delay * 2 ))
  attempt=$(( attempt + 1 ))
done
