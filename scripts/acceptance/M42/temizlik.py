"""M42 kabulünün bıraktığı kayıtları siler: kabul oturumunun (varsayılan timasai) `--since` anından sonraki kanal değişiklik
kaydı satırları (channel_*: okuma, dışa aktarma; kabul eşleme/öneri/yükleme yazmaz ama yazıldıysa onlar da). `--suggestions`
ve `--imports` verilen kimlikleri (elle deneme yapıldıysa) de siler. Önbellek (Logo/CRM okuması) test verisi değildir,
silinmez. Silinen sayılar ekrana ve günlüğe yazılır.

Kullanım: temizlik.py --since 2026-09-28T10:00:00+00:00 [--actor timasai] [--suggestions a,b] [--imports c] [--dry]
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.environ.get("M42_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402
from semantic_bridge.channels import store as S  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--since", required=True)
ap.add_argument("--actor", default="timasai")
ap.add_argument("--suggestions", default="")
ap.add_argument("--imports", default="")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
since = datetime.fromisoformat(a.since)
eng = open_store(SemanticSettings.from_env().store_dsn).engine
S.ensure(eng)
AUDIT = sa.Table("semantic_audit", sa.MetaData(), autoload_with=eng)
counts: dict[str, int] = {}
sugs = [x for x in a.suggestions.split(",") if x]
imps = [x for x in a.imports.split(",") if x]
with eng.begin() as c:
    cond = [AUDIT.c.kind.like("channel%"), AUDIT.c.actor == a.actor, AUDIT.c.at >= since]
    counts["değişiklik kaydı"] = c.execute(sa.select(sa.func.count()).select_from(AUDIT).where(*cond)).scalar()
    if sugs:
        counts["öneri"] = c.execute(sa.select(sa.func.count()).select_from(S.SUGGESTIONS).where(S.SUGGESTIONS.c.id.in_(sugs))).scalar()
    if imps:
        counts["yükleme"] = c.execute(sa.select(sa.func.count()).select_from(S.IMPORTS).where(S.IMPORTS.c.id.in_(imps))).scalar()
    if not a.dry:
        c.execute(AUDIT.delete().where(*cond))
        if sugs:
            c.execute(S.SUGGESTIONS.delete().where(S.SUGGESTIONS.c.id.in_(sugs)))
        if imps:
            c.execute(S.IMPORT_ROWS.delete().where(S.IMPORT_ROWS.c.import_id.in_(imps)))
            c.execute(S.IMPORTS.delete().where(S.IMPORTS.c.id.in_(imps)))
print(("[deneme] " if a.dry else "") + "silinen: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
