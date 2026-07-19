# Architecture baseline

Locked decisions (see also `docs/architecture/locked-architecture.md`):

1. DB-GPT v0.8.1 + Qdrant
2. Orchestration owner: `nanobase_api`
3. Customer SQL execute: Query Gateway only
4. Secrets: file default; Vault optional
5. Workflows: nl2sql-plan → Gateway → result-explain

Forbidden: Frontend→DBGPT/QG/Vault/Qdrant; DBGPT/AWEL/Qwen/BGE/Qdrant→customer DB.

Owner: Engineering Lead  
Status: DRAFT — fill digests from release-manifest.json
