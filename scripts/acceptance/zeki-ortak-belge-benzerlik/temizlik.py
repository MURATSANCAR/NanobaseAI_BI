"""Belge okuma / kitap benzerliği / soru kümeleri kabulünün bıraktığı kayıtları siler: kabulde kurulan «öneri»
durumundaki soru kümeleri ve üyeleri (`semantic_mq_clusters`, `semantic_mq_cluster_members`) — kimlikle; ayrıca kabul
hesabının (timasai) başlangıç zamanından sonra verdiği küme kararları ve yazdığı soru sınıfları
(`semantic_mq_query_classes`), kabul karar vermez ama elle denenmişse kalmasın diye. Kitap benzerliği dizini
(`semantic_book_embeddings`) ürün verisidir, silinmez. OCR kabulü hiçbir şey yazmaz (kart servisi deftere yazmaz).
Değişiklik kaydı (`semantic_audit`) satırları gerçek hesabın izi olduğu için silinmez. Silinen sayılar ekrana yazılır.

Kullanım: temizlik.py --ids-file /tmp/claude-benzerlik/kabul.json --actor timasai --since 2026-09-28T10:00 [--dry]
"""
import argparse
import json
from datetime import datetime

import sqlalchemy as sa
from semantic_layer.config import SemanticSettings
from semantic_layer.store.catalog_store import open_store
from semantic_bridge import model_quality_clusters as MC

ap = argparse.ArgumentParser()
ap.add_argument("--ids-file", default="")
ap.add_argument("--actor", default="")
ap.add_argument("--since", default="")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
ids = list((json.load(open(a.ids_file)) if a.ids_file else {}).get("kume") or [])
eng = open_store(SemanticSettings.from_env().store_dsn).engine
MC.ensure(eng)
counts = {}
with eng.begin() as c:
    if a.actor and a.since:
        since = datetime.fromisoformat(a.since)
        decided = [r[0] for r in c.execute(sa.select(MC.CLUSTERS.c.id).where(MC.CLUSTERS.c.decided_by == a.actor,
                                                                           MC.CLUSTERS.c.decided_at >= since))]
        ids += decided
        q = MC.QUERY_CLASSES.delete().where(MC.QUERY_CLASSES.c.decided_by == a.actor, MC.QUERY_CLASSES.c.decided_at >= since)
        counts["soru sınıfı (küme kararı)"] = c.execute(sa.select(sa.func.count()).select_from(MC.QUERY_CLASSES).where(
            MC.QUERY_CLASSES.c.decided_by == a.actor, MC.QUERY_CLASSES.c.decided_at >= since)).scalar()
        if not a.dry:
            c.execute(q)
    ids = list(dict.fromkeys(ids))
    counts["küme"] = c.execute(sa.select(sa.func.count()).select_from(MC.CLUSTERS).where(MC.CLUSTERS.c.id.in_(ids))).scalar() if ids else 0
    counts["küme üyesi"] = c.execute(sa.select(sa.func.count()).select_from(MC.MEMBERS).where(MC.MEMBERS.c.cluster_id.in_(ids))).scalar() if ids else 0
    if ids and not a.dry:
        c.execute(MC.MEMBERS.delete().where(MC.MEMBERS.c.cluster_id.in_(ids)))
        c.execute(MC.CLUSTERS.delete().where(MC.CLUSTERS.c.id.in_(ids)))
for k, v in counts.items():
    print(f"{'(kuru) ' if a.dry else ''}silinen {k}: {v}")
