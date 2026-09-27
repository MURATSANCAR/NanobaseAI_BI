"""M31 kabul testinin bıraktığı kayıtları kimlikle siler: ortak ziyaret tablosundaki okul ziyareti ve ayrıntısı, plan,
katalog, bayi bağı ve bu kimliklere ait değişiklik kaydı (semantic_audit) satırları. Test kullanıcısı/verisi bırakılmaz
(AGENTS.md). Kullanım:

    cleanup.py --file /tmp/claude-m31/created.json [--visits id1,id2] [--plans …] [--catalogs …] [--links …] [--dry]

Kimliği verilmeyen hiçbir satıra dokunmaz; silinen sayılar ekrana (günlüğe yazılmak üzere) basılır."""
import argparse
import json
import os
import sys

sys.path.insert(0, os.environ.get("BI_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402
from semantic_bridge import school_visits as SV  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--file", default="")
ap.add_argument("--visits", default="")
ap.add_argument("--plans", default="")
ap.add_argument("--catalogs", default="")
ap.add_argument("--links", default="")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()


def ids(s):
    return [x for x in s.split(",") if x]


got = {"visits": ids(a.visits), "plans": ids(a.plans), "catalogs": ids(a.catalogs), "links": ids(a.links)}
if a.file and os.path.exists(a.file):
    for k, v in json.load(open(a.file)).items():
        got.setdefault(k, []).extend(v)
eng = open_store(SemanticSettings.from_env().store_dsn).engine
SV.ensure(eng)
AUDIT = sa.Table("semantic_audit", sa.MetaData(), autoload_with=eng)
obj = AUDIT.c.object_id if "object_id" in AUDIT.c else None
every = [x for v in got.values() for x in v]
counts = {}
with eng.begin() as c:
    for name, t, col, vals in (("ziyaret ayrıntısı", SV.VISIT_DETAILS, SV.VISIT_DETAILS.c.ziyaret_id, got["visits"]),
                               ("okul ziyareti", SV.SAHA_ZIYARET, SV.SAHA_ZIYARET.c.id, got["visits"]),
                               ("plan", SV.PLANS, SV.PLANS.c.id, got["plans"]),
                               ("katalog", SV.CATALOGS, SV.CATALOGS.c.id, got["catalogs"]),
                               ("bayi bağı", SV.DEALER_LINKS, SV.DEALER_LINKS.c.id, got["links"])):
        if not vals:
            continue
        where = col.in_(vals)
        if t is SV.SAHA_ZIYARET:
            where = sa.and_(where, SV.SAHA_ZIYARET.c.tur == "okul")
        counts[name] = c.execute(sa.select(sa.func.count()).select_from(t).where(where)).scalar()
        if not a.dry:
            c.execute(t.delete().where(where))
    if obj is not None and every:
        counts["değişiklik kaydı"] = c.execute(sa.select(sa.func.count()).select_from(AUDIT).where(obj.in_(every))).scalar()
        if not a.dry:
            c.execute(AUDIT.delete().where(obj.in_(every)))
print("silinecek" if a.dry else "silinen", counts)
