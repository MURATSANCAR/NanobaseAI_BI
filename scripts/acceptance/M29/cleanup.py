"""M29 kabulünün bıraktığı kayıtları kimlikle siler: plan, satır, benzer kitap, takip, uyarı ve bu planlara ait
değişiklik kaydı satırları (dist_plan / dist_line / dist_export). «Dağılım bekleyen kitaplar» anlık görüntüsü
(`semantic_dist_books`, `semantic_dist_meta`) test verisi değildir, kalır. Silinen sayılar günlüğe yazılır.

Kullanım: cleanup.py --ids-file /tmp/claude-m29/kabul-kimlikler.json [--ids a,b] [--actor timasai --since 2026-09-28T10:00] [--dry]
`--actor/--since` o kişinin o andan sonraki dist_* değişiklik kaydını da siler (liste yenileme satırları dahil).
"""
import argparse
import json
import os
import sys
from datetime import datetime

# Aday ağaç (git archive) önce: canlı ağaçta M29 kodu kurulumdan önce yoktur.
sys.path.insert(0, os.environ.get("M29_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402
from semantic_bridge import distribution as D  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ids-file", default="")
ap.add_argument("--ids", default="")
ap.add_argument("--actor", default="")
ap.add_argument("--since", default="")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
ids = [x for x in a.ids.split(",") if x]
if a.ids_file:
    ids += json.load(open(a.ids_file)).get("plans", [])
eng = open_store(SemanticSettings.from_env().store_dsn).engine
D.ensure(eng)
AUDIT = sa.Table("semantic_audit", sa.MetaData(), autoload_with=eng)
counts = {}
with eng.begin() as c:
    # Revizyonla açılan sürümler de (revision_of) aynı turda silinir.
    more = [r.id for r in c.execute(sa.select(D.PLANS.c.id).where(D.PLANS.c.revision_of.in_(ids)))] if ids else []
    ids = list(dict.fromkeys(ids + more))
    for name, t, col in (("takip", D.TRACKING, D.TRACKING.c.plan_id), ("benzer", D.COMPS, D.COMPS.c.plan_id),
                         ("satır", D.LINES, D.LINES.c.plan_id), ("uyarı", D.ALERTS, D.ALERTS.c.plan_id),
                         ("plan", D.PLANS, D.PLANS.c.id)):
        if not ids:
            continue
        counts[name] = c.execute(sa.select(sa.func.count()).select_from(t).where(col.in_(ids))).scalar()
        if not a.dry:
            c.execute(t.delete().where(col.in_(ids)))
    cond = [AUDIT.c.kind.in_(("dist_plan", "dist_line", "dist_export"))]
    by_obj = sa.or_(*[AUDIT.c.object_id.like(f"{i}%") for i in ids]) if ids else sa.false()
    if a.actor and a.since:
        by_obj = sa.or_(by_obj, sa.and_(AUDIT.c.actor == a.actor, AUDIT.c.at >= datetime.fromisoformat(a.since)))
    counts["değişiklik kaydı"] = c.execute(sa.select(sa.func.count()).select_from(AUDIT).where(*cond, by_obj)).scalar()
    if not a.dry:
        c.execute(AUDIT.delete().where(*cond, by_obj))
print("silinecek" if a.dry else "silinen", counts, "planlar:", ids)
