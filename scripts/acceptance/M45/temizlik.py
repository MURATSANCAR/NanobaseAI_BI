"""M45 kabulünün bıraktığı kayıtları siler: kimlikle vergi takvimi kayıtları, kabul oturumunun (timasai) değişiklik kaydı
satırları (finance_* türleri) ve kabulde yazılmışsa sapma notları. Logo okumasının anlık görüntüsü (`semantic_finance_*`
gerçekleşme tabloları, nakit tablosu koşusu) test verisi değildir; uygulamanın kendi durumudur, kalır.
Silinen sayılar ekrana (ve günlüğe) yazılır.

Kullanım: temizlik.py --ids-file /tmp/claude-m45/kabul-kimlikler.json --actor timasai --since 2026-09-28T10:00 [--dry]
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.environ.get("M45_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402
from semantic_bridge import finance as F  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ids-file", default="")
ap.add_argument("--actor", default="")
ap.add_argument("--since", default="")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
ids = json.load(open(a.ids_file)) if a.ids_file else {}
tax = list(ids.get("tax") or [])
eng = open_store(SemanticSettings.from_env().store_dsn).engine
F.ensure(eng)
AUDIT = sa.Table("semantic_audit", sa.MetaData(), autoload_with=eng)
counts = {}
with eng.begin() as c:
    if a.actor and a.since:
        since = datetime.fromisoformat(a.since)
        extra = [r.id for r in c.execute(sa.select(F.TAX.c.id).where(F.TAX.c.created_by == a.actor, F.TAX.c.created_at >= since,
                                                                      F.TAX.c.beyan.like("KABUL DENEMESİ%")))]
        tax = list(dict.fromkeys(tax + extra))
    if tax:
        counts["vergi takvimi"] = c.execute(sa.select(sa.func.count()).select_from(F.TAX).where(F.TAX.c.id.in_(tax))).scalar()
        if not a.dry:
            c.execute(F.TAX.delete().where(F.TAX.c.id.in_(tax)))
    if a.actor and a.since:
        since = datetime.fromisoformat(a.since)
        note = [F.NOTES.c.hazirlayan == a.actor, F.NOTES.c.tarih >= since]
        counts["sapma notu"] = c.execute(sa.select(sa.func.count()).select_from(F.NOTES).where(*note)).scalar()
        cond = [AUDIT.c.kind.like("finance_%"), AUDIT.c.actor == a.actor, AUDIT.c.at >= since]
        counts["değişiklik kaydı"] = c.execute(sa.select(sa.func.count()).select_from(AUDIT).where(*cond)).scalar()
        if not a.dry:
            c.execute(F.NOTES.delete().where(*note))
            c.execute(AUDIT.delete().where(*cond))
print("silinecek" if a.dry else "silinen", counts)
