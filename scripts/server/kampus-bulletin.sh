#!/usr/bin/env bash
# Kampüs sesli bülteni: sunucuda üretilen sesi ekler ya da listeler (bkz. backend/semantic_bridge/bulletins.py).
#
#   sudo scripts/server/kampus-bulletin.sh add /yol/bulten.mp3 --title "…" --episode 3 --voice "ZEKİ AI" --duration 842 --publish
#   sudo scripts/server/kampus-bulletin.sh list
#
# Köprünün kullanıcısı, ortam dosyası, çalışma klasörü ve Python'u köprü servisinin kendi tanımından okunur:
# ortam dosyasını yalnız root okur, ses klasörü köprü kullanıcısınındır. Eklenecek ses köprü kullanıcısının
# okuyabileceği geçici bir kopyaya alınır (dosya adı korunur; başlık verilmezse addan çıkar).
set -euo pipefail

UNIT="${SEMANTIC_BRIDGE_UNIT:-nanobase-semantic-bridge.service}"
[ "$(id -u)" = 0 ] || { echo "sudo ile çalıştırın" >&2; exit 1; }

prop() { systemctl show "$UNIT" -p "$1" --value; }
RUN_AS="$(prop User)"
WORKDIR="$(prop WorkingDirectory)"
ENV_FILE="$(prop EnvironmentFiles | awk '{print $1}')"
EXEC="$(prop ExecStart | sed -n 's/.*path=\([^ ;]*\).*/\1/p')"
PY="$(dirname "$EXEC")/python"
[ -n "$RUN_AS" ] && [ -d "$WORKDIR" ] && [ -f "$ENV_FILE" ] && [ -x "$PY" ] || {
  echo "köprü servisi okunamadı ($UNIT): kullanıcı=$RUN_AS klasör=$WORKDIR ortam=$ENV_FILE python=$PY" >&2
  exit 1
}

args=("$@")
if [ "${1:-}" = add ] && [ -n "${2:-}" ]; then
  [ -f "$2" ] || { echo "dosya yok: $2" >&2; exit 1; }
  tmp="$(mktemp -d)"
  trap 'rm -rf "$tmp"' EXIT
  cp -- "$2" "$tmp/"
  chown -R "$RUN_AS" "$tmp"
  args[1]="$tmp/$(basename -- "$2")"
fi

systemd-run --quiet --pipe --wait --collect \
  -p User="$RUN_AS" -p EnvironmentFile="$ENV_FILE" -p WorkingDirectory="$WORKDIR" \
  --setenv=PYTHONPATH="$WORKDIR" \
  "$PY" -m semantic_bridge.bulletins "${args[@]}"
