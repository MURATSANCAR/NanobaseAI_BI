#!/usr/bin/env python3
"""M28 kabul testinin bıraktığı kayıtları siler (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»).

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/m28/temizlik.py --ids /tmp/claude-<oturum>/m28-ids.json

Silinenler: kabul.py --yazma'nın açtığı kişi kartı, notu, hediye satırları, proje ve proje olayları; adı «KABUL TESTİ»
ile başlayan artık kişi/kurum/proje kalmışsa onlar ve bağlı satırları; bu kayıtların değişiklik kaydı (`semantic_audit`,
tür `rel_*`) satırları. Silinen satır sayıları ekrana yazılır; günlüğe geçirilir. CRM'e dokunulmaz (zaten yazılmaz).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import public_affairs as PA  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="m28-ids.json")
    args = ap.parse_args()
    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    PA.ensure(engine)
    admin_mod.ensure(engine)
    ids = json.loads(Path(args.ids).read_text()) if Path(args.ids).exists() else {}
    with engine.begin() as c:
        people = set(ids.get("people") or []) | {r[0] for r in c.execute(
            sa.select(PA.PEOPLE.c.id).where(PA.PEOPLE.c.name.like("KABUL TESTİ%"))).all()}
        orgs = set(ids.get("orgs") or []) | {r[0] for r in c.execute(sa.select(PA.ORGS.c.id).where(PA.ORGS.c.name.like("KABUL TESTİ%"))).all()}
        projects = set(ids.get("projects") or []) | {r[0] for r in c.execute(
            sa.select(PA.PROJECTS.c.id).where(PA.PROJECTS.c.title.like("KABUL TESTİ%"))).all()}
        gifts = set(ids.get("gifts") or [])
        notes = set(ids.get("notes") or [])
        if people:
            gifts |= {r[0] for r in c.execute(sa.select(PA.GIFTS.c.id).where(PA.GIFTS.c.person_id.in_(sorted(people)))).all()}
            notes |= {r[0] for r in c.execute(sa.select(PA.NOTES.c.id).where(PA.NOTES.c.person_id.in_(sorted(people)))).all()}
        if orgs:
            notes |= {r[0] for r in c.execute(sa.select(PA.NOTES.c.id).where(PA.NOTES.c.org_id.in_(sorted(orgs)))).all()}
        out = {
            "hediye": c.execute(PA.GIFTS.delete().where(PA.GIFTS.c.id.in_(sorted(gifts)))).rowcount if gifts else 0,
            "not": c.execute(PA.NOTES.delete().where(PA.NOTES.c.id.in_(sorted(notes)))).rowcount if notes else 0,
            "proje_olayi": c.execute(PA.EVENTS.delete().where(PA.EVENTS.c.project_id.in_(sorted(projects)))).rowcount if projects else 0,
            "proje": c.execute(PA.PROJECTS.delete().where(PA.PROJECTS.c.id.in_(sorted(projects)))).rowcount if projects else 0,
            "kisi": c.execute(PA.PEOPLE.delete().where(PA.PEOPLE.c.id.in_(sorted(people)))).rowcount if people else 0,
            "kurum": c.execute(PA.ORGS.delete().where(PA.ORGS.c.id.in_(sorted(orgs)))).rowcount if orgs else 0,
        }
        objs = sorted(people | orgs | projects | gifts | notes)
        out["degisiklik_kaydi"] = c.execute(admin_mod.AUDIT.delete().where(
            admin_mod.AUDIT.c.kind.in_(("rel_person", "rel_org", "rel_note", "rel_gift", "rel_project")),
            admin_mod.AUDIT.c.object_id.in_(objs))).rowcount if objs else 0
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
