"""Öneri 4–8 kabulünün bıraktığı kayıtları siler: timasai'nin panosuna eklenen geçici kartlar (`semantic_board_cards`,
kimlik «zf-» ile başlar ya da `--ids-file`). Uyarı eşik önerisi, «Neden?», bütçe sapma nedeni ve nakit bandı yazmaz.
Değişiklik kaydı (`semantic_audit`) satırları gerçek hesabın izi olduğu için silinmez; aralık ekrana yazılır.

Kullanım: temizlik.py --ids-file /tmp/claude-zf/kabul-kimlikler.json --user timasai [--dry]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.environ.get("ZK_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402
from semantic_bridge import board as B  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ids-file", default="")
ap.add_argument("--user", default="timasai")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
ids = list((json.load(open(a.ids_file)) if a.ids_file else {}).get("kart") or [])
eng = open_store(SemanticSettings.from_env().store_dsn).engine
B.ensure(eng)
with eng.begin() as c:
    q = sa.select(B.CARDS.c.id).where(sa.func.lower(B.CARDS.c.username) == a.user.lower(),
                                      sa.or_(B.CARDS.c.id.in_(ids or [""]), B.CARDS.c.id.like("zf-%")))
    found = [r.id for r in c.execute(q)]
    if found and not a.dry:
        c.execute(B.CARDS.delete().where(B.CARDS.c.id.in_(found)))
    audit = sa.Table("semantic_audit", sa.MetaData(), autoload_with=eng)
    cols = audit.c
    print("değişiklik kaydı (silinmedi, günlüğe yazın):",
          tuple(c.execute(sa.select(sa.func.min(cols.id), sa.func.max(cols.id), sa.func.count()).where(
              cols.actor == a.user, cols.kind.in_(["board", "fark"]))).first()))
print(("(deneme) " if a.dry else "") + "silinen pano kartı:", len(found), found)
