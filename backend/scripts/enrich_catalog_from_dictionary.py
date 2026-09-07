"""Carry the vendor dictionary's meanings into a catalog that was profiled without them.

A catalog is built by profiling a source, and the descriptions it stores are whatever the source
offered at the time. This one was profiled before the dictionary existed, so it holds four hundred
and nineteen tables and fourteen thousand columns with not one description between them — the
identifiers and nothing else. The meanings have been imported since, into
`configs/schemas/logo-ldds.json`, but a stored profile does not go back and re-read them.

Re-profiling would fix it and also re-scan every table in a live ERP. This does the part that does
not need the database: it fills what is empty from the dictionary and touches nothing else.

    python backend/scripts/enrich_catalog_from_dictionary.py [--apply]

Without `--apply` it reports what it would fill and writes nothing. Anything already described — by
the source, by a person in the portal, by an earlier probe — is left exactly as it is: a generic
vendor line must never displace something somebody wrote.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from semantic_layer.config import SemanticSettings          # noqa: E402
from semantic_layer.profiler import logo_dictionary          # noqa: E402
from semantic_layer.store.catalog_store import open_store    # noqa: E402


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn)
    profiles = store.list_profiles(s.datasource_id)
    if not profiles:
        print(f"katalog boş ({s.store_dsn}, datasource={s.datasource_id})", file=sys.stderr)
        return 1

    tables = cols = untouched = 0
    changed = []
    for p in profiles:
        touched = False
        if not (p.description or "").strip():
            if text := logo_dictionary.table_description(p.table_name):
                p.description = text
                tables += 1
                touched = True
        for c in p.columns:
            if (c.description or "").strip():
                untouched += 1
                continue
            if text := logo_dictionary.column_description(p.table_name, c.name):
                c.description = text
                cols += 1
                touched = True
        if touched:
            changed.append(p)

    print(f"{len(profiles)} profil okundu")
    print(f"  tablo açıklaması doldurulacak : {tables}")
    print(f"  kolon açıklaması doldurulacak : {cols}")
    print(f"  dokunulmayan (zaten yazılı)   : {untouched}")
    if not apply:
        print("\n(kuru çalışma — yazmak için --apply)")
        return 0

    for p in changed:
        store.upsert_profile(p)
    print(f"\n{len(changed)} profil güncellendi")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
