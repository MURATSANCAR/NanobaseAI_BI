# Editör (Hermes Book Director)

Kanıta bağlı kitap analizi. BI'dan ayrı bir modüldür: yalnız kodu bu depoda durur; veritabanı,
vektör deposu, model kopyaları, konteynerler ve ağ kendisine aittir (TT GPU sunucusu, `/data/editor`).

- Karar metni: [docs/NIHAI-KARAR.md](docs/NIHAI-KARAR.md)
- Uygulama notları ve açık konular: [docs/UYGULAMA-NOTLARI.md](docs/UYGULAMA-NOTLARI.md)

```
Hermes Book Director (editor-hermes, API :19110)
 ├── Book Skills (hermes/skills/book/*, 15 skill)      ├── Critic Agent / Editor Review Agent (delegate_task)
 ├── MCP (editor-mcp): document · vision · knowledge · retrieval · quality · jobs
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
| `src/editor/mcp_servers.py` | Hermes'e açık MCP araçları |
| `src/editor/{document,vision,knowledge,retrieval,summary,quality}.py` | Araçların arkasındaki iş |
| `src/editor/ledger.py`, `db/migrations/` | Kanıt defteri ve kuralları |
| `src/editor/workflow/` | Temporal iş akışı (15 adım), etkinlikler, işçi |
| `src/editor/prompts/` | Sürümlü prompt'lar (defterde kayıtlı) |
| `hermes/` | SOUL.md (Book Director), config şablonu, skill'ler |
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
editorctl hermes chat             # Hermes ile konuşma
editorctl down                    # her şeyi durdur
```

Kod güncellemesi: `rsync -az --delete apps/editor/ tt-gpu:/data/editor/app/`, sonra `editorctl install && editorctl up`.
