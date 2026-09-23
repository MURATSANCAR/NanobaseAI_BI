#!/usr/bin/env bash
# İki karta tek kapı: GPU sunucusunda, sudo ile:  sudo bash /data/editor/llm-dispatch/install.sh
# Her adım kontrollü; biri tutmazsa durur. Geri almak: sudo bash /data/editor/llm-dispatch/rollback.sh
set -euo pipefail
cd "$(dirname "$0")"
APP=/data/editor/app
VER=$(cat "$APP/VERSION")
IMG="editor-py:$VER"
run_as() { sudo -u gpuubuntu "$@"; }

echo "== 1/6 koşan kitap analizi yok mu (geçit yeniden başlarken analiz kesilmesin)"
n=$(docker exec editor-postgres psql -U postgres -d editor -tA -c "select count(*) from ed.analysis_job where status in ('QUEUED','RUNNING')")
[ "$n" = "0" ] || { echo "DUR: $n analiz koşuyor; bitince tekrar deneyin"; exit 1; }

echo "== 2/6 editör imajı $IMG (geçidin 'also_serves' özelliği)"
run_as docker build -q -t "$IMG" --build-arg CODE_VERSION="$VER" -f "$APP/images/py/Dockerfile" "$APP" >/dev/null
grep -q "also_serves" <(docker run --rm "$IMG" cat /app/src/editor/gateway.py) || { echo "DUR: imajda also_serves yok"; exit 1; }

echo "== 3/6 geçit yeni imajla"
( cd "$APP" && EDITOR_PY_IMAGE="$IMG" docker compose -f deploy/docker-compose.yml --project-name editor \
    --profile analysis up -d --no-deps gateway )
[ "$(docker inspect editor-gateway --format '{{.Config.Image}}')" = "$IMG" ] || { echo "DUR: geçit yanlış imajda"; exit 1; }

echo "== 4/6 GPU 1'deki ana model 'nanobaseAI' adıyla yeniden kurulur (geçit 15 sn'de bir kontrol eder)"
docker stop -t 30 editor-model-director >/dev/null 2>&1 || true
for i in $(seq 1 60); do
  names=$(docker run --rm --network editor-net curlimages/curl:8.10.1 -s -m 5 \
          http://editor-model-director:8000/v1/models 2>/dev/null || true)
  if echo "$names" | grep -q '"nanobaseAI"'; then echo "   hazır ($((i*10)) sn)"; break; fi
  sleep 10
done
echo "$names" | grep -q '"nanobaseAI"' || { echo "DUR: GPU 1 modeli 10 dakikada nanobaseAI adıyla kalkmadı"; exit 1; }

echo "== 5/6 dağıtıcı (127.0.0.1:8010)"
docker run --rm -v "$PWD/nginx.conf:/etc/nginx/nginx.conf:ro" --network editor-net nginx:1.29-alpine nginx -t
docker compose up -d
for i in $(seq 1 10); do curl -fs -m 3 http://127.0.0.1:8010/dispatch/health >/dev/null && break; sleep 2; done
curl -fs -m 60 http://127.0.0.1:8010/v1/models | grep -q nanobaseAI || { echo "DUR: dağıtıcı modele ulaşamıyor"; exit 1; }

echo "== 6/6 ters tünel 8001 yerine dağıtıcıya (BI birkaç saniye modelsiz kalır)"
cp /etc/systemd/system/editor-gpu-tunnel.service /root/editor-gpu-tunnel.service.pre-dispatch
sed -i 's|-R 127.0.0.1:18885:127.0.0.1:8001|-R 127.0.0.1:18885:127.0.0.1:8010|' /etc/systemd/system/editor-gpu-tunnel.service
grep -q '18885:127.0.0.1:8010' /etc/systemd/system/editor-gpu-tunnel.service || { echo "DUR: tünel birimi değişmedi"; exit 1; }
systemctl daemon-reload && systemctl restart editor-gpu-tunnel.service
sleep 5; systemctl is-active editor-gpu-tunnel.service

echo "== bitti: iki kart da BI prompt'larına cevap veriyor. Kontrol: curl -si http://127.0.0.1:8010/v1/models | grep X-Served-By"
