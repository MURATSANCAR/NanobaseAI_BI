#!/usr/bin/env bash
# TT GPU'da çalıştırılır. Önkoşul: /data/bi-forecast/{timesfm,models/timesfm-3.0-pytorch} (test sunucusundan kopya)
# ve bu klasörün yanında backend/forecasting kopyası (FORECAST_SRC). Derler, kaldırır, /health hazır olana dek bekler.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${FORECAST_SRC:?backend/forecasting yolu}"
B="$HERE/build"
rm -rf "$B" && mkdir -p "$B"
cp "$HERE/Dockerfile" "$B/"
cp -a /data/bi-forecast/timesfm "$B/timesfm"
cp -a "$SRC" "$B/forecasting"
find "$B" \( -name '._*' -o -name __pycache__ -o -name '.git' \) -prune -exec rm -rf {} +
cd "$HERE" && docker compose up -d --build
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8793/health | grep -q '"ready": *true'; then curl -s http://127.0.0.1:8793/health; echo; exit 0; fi
  sleep 5
done
echo "hazır olmadı"; docker logs --tail 40 bi-forecast; exit 1
