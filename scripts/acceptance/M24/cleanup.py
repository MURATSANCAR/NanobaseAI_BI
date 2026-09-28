"""M24 kabulünün bıraktığı kayıtları kimlikle siler: katalog, katalog kitapları, bülten, bülten kitapları, sonuçlar,
Zeki AI işleri ve bu kayıtlara ait değişiklik kaydı satırları (catalog*, newsletter*). Kitap havuzu anlık görüntüsü
(`semantic_catalog_meta`) test verisi değildir, silinmez. Silinen sayılar günlüğe yazılır.

Kullanım: cleanup.py --ids-file /tmp/claude-m24/kabul-kimlikler.json [--catalogs a,b] [--newsletters c,d]
          [--actor timasai --since 2026-09-28T10:00] [--dry]
`--actor/--since` o kişinin o andan sonraki catalog*/newsletter* değişiklik kaydını da siler (segment sayımı dahil).
"""
import argparse
import json
import os
import sys
from datetime import datetime

# Aday ağaç (git archive) önce: canlı ağaçta M24 kodu kurulumdan önce yoktur.
sys.path.insert(0, os.environ.get("M24_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402
from semantic_bridge import catalogs as C  # noqa: E402
from semantic_bridge import newsletters as N  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ids-file", default="")
ap.add_argument("--catalogs", default="")
ap.add_argument("--newsletters", default="")
ap.add_argument("--actor", default="")
ap.add_argument("--since", default="")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
cats = [x for x in a.catalogs.split(",") if x]
nls = [x for x in a.newsletters.split(",") if x]
if a.ids_file:
    d = json.load(open(a.ids_file))
    cats += d.get("catalogs", [])
    nls += d.get("newsletters", [])
cats, nls = list(dict.fromkeys(cats)), list(dict.fromkeys(nls))
eng = open_store(SemanticSettings.from_env().store_dsn).engine
C.ensure(eng)
N.ensure(eng)
AUDIT = sa.Table("semantic_audit", sa.MetaData(), autoload_with=eng)
counts: dict[str, int] = {}
with eng.begin() as c:
    for name, t, col, ids in (("katalog kitabı", C.ITEMS, C.ITEMS.c.catalog_id, cats), ("iş", C.JOBS, C.JOBS.c.ref_id, cats + nls),
                              ("katalog", C.CATALOGS, C.CATALOGS.c.id, cats),
                              ("bülten kitabı", N.NL_ITEMS, N.NL_ITEMS.c.newsletter_id, nls),
                              ("bülten sonucu", N.RESULTS, N.RESULTS.c.newsletter_id, nls),
                              ("bülten", N.NEWSLETTERS, N.NEWSLETTERS.c.id, nls)):
        if not ids:
            continue
        counts[name] = c.execute(sa.select(sa.func.count()).select_from(t).where(col.in_(ids))).scalar()
        if not a.dry:
            c.execute(t.delete().where(col.in_(ids)))
    keys = cats + nls
    cond = [sa.or_(AUDIT.c.kind.like("catalog%"), AUDIT.c.kind.like("newsletter%"))]
    by_obj = sa.or_(*[AUDIT.c.object_id.like(f"{i}%") for i in keys]) if keys else sa.false()
    if a.actor and a.since:
        by_obj = sa.or_(by_obj, sa.and_(AUDIT.c.actor == a.actor, AUDIT.c.at >= datetime.fromisoformat(a.since)))
    counts["değişiklik kaydı"] = c.execute(sa.select(sa.func.count()).select_from(AUDIT).where(*cond, by_obj)).scalar()
    if not a.dry:
        c.execute(AUDIT.delete().where(*cond, by_obj))
print("silinecek" if a.dry else "silinen", counts, "kataloglar:", cats, "bültenler:", nls)
