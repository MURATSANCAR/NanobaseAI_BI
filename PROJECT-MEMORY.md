# NanobaseAI BI — Proje Belleği

Bu dosya canlı özet, tek doğru kaynak. Değişiklik olunca üzerine yazılır (eski bilgi silinir/düzeltilir). Kronolojik geçmiş için [docs/GELISTIRME-GUNLUGU.md](docs/GELISTIRME-GUNLUGU.md)'ye bak.

## Proje ne

Doğal dilde soru → yönetilen SQL → doğru veri. Tek başına kurulan BI ürünü: React arayüz, FastAPI backend, Query Gateway, semantic katman, senaryo motoru ve LLM servisi. İlk/ana müşteri: TİMAŞ Logo (mağaza/satış verisi).

## Mimari (üstten alta)

```
React (src/, Vite)  →  nanobase_api (FastAPI, :8790)  →  semantic_layer (Katalog + Evidence Engine + Resolver/Compiler)
                                                        →  semantic_bridge (:8795, Timaş'a özel köprü)
                                                        →  query_gateway (:8792, salt-okunur/izin listeli tek SQL çalışma noktası)
                        nanobase_awel  →  LLM operatörleri (planlama/onarım/açıklama iş akışları)
```

- **semantic_layer**: NL→SQL çekirdeği. Katalog + kanıt motoru esas doğru kaynak (WrenAI kaldırıldı, bkz. proje belleği `wren-teardown-done`). Detay: `docs/architecture/semantic-layer-v1.md`.
- **semantic_bridge (:8795)**: Timaş kokpitine özel köprü — `/api/v1/ask`, `/run_sql`, `/api/v1/semantic/*`, `/api/v1/schema/*`.
- **query_gateway (:8792)**: Müşteri SQL'inin tek çalışma noktası, salt okunur, izin listeli.
- **nanobase_api (:8790)**: API, chat gateway, semantic katalog, senaryo motoru.

## Stack

- Frontend: React + Vite + TypeScript (`src/`), Tailwind.
- Backend: Python/FastAPI (`backend/nanobase_api`, `backend/nanobase_awel`, `backend/query_gateway`, `backend/semantic_layer`, `backend/semantic_bridge`).
- Şema tarama/gömme: `tools/schema-indexer`.
- Kurulum: Docker Compose (`deploy/compose`, müşteri paketi), `deploy/llm-server` (GPU sunucusu LLM tanımı).
- Meta DB: Postgres (:5434).

## Sunucu / port yapısı

| Servis | Port |
|---|---|
| Web (Vite dev) | 5174 |
| API (`nanobase_api`) | 8790 |
| Query Gateway | 8792 |
| Semantic Bridge (Timaş) | 8795 |
| LLM (OpenAI uyumlu) | 8010 yerel / harici GPU sunucusu (A40) |
| Gömme servisi | 8083 (embedder, CPU) |
| Meta DB (Postgres) | 5434 |
| BI uygulama VM (müşteri) | http://192.168.0.55/timas/ |

Ayrıntı proje belleklerinde: `semantic-production-deployment`, `bi-app-vm-55`, `llm-topology-a40`, `a40-shutdown-cpu-embedder`, `timas-logo-network-access`.

## Dizin haritası

| Dizin | İçerik |
|---|---|
| `src/` | React + Vite arayüz (tek frontend, kanvas: `src/canvas`) |
| `backend/nanobase_api` | API, chat gateway, semantic katalog, senaryo motoru |
| `backend/nanobase_awel` | LLM operatörleri, planlama/onarım/açıklama iş akışları |
| `backend/query_gateway` | Müşteri SQL'inin tek çalışma noktası |
| `backend/semantic_layer` | Semantic Catalog + Evidence Engine + History Miner + Profiler + Resolver/Compiler |
| `backend/semantic_bridge` | Timaş kokpiti köprüsü (:8795) |
| `tools/schema-indexer` | Şema tarama ve gömme |
| `deploy/compose` | Müşteri kurulum paketi (Docker) |
| `deploy/llm-server` | GPU sunucusu için LLM servis tanımı |
| `docs/architecture` | Kilitli mimari, tasarım ve plan belgeleri |
| `docs/audits` | Denetim/inceleme kayıtları |
| `docs/product` | Ürün belgeleri |
| `configs/` | Operatör yapılandırmaları (bağlantı profilleri, şema katalogları, semantic bağlamalar) |

## Kritik kurallar (AGENTS.md'den, kısa özet)

- **Mobil öncelik**: Her arayüz değişikliği 320/390/768/masaüstü genişliklerde tarayıcıda kontrol edilir; yatay taşma yok. Detay: `apps/cockpit/AGENTS.md`.
- **Gerçek DB ile doğrulama zorunlu**: Veri alma/SQL/hesaplama/raporlama etkileyen her değişiklik bağlı gerçek veritabanı + gerçek API akışıyla doğrulanmadan tamamlanmış sayılmaz. Yerel mock/fixture/SQLite ile test **yasak** (kullanıcı ayrıca istemedikçe). Doğrulanamıyorsa **DOĞRULANAMADI** diye raporla, başarı iddia etme.
- **Tek şirket, çok yıllık yedek**: TİMAŞ'ta tek şirket var; `211`/`411` gibi kodlar farklı şirket değil, yıl yedekleridir (bkz. proje belleği `logo-period-prefixes-are-years`, `timas-logo-database-shape`).
- Tam kural metni: [AGENTS.md](AGENTS.md).

## Notlar

- Bu proje için ayrıca kalıcı bellek kayıtları `~/.claude/projects/.../memory/MEMORY.md` altında tutulur (semantic layer kararları, sertifikalama, kalite kapısı, vb.) — kod tabanından türetilemeyen proje bağlamı orada.
- Bu dosya + `docs/GELISTIRME-GUNLUGU.md` çifti bir **talimat**tır, hook değildir: oturumdaki Claude'un CLAUDE.md'yi okuyup uygulamasına bağlıdır, zorlayıcı değildir. Gerçek zorlama istenirse `.claude/settings.json`'a bir hook eklenebilir (örn. commit sonrası günlük güncellendi mi kontrolü) — bu ayrı bir iş, henüz yapılmadı.
