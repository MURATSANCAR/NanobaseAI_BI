# DB-GPT Backend (sidecar + BI bridge)

[DB-GPT](https://github.com/eosphoros-ai/DB-GPT) via pip + a thin FastAPI **bridge** so the React BI app keeps calling `/api/v1/bi/*` while execution runs on DB-GPT.

```
FE (:5174/bi or portal/bi) → bridge :8787 → DB-GPT :5670 → LLM :8010/:8015
```

## Prerequisites

- Python **3.11** (`brew install python@3.11`) + [uv](https://docs.astral.sh/uv/)
- LLM OpenAI-compatible API (llama.cpp server, see `deploy/compose/README.md`):

| | |
|--|--|
| Local (server) | `http://127.0.0.1:8010/v1` |
| Remote proxy | `http://38.247.162.28:8015/v1` |
| Key | `nanobase-local` |
| Model | `nanobaseai-bi-llm` |

## Setup

```bash
cd backend
./scripts/setup.sh
cp .env.example .env
./scripts/start-stack.sh   # DB-GPT + bridge; registers Neon if local JSON exists
./scripts/stop.sh
```

## Semantic catalog

The catalog is built here, on our own machines, from the knowledge pack — it reads files in this
repository and never touches a customer database. The semantic layer imports none of DB-GPT, so it
installs on its own in seconds:

```bash
cd backend
./scripts/setup.sh --semantic-only          # .venv from requirements-semantic.txt (Python 3.11)
./scripts/build-semantic-catalog.sh         # profile → mine → certify → status
.venv/bin/python -m pytest semantic_layer/tests/ -q
```

The store lands in gitignored `backend/var/semantic_layer.db`; it is derived from the pack and the
source, so it is rebuilt rather than committed. `SEMANTIC_STORE_DSN` overrides it (Postgres in the
deployment). Pointing the pipeline at a live source is a separate, deliberate act — set
`SEMANTIC_CONNECTION_FILE` — and installs that source's driver (`pyodbc`, `psycopg2`).

The Logo vendor dictionary behind the catalog is regenerated from the workbook and the Turkish
structure document:

```bash
python backend/scripts/import_logo_ldds.py LDDS.xls --doc LOGO_TABLE_YAPISI.DOC
```

Manual pieces:

```bash
./scripts/start.sh                 # DB-GPT only
python -m uvicorn bridge.app:app --port 8787
./scripts/register-neon-sources.sh
```

## Neon datasources

Passwords live in gitignored `configs/sources/local/connection.local.json` (or `BI_ERP_PASSWORD` / `BI_SIGORTA_PASSWORD`). Never commit plaintext.

## Layout

| Path | Role |
|------|------|
| `configs/dbgpt-openai-compat.toml` | DB-GPT LLM/embedding |
| `bridge/app.py` | FE contract adapter |
| `scripts/start-stack.sh` | One-shot start |

## Embeddings

Default points at `${OPENAI_API_BASE}/embeddings`. If llama.cpp has no embedding route, RAG may fail; chat/Text2SQL still works. Optional: BGE-M3 on `:8083` — set `EMBEDDING_MODEL_API_URL`.
