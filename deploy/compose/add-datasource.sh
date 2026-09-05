#!/usr/bin/env bash
# NanobaseAI BI — müşteri veritabanını (uzak PostgreSQL, salt-okunur) bağla
#
#   ./add-datasource.sh --id erp --label "ERP" --host db.musteri.local --port 5432 \
#       --database erpdb --user bi_ro [--no-ssl] [--schemas public,sales] [--tables "*"]
#   ./add-datasource.sh --type mssql --id logo --label "Logo ERP" --host 192.168.0.155 --port 1433 \
#       --database LOGO_DB --user 'DOMAIN\\bi_ro' --schemas dbo --patterns "LG_411_01_%,LG_411_[A-Z]%"
#
# --type postgres (varsayılan) | mssql (Microsoft SQL Server; --patterns ile taranacak tablo
#   desenleri (T-SQL LIKE) verilir — ERP veritabanlarında binlerce tablo vardır).
#
# Şifre güvenli biçimde sorulur (ya da PGPASSWORD ortam değişkeninden okunur) ve
# secrets/<id>.password dosyasına yazılır. Kaynak, Query Gateway izin listesine
# eklenir, şema taraması başlatılır ve aktif kaynak yapılır.
#
# Kullanıcı SADECE SELECT yetkili olmalıdır; yazma yetkisi olan hesap kullanmayın.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
log() { printf '\033[1;34m[nanobaseai-bi]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[nanobaseai-bi] HATA:\033[0m %s\n' "$*" >&2; exit 1; }

ID=""; LABEL=""; HOST=""; PORT=""; DB=""; USER_=""; SSL=1; SCHEMAS=""; TABLES="*"; TYPE="postgres"; PATTERNS=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --id) ID="$2"; shift 2 ;;
    --label) LABEL="$2"; shift 2 ;;
    --host) HOST="$2"; shift 2 ;;
    --port) PORT="$2"; shift 2 ;;
    --database) DB="$2"; shift 2 ;;
    --user) USER_="$2"; shift 2 ;;
    --no-ssl) SSL=0; shift ;;
    --schemas) SCHEMAS="$2"; shift 2 ;;
    --tables) TABLES="$2"; shift 2 ;;
    --type) TYPE="$2"; shift 2 ;;
    --patterns) PATTERNS="$2"; shift 2 ;;
    -h|--help) sed -n 2,12p "$0"; exit 0 ;;
    *) die "bilinmeyen seçenek: $1" ;;
  esac
done
[[ -n "$ID" && -n "$HOST" && -n "$DB" && -n "$USER_" ]] || die "--id, --host, --database, --user zorunlu (bkz. --help)"
[[ "$ID" =~ ^[a-z][a-z0-9_]{1,31}$ ]] || die "--id yalnız küçük harf/rakam/alt çizgi (örn. erp)"
[[ "$TYPE" == "postgres" || "$TYPE" == "mssql" ]] || die "--type postgres | mssql"
if [[ "$TYPE" == "mssql" ]]; then PORT="${PORT:-1433}"; SCHEMAS="${SCHEMAS:-dbo}"; else PORT="${PORT:-5432}"; SCHEMAS="${SCHEMAS:-public}"; fi
[[ -f .env ]] || die "önce ./install.sh çalıştırın"
set -a; . ./.env; set +a
SECRETS_DIR="${SECRETS_DIR:-./secrets}"; PORT_HTTP="${PUBLIC_HTTP_PORT:-80}"

if [[ -z "${PGPASSWORD:-}" ]]; then
  read -r -s -p "Veritabanı şifresi ($USER_@$HOST): " PGPASSWORD; echo
fi
[[ -n "$PGPASSWORD" ]] || die "şifre boş"

PW_FILE="$SECRETS_DIR/${ID}.password"
printf '%s' "$PGPASSWORD" > "$PW_FILE"; chmod 600 "$PW_FILE"; chown 10001:10001 "$PW_FILE" 2>/dev/null || true

