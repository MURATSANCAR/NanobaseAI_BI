# NanobaseAI BI

Doğal dilde soru → yönetilen SQL → doğru veri. Tek başına kurulan BI ürünü: React arayüz,
FastAPI backend, Query Gateway, semantic katman, senaryo motoru ve LLM servisi.

## Müşteri kurulumu (önerilen)

```bash
cd deploy/compose && ./install.sh
```

Ayrıntı: [deploy/compose/README.md](deploy/compose/README.md) — tek komutla kurulum,
uzak veritabanı bağlama (`add-datasource.sh`), LLM seçenekleri, işletim ve sorun giderme.

## Geliştirme

```bash
npm install
cp .env.example .env
cd backend && ./scripts/setup.sh && cp .env.example .env && ./scripts/start-stack.sh && cd ..
npm run dev            # http://127.0.0.1:5174/bi/
```

| Servis | Port |
|---|---|
| Web (Vite dev) | 5174 |
| API (`nanobase_api`) | 8790 |
| Query Gateway | 8792 |
| Semantic Bridge (Timaş, WrenAI'siz) | 8795 |
| LLM (OpenAI uyumlu) | 8010 yerel / harici GPU sunucusu |
| Gömme servisi | 8083 |
| Meta DB (Postgres) | 5434 |

LLM model takma adı: `nanobaseai-bi-llm` (bkz. `deploy/llm-server/`).

## Yapı

| Dizin | İçerik |
|---|---|
| `src/` | React + Vite arayüz |
| `backend/nanobase_api` | API, chat gateway, semantic katalog, senaryo motoru |
| `backend/nanobase_awel` | LLM operatörleri, planlama/onarım/açıklama iş akışları |
| `backend/query_gateway` | Müşteri SQL'inin tek çalışma noktası (salt-okunur, izin listeli) |
| `backend/semantic_layer` | Semantic Catalog + Evidence Engine + History Miner + Profiler + Resolver/Compiler (WrenAI'siz NL→SQL çekirdeği; `docs/architecture/semantic-layer-v1.md`) |
| `backend/semantic_bridge` | Timaş kokpiti için WrenAI'siz köprü (:8795) — `/api/v1/ask`, `/run_sql`, `/api/v1/semantic/*`, `/api/v1/schema/*` |
| `tools/schema-indexer` | Şema tarama ve gömme |
| `deploy/compose` | Müşteri kurulum paketi (Docker) |
| `deploy/llm-server` | GPU sunucusu için LLM servis tanımı |
| `docs/architecture` | Kilitli mimari, tasarım ve plan belgeleri |

## Yapılandırma

| Değişken | Amaç |
|---|---|
| `VITE_API_BASE` | Aynı origin proxy kullanılmıyorsa API adresi |
| `VITE_BASE` | Uygulama alt yolu (varsayılan `/bi/`, müşteri paketinde `/`) |

Operatör yapılandırmaları [`configs/`](configs/README.md) altındadır (bağlantı profilleri,
şema katalogları, semantic bağlamalar). Parolalar depoya girmez; `secrets/` veya Vault.
