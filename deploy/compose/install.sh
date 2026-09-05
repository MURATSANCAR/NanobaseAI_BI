#!/usr/bin/env bash
# NanobaseAI BI — tek komutla müşteri kurulumu
#
#   ./install.sh                  LLM harici sunucuda (LLM_API_BASE / LLM_API_KEY .env'de)
#   ./install.sh --with-gpu-llm   LLM'i bu makinede çalıştır (NVIDIA GPU + nvidia-container-toolkit)
#   ./install.sh --with-analytics analitik paneli de kur
#   ./install.sh --with-demo      örnek raporlama DB'sini de kur (yalnız demo)
#
# Tekrar çalıştırmak güvenlidir (idempotent): mevcut .env ve gizli değerler korunur.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

log()  { printf '\033[1;34m[nanobaseai-bi]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[nanobaseai-bi] HATA:\033[0m %s\n' "$*" >&2; exit 1; }

WITH_GPU_LLM=0; WITH_ANALYTICS=0; WITH_DEMO=0
for a in "$@"; do
  case "$a" in
    --with-gpu-llm) WITH_GPU_LLM=1 ;;
    --with-analytics) WITH_ANALYTICS=1 ;;
    --with-demo) WITH_DEMO=1 ;;
    -h|--help) sed -n 2,10p "$0"; exit 0 ;;
    *) die "bilinmeyen seçenek: $a" ;;
  esac
done

# --- 0. ön koşullar ---------------------------------------------------------
command -v docker >/dev/null || die "docker bulunamadı (https://docs.docker.com/engine/install/)"
docker compose version >/dev/null 2>&1 || die "docker compose v2 gerekli"
if [[ $WITH_GPU_LLM == 1 ]]; then
  docker info 2>/dev/null | grep -qi nvidia || die "nvidia-container-toolkit kurulu değil (docker info içinde 'nvidia' runtime yok)"
fi

# --- 1. .env ve gizli değerler ---------------------------------------------
[[ -f .env ]] || { cp .env.example .env; log ".env oluşturuldu (.env.example kopyası)"; }
set -a; . ./.env; set +a

