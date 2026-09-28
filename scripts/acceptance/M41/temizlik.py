"""M41 kabulünün bıraktığı kayıtları siler: kabul oturumunun (varsayılan timasai) `--since` anından sonraki Amazon/yurtdışı
değişiklik kaydı satırları (amazon_*, intl_*; M41 kaynaklı channel_account). `--drafts`, `--cards`, `--params` verilen
kimlikleri (kabulde M41_TASLAK ya da elle deneme yapıldıysa) siler. Önbellek (Logo/CRM okuması) test verisi değildir,
silinmez. Silinen sayılar ekrana yazılır (günlüğe geçirilir).

Kullanım: temizlik.py --since 2026-09-28T10:00:00+00:00 [--actor timasai] [--drafts a,b] [--cards c] [--params DE] [--dry]
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.environ.get("M41_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402
from semantic_bridge.channels import amazon as A  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--since", required=True)
ap.add_argument("--actor", default="timasai")
ap.add_argument("--drafts", default="")
ap.add_argument("--cards", default="")
ap.add_argument("--params", default="")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
since = datetime.fromisoformat(a.since)
eng = open_store(SemanticSettings.from_env().store_dsn).engine
A.ensure(eng)
AUDIT = sa.Table("semantic_audit", sa.MetaData(), autoload_with=eng)
ids = {k: [x for x in v.split(",") if x] for k, v in (("drafts", a.drafts), ("cards", a.cards), ("params", a.params))}
counts: dict[str, int] = {}
with eng.begin() as c:
    cond = [sa.or_(AUDIT.c.kind.like("amazon%"), AUDIT.c.kind.like("intl%"),
                   sa.and_(AUDIT.c.kind == "channel_account", AUDIT.c.detail.like('%"M41"%'))),
            AUDIT.c.actor == a.actor, AUDIT.c.at >= since]
    counts["değişiklik kaydı"] = c.execute(sa.select(sa.func.count()).select_from(AUDIT).where(*cond)).scalar()
    for key, table, col in (("drafts", A.DRAFTS, A.DRAFTS.c.id), ("cards", A.CARDS, A.CARDS.c.id), ("params", A.PARAMS, A.PARAMS.c.pazar)):
        if ids[key]:
            counts[key] = c.execute(sa.select(sa.func.count()).select_from(table).where(col.in_(ids[key]))).scalar()
    if not a.dry:
        c.execute(AUDIT.delete().where(*cond))
        if ids["drafts"]:
            c.execute(A.DRAFTS.delete().where(A.DRAFTS.c.id.in_(ids["drafts"])))
        if ids["cards"]:
            c.execute(A.CARDS.delete().where(A.CARDS.c.id.in_(ids["cards"])))
        if ids["params"]:
            c.execute(A.PARAMS.delete().where(A.PARAMS.c.pazar.in_([x.upper() for x in ids["params"]])))
print(("[deneme] " if a.dry else "") + "silinen: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
