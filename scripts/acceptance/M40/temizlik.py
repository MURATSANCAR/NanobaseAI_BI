"""M40 kabulünün bıraktığı kayıtları siler: kabul oturumunun (varsayılan timasai) `--since` anından sonraki Trendyol
değişiklik kaydı satırları (trendyol_*: okuma, yükleme, taslak, dışa aktarma; channel_account ve channel_suggestion
yalnız Trendyol için). `--imports`, `--suggestions` verilen kimlikleri (elle deneme yapıldıysa) satırlarıyla siler; yanıt
taslağı yazıldıysa `--drafts-since` ile o andan sonra bu oturumun yazdığı taslak alanları boşaltılır. Önbellek (Logo
okuması, barkod) test verisi değildir, silinmez. Silinen sayılar ekrana yazılır (günlüğe geçirilir).

Kullanım: temizlik.py --since 2026-09-28T10:00:00+00:00 [--actor timasai] [--imports a,b] [--suggestions c] [--dry]
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.environ.get("M40_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402
from semantic_bridge.channels import store as S  # noqa: E402
from semantic_bridge.channels import trendyol as T  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--since", required=True)
ap.add_argument("--actor", default="timasai")
ap.add_argument("--imports", default="")
ap.add_argument("--suggestions", default="")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
since = datetime.fromisoformat(a.since)
eng = open_store(SemanticSettings.from_env().store_dsn).engine
T.ensure(eng)
AUDIT = sa.Table("semantic_audit", sa.MetaData(), autoload_with=eng)
imps = [x for x in a.imports.split(",") if x]
sugs = [x for x in a.suggestions.split(",") if x]
counts: dict[str, int] = {}
with eng.begin() as c:
    cond = [AUDIT.c.kind.like("trendyol%"), AUDIT.c.actor == a.actor, AUDIT.c.at >= since]
    counts["değişiklik kaydı"] = c.execute(sa.select(sa.func.count()).select_from(AUDIT).where(*cond)).scalar()
    drafts = [T.QUESTIONS.c.taslak_yazan == a.actor, T.QUESTIONS.c.taslak_zamani >= since]
    counts["soru taslağı"] = c.execute(sa.select(sa.func.count()).select_from(T.QUESTIONS).where(*drafts)).scalar()
    rdrafts = [T.REVIEWS.c.taslak_yazan == a.actor, T.REVIEWS.c.taslak_zamani >= since]
    counts["yorum taslağı"] = c.execute(sa.select(sa.func.count()).select_from(T.REVIEWS).where(*rdrafts)).scalar()
    if imps:
        counts["yükleme"] = c.execute(sa.select(sa.func.count()).select_from(T.IMPORTS).where(T.IMPORTS.c.id.in_(imps))).scalar()
    if sugs:
        counts["öneri"] = c.execute(sa.select(sa.func.count()).select_from(S.SUGGESTIONS).where(S.SUGGESTIONS.c.id.in_(sugs),
                                                                                               S.SUGGESTIONS.c.platform == "trendyol")).scalar()
    if not a.dry:
        c.execute(AUDIT.delete().where(*cond))
        c.execute(AUDIT.delete().where(AUDIT.c.kind.in_(["channel_account", "channel_suggestion"]), AUDIT.c.actor == a.actor,
                                       AUDIT.c.at >= since, sa.or_(AUDIT.c.detail.like('%"M40"%'), AUDIT.c.detail.like('%vitrin%'))))
        c.execute(T.QUESTIONS.update().where(*drafts).values(taslak=None, taslak_yazan=None, taslak_zamani=None))
        c.execute(T.REVIEWS.update().where(*rdrafts).values(taslak=None, taslak_yazan=None, taslak_zamani=None))
        for iid in imps:
            for tb in T.TABLES.values():
                c.execute(tb.delete().where(tb.c.import_id == iid))
            c.execute(T.IMPORTS.delete().where(T.IMPORTS.c.id == iid))
        if sugs:
            c.execute(S.SUGGESTIONS.delete().where(S.SUGGESTIONS.c.id.in_(sugs), S.SUGGESTIONS.c.platform == "trendyol"))
print(("[deneme] " if a.dry else "") + "silinen: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
