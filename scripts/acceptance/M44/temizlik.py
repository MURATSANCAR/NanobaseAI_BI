"""M44 kabulünün bıraktığı kayıtları kimlikle siler: mesaj taslakları, karar kayıtları ve bunlara ait değişiklik kaydı
satırları (shipping*). Hata sınıfları (semantic_shipping_classes) ve zamanlayıcı damgaları uygulama durumudur, test verisi
değildir; silinmez. Silinen sayılar günlüğe yazılır.

Kullanım: temizlik.py --ids-file /tmp/claude-m44/kabul-kimlikler.json [--actor timasai --since 2026-09-28T10:00] [--dry]
`--actor/--since` o kişinin o andan sonraki shipping* değişiklik kaydını da siler (Excel indirme, eşik denemesi).
"""
import argparse
import json
import os
import sys
from datetime import datetime

# Aday ağaç (git archive) önce: canlı ağaçta M44 kodu kurulumdan önce yoktur.
sys.path.insert(0, os.environ.get("M44_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402
from semantic_bridge import shipping as S  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ids-file", default="")
ap.add_argument("--drafts", default="")
ap.add_argument("--decisions", default="")
ap.add_argument("--actor", default="")
ap.add_argument("--since", default="")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
data = json.load(open(a.ids_file)) if a.ids_file else {}
drafts = list(dict.fromkeys(data.get("drafts", []) + [x for x in a.drafts.split(",") if x]))
decisions = list(dict.fromkeys(data.get("decisions", []) + [x for x in a.decisions.split(",") if x]))
eng = open_store(SemanticSettings.from_env().store_dsn).engine
S.ensure(eng)
AUDIT = sa.Table("semantic_audit", sa.MetaData(), autoload_with=eng)
counts: dict[str, int] = {}
with eng.begin() as c:
    for name, t, ids in (("taslak", S.DRAFTS, drafts), ("karar", S.DECISIONS, decisions)):
        counts[name] = c.execute(sa.select(sa.func.count()).select_from(t).where(t.c.id.in_(ids or ["-"]))).scalar()
        if not a.dry and ids:
            c.execute(t.delete().where(t.c.id.in_(ids)))
    keys = drafts + decisions
    cond = [AUDIT.c.kind.like("shipping%")]
    by_obj = sa.or_(*[AUDIT.c.object_id == i for i in keys]) if keys else sa.false()
    if a.actor and a.since:
        by_obj = sa.or_(by_obj, sa.and_(AUDIT.c.actor == a.actor, AUDIT.c.at >= datetime.fromisoformat(a.since)))
    counts["değişiklik kaydı"] = c.execute(sa.select(sa.func.count()).select_from(AUDIT).where(*cond, by_obj)).scalar()
    if not a.dry:
        c.execute(AUDIT.delete().where(*cond, by_obj))
print("silinecek" if a.dry else "silinen", counts, "taslak:", drafts, "karar:", decisions)
