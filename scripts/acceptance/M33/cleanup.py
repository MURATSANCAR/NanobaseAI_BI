"""M33 kabulünün bıraktığı kayıtları kimlikle siler: ihale, kalem, kontrol listesi, dosya (diskteki dahil), karar,
sonuç, iş, hatırlatma ve bu ihalelere ait değişiklik kaydı satırları (tender*). Şirket belge arşivine kabulde yazılmaz;
`--documents` ile verilen belge kimlikleri de silinir. Silinen sayılar günlüğe yazılır.

Kullanım: cleanup.py --ids-file /tmp/claude-m33/kabul-kimlikler.json [--ids a,b] [--documents d1,d2]
          [--actor timasai --since 2026-09-28T10:00] [--dry]
`--actor/--since` o kişinin o andan sonraki tender* değişiklik kaydını da siler.
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# Aday ağaç (git archive) önce: canlı ağaçta M33 kodu kurulumdan önce yoktur.
sys.path.insert(0, os.environ.get("M33_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402
from semantic_bridge import tenders as T  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ids-file", default="")
ap.add_argument("--ids", default="")
ap.add_argument("--documents", default="")
ap.add_argument("--actor", default="")
ap.add_argument("--since", default="")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
ids = [x for x in a.ids.split(",") if x]
if a.ids_file:
    ids += json.load(open(a.ids_file)).get("tenders", [])
ids = list(dict.fromkeys(ids))
docs = [x for x in a.documents.split(",") if x]
eng = open_store(SemanticSettings.from_env().store_dsn).engine
T.ensure(eng)
AUDIT = sa.Table("semantic_audit", sa.MetaData(), autoload_with=eng)
counts: dict[str, int] = {}
paths: list[str] = []
with eng.begin() as c:
    if ids:
        paths += [r.dosya_yolu for r in c.execute(sa.select(T.FILES.c.dosya_yolu).where(T.FILES.c.tender_id.in_(ids)))]
        for name, t, col in (("kalem", T.ITEMS, T.ITEMS.c.tender_id), ("kontrol", T.CHECKLIST, T.CHECKLIST.c.tender_id),
                             ("dosya", T.FILES, T.FILES.c.tender_id), ("karar", T.DECISIONS, T.DECISIONS.c.tender_id),
                             ("sonuç", T.RESULTS, T.RESULTS.c.tender_id), ("iş", T.JOBS, T.JOBS.c.tender_id),
                             ("ihale", T.TENDERS, T.TENDERS.c.id)):
            counts[name] = c.execute(sa.select(sa.func.count()).select_from(t).where(col.in_(ids))).scalar()
            if not a.dry:
                c.execute(t.delete().where(col.in_(ids)))
        rem = sa.or_(*[T.REMINDERS.c.key.like(f"%:{i}:%") for i in ids])
        counts["hatırlatma"] = c.execute(sa.select(sa.func.count()).select_from(T.REMINDERS).where(rem)).scalar()
        if not a.dry:
            c.execute(T.REMINDERS.delete().where(rem))
    if docs:
        paths += [r.dosya_yolu for r in c.execute(sa.select(T.DOCUMENTS.c.dosya_yolu).where(T.DOCUMENTS.c.id.in_(docs))) if r.dosya_yolu]
        counts["belge"] = c.execute(sa.select(sa.func.count()).select_from(T.DOCUMENTS).where(T.DOCUMENTS.c.id.in_(docs))).scalar()
        if not a.dry:
            c.execute(T.DOCUMENTS.delete().where(T.DOCUMENTS.c.id.in_(docs)))
    cond = [AUDIT.c.kind.like("tender%")]
    keys = ids + docs
    by_obj = sa.or_(*[AUDIT.c.object_id.like(f"{i}%") for i in keys], *[AUDIT.c.detail.like(f"%{i}%") for i in ids]) if keys else sa.false()
    if a.actor and a.since:
        by_obj = sa.or_(by_obj, sa.and_(AUDIT.c.actor == a.actor, AUDIT.c.at >= datetime.fromisoformat(a.since)))
    counts["değişiklik kaydı"] = c.execute(sa.select(sa.func.count()).select_from(AUDIT).where(*cond, by_obj)).scalar()
    if not a.dry:
        c.execute(AUDIT.delete().where(*cond, by_obj))
removed = 0
if not a.dry:
    for p in paths:
        if p and Path(p).exists():
            Path(p).unlink()
            removed += 1
    for i in ids:  # ihale klasörü boş kaldıysa
        d = T.files_root() / i
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
counts["disk dosyası"] = removed if not a.dry else len(paths)
print("silinecek" if a.dry else "silinen", counts, "ihaleler:", ids)
