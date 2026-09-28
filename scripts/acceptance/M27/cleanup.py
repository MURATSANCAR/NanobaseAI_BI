"""M27 kabulünün bıraktığı kayıtları kimlikle siler: fuar kartı ve ona bağlı kitap, görev, gider (fiş dosyası dahil),
yazar programı, hatırlatma satırları; ödül ve başvurular (`--awards`); bu kimliklere ait değişiklik kaydı (events*,
award*) satırları. Kimliği verilmeyen hiçbir satıra dokunmaz. Silinen sayılar günlüğe yazılmak üzere basılır.

Kullanım: cleanup.py --ids-file /tmp/claude-m27/kabul-kimlikler.json [--fairs a,b] [--awards x] [--actor timasai
          --since 2026-09-28T10:00] [--dry]
`--actor/--since` o kişinin o andan sonraki events*/award* değişiklik kaydını da siler (kart API'den silindiyse
satırlar kimlikle bulunamayabilir).
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.environ.get("M27_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402
from semantic_bridge import events as E  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ids-file", default="")
ap.add_argument("--fairs", default="")
ap.add_argument("--awards", default="")
ap.add_argument("--actor", default="")
ap.add_argument("--since", default="")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()


def ids(s: str) -> list[str]:
    return [x for x in s.split(",") if x]


got = {"fairs": ids(a.fairs), "tasks": [], "costs": [], "authors": [], "awards": ids(a.awards)}
if a.ids_file and os.path.exists(a.ids_file):
    for k, v in json.load(open(a.ids_file)).items():
        got.setdefault(k, []).extend(v)
eng = open_store(SemanticSettings.from_env().store_dsn).engine
E.ensure(eng)
AUDIT = sa.Table("semantic_audit", sa.MetaData(), autoload_with=eng)
counts: dict[str, int] = {}
files: list[str] = []
with eng.begin() as c:
    fairs = got["fairs"]
    if fairs:
        got["tasks"] += list(c.execute(sa.select(E.TASKS.c.id).where(E.TASKS.c.fair_id.in_(fairs))).scalars())
        got["costs"] += list(c.execute(sa.select(E.COSTS.c.id).where(E.COSTS.c.fair_id.in_(fairs))).scalars())
        got["authors"] += list(c.execute(sa.select(E.AUTHORS.c.id).where(E.AUTHORS.c.fair_id.in_(fairs))).scalars())
        files += [f"{r.fair_id}/{r.receipt_ref}" for r in c.execute(sa.select(E.COSTS.c.fair_id, E.COSTS.c.receipt_ref)
                                                                     .where(E.COSTS.c.fair_id.in_(fairs), E.COSTS.c.receipt_ref.isnot(None)))]
        for name, t, col in (("kitap", E.BOOKS, E.BOOKS.c.fair_id), ("görev", E.TASKS, E.TASKS.c.fair_id),
                             ("gider", E.COSTS, E.COSTS.c.fair_id), ("yazar programı", E.AUTHORS, E.AUTHORS.c.fair_id),
                             ("kart", E.FAIRS, E.FAIRS.c.id)):
            counts[name] = c.execute(sa.select(sa.func.count()).select_from(t).where(col.in_(fairs))).scalar()
            if not a.dry:
                c.execute(t.delete().where(col.in_(fairs)))
    awards = got["awards"]
    if awards:
        got["entries"] = list(c.execute(sa.select(E.ENTRIES.c.id).where(E.ENTRIES.c.award_id.in_(awards))).scalars())
        counts["başvuru"] = len(got["entries"])
        counts["ödül"] = c.execute(sa.select(sa.func.count()).select_from(E.AWARDS).where(E.AWARDS.c.id.in_(awards))).scalar()
        if not a.dry:
            c.execute(E.ENTRIES.delete().where(E.ENTRIES.c.award_id.in_(awards)))
            c.execute(E.AWARDS.delete().where(E.AWARDS.c.id.in_(awards)))
    every = [x for k in ("fairs", "tasks", "costs", "authors", "awards", "entries") for x in got.get(k, [])]
    if every:
        rem = E.REMINDERS.c.ref_id.in_(every)
        counts["hatırlatma"] = c.execute(sa.select(sa.func.count()).select_from(E.REMINDERS).where(rem)).scalar()
        if not a.dry:
            c.execute(E.REMINDERS.delete().where(rem))
    kinds = sa.or_(AUDIT.c.kind.like("events%"), AUDIT.c.kind.like("award%"))
    by_obj = sa.or_(AUDIT.c.object_id.in_(every), *[AUDIT.c.detail.like(f"%{i}%") for i in fairs]) if every else sa.false()
    if a.actor and a.since:
        by_obj = sa.or_(by_obj, sa.and_(AUDIT.c.actor == a.actor, AUDIT.c.at >= datetime.fromisoformat(a.since)))
    counts["değişiklik kaydı"] = c.execute(sa.select(sa.func.count()).select_from(AUDIT).where(kinds, by_obj)).scalar()
    if not a.dry:
        c.execute(AUDIT.delete().where(kinds, by_obj))
removed = 0
if not a.dry:
    for rel in files:
        p = E.files_root() / rel
        try:
            p.unlink()
            removed += 1
        except OSError:
            pass
    for f in got["fairs"]:
        try:
            (E.files_root() / f).rmdir()
        except OSError:
            pass
counts["fiş dosyası"] = removed if not a.dry else len(files)
print(("(deneme, silinmedi) " if a.dry else "silindi: ") + json.dumps(counts, ensure_ascii=False))
