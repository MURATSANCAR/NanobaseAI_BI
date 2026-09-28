#!/usr/bin/env bash
# Zeki AI sesli not servisini TT GPU'ya kurar (GPU'da çalıştırılır; derleme yok).
#
#   VOICE_SRC=/tmp/voice-note-src/apps/voice-note  VOICE_MODEL=<hf-depo-adı>  ./install.sh
#
# VOICE_SRC: `git archive main apps/voice-note deploy/tt-gpu/voice-note | ssh tt-gpu tar -x -C /tmp/voice-note-src`
# ile gelen kaynak (Mac artığı ._* taşımaz). VOICE_MODEL: ölçümle seçilen model (OLCUM.md); yoksa indirilir
# (hazır vLLM imajındaki huggingface_hub ile, /data/voice-note/models/<ad>), `current` bağı ona çevrilir.
# Anahtar /data/voice-note/voice-note.env'de yoksa üretilir (0600); değer ekrana basılmaz.
# Çalışan hiçbir başka servise dokunmaz; yalnız voice-note konteynerini kurar/yeniler.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
SRC="${VOICE_SRC:?apps/voice-note kaynak yolu}"
MODEL="${VOICE_MODEL:-openai/whisper-large-v3}"  # OLCUM.md: seçilen model
ROOT=/data/voice-note
IMG=vllm/vllm-openai:v0.27.1

sudo mkdir -p "$ROOT/app" "$ROOT/models"
sudo chown -R "$(id -u):$(id -g)" "$ROOT"

# 1) kod: yalnız paket, Mac artığı ve önbellek olmadan
rm -rf "$ROOT/app.new" && mkdir -p "$ROOT/app.new"
cp -a "$SRC/voice_note_service" "$ROOT/app.new/"
find "$ROOT/app.new" \( -name '._*' -o -name '__pycache__' \) -prune -exec rm -rf {} +
rm -rf "$ROOT/app.old" && { [ -d "$ROOT/app" ] && mv "$ROOT/app" "$ROOT/app.old" || true; } && mv "$ROOT/app.new" "$ROOT/app"

# 2) model (yalnız eksikse indirilir)
DIR="$ROOT/models/${MODEL//\//__}"
if [ ! -f "$DIR/config.json" ]; then
  docker run --rm -e HF_HUB_DISABLE_XET=1 -v "$ROOT/models:/m" --entrypoint python3 "$IMG" -c "
from huggingface_hub import snapshot_download
snapshot_download('$MODEL', local_dir='/m/${MODEL//\//__}', allow_patterns=['*.json','*.txt','*.jinja','model.safetensors','model-0*.safetensors'], max_workers=8)
print('indirildi')"
fi
ln -sfn "$DIR" "$ROOT/models/current"

# 3) anahtar
if [ ! -s "$ROOT/voice-note.env" ]; then
  umask 077
  printf 'VOICE_TOKEN=%s\n' "$(openssl rand -hex 32)" > "$ROOT/voice-note.env"
  echo "yeni anahtar üretildi: $ROOT/voice-note.env (köprü ortamına VOICE_NOTE_TOKEN olarak aynı değer yazılır)"
fi
chmod 600 "$ROOT/voice-note.env"

# 4) kaldır ve hazır olana dek bekle
cd "$HERE" && docker compose -f compose.yaml up -d --force-recreate
for i in $(seq 1 60); do
  if curl -sf http://127.0.0.1:8797/health | grep -q '"ready": *true'; then
    curl -s http://127.0.0.1:8797/health; echo
    echo "Mac artığı: $(find "$ROOT/app" -name '._*' -type f | wc -l)"
    echo "imaj: $(docker inspect voice-note --format '{{.Config.Image}}')"
    exit 0
  fi
  sleep 5
done
echo "hazır olmadı"; docker logs --tail 40 voice-note; exit 1
