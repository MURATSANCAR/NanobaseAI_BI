"""M43 kabulünün bıraktığı kayıtları kimlikle siler: taslak güvenlik stoku, not ve bunların değişiklik kaydı satırları
(stock_threshold / stock_note / stock_export / stock_suggestion). Gece fotoğrafı, öneriler ve son koşu özeti test verisi
değildir (gece işinin ürünüdür), kalır. Silinen sayılar günlüğe yazılır.

Kullanım: cleanup.py --ids-file /tmp/claude-m43/kabul-kimlikler.json [--actor timasai --since 2026-09-28T10:00] [--dry]
`--actor/--since` o kişinin o andan sonraki stock_* değişiklik kaydını da siler (Excel indirme satırı dahil).
"""
import argparse
import json
import os
import sys
from datetime import datetime

# Aday ağaç (git archive) önce: canlı ağaçta M43 kodu kurulumdan önce yoktur.
sys.path.insert(0, os.environ.get("M43_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402
from semantic_bridge import stock_store as store  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ids-file", default="")
ap.add_argument("--actor", default="")
ap.add_argument("--since", default="")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
ids = json.load(open(a.ids_file)) if a.ids_file else {"thresholds": [], "notes": []}
eng = open_store(SemanticSettings.from_env().store_dsn).engine
store.ensure(eng)
AUDIT = sa.Table("semantic_audit", sa.MetaData(), autoload_with=eng)
counts = {}
with eng.begin() as c:
    for name, t, col, key in (("eşik", store.THRESHOLDS, store.THRESHOLDS.c.id, "thresholds"),
                              ("not", store.NOTES, store.NOTES.c.id, "notes")):
        vals = ids.get(key) or []
        if not vals:
            continue
        counts[name] = c.execute(sa.select(sa.func.count()).select_from(t).where(col.in_(vals))).scalar()
        if not a.dry:
            c.execute(t.delete().where(col.in_(vals)))
    all_ids = (ids.get("thresholds") or []) + (ids.get("notes") or [])
    cond = [AUDIT.c.kind.in_(("stock_threshold", "stock_note", "stock_export", "stock_suggestion"))]
    by_obj = AUDIT.c.object_id.in_(all_ids) if all_ids else sa.false()
    if a.actor and a.since:
        by_obj = sa.or_(by_obj, sa.and_(AUDIT.c.actor == a.actor, AUDIT.c.at >= datetime.fromisoformat(a.since)))
    counts["değişiklik kaydı"] = c.execute(sa.select(sa.func.count()).select_from(AUDIT).where(*cond, by_obj)).scalar()
    if not a.dry:
        c.execute(AUDIT.delete().where(*cond, by_obj))
print("silinecek" if a.dry else "silinen", counts, "kimlikler:", ids)
