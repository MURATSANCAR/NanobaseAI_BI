# Editör

Kanıta bağlı kitap analizi. BI'dan ayrı bir modüldür: yalnız kodu bu depoda durur; veritabanı,
vektör deposu, model kopyaları, konteynerler ve ağ kendisine aittir (TT GPU sunucusu, `/data/editor`).

- Karar metni: [docs/NIHAI-KARAR.md](docs/NIHAI-KARAR.md)
- Uygulama notları ve açık konular: [docs/UYGULAMA-NOTLARI.md](docs/UYGULAMA-NOTLARI.md)
- 2026-10-03: karar metnindeki sohbet ajanı ve onun araç katmanı (MCP) kaldırıldı. Kitaba sor kart servisinden
  doğrudan kodla cevaplanır; okuma Temporal iş akışıyla yürür.

```
Kart servisi (editor-cards :19141): kitap kartları, inceleme kuyruğu, Kitaba sor (quick_answer)
 ├── Local Model Gateway (editor-gateway :19100) → vLLM konteynerleri (ihtiyaç anında)
 ├── Temporal (editor-temporal, UI :19120) + LangGraph → editor-worker
 ├── PostgreSQL Evidence Ledger (editor-postgres :19130, şema ed)
 ├── Qdrant (editor-qdrant)
 └── PDF/görüntü deposu (/data/editor/storage)
```

## Dizinler

| Yol | İçerik |
|---|---|
| `src/editor/gateway.py` | Model Gateway: takma ad → vLLM konteyneri, ihtiyaçta aç, boşta kapat |
| `src/editor/{document,vision,knowledge,retrieval,summary,quality}.py` | Okuma adımlarının işi |
| `src/editor/card_api.py`, `src/editor/quick_answer.py` | Kart servisi; Kitaba sor (en çok iki model çağrısı) |
| `src/editor/ledger.py`, `db/migrations/` | Kanıt defteri ve kuralları |
| `src/editor/workflow/` | Temporal iş akışı (15 adım), etkinlikler, işçi |
| `src/editor/prompts/` | Sürümlü prompt'lar (defterde kayıtlı) |
| `deploy/` | docker-compose, models.yaml, Temporal ayarı, `editorctl` |
| `tests/regression/` | Kitap başına altın beklentiler |

## Kullanım (tt-gpu)

```bash
editorctl install                 # ilk kurulum / kod güncellemesi sonrası
editorctl up                      # çekirdek servisler (GPU kullanmaz)
editorctl analyze kitap.pdf --title "Ad"
editorctl wait <job_id>
editorctl cli report <generation_id>
editorctl cli review list <generation_id>
editorctl down                    # her şeyi durdur
```

Kod güncellemesi: `rsync -az --delete apps/editor/ tt-gpu:/data/editor/app/`, sonra `editorctl install && editorctl up`.
