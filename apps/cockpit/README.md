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
