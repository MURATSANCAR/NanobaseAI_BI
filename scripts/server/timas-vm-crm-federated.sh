#!/usr/bin/env bash
# ⚠️ UYARI (2026-09-19 denemesi): Bu betiğin KATALOG TAŞIMA stratejisi kusurlu. Tanım tablolarını
# (sl_concept/sl_mapping/sl_schema_profile...) test'ten VM'e kopyalayıp sl_catalog_version'ı BIRAKMAK,
# sürüm tutarsızlığı yarattı: federated açılınca temel Logo sorusu 81.760 yerine 0 döndü (gerileme),
# CRM SQL_INVALID, IKISI federated'a girmedi. --rollback ile geri alındı, üretim kurtarıldı. TEKRAR
# KOŞMADAN ÖNCE düzelt: ya sl_catalog_version dâhil TAM katalog taşı, ya da VM'de gerçek tarama+madencilik
# koştur. Ayrıntı: docs/GELISTIRME-GUNLUGU.md 2026-09-19 kaydı.
# TİMAŞ BI VM'inde (192.168.0.55) iki kaynaklı (CRM × Logo) sorguları açar.
# Bu sunucuda (nanobase-direct) çalıştırılır; VM'e tun0 üzerinden bağlanır. ÖNCE kod yayını yapılmış olmalı.
#
#   bash scripts/server/timas-vm-crm-federated.sh            # kur + doğrula
#   bash scripts/server/timas-vm-crm-federated.sh --rollback # yedekten katalog + .env/override geri al
#
# Adımlar (hepsi geri alınabilir): 1) VM katalog yedeği  2) CRM secret VM'e  3) tanım tabloları test→VM
# 4) docker-compose.override.yml CRM mount  5) .env SEMANTIC_FEDERATED=1 + CRM yolu  6) yeniden yarat + doğrula
set -euo pipefail

VM="${VM:-timas-vm}"
VM_DIR="${VM_DIR:-/home/ai/bi-docker/infra/docker/bi}"
SRC_SECRET="${SRC_SECRET:-/data/nanobaseai/bi/secrets/crm-mssql-connection.json}"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=15"
DEFS="sl_schema_profile sl_concept sl_mapping sl_evidence sl_candidate sl_counter_evidence sl_coverage sl_vocabulary sl_schema_annotation"
STAMP=$(date +%Y%m%d-%H%M%S)

# server → VM → docker db → psql, SQL stdin'den (tırnak sorunu yok)
vm_psql_stdin() { $SSH "$VM" "cd '$VM_DIR' && docker compose exec -T db psql -U bi_meta -d bi_meta $* -f -"; }

if [[ "${1:-}" == "--rollback" ]]; then
  echo "== .env + override geri alınıyor, katalog yedekten yükleniyor"
  $SSH "$VM" bash -s <<'RB'
set -e
cd /home/ai/bi-docker/infra/docker/bi
[ -f .env.before-crm ] && cp .env.before-crm .env && chmod 600 .env && echo ".env geri alındı"
if [ -f docker-compose.override.yml.before-crm ]; then cp docker-compose.override.yml.before-crm docker-compose.override.yml; else rm -f docker-compose.override.yml; fi
LAST=$(ls -t ~/timas-vm-catalog-before-crm-*.sql.gz 2>/dev/null | head -1)
if [ -n "$LAST" ]; then echo "katalog geri yükleniyor: $LAST"; gunzip -c "$LAST" | docker compose exec -T db psql -U bi_meta -d bi_meta -q >/dev/null && echo "katalog geri yüklendi"; fi
docker compose up -d bridge jobs
RB
  echo "geri alma bitti"; exit 0
fi

DSN=$(sudo grep -E '^SEMANTIC_STORE_DSN=' /etc/nanobase/semantic-bridge.env | cut -d= -f2- | sed 's/+psycopg2//')

echo "== 0/6 önkoşullar"
$SSH "$VM" 'echo ok >/dev/null' || { echo "HATA: VM'e ulaşılamıyor (tun0 kapalı olabilir)."; exit 1; }
sudo test -s "$SRC_SECRET" || { echo "HATA: $SRC_SECRET yok."; exit 1; }
$SSH "$VM" 'grep -q _with_bridges /home/ai/bi-docker/backend/semantic_layer/runtime/compiler.py' \
  || { echo "HATA: VM kodu güncel değil (önce deploy-customer-vm.sh)."; exit 1; }
echo "önkoşullar tamam"

echo "== 1/6 VM kataloğu yedekleniyor"
BK="~/timas-vm-catalog-before-crm-$STAMP.sql.gz"
$SSH "$VM" "cd '$VM_DIR' && docker compose exec -T db pg_dump -U bi_meta -d bi_meta --clean --if-exists $(for t in $DEFS; do printf -- '-t %s ' "$t"; done) | gzip > $BK && echo 'yedek boyutu:' && du -h $BK | cut -f1"

