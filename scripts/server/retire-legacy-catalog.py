"""Retire only the active legacy semantic catalog; keep raw schemas and query/audit history.
Run on the test server with its bridge environment. No Logo/CRM writes.
Backup is a consistent PostgreSQL snapshot, fully decoded before any DELETE.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

import sqlalchemy as sa
from semantic_layer.config import SemanticSettings

CHILDREN = ("sl_mapping", "sl_evidence", "sl_counter_evidence", "sl_candidate")
SCOPED = ("sl_catalog_version", "sl_vocabulary")
DS_ONLY = ("sl_suggestion",)
TABLES = (*CHILDREN, "sl_concept", *SCOPED, *DS_ONLY)

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--backup-dir", required=True)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    if sys.platform != "linux":
        raise SystemExit("Run on the connected test server only.")
    settings = SemanticSettings.from_env()
    engine = sa.create_engine(settings.store_dsn)
    if engine.dialect.name != "postgresql":
        raise SystemExit("PostgreSQL metadata store required.")
    scope = {"tenant": settings.tenant_id, "ds": settings.datasource_id}
    parent = "tenant_id=:tenant AND datasource_id=:ds"
    predicates = {t: "concept_id IN (SELECT id FROM sl_concept WHERE " + parent + ")" for t in CHILDREN}
    predicates.update({t: parent for t in ("sl_concept", *SCOPED)})
    predicates.update({t: "datasource_id=:ds" for t in DS_ONLY})
    def counts(c):
        return {t: c.execute(sa.text("SELECT count(*) FROM " + t + " WHERE " + predicates[t]), scope).scalar_one() for t in TABLES}
    with engine.connect() as c:
        before = counts(c)
    print(json.dumps({"scope": scope, "before": before, "apply": args.apply}), flush=True)
    if not args.apply:
        return
    os.umask(0o077)
    out = Path(args.backup_dir)
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    archive = out / "legacy-catalog.dump"
    url = engine.url
    pg_env = dict(os.environ, PGPASSWORD=url.password or "")
    base = ["pg_dump", "-Fc", "-Z", "zstd:1", "--no-owner", "--no-acl", "-h", url.host or "localhost",
            "-p", str(url.port or 5432), "-U", url.username or "", "-d", url.database or "",
            "-f", str(archive)]
    # Freeze only these catalog tables while exporting; shared raw schema and audit
    # tables are not locked or deleted. SHARE permits the pg_dump reader.
    with engine.connect().execution_options(isolation_level="REPEATABLE READ") as c:
        with c.begin():
            c.execute(sa.text("SET LOCAL lock_timeout = '15s'"))
            c.execute(sa.text("LOCK TABLE " + ", ".join(TABLES) + " IN SHARE MODE"))
            before = counts(c)
            snapshot = c.execute(sa.text("SELECT pg_export_snapshot()")).scalar_one()
            subprocess.run(base + ["--snapshot", snapshot] + [x for t in TABLES for x in ("-t", "public." + t)], env=pg_env, check=True)
            # Full decompression/read, not merely a TOC listing; no restore to any DB.
            subprocess.run(["pg_restore", "-f", "/dev/null", str(archive)], check=True)
            digest = hashlib.file_digest(archive.open("rb"), "sha256").hexdigest()
            (out / "backup.json").write_text(json.dumps({"scope": scope, "counts": before, "sha256": digest,
                "bytes": archive.stat().st_size, "capturedAt": datetime.now(timezone.utc).isoformat()}, indent=2))
            print("BACKUP_VERIFIED " + digest, flush=True)
            # Reject repopulation even by an old side worker or old admin endpoint.
            c.execute(sa.text("""
CREATE OR REPLACE FUNCTION public.reject_retired_legacy_catalog() RETURNS trigger
LANGUAGE plpgsql AS $body$
DECLARE item jsonb := to_jsonb(NEW);
BEGIN
 IF item->>'datasource_id' = TG_ARGV[1]
    AND (NOT (item ? 'tenant_id') OR item->>'tenant_id' = TG_ARGV[0]) THEN
   RAISE EXCEPTION 'Legacy semantic catalog retired; use the contract engine';
 END IF;
 RETURN NEW;
END $body$"""))
            for t in ("sl_concept", *SCOPED, *DS_ONLY):
                # Quote values with the driver's literal compiler; never interpolate secrets.
                tenant = str(sa.literal(scope["tenant"]).compile(dialect=engine.dialect, compile_kwargs={"literal_binds": True}))
                ds = str(sa.literal(scope["ds"]).compile(dialect=engine.dialect, compile_kwargs={"literal_binds": True}))
                c.execute(sa.text("CREATE TRIGGER legacy_catalog_retired BEFORE INSERT OR UPDATE ON " + t +
                    " FOR EACH ROW EXECUTE FUNCTION public.reject_retired_legacy_catalog(" + tenant + ", " + ds + ")"))
            deleted = {}
            for t in TABLES:
                deleted[t] = c.execute(sa.text("DELETE FROM " + t + " WHERE " + predicates[t]), scope).rowcount
            after = counts(c)
            if any(after.values()):
                raise RuntimeError("Retirement incomplete; transaction rolled back.")
    result = {"scope": scope, "deleted": deleted, "after": after, "backup": str(archive), "backupSha256": digest,
              "preserved": ["sl_schema_profile", "sl_schema_annotation", "sl_query_log", "semantic_*", "Logo", "CRM"]}
    (out / "retirement.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)

if __name__ == "__main__":
    main()
