# DB-GPT Backend (sidecar + BI bridge)

[DB-GPT](https://github.com/eosphoros-ai/DB-GPT) via pip + a thin FastAPI **bridge** so the React BI app keeps calling `/api/v1/bi/*` while execution runs on DB-GPT.

```
FE (:5174/bi or portal/bi) → bridge :8787 → DB-GPT :5670 → LLM :8010/:8015
```

## Prerequisites

- Python **3.11** (`brew install python@3.11`) + [uv](https://docs.astral.sh/uv/)
- LLM OpenAI-compatible API (MobilTest [LLM-SERVER.md](https://github.com/)):

| | |
|--|--|
| Local (server) | `http://127.0.0.1:8010/v1` |
| Remote proxy | `http://38.247.162.28:8015/v1` |
| Key | `nanobase-local` |
| Model | `nanobase-qwen36-35b-a3b-mtp` |

## Setup

```bash
cd backend
./scripts/setup.sh
cp .env.example .env
./scripts/start-stack.sh   # DB-GPT + bridge; registers Neon if local JSON exists
./scripts/stop.sh
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
