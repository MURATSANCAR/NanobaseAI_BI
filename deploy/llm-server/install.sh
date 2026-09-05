#!/usr/bin/env bash
# NanobaseAI BI LLM — GPU sunucusuna (Docker'sız) kurulum
#   sudo ./install.sh            # llama.cpp derler, ağırlıkları indirir, systemd servisini kurar
# Gereksinim: NVIDIA sürücü + CUDA toolkit (nvcc), cmake, gcc, git, python3, ≥128 GB RAM, ≥120 GB disk
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
log() { printf '\033[1;34m[nanobaseai-bi-llm]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[nanobaseai-bi-llm] HATA:\033[0m %s\n' "$*" >&2; exit 1; }

PREFIX=/opt/nanobaseai
MODELS_DIR="${MODELS_DIR:-$PREFIX/models/llm}"
SVC_USER="${SVC_USER:-nanobaseai}"
LLAMA_CPP_REF="${LLAMA_CPP_REF:-refs/pull/28243/head}"   # MTP desteği; ana dala girince: master
CUDA_ARCH="${CUDA_ARCH:-86}"                              # A40/A10/RTX30xx=86, RTX40xx/L4=89, H100=90, A100=80
HF_REPO="${HF_REPO:-unsloth/Qwen3.8-Flash-Next-GGUF}"
HF_INCLUDE="${HF_INCLUDE:-UD-IQ4_XS/*}"
HF_DRAFT="${HF_DRAFT:-MTP/mtp-Qwen3.8-Flash-Next-shared-Q8_0.gguf}"

[[ $EUID -eq 0 ]] || die "root olarak çalıştırın (sudo)"
command -v nvidia-smi >/dev/null || die "NVIDIA sürücüsü yok"
NVCC="$(command -v nvcc || ls /usr/local/cuda/bin/nvcc 2>/dev/null || true)"; [[ -n "$NVCC" ]] || die "nvcc (CUDA toolkit) bulunamadı"
for c in cmake gcc git python3; do command -v "$c" >/dev/null || die "$c gerekli"; done

id -u "$SVC_USER" >/dev/null 2>&1 || useradd -r -m -d "$PREFIX" -s /usr/sbin/nologin "$SVC_USER"
mkdir -p "$PREFIX" "$MODELS_DIR" /etc/nanobaseai
chown -R "$SVC_USER:$SVC_USER" "$PREFIX"

# 1) llama.cpp (CUDA)
if [[ ! -x "$PREFIX/llm/bin/llama-server" ]]; then
  log "llama.cpp derleniyor ($LLAMA_CPP_REF, sm_$CUDA_ARCH)"
  rm -rf "$PREFIX/llm-src"; git clone -q https://github.com/ggml-org/llama.cpp "$PREFIX/llm-src"
  git -C "$PREFIX/llm-src" fetch -q origin "$LLAMA_CPP_REF" && git -C "$PREFIX/llm-src" checkout -q FETCH_HEAD
  PATH="$(dirname "$NVCC"):$PATH" cmake -S "$PREFIX/llm-src" -B "$PREFIX/llm-src/build" -DCMAKE_BUILD_TYPE=Release \
    -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES="$CUDA_ARCH" -DLLAMA_CURL=ON -DGGML_NATIVE=ON >/dev/null
  cmake --build "$PREFIX/llm-src/build" --config Release -j "$(nproc)" --target llama-server >/dev/null
  mkdir -p "$PREFIX/llm/bin"; cp "$PREFIX/llm-src/build/bin/"* "$PREFIX/llm/bin/"
fi

# 2) ağırlıklar
if [[ ! -s "$MODELS_DIR/${HF_INCLUDE%/*}/$(basename "$HF_DRAFT" | sed 's/.*/&/')" && -z "$(ls "$MODELS_DIR/${HF_INCLUDE%/*}" 2>/dev/null)" ]]; then
  log "ağırlıklar indiriliyor (~94 GB + 2.6 GB MTP)"
  python3 -m pip install -q --user "huggingface_hub[hf_transfer]" 2>/dev/null || python3 -m pip install -q --user --break-system-packages "huggingface_hub[hf_transfer]"
  HF_HUB_ENABLE_HF_TRANSFER=1 "$HOME/.local/bin/hf" download "$HF_REPO" --include "$HF_INCLUDE" --local-dir "$MODELS_DIR"
  HF_HUB_ENABLE_HF_TRANSFER=1 "$HOME/.local/bin/hf" download "$HF_REPO" "$HF_DRAFT" --local-dir "$MODELS_DIR"
  chown -R "$SVC_USER:$SVC_USER" "$MODELS_DIR"
fi

# 3) yapılandırma + anahtar + servis
[[ -f /etc/nanobaseai/nanobaseai-bi-llm.env ]] || { sed "s|/opt/nanobaseai/models/llm|$MODELS_DIR|g" nanobaseai-bi-llm.env.example > /etc/nanobaseai/nanobaseai-bi-llm.env; log "env yazıldı: /etc/nanobaseai/nanobaseai-bi-llm.env"; }
if [[ ! -s /etc/nanobaseai/nanobaseai-bi-llm.key ]]; then
  openssl rand -hex 20 > /etc/nanobaseai/nanobaseai-bi-llm.key
  chown "$SVC_USER" /etc/nanobaseai/nanobaseai-bi-llm.key; chmod 0400 /etc/nanobaseai/nanobaseai-bi-llm.key
  log "API anahtarı üretildi: /etc/nanobaseai/nanobaseai-bi-llm.key (BI paketinde LLM_API_KEY olarak kullanın)"
fi
sed "s|User=nanobaseai|User=$SVC_USER|; s|Group=nanobaseai|Group=$SVC_USER|" nanobaseai-bi-llm.service > /etc/systemd/system/nanobaseai-bi-llm.service
systemctl daemon-reload
systemctl enable --now nanobaseai-bi-llm.service

# 4) sağlık
for i in $(seq 1 90); do
  if curl -fsS -H "Authorization: Bearer $(cat /etc/nanobaseai/nanobaseai-bi-llm.key)" "http://127.0.0.1:$(grep -E '^LLAMA_PORT=' /etc/nanobaseai/nanobaseai-bi-llm.env | cut -d= -f2)/v1/models" >/dev/null 2>&1; then
    log "hazır — model yüklendi"; nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader; exit 0
  fi; sleep 10
done
die "servis 15 dakikada hazır olmadı: journalctl -u nanobaseai-bi-llm -n 100"
