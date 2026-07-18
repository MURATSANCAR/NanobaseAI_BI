# DB-GPT Backend (sidecar)

Standalone [DB-GPT](https://github.com/eosphoros-ai/DB-GPT) install via pip. Provides Text2SQL, agents, datasources, and RAG over a FastAPI process. The built-in web UI on port 5670 is **not** used by the Nanobase React BI frontend (no `/api/v1/bi/*` bridge in this phase).

Upstream: https://github.com/eosphoros-ai/DB-GPT · Package: `dbgpt-app` (PyPI)

## Prerequisites

- Python **3.11** recommended (`brew install python@3.11`) — DB-GPT 0.8.1 pins `aiohttp==3.8.4`, which often fails to build on 3.12+
- Python **3.10+** minimum
- [uv](https://docs.astral.sh/uv/) recommended for install (`curl -LsSf https://astral.sh/uv/install.sh | sh`)
- OpenAI-compatible LLM at `http://127.0.0.1:8010/v1` (or change `OPENAI_API_BASE`)

## Setup

```bash
cd backend
./scripts/setup.sh
cp .env.example .env   # edit if needed
```

Installs into `backend/.venv`:

- `dbgpt-app==0.8.1` (includes OpenAI proxy + ChromaDB/RAG)
- `dbgpt-ext[datasource_postgres]==0.8.1`

## Start / stop

```bash
./scripts/start.sh    # http://127.0.0.1:5670
./scripts/stop.sh
```

`DBGPT_HOME` defaults to `backend/.dbgpt` (SQLite meta + Chroma under that tree).

Config file: [`configs/dbgpt-openai-compat.toml`](configs/dbgpt-openai-compat.toml)

## Environment

| Variable | Default | Purpose |
|----------|---------|---------|
| `OPENAI_API_BASE` | `http://127.0.0.1:8010/v1` | OpenAI-compatible chat API |
| `OPENAI_API_KEY` | `nanobase-local` | API key for the proxy |
| `LLM_MODEL_NAME` | `nanobase-qwen36-35b-a3b-mtp` | Model id sent to the proxy |
| `EMBEDDING_MODEL_API_URL` | `…/v1/embeddings` | Embedding endpoint (override if LLM host has none) |
| `DBGPT_PORT` | `5670` | Listen port |
| `DBGPT_HOME` | `backend/.dbgpt` | Workspace root |

## Scope

- **In:** DB-GPT REST API / agent backend as a separate process
- **Out:** Cloning DB-GPT’s React UI; wiring this app’s Vite proxy or `src/api/bi-api.ts` to DB-GPT

Postgres datasource support is included. Neon **ERP** + **Sigorta** (both DB name `neondb`) are registered as connection ids `erp` / `sigorta` via `scripts/register_neon_datasources.py`. `scripts/run_web.py` patches DB-GPT so `ext_config.database` is used as the real Postgres database.

```bash
./scripts/start.sh
./.venv/bin/python scripts/register_neon_datasources.py
```

Secrets: `../configs/sources/local/neon-dsns.env` (gitignored). Connecting the Nanobase BI SPA still requires the MobilTest runner `/api/v1/bi/*`.

## Docs

- Quick start: https://docs.dbgpt.cn/docs/getting-started/cli-quickstart
- Datasources: http://docs.dbgpt.cn/docs/modules/connections
