# Finans & Bütçe Masası (yeni arayüz)

Semantik motorun (wren-ui :3000) **önüne** konan yönetim kokpiti. Motorun modelleme, deploy, thread ve
NL→SQL yetenekleri olduğu gibi kalır; bu uygulama yalnız `/api/v1/run_sql`, `/api/v1/ask` ve
`/api/graphql` uçlarını tüketir.

## Geliştirme

```bash
# 1) sunucudaki wren-ui'ye tünel (port yalnız 127.0.0.1'e bağlı)
ssh -N -L 3000:127.0.0.1:3000 nanobase

# 2) uygulama
cd apps/cockpit && npm install && npm run dev      # http://localhost:5180
```

`VITE_DATA_MODE=fixture` ile motor olmadan (gerçek Logo rakamlarından alınmış önbellekle) çalışır;
`auto` (varsayılan) önce canlıyı dener, olmazsa önbelleğe düşer ve üst çubukta **ÖNBELLEK** yazar.

## Üretim (WrenAI main / open-core hattı, 2026-09-06)

Motor artık **WrenAI `main`** (`pip install 'wrenai[mssql,memory]'`, sürüm 0.13.4 = `core/wren`) — legacy
`v1-final` Docker yığını (wren-ui / wren-ai-service / ibis) kullanılmaz. Cockpit sözleşmesini
(`/api/v1/run_sql`, `/api/v1/ask`, `/api/v1/engine`) `backend/wren_bridge` (FastAPI :8794) sunar: engine
süreç içinde (DataFusion + MDL, FreeTDS ODBC ile SQL Server), NL→SQL orkestrasyonu bizim LLM'de
(kurallar → anımsanan soru→SQL çiftleri → şema bağlamı → SQL → dry_run → run_sql → özet).

```bash
# proje (legacy MDL + bilgi kayıtlarından üretildi): /data/nanobaseai/bi/wren-project/logo_timas
python3 tools/wren/legacy_to_project.py --mdl mdl-legacy.json --knowledge knowledge-legacy.json --out logo_timas --profile logo-tunnel
./scripts/server/deploy-wren-bridge.sh      # context build + memory index + smoke + systemd nanobase-wren-bridge
./scripts/server/switch-timas-api.sh bridge # nginx /timas/api/ → :8794  (legacy: ... legacy)
VITE_BASE=/timas/ VITE_WREN_BASE=/timas npm run build && rsync dist/ nanobase:/data/nanobaseai/bi/cockpit/dist/
```

Ajanlar için MCP: `cd /data/nanobaseai/bi/wren-project/logo_timas && wren serve mcp --transport http --port 8090`
(araçlar: run_sql, dry_run, dry_plan, get_mdl, describe_schema, get_instructions, recall_queries, get_context).

## Veri kuralları (Logo, firma 411 = 2026)

`src/lib/metrics.ts` başındaki yorumda; TRCODE/LINETYPE/OUTCOST anlamları canlı veride doğrulanmıştır.

## SQL lehçesi notu (MSSQL yolu)

Motorun MSSQL yolunda `EXTRACT`, `DATE_PART`, `DATE_TRUNC`, `MONTH()` ve `TRIM` (→ `BTRIM`) çevrilemiyor.
Ay kırılımı tarih aralığı kovalarıyla (`"DATE_" >= '2026-01-01' AND "DATE_" < '2026-02-01'`), gün kırılımı
`CAST("DATE_" AS DATE)` ile yapılır; `GROUP BY` içinde takma ad kullanılmaz.

## Sunucu notları (2026-09-06)

- Embedder A40 GPU'da: `nanobaseai-bi-embed.service` (:8012). nanobase → A40 tüneli `a40-embed-tunnel.service`
  (172.17.0.1:8021) + wren köprüsü `nanobase-bridge-wren-8021.service` (172.31.0.1:8021). Motor `config.yaml`
  embedder `api_base` bu adrese bakar. İndexleme ~10 s.
- `deploy/wren_knowledge.py` motorun *instructions* + *sql pairs* mekanizmasına Logo iş kurallarını yazar;
  her model değişikliğinden sonra tekrar çalıştırılabilir (mevcut kayıtları atlar).
