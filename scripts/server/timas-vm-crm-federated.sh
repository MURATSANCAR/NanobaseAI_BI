#!/usr/bin/env bash
# TİMAŞ BI VM'inde (192.168.0.55) iki kaynaklı (CRM × Logo) sorguları açar.
#
# Bu sunucuda (nanobase-direct) çalıştırılır; VM'e tun0 üzerinden bağlanır. ÖNCE kod yayını
# (deploy-customer-vm.sh) yapılmış olmalı — VM kodu main ile eş değilse dur.
#
# Ne yapar (hepsi geri alınabilir):
#   1. VM kataloğunun tam yedeği (pg_dump) alınır → VM'de ~/timas-vm-catalog-before-crm-*.sql.gz
#   2. CRM bağlantı gizli dosyası test sunucusundan VM'e kopyalanır (secrets/crm-mssql-connection.json, 0600)
#   3. Katalog TANIM tabloları test → VM taşınır (kavram/eşleme/profil/kanıt/sözlük; kaynak-arası bağlar dâhil).
#      Anlık görüntü (sl_catalog_version), sorgu logu ve LLM kuyruğu TAŞINMAZ.
#   4. docker-compose.override.yml: CRM gizli dosyasını bridge+jobs container'ına mount et (deploy ezmez).
#   5. .env: SEMANTIC_CRM_CONNECTION_FILE + SEMANTIC_FEDERATED=1
#   6. bridge+jobs yeniden yaratılır; üç gerçek soruyla doğrulanır (Logo, CRM, iki kaynaklı).
#
#   bash scripts/server/timas-vm-crm-federated.sh            # kur + doğrula
#   bash scripts/server/timas-vm-crm-federated.sh --rollback # yedekten katalog + .env/override geri al
set -euo pipefail

VM="${VM:-timas-vm}"
VM_DIR="${VM_DIR:-/home/ai/bi-docker/infra/docker/bi}"
SRC_SECRET="${SRC_SECRET:-/data/nanobaseai/bi/secrets/crm-mssql-connection.json}"
SSH="ssh -o BatchMode=yes -o ConnectTimeout=15"
DEFS=(sl_schema_profile sl_concept sl_mapping sl_evidence sl_candidate sl_counter_evidence sl_coverage sl_vocabulary sl_schema_annotation)
STAMP=$(date +%Y%m%d-%H%M%S)

vm_psql() { $SSH "$VM" "cd $VM_DIR && docker compose exec -T db psql -U bi_meta -d bi_meta $*"; }

