# WrenAI MCP sunucusuna ajan bağlama (Claude Code, Cursor, Codex)

Sunucu: `nanobase-wren-mcp.service` → `127.0.0.1:8090/mcp` (Streamable HTTP, **yalnız loopback**, kimlik doğrulama yok).
Proje: `/data/nanobaseai/bi/wren-project/logo_timas` · Profil: `logo-tunnel` · **`--allow-write` açık** (ajan `store_query` ile öğrendiğini yazar).

18 araç: `run_sql`, `dry_run`, `dry_plan`, `query_cube`, `get_mdl`, `list_models`, `describe_model`, `get_data_source`,
`list_cubes`, `describe_cube`, `list_functions`, `get_instructions`, `recall_queries`, `get_context`, `describe_schema`,
`list_stored_queries`, `list_knowledge`, `store_query`.

## Sunucu üzerinden (aynı makinede çalışan ajan)

```bash
claude mcp add --transport http wren-logo http://127.0.0.1:8090/mcp
```

## Uzaktan (Mac'ten) — SSH tüneliyle

```bash
ssh -N -L 8090:127.0.0.1:8090 nanobase &
claude mcp add --transport http wren-logo http://127.0.0.1:8090/mcp
```

## Elle yapılandırma (Cursor, Codex, diğer MCP istemcileri)

```json
{
  "mcpServers": {
    "wren-logo": { "transport": "http", "url": "http://127.0.0.1:8090/mcp" }
  }
}
```

## Doğrulama

```bash
curl -s -X POST http://127.0.0.1:8090/mcp \
  -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}'
```

`serverInfo: {"name":"wren","version":"1.29.1"}` dönmeli. Araç listesi için `tools/list` çağır.

## Notlar

- `mcp` paketi **1.x'te sabit** olmalı (`mcp<2`); 2.x'te FastMCP yeniden adlandırıldığı için sunucu açılışta düşer.
- Kimlik doğrulama yok: portu dışarı açma, uzaktan erişim için SSH tüneli kullan.
- `store_query` açık olduğu için ajanların yazdığı çiftler `knowledge/sql/` altına düşer ve git'e girer; periyodik gözden geçir.
