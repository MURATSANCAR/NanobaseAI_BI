#!/bin/sh
# Müzik modellerini indirir (muzik_indir.py). Sistem diskine yazmaz: salt okunur kap, günlük kapalı, --restart no.
# /data/editor/secrets/hf-token varsa (Stable Audio 3 kapılı deposu için okuma anahtarı) yalnız o dosya salt okunur
# bağlanır. Yeniden çalıştırmak güvenlidir: biten model atlanır, yarım kalan sürer.
set -e
I=/data/editor/models/_indirme
M=$I/muzik
TOKEN=""
[ -s /data/editor/secrets/hf-token ] && TOKEN="-v /data/editor/secrets/hf-token:/run/hf-token:ro"
docker rm muzik-indir >/dev/null 2>&1 || true
echo "---- $(date '+%F %T') muzik_baslat.sh (anahtar: $([ -n "$TOKEN" ] && echo var || echo yok))" >> $I/muzik.log
# shellcheck disable=SC2086
docker run -d --name muzik-indir --restart no --log-driver none --read-only --tmpfs /tmp:size=64m --network host \
  --user "$(id -u gpuubuntu):$(id -g gpuubuntu)" -v /data/editor/models:/data/editor/models $TOKEN \
  -e HOME=$M/home -e HF_HOME=$M/hf-home -e TMPDIR=$M/tmp -e HF_HUB_DISABLE_XET=1 \
  --entrypoint sh vllm/vllm-openai:v0.29.0 -c "python3 $I/muzik_indir.py >> $I/muzik.log 2>&1"