if [[ "${1:-}" == "--rollback" ]]; then
  echo "== .env ve override geri alınıyor"
  $SSH "$VM" "cd $VM_DIR
    test -f .env.before-crm && cp .env.before-crm .env && chmod 600 .env
    test -f docker-compose.override.yml.before-crm && cp docker-compose.override.yml.before-crm docker-compose.override.yml || rm -f docker-compose.override.yml
    LAST=\$(ls -t ~/timas-vm-catalog-before-crm-*.sql.gz 2>/dev/null | head -1)
    if [ -n \"\$LAST\" ]; then echo \"katalog geri yükleniyor: \$LAST\"; gunzip -c \"\$LAST\" | docker compose exec -T db psql -U bi_meta -d bi_meta -q >/dev/null && echo 'katalog geri yüklendi'; fi
    docker compose up -d bridge jobs"
  echo "geri alma bitti"; exit 0
fi

DSN=$(sudo grep -E '^SEMANTIC_STORE_DSN=' /etc/nanobase/semantic-bridge.env | cut -d= -f2- | sed 's/+psycopg2//')

echo "== 0/6 önkoşul: VM ulaşılır, CRM gizli dosyası kaynağı var, kod yeni mi"
$SSH "$VM" "echo VM-OK >/dev/null" || { echo "HATA: VM'e ulaşılamıyor (tun0 kapalı olabilir)."; exit 1; }
sudo test -s "$SRC_SECRET" || { echo "HATA: $SRC_SECRET yok."; exit 1; }
# yeni kod işareti: federated derleyicinin _with_bridges'i main'de var
$SSH "$VM" "grep -q '_with_bridges' $VM_DIR/../../../backend/semantic_layer/runtime/compiler.py 2>/dev/null" || { echo "HATA: VM kodu güncel değil (deploy-customer-vm.sh önce koşmalı)."; exit 1; }

echo "== 1/6 VM kataloğu yedekleniyor"
$SSH "$VM" "cd $VM_DIR && docker compose exec -T db pg_dump -U bi_meta -d bi_meta --clean --if-exists $(printf ' -t %s' "${DEFS[@]}") | gzip > ~/timas-vm-catalog-before-crm-$STAMP.sql.gz && echo yedek: ~/timas-vm-catalog-before-crm-$STAMP.sql.gz (\$(du -h ~/timas-vm-catalog-before-crm-$STAMP.sql.gz | cut -f1))"

echo "== 2/6 CRM gizli dosyası VM'e kopyalanıyor"
sudo cat "$SRC_SECRET" | $SSH "$VM" "cat > $VM_DIR/secrets/crm-mssql-connection.json && chmod 600 $VM_DIR/secrets/crm-mssql-connection.json && echo 'kopyalandı, host=' \$(python3 -c 'import json;print(json.load(open(\"$VM_DIR/secrets/crm-mssql-connection.json\"))[\"host\"])')"

echo "== 3/6 katalog tanım tabloları test → VM (tek işlemde, hata olursa durur)"
tmp=$(mktemp)
pg_dump "$DSN" --data-only --disable-triggers $(printf ' -t %s' "${DEFS[@]}") > "$tmp"
echo "dump boyutu: $(du -h "$tmp" | cut -f1)"
{ echo "BEGIN; SET session_replication_role = replica;"; printf 'TRUNCATE %s CASCADE;\n' "$(IFS=,; echo "${DEFS[*]}")"; cat "$tmp"; echo "COMMIT;"; } \
  | $SSH "$VM" "cd $VM_DIR && docker compose exec -T db psql -U bi_meta -d bi_meta -v ON_ERROR_STOP=1 -q" && echo "katalog yüklendi"
rm -f "$tmp"
echo "VM'de CRM kavram/bağ kontrolü:"
vm_psql -tAc "\"select (select count(*) from sl_concept c join sl_mapping m on m.concept_id=c.id join sl_schema_profile p on upper(p.entity)=upper(m.entity) where p.schema_name ilike 'Timas_MSCRM%' and c.status='CERTIFIED') crm_kavram, (select count(*) from sl_schema_profile p, jsonb_array_elements(relationships_json) r where (r->>'cross_source')='true') cross_bag\""

echo "== 4/6 docker-compose.override.yml (CRM mount, deploy ezmez)"
$SSH "$VM" "cd $VM_DIR
  test -f docker-compose.override.yml && cp docker-compose.override.yml docker-compose.override.yml.before-crm || true
  cat > docker-compose.override.yml <<'YML'
# timas-vm-crm-federated.sh: CRM gizli dosyasını motor container'larına ekler. deploy-customer-vm.sh bunu ezmez.
services:
  bridge:
    volumes:
      - ./secrets/crm-mssql-connection.json:/app/secrets/crm-mssql-connection.json:ro
  jobs:
    volumes:
      - ./secrets/crm-mssql-connection.json:/app/secrets/crm-mssql-connection.json:ro
YML
  docker compose config -q && echo 'override geçerli'"

echo "== 5/6 .env: CRM yolu + federated"
$SSH "$VM" "cd $VM_DIR
  test -f .env.before-crm || cp .env .env.before-crm
  put(){ if grep -q \"^\$1=\" .env; then sed -i \"s#^\$1=.*#\$1=\$2#\" .env; else printf '%s=%s\n' \"\$1\" \"\$2\" >> .env; fi; }
  put SEMANTIC_CRM_CONNECTION_FILE /app/secrets/crm-mssql-connection.json
  put SEMANTIC_FEDERATED 1
  chmod 600 .env"

echo "== 6/6 bridge+jobs yeniden yaratılıyor ve doğrulama"
$SSH "$VM" "cd $VM_DIR && docker compose up -d bridge jobs && sleep 25 && docker compose ps --format '{{.Service}} {{.State}} {{.Status}}'"
$SSH "$VM" "cd $VM_DIR && T=\$(grep -E '^SEMANTIC_CALLER_TOKEN=' .env | cut -d= -f2-) && docker compose exec -T -e T=\"\$T\" bridge python - <<'PY'
import json, os, urllib.request
def ask(q):
    r=urllib.request.Request('http://127.0.0.1:8795/api/v1/ask', data=json.dumps({'question':q}).encode(),
        headers={'X-Semantic-Caller':os.environ['T'],'Content-Type':'application/json'})
    d=json.load(urllib.request.urlopen(r,timeout=180))
    return d.get('type'), d.get('rowCount'), d.get('federated'), (d.get('summary') or d.get('explanation') or '')[:80]
for etiket,q in [('LOGO','bu yil kac fatura kesildi'),
                 ('CRM','kac aktif sozlesme var'),
                 ('IKISI','bu yil satis hedefi ile gerceklesen ciroyu kitap bazinda karsilastir')]:
    try: t,n,f,s = ask(q); print(f'{etiket}: tip={t} satir={n} federated={f} | {s}')
    except Exception as e: print(f'{etiket}: HATA {str(e)[:120]}')
PY"
echo
echo "BİTTİ. Geri almak: bash scripts/server/timas-vm-crm-federated.sh --rollback"
