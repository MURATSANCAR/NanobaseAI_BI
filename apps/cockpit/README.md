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

## Üretim

`npm run build` → `dist/`. Reverse proxy'de `/api/*` → `wren-ui:3000`, geri kalan → `dist/`.

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
