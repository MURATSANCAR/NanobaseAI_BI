# WrenAI: `v1-final` → `main` (open-core) geçişi — 2026-09-06

**Karar (kullanıcı):** WrenAI doğru seçim; ama legacy `v1-final` (Wren GenBI Classic: wren-ui 0.32.2 / wren-ai-service 0.29.0 /
wren-engine 0.22.0, Docker) yerine 2026 `main` hattı kullanılır: `core/wren` (`pip install 'wrenai[mssql,memory,mcp]'`,
sürüm **0.13.4** = `main` `core/wren` 0.13.4, 2026-09-02). UI ve "ask pipeline" yok; orkestrasyon bizim LLM'de, Wren
semantik bağlam katmanı (MDL + knowledge + memory) ve governed SQL yürütücüsüdür.

```
Qwen (A40 llama.cpp, 24.576 ctx yeterli)
   │  OpenAI-uyumlu chat  (backend/wren_bridge → /api/v1/ask)      ┐ aynı bağlam araçları
   │  MCP tool call        (nanobase-wren-mcp :8090 → run_sql, get_context, recall_queries …) ┘
   ▼
WrenAI core engine (in-process DataFusion + MDL)  ←  proje /data/nanobaseai/bi/wren-project/logo_timas
   │   7 model · 1620 kolon · 8 ilişki · knowledge/rules (6) · knowledge/sql (8) · LanceDB memory (1635 şema öğesi)
   ▼
SQL Server (Logo LOGO_DB, FreeTDS ODBC, tünel 127.0.0.1:14330)
```

## Bileşenler

| Parça | Nerede | Not |
|---|---|---|
| CLI/engine venv | `/data/nanobaseai/bi/wren-venv` | `wrenai 0.13.4`, `mcp<2` (wrenai FastMCP v1 bekler), torch CPU + LanceDB (memory) |
| Proje | `/data/nanobaseai/bi/wren-project/logo_timas` | `tools/wren/legacy_to_project.py` ile legacy `deploy_log.manifest` + `instruction`/`sql_pair` tablolarından üretildi; kolon budama yok |
| Bağlantı | `secrets/wren-logo-connection.json`, profil `logo-tunnel` | driver FreeTDS, TDS 7.4, ClientCharset UTF-8 |
| ODBC şimi | `tools/wren/sitecustomize.py` → venv `nanobaseai_odbc_shim.pth` | wrenai her ODBC değerini `{}` ile sarar, FreeTDS `HY001` verir; şim yalnız gerekince sarar |
| Köprü | `backend/wren_bridge` → `nanobase-wren-bridge.service` :8794 | cockpit sözleşmesi: `/api/v1/run_sql`, `/api/v1/ask`, `/api/v1/engine`; engine erişimi kilitle serileştirilir |
| MCP | `nanobase-wren-mcp.service` 127.0.0.1:8090/mcp | 17 araç; Streamable HTTP, auth yok → yalnız loopback |
| nginx | `scripts/server/switch-timas-api.sh bridge\|legacy` | `/timas/api/` → :8794 |

## Ölçümler (2026-09-06)

- Dashboard 5 SQL: yeni engine ↔ legacy birebir aynı rakamlar (satış 922.418.666,06 TL; 70.664 fatura). Paralel 6 istek: 8,6 s / 5,3 s.
- Copilot istemi: 2.575–4.141 token (legacy: 22.900 → LLM 24.576 bağlamı aşıyordu). LLM bağlamı 24.576'da bırakıldı.
- Copilot 5/5: doğru T-SQL (TOP, DATEFROMPARTS, ilişki join'leri, TRCODE/LINETYPE kuralları) + Türkçe özet, 23–32 s/soru.

## Runbook

```bash
./scripts/server/deploy-wren-bridge.sh   # şim + context build + memory index + smoke + systemd köprü
./scripts/server/deploy-wren-mcp.sh      # MCP sunucusu
./scripts/server/switch-timas-api.sh bridge
cd apps/cockpit && VITE_BASE=/timas/ VITE_WREN_BASE=/timas npm run build   # dist → /data/nanobaseai/bi/cockpit/dist/
```

Model/bilgi değişince: `wren context build && wren memory index` (proje dizininde), köprü ve MCP restart.

## Açık işler

- Legacy Docker yığını (`nanobaseai-wren-*`) hâlâ ayakta; `/timas` artık kullanmıyor → durdurulabilir.
- MDL kolon açıklamaları (Türkçe) eklenirse `get_context` sıralaması iyileşir (şimdi ilişkili kolonlar büyük ölçüde doğrulanmış SQL çiftlerinden geliyor).
- `wren memory store` ile doğrulanan yeni soru→SQL çiftleri `knowledge/sql/` altına eklenmeli (köprü `--allow-write` kullanmıyor).
