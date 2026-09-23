#!/usr/bin/env bash
# Tüneli doğrudan GPU 0'a geri çevirir ve dağıtıcıyı kapatır:  sudo bash /data/editor/llm-dispatch/rollback.sh
# GPU 1'deki modelin fazladan 'nanobaseAI' adı kalabilir; kimse o adla oraya gitmez, zararı yok.
set -euo pipefail
cd "$(dirname "$0")"
sed -i 's|-R 127.0.0.1:18885:127.0.0.1:8010|-R 127.0.0.1:18885:127.0.0.1:8001|' /etc/systemd/system/editor-gpu-tunnel.service
systemctl daemon-reload && systemctl restart editor-gpu-tunnel.service
docker compose down
echo "tünel yeniden GPU 0'a (8001) bakıyor, dağıtıcı kapalı"
