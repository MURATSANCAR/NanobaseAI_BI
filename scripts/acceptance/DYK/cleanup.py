"""DYK kabulünün bıraktığı kayıtları kimlikle siler: toplantı (gündem, karar, aksiyon), paket (PDF dosyası ve dağıtım
kaydı dahil), kabul sırasında `--actor` adına açılan Zeki AI işleri ve yorumlar. Gösterge ölçümleri (semantic_kurul_values)
silinmez: zamanlayıcının da yazdığı olağan sistem ölçümüdür, test verisi değildir. `timasai`'nin değişiklik kaydı satırları
AGENTS.md kuralıyla silinmez; kimlik aralığı yazdırılır. Silinen sayılar günlüğe yazılır.

Kullanım: cleanup.py --ids-file /tmp/claude-dyk/kabul-kimlikler.json --actor timasai [--dry]
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.environ.get("DYK_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402
from semantic_bridge import kurul as K  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ids-file", required=True)
ap.add_argument("--actor", default="timasai")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
ids = json.load(open(a.ids_file))
since = datetime.fromisoformat(ids["since"])
meetings, packages = ids.get("meetings", []), ids.get("packages", [])
eng = open_store(SemanticSettings.from_env().store_dsn).engine
K.ensure(eng)
counts: dict[str, int] = {}
paths: list[str] = []


def run(c, name, table, cond, file_cols=()):
    rows = c.execute(sa.select(table).where(cond)).all()
    counts[name] = len(rows)
    for r in rows:
        for col in file_cols:
            p = r._mapping.get(col)
            if p:
                paths.append(p)
    if not a.dry and rows:
        c.execute(table.delete().where(cond))


with eng.begin() as c:
    pk = [r.id for r in c.execute(sa.select(K.PACKAGES.c.id).where(
        sa.or_(K.PACKAGES.c.id.in_(packages or [""]), K.PACKAGES.c.meeting_id.in_(meetings or [""]))))]
    run(c, "dağıtım kaydı", K.DISTRIBUTION, K.DISTRIBUTION.c.package_id.in_(pk or [""]))
    run(c, "paket", K.PACKAGES, K.PACKAGES.c.id.in_(pk or [""]), ("pdf_yol",))
    run(c, "aksiyon", K.ACTIONS, K.ACTIONS.c.meeting_id.in_(meetings or [""]))
    run(c, "karar", K.DECISIONS, K.DECISIONS.c.meeting_id.in_(meetings or [""]))
    run(c, "gündem", K.AGENDA, K.AGENDA.c.meeting_id.in_(meetings or [""]))
    run(c, "toplantı", K.MEETINGS, K.MEETINGS.c.id.in_(meetings or [""]))
    run(c, "iş", K.JOBS, sa.and_(K.JOBS.c.baslatan == a.actor, K.JOBS.c.baslangic >= since))
    run(c, "yorum", K.COMMENTS, sa.and_(K.COMMENTS.c.yazan == a.actor, K.COMMENTS.c.yazildi_at >= since))
    audit = sa.Table("semantic_audit", sa.MetaData(), autoload_with=eng)
    kept = c.execute(sa.select(sa.func.min(audit.c.id), sa.func.max(audit.c.id), sa.func.count()).where(
        audit.c.actor == a.actor, audit.c.kind.like("kurul%"), audit.c.at >= since)).first() if "at" in audit.c else None

removed_files = 0
for p in paths:
    if not a.dry and Path(p).exists():
        Path(p).unlink()
        removed_files += 1
print(("(deneme) " if a.dry else "") + "silinen: " + ", ".join(f"{k} {v}" for k, v in counts.items()) + f", PDF dosyası {removed_files}")
if kept:
    print(f"değişiklik kaydı (silinmedi, {a.actor}): {kept[2]} satır, kimlik {kept[0]}–{kept[1]}")
