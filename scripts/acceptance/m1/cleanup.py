"""Kabul testinin bıraktığı M1 kayıtlarını kimlikle siler: başvuru, dosya (disk dahil), rapor, yazı, günlük, oturum,
gündem, oy ve bu kimliklere ait değişiklik kaydı satırları. Kullanım: cleanup.py --apps id1,id2 --sessions s1 [--dry]"""
import argparse, os, sys
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
import sqlalchemy as sa
from semantic_layer.config import SemanticSettings
from semantic_layer.store.catalog_store import open_store
from semantic_bridge import editorial_applications as M

ap = argparse.ArgumentParser()
ap.add_argument("--apps", default="")
ap.add_argument("--sessions", default="")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
apps = [x for x in a.apps.split(",") if x]
sess = [x for x in a.sessions.split(",") if x]
eng = open_store(SemanticSettings.from_env().store_dsn).engine
M.ensure(eng)
md = sa.MetaData()
AUDIT = sa.Table("semantic_audit", md, autoload_with=eng)
cols = AUDIT.c.keys()
print("audit kolonları:", cols)
ids = apps + sess
with eng.begin() as c:
    files = [r.path for r in c.execute(sa.select(M.FILES.c.path).where(M.FILES.c.app_id.in_(apps)))] if apps else []
    lids = [r.id for r in c.execute(sa.select(M.LETTERS.c.id).where(M.LETTERS.c.app_id.in_(apps)))] if apps else []
    fids = [r.id for r in c.execute(sa.select(M.FILES.c.id).where(M.FILES.c.app_id.in_(apps)))] if apps else []
    counts = {}
    obj = AUDIT.c.object_id if "object_id" in cols else None
    counts["audit"] = c.execute(sa.select(sa.func.count()).select_from(AUDIT).where(obj.in_(ids + lids + fids))).scalar() if obj is not None and ids else 0
    for name, t, col, vals in (("oy", M.VOTES, M.VOTES.c.session_id, sess), ("oy(başvuru)", M.VOTES, M.VOTES.c.app_id, apps),
                               ("gündem", M.AGENDA, M.AGENDA.c.app_id, apps), ("gündem(oturum)", M.AGENDA, M.AGENDA.c.session_id, sess),
                               ("oturum", M.SESSIONS, M.SESSIONS.c.id, sess), ("yazı", M.LETTERS, M.LETTERS.c.app_id, apps),
                               ("rapor", M.REPORTS, M.REPORTS.c.app_id, apps), ("değerlendirme", M.EVALS, M.EVALS.c.app_id, apps),
                               ("günlük", M.LOG, M.LOG.c.app_id, apps), ("dosya", M.FILES, M.FILES.c.app_id, apps),
                               ("başvuru", M.APPS, M.APPS.c.id, apps)):
        if not vals:
            continue
        n = c.execute(sa.select(sa.func.count()).select_from(t).where(col.in_(vals))).scalar()
        counts[name] = counts.get(name, 0) + n
        if not a.dry:
            c.execute(t.delete().where(col.in_(vals)))
    if not a.dry and obj is not None and ids:
        c.execute(AUDIT.delete().where(obj.in_(ids + lids + fids)))
print("silinen" if not a.dry else "silinecek", counts)
if not a.dry:
    for p in files:
        try:
            os.remove(p)
            print("dosya silindi", p)
        except OSError as e:
            print("dosya silinemedi", p, e)
    for aid in apps:
        d = os.path.join(M._root(), SemanticSettings.from_env().tenant_id, aid)
        try:
            os.rmdir(d)
        except OSError:
            pass
