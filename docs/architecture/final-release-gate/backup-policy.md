# Backup policy

Back up: metadata PG, audit, Vault/platform, Qdrant snapshots, semantic/prompt/policy catalogs,
IaC, registry metadata, release artifacts, test evidence.

Do **not** assume Nanobase backs up customer production databases (contractual out-of-scope).

Security: encryption at rest/transit, separate credentials, immutable/object lock, retention, access audit, restore tests.

Valid backup = successful restore log + checksum + E2E smoke.