if [[ "$TYPE" == "mssql" ]]; then MAP="$SECRETS_DIR/mssql-ro.datasources.json"; else MAP="$SECRETS_DIR/postgres-ro.datasources.json"; fi
[[ -s "$MAP" ]] || printf '{ "sources": {} }\n' > "$MAP"
ID="$ID" LABEL="${LABEL:-$ID}" HOST="$HOST" PORT="$PORT" DB="$DB" USER_="$USER_" SSL="$SSL" SCHEMAS="$SCHEMAS" TABLES="$TABLES" MAP="$MAP" TYPE="$TYPE" PATTERNS="$PATTERNS" \
python3 - <<'PY'
import json, os
p = os.environ["MAP"]
raw = json.load(open(p))
raw.setdefault("sources", {})
schemas = [s.strip() for s in os.environ["SCHEMAS"].split(",") if s.strip()]
tables = os.environ["TABLES"].strip()
if os.environ["TYPE"] == "mssql":
    entry = {
        "label": os.environ["LABEL"],
        "driver": "mssql",
        "dialect": "mssql",
        "host": os.environ["HOST"],
        "port": int(os.environ["PORT"]),
        "database": os.environ["DB"],
        "user": os.environ["USER_"],
        "password_file": f"/secrets/{os.environ['ID']}.password",
        "allowed_schemas": schemas,
        "allowed_tables": "*" if tables == "*" else [t.strip() for t in tables.split(",") if t.strip()],
        "table_patterns": [x.strip() for x in os.environ["PATTERNS"].split(",") if x.strip()],
        "size_profile": "large",
    }
else:
  entry = {
    "label": os.environ["LABEL"],
    "driver": "postgresql",
    "dialect": "postgres",
    "host": os.environ["HOST"],
    "port": int(os.environ["PORT"]),
    "database": os.environ["DB"],
    "user": os.environ["USER_"],
    "password_file": f"/secrets/{os.environ['ID']}.password",
    "sslmode": "require" if os.environ["SSL"] == "1" else "disable",
    "allowed_schemas": schemas,
    "allowed_tables": "*" if tables == "*" else [t.strip() for t in tables.split(",") if t.strip()],
    "size_profile": "medium",
  }
raw["sources"][os.environ["ID"]] = entry
json.dump(raw, open(p, "w"), indent=2, ensure_ascii=False)
print(f"  kaynak yazıldı: {os.environ['ID']} → {p}")
PY
chown 10001:10001 "$MAP" 2>/dev/null || true

log "gateway ve api yeniden başlatılıyor (yeni kaynak yüklensin)"
docker compose restart gateway api worker >/dev/null

API="http://127.0.0.1:${PORT_HTTP}/api/v1/bi"
for i in $(seq 1 40); do curl -fsS "$API/health" >/dev/null 2>&1 && break; sleep 3; done

log "bağlantı testi"
curl -fsS -X POST "$API/sources/${ID}/test" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("  ok:", d.get("ok", d.get("success")), "| via:", d.get("via", "meta"))' \
  || die "bağlantı testi başarısız — host/port/şifre/SSL ayarlarını ve DB tarafındaki erişim kurallarını kontrol edin"

log "şema taraması başlatılıyor (arka planda; süre tablo sayısına bağlıdır)"
curl -fsS -X POST "$API/sources/${ID}/scan" | python3 -c 'import json,sys; d=json.load(sys.stdin); print("  tarama:", d.get("scan_id") or d.get("id") or d)' || log "tarama başlatılamadı — arayüzden Kaynaklar › Tara ile tekrar deneyin"

log "aktif kaynak yapılıyor"
curl -fsS -X POST "$API/sources/${ID}/activate" >/dev/null && log "tamam — arayüzde '${LABEL:-$ID}' kaynağı ile soru sorabilirsiniz"
