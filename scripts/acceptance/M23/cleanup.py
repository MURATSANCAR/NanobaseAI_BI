"""M23 kabulünün bıraktığı kayıtları kimlikle siler: içerik üreticisi, hesap, ölçüm, işbirliği, olay, taslak, ödeme
satırı, gönderilmiş hatırlatma anahtarı ve bu kayıtlara ait değişiklik kaydı satırları (influencer*). Silinen sayılar
ekrana yazılır; günlüğe geçirilir.

Kullanım: cleanup.py --ids-file /tmp/claude-m23/kabul-kimlikler.json [--people a,b] [--collabs c,d]
          [--actor timasai --since 2026-09-28T10:00] [--dry]
`--actor/--since` o kişinin o andan sonraki influencer* değişiklik kaydını da siler.
"""
import argparse
import json
import os
import sys
from datetime import datetime

# Aday ağaç (git archive) önce: canlı ağaçta M23 kodu kurulumdan önce yoktur.
sys.path.insert(0, os.environ.get("M23_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402
from semantic_bridge import influencers as I  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ids-file", default="")
ap.add_argument("--people", default="")
ap.add_argument("--collabs", default="")
ap.add_argument("--actor", default="")
ap.add_argument("--since", default="")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
people = [x for x in a.people.split(",") if x]
collabs = [x for x in a.collabs.split(",") if x]
if a.ids_file:
    data = json.load(open(a.ids_file))
    people += data.get("people", [])
    collabs += data.get("collabs", [])
eng = open_store(SemanticSettings.from_env().store_dsn).engine
I.ensure(eng)
AUDIT = sa.Table("semantic_audit", sa.MetaData(), autoload_with=eng)
counts: dict[str, int] = {}


def drop(c, name, table, cond):
    counts[name] = counts.get(name, 0) + (c.execute(sa.select(sa.func.count()).select_from(table).where(cond)).scalar() or 0)
    if not a.dry:
        c.execute(table.delete().where(cond))


with eng.begin() as c:
    if people:
        collabs += [r.id for r in c.execute(sa.select(I.COLLABS.c.id).where(I.COLLABS.c.person_id.in_(people)))]
    collabs = list(dict.fromkeys(collabs))
    people = list(dict.fromkeys(people))
    accounts = [r.id for r in c.execute(sa.select(I.ACCOUNTS.c.id).where(I.ACCOUNTS.c.person_id.in_(people or [""])))]
    if collabs:
        drop(c, "olay", I.EVENTS, I.EVENTS.c.collab_id.in_(collabs))
        drop(c, "taslak", I.DRAFTS, I.DRAFTS.c.collab_id.in_(collabs))
        drop(c, "ödeme satırı", I.PAYOUTS, I.PAYOUTS.c.collab_id.in_(collabs))
        drop(c, "hatırlatma", I.REMINDERS, sa.or_(*[I.REMINDERS.c.key.like(f"%:{i}%") for i in collabs]))
        drop(c, "işbirliği", I.COLLABS, I.COLLABS.c.id.in_(collabs))
    if accounts:
        drop(c, "ölçüm", I.SNAPSHOTS, I.SNAPSHOTS.c.account_id.in_(accounts))
        drop(c, "hatırlatma", I.REMINDERS, sa.or_(*[I.REMINDERS.c.key.like(f"%:{i}:%") for i in accounts]))
        drop(c, "hesap", I.ACCOUNTS, I.ACCOUNTS.c.id.in_(accounts))
    if people:
        drop(c, "kişi", I.PEOPLE, I.PEOPLE.c.id.in_(people))
    keys = people + collabs + accounts
    by_obj = sa.or_(*[AUDIT.c.object_id.like(f"{i}%") for i in keys], *[AUDIT.c.detail.like(f"%{i}%") for i in collabs]) if keys else sa.false()
    if a.actor and a.since:
        by_obj = sa.or_(by_obj, sa.and_(AUDIT.c.actor == a.actor, AUDIT.c.at >= datetime.fromisoformat(a.since)))
    drop(c, "değişiklik kaydı", AUDIT, sa.and_(AUDIT.c.kind.like("influencer%"), by_obj))
print("silinecek" if a.dry else "silinen", counts, "kişiler:", people, "işbirlikleri:", collabs)