gen_secret() { openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n'; }
set_env_if_empty() {
  local key="$1" val="$2"
  if ! grep -qE "^${key}=.+" .env; then
    if grep -qE "^${key}=" .env; then
      sed -i.bak "s|^${key}=.*|${key}=${val}|" .env && rm -f .env.bak
    else
      printf '%s=%s\n' "$key" "$val" >> .env
    fi
    log "$key üretildi"
  fi
}
for k in META_DB_PASSWORD JWT_SECRET QG_SERVICE_JWT_SECRET QG_HMAC_SECRET EMBED_API_KEY; do
  set_env_if_empty "$k" "$(gen_secret)"
done
if [[ $WITH_GPU_LLM == 1 ]]; then set_env_if_empty LLM_API_KEY "$(gen_secret)"; fi
if [[ $WITH_ANALYTICS == 1 ]]; then
  for k in ANALYTICS_DB_PASSWORD ANALYTICS_SECRET_KEY ANALYTICS_GUEST_SECRET ANALYTICS_ADMIN_PASSWORD; do
    set_env_if_empty "$k" "$(gen_secret)"
  done
  sed -i.bak 's|^ANALYTICS_ENABLED=.*|ANALYTICS_ENABLED=true|' .env && rm -f .env.bak
fi
set -a; . ./.env; set +a

DATA_DIR="${DATA_DIR:-./data}"; SECRETS_DIR="${SECRETS_DIR:-./secrets}"; MODELS_DIR="${MODELS_DIR:-./models}"
mkdir -p "$DATA_DIR" "$SECRETS_DIR" "$MODELS_DIR/embedding" "$MODELS_DIR/llm"
chmod 700 "$SECRETS_DIR"
[[ -s "$SECRETS_DIR/bi-meta-db.password" ]] || { printf '%s' "$META_DB_PASSWORD" > "$SECRETS_DIR/bi-meta-db.password"; chmod 600 "$SECRETS_DIR/bi-meta-db.password"; }
# demo DB şifreleri (compose secrets dosyaları var olmak zorunda)
[[ -s "$SECRETS_DIR/reporting-admin.password" ]] || { gen_secret > "$SECRETS_DIR/reporting-admin.password"; chmod 600 "$SECRETS_DIR/reporting-admin.password"; }
if [[ $WITH_DEMO == 1 ]]; then
  [[ -s "$SECRETS_DIR/reporting-ro.password" ]] || { gen_secret > "$SECRETS_DIR/reporting-ro.password"; chmod 600 "$SECRETS_DIR/reporting-ro.password"; }
else
  # reporting-ro.password YOKSA gateway/api demo DB'yi kaydetmez — dosya boş kalsın
  [[ -e "$SECRETS_DIR/reporting-ro.password" ]] || : > "$SECRETS_DIR/reporting-ro.password"
fi
[[ -s "$SECRETS_DIR/postgres-ro.datasources.json" ]] || printf '{ "sources": {} }\n' > "$SECRETS_DIR/postgres-ro.datasources.json"
[[ -s "$DATA_DIR/connection.json" ]] || printf '{ "active_id": null, "sources": {} }\n' > "$DATA_DIR/connection.json"
# konteyner kullanıcısı (uid 10001) yazabilsin
chown -R 10001:10001 "$DATA_DIR" "$SECRETS_DIR" 2>/dev/null || chmod -R a+rwX "$DATA_DIR" "$SECRETS_DIR"

# --- 2. model dosyaları -------------------------------------------------------
hf_download() { # repo, local_dir, include-pattern...
  local repo="$1" dest="$2"; shift 2
  local inc=(); for p in "$@"; do inc+=(--include "$p"); done
  docker run --rm -e HF_HUB_ENABLE_HF_TRANSFER=1 ${HF_TOKEN:+-e HF_TOKEN="$HF_TOKEN"} \
    -v "$(cd "$dest" && pwd)":/dl -w /dl python:3.11-slim bash -c \
    "pip install -q 'huggingface_hub[hf_transfer]' >/dev/null && hf download '$repo' ${inc[*]} --local-dir /dl && chown -R $(id -u):$(id -g) /dl"
}
if [[ ! -s "$MODELS_DIR/embedding/${EMBED_MODEL_FILE}" ]]; then
  log "gömme modeli indiriliyor: ${EMBED_HF_REPO}/${EMBED_MODEL_FILE}"
  hf_download "$EMBED_HF_REPO" "$MODELS_DIR/embedding" "$EMBED_MODEL_FILE"
fi
if [[ $WITH_GPU_LLM == 1 ]]; then
  if [[ ! -s "$MODELS_DIR/llm/${LLM_MODEL_FILE}" ]]; then
    log "LLM ağırlıkları indiriliyor (~94 GB): ${LLM_HF_REPO} ${LLM_HF_INCLUDE}"
    hf_download "$LLM_HF_REPO" "$MODELS_DIR/llm" "$LLM_HF_INCLUDE" "$LLM_DRAFT_HF_FILE"
  fi
fi

# --- 3. imajlar ve servisler -----------------------------------------------
PROFILES=()
[[ $WITH_GPU_LLM == 1 ]] && PROFILES+=(--profile gpu-llm)
[[ $WITH_ANALYTICS == 1 ]] && PROFILES+=(--profile analytics)
[[ $WITH_DEMO == 1 ]] && PROFILES+=(--profile demo)
compose() { docker compose "${PROFILES[@]}" "$@"; }

log "imajlar derleniyor"
compose build
log "altyapı başlatılıyor (meta-db, redis, qdrant, embedding, gateway)"
compose up -d meta-db redis qdrant embedding gateway
[[ $WITH_DEMO == 1 ]] && compose up -d demo-db
[[ $WITH_GPU_LLM == 1 ]] && { log "LLM başlatılıyor (ilk yükleme birkaç dakika sürer)"; compose up -d llm; }

log "meta veritabanı şeması uygulanıyor (alembic)"
compose run --rm --no-deps -w /app/backend/nanobase_api api alembic -c alembic.ini upgrade head

log "API, işçi ve web başlatılıyor"
compose up -d api worker web
[[ $WITH_ANALYTICS == 1 ]] && compose up -d superset-db superset

# --- 4. sağlık ---------------------------------------------------------------
PORT="${PUBLIC_HTTP_PORT:-80}"
for i in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${PORT}/api/v1/bi/health" >/dev/null 2>&1; then
    log "hazır → http://<sunucu-adresi>:${PORT}${WEB_BASE_PATH:-/}"
    curl -fsS "http://127.0.0.1:${PORT}/api/v1/bi/health" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("  durum:", d.get("status"), "| llm:", d.get("llm"), "| gateway:", d.get("query_gateway"), "| redis:", d.get("redis"))' 2>/dev/null || true
    log "sonraki adım: müşteri veritabanını bağlayın → ./add-datasource.sh --help"
    exit 0
  fi
  sleep 5
done
die "API 5 dakikada hazır olmadı — 'docker compose logs api' ile inceleyin"