echo "== 2/6 CRM secret VM'e kopyalanıyor"
sudo cat "$SRC_SECRET" | $SSH "$VM" "cat > '$VM_DIR/secrets/crm-mssql-connection.json' && chmod 600 '$VM_DIR/secrets/crm-mssql-connection.json' && echo 'secret yazıldı, host:' && python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))[\"host\"])' '$VM_DIR/secrets/crm-mssql-connection.json'"

echo "== 3/6 katalog tanım tabloları test → VM (tek işlem, hata olursa durur)"
tmp=$(mktemp)
{
  echo "BEGIN;"
  echo "SET session_replication_role = replica;"
  echo "TRUNCATE $(echo $DEFS | tr ' ' ',') CASCADE;"
  pg_dump "$DSN" --data-only --disable-triggers $(for t in $DEFS; do printf -- '-t %s ' "$t"; done)
  echo "COMMIT;"
} > "$tmp"
echo "yüklenecek dosya boyutu:"; du -h "$tmp" | cut -f1
vm_psql_stdin -v ON_ERROR_STOP=1 -q < "$tmp" && echo "katalog yüklendi"
rm -f "$tmp"
echo "VM'de CRM kavram + kaynak-arası bağ sayısı:"
printf "select (select count(*) from sl_concept c join sl_mapping m on m.concept_id=c.id join sl_schema_profile p on upper(p.entity)=upper(m.entity) where p.schema_name ilike 'Timas_MSCRM%%' and c.status='CERTIFIED') crm_kavram, (select count(*) from sl_schema_profile p, jsonb_array_elements(relationships_json) r where (r->>'cross_source')='true') cross_bag;\n" | vm_psql_stdin -tA

echo "== 4/6 docker-compose.override.yml (CRM mount)"
ovr=$(mktemp)
cat > "$ovr" <<'YML'
# timas-vm-crm-federated.sh: CRM secret'ini motor container'larına ekler. deploy-customer-vm.sh bunu ezmez.
services:
  bridge:
    volumes:
      - ./secrets/crm-mssql-connection.json:/app/secrets/crm-mssql-connection.json:ro
  jobs:
    volumes:
      - ./secrets/crm-mssql-connection.json:/app/secrets/crm-mssql-connection.json:ro
YML
$SSH "$VM" "cd '$VM_DIR' && { [ -f docker-compose.override.yml ] && cp docker-compose.override.yml docker-compose.override.yml.before-crm || true; } && cat > docker-compose.override.yml" < "$ovr"
rm -f "$ovr"
$SSH "$VM" "cd '$VM_DIR' && docker compose config -q && echo 'override geçerli'"

echo "== 5/6 .env: CRM yolu + federated"
$SSH "$VM" bash -s <<'ENV'
set -e
cd /home/ai/bi-docker/infra/docker/bi
[ -f .env.before-crm ] || cp .env .env.before-crm
put(){ if grep -q "^$1=" .env; then sed -i "s#^$1=.*#$1=$2#" .env; else printf '%s=%s\n' "$1" "$2" >> .env; fi; }
put SEMANTIC_CRM_CONNECTION_FILE /app/secrets/crm-mssql-connection.json
put SEMANTIC_FEDERATED 1
chmod 600 .env
echo ".env güncellendi"
ENV

echo "== 6/6 bridge+jobs yeniden yaratılıyor ve doğrulama"
$SSH "$VM" "cd '$VM_DIR' && docker compose up -d bridge jobs && sleep 25 && docker compose ps --format '{{.Service}} {{.State}} {{.Status}}'"
$SSH "$VM" bash -s <<'VERIFY'
set -e
cd /home/ai/bi-docker/infra/docker/bi
T=$(grep -E '^SEMANTIC_CALLER_TOKEN=' .env | cut -d= -f2-)
docker compose exec -T -e T="$T" bridge python - <<'PY'
import json, os, urllib.request
def ask(q):
    r=urllib.request.Request('http://127.0.0.1:8795/api/v1/ask', data=json.dumps({'question':q}).encode(),
        headers={'X-Semantic-Caller':os.environ['T'],'Content-Type':'application/json'})
    d=json.load(urllib.request.urlopen(r,timeout=180)); return d.get('type'),d.get('rowCount'),d.get('federated'),(d.get('summary') or d.get('explanation') or '')[:80]
for et,q in [('LOGO','bu yil kac fatura kesildi'),('CRM','kac aktif sozlesme var'),('IKISI','bu yil satis hedefi ile gerceklesen ciroyu kitap bazinda karsilastir')]:
    try:
        t,n,f,s=ask(q); print(f'{et}: tip={t} satir={n} federated={f} | {s}')
    except Exception as e:
        print(f'{et}: HATA {str(e)[:120]}')
PY
VERIFY
echo
echo "BİTTİ. Geri almak: bash scripts/server/timas-vm-crm-federated.sh --rollback"
