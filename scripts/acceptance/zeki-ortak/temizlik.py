"""Ortak Zeki AI kabulünün bıraktığı kayıtları siler: kabulde açılan aylık finansal yorum satırları (`semantic_finance_notes`,
tur='ozet') — kimlikle ya da kabul oturumunun hesabı + başlangıç zamanıyla — ve aynı dönemin yorum kaynağı kaydı
(`semantic_finance_meta` «yorum:…»). Değişiklik kaydı (`semantic_audit`) satırları gerçek hesabın (timasai) izi olduğu
için silinmez (AGENTS.md 2026-09-28); kimlik aralığı ekrana yazılır, günlüğe geçirilir. Sabah brifi ve tahmin aralığı
yazmaz. Silinen sayılar ekrana yazılır.

Kullanım: temizlik.py --ids-file /tmp/claude-zeki/kabul-kimlikler.json --actor timasai --since 2026-09-28T10:00 [--dry]
"""
import argparse
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.environ.get("ZK_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
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
ids = list((json.load(open(a.ids_file)) if a.ids_file else {}).get("yorum") or [])
eng = open_store(SemanticSettings.from_env().store_dsn).engine
F.ensure(eng)
counts = {}
with eng.begin() as c:
    if a.actor and a.since:
        since = datetime.fromisoformat(a.since)
        ids += [r.id for r in c.execute(sa.select(F.NOTES.c.id).where(F.NOTES.c.tur == "ozet", F.NOTES.c.hazirlayan == a.actor,
                                                                        F.NOTES.c.tarih >= since))]
    ids = list(dict.fromkeys(ids))
    rows = c.execute(sa.select(F.NOTES).where(F.NOTES.c.id.in_(ids))).all() if ids else []
    counts["aylık yorum"] = len(rows)
    metas = [f"yorum:{r.tenant_id[:30]}:{int(r.year):04d}-{int(r.month):02d}" for r in rows if r.month]
    counts["yorum kaynağı kaydı"] = c.execute(sa.select(sa.func.count()).select_from(F.META).where(F.META.c.key.in_(metas))).scalar() if metas else 0
    if not a.dry:
        if ids:
            c.execute(F.NOTES.delete().where(F.NOTES.c.id.in_(ids)))
        if metas:
            c.execute(F.META.delete().where(F.META.c.key.in_(metas)))
    if a.actor and a.since:
        audit = sa.Table("semantic_audit", sa.MetaData(), autoload_with=eng)
        cols = audit.c
        q = sa.select(sa.func.min(cols.id), sa.func.max(cols.id), sa.func.count()).where(
            cols.actor == a.actor, cols.kind == "finance_commentary")
        if "at" in cols:
            q = q.where(cols.at >= datetime.fromisoformat(a.since))
        print("değişiklik kaydı (silinmedi, günlüğe yazın):", tuple(c.execute(q).first()))
print(("(deneme) " if a.dry else "") + "silinen:", json.dumps(counts, ensure_ascii=False))
