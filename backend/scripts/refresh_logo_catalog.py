"""Prepare a private catalog candidate with the current Logo dictionary descriptions.

No ERP scan or DDL: only already-profiled columns receive descriptions. Physical types,
observations and portal annotations are preserved. Publication uses nightly.Release separately.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from semantic_layer.config import SemanticSettings
from semantic_layer.profiler import logo_dictionary as ld
from semantic_layer.store.catalog_store import open_store
from semantic_layer.nightly import Release


def refresh(store, datasource):
    stats = {'profiles': 0, 'tables_updated': 0, 'columns_updated': 0, 'profiles_updated': 0}
    for profile in store.list_profiles(datasource):
        stats['profiles'] += 1
        changed = False
        text = ld.table_description(profile.table_name)
        if text and profile.description != text:
            profile.description = text
            stats['tables_updated'] += 1
            changed = True
        for col in profile.columns:
            text = ld.column_description(profile.table_name, col.name)
            if text and col.description != text:
                col.description = text
                stats['columns_updated'] += 1
                changed = True
        if changed:
            store.upsert_profile(profile)
            stats['profiles_updated'] += 1
    return stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', type=Path, required=True)
    args = parser.parse_args()
    args.run_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    journal = args.run_dir / 'journal.json'
    if journal.exists():
        raise SystemExit('Existing release journal: use a new run directory')
    settings = SemanticSettings.from_env()
    live = open_store(settings.store_dsn, create=False)
    stage = Release(live, settings.tenant_id, settings.datasource_id, journal).prepare(
        'sqlite:///' + str((args.run_dir / 'candidate.sqlite').resolve()))
    stats = refresh(stage, settings.datasource_id)
    (args.run_dir / 'refresh.json').write_text(json.dumps(stats, indent=2))
    print(json.dumps(stats))


if __name__ == '__main__':
    main()
