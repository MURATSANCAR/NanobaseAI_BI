"""M47 kabulünün bıraktığı kayıtları kimlikle siler: risk (aksiyon, gözden geçirme, gösterge bağı, dosyalar), uyum
yükümlülüğü (dönemleri ve kanıt dosyaları), poliçe, BCP, brifing ve işleri, kabul sırasında `--actor` adına yazılan
gösterge ölçümleri (ve ölçümü kalmayan göstergenin kenar durumu), hatırlatma kayıtları ve değişiklik kaydı satırları
(risk*, compliance*). Silinen sayılar günlüğe yazılır.

Kullanım: cleanup.py --ids-file /tmp/claude-m47/kabul-kimlikler.json --actor timasai [--dry]
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.environ.get("M47_BACKEND", "/data/nanobaseai/bi/frontend/backend"))
import sqlalchemy as sa  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402
from semantic_bridge import risk as R  # noqa: E402

ap = argparse.ArgumentParser()
ap.add_argument("--ids-file", required=True)
ap.add_argument("--actor", default="timasai")
ap.add_argument("--dry", action="store_true")
a = ap.parse_args()
ids = json.load(open(a.ids_file))
since = datetime.fromisoformat(ids["since"])
risks, items, pols, bcps, reps = (ids.get(k, []) for k in ("risks", "items", "policies", "bcp", "reports"))
eng = open_store(SemanticSettings.from_env().store_dsn).engine
R.ensure(eng)
AUDIT = sa.Table("semantic_audit", sa.MetaData(), autoload_with=eng)
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
    act_ids = [r.id for r in c.execute(sa.select(R.ACTIONS.c.id).where(R.ACTIONS.c.risk_id.in_(risks or [""])))]
    run(c, "aksiyon", R.ACTIONS, R.ACTIONS.c.risk_id.in_(risks or [""]), ("kanit_yolu",))
    run(c, "gözden geçirme", R.REVIEWS, R.REVIEWS.c.risk_id.in_(risks or [""]))
    run(c, "gösterge bağı", R.LINKS, R.LINKS.c.risk_id.in_(risks or [""]))
    run(c, "risk", R.RISKS, R.RISKS.c.id.in_(risks or [""]))
    ev_ids = [r.id for r in c.execute(sa.select(R.COMP_EVENTS.c.id).where(R.COMP_EVENTS.c.item_id.in_(items or [""])))]
    run(c, "uyum dönemi", R.COMP_EVENTS, R.COMP_EVENTS.c.item_id.in_(items or [""]), ("kanit_yolu",))
    run(c, "uyum maddesi", R.COMP_ITEMS, R.COMP_ITEMS.c.id.in_(items or [""]))
    run(c, "poliçe", R.POLICIES, R.POLICIES.c.id.in_(pols or [""]), ("belge_yolu",))
    run(c, "bcp", R.BCP, R.BCP.c.id.in_(bcps or [""]))
    run(c, "brifing", R.REPORTS, R.REPORTS.c.id.in_(reps or [""]))
    run(c, "iş", R.JOBS, sa.and_(R.JOBS.c.baslatan == a.actor, R.JOBS.c.baslangic >= since))
    run(c, "ölçüm", R.VALUES, sa.and_(R.VALUES.c.olcen == a.actor, R.VALUES.c.olcum_at >= since))
    keys = risks + act_ids + ev_ids + pols
    rem = sa.or_(*[R.REMINDERS.c.key.like(f"%:{i}%") for i in keys]) if keys else sa.false()
    run(c, "hatırlatma", R.REMINDERS, rem)
    # Ölçümü kalmayan göstergenin kenar durumu (kabul ilk ölçümse) silinir; sistem ölçümü varsa dokunulmaz.
    if not a.dry:
        left = {r.kod for r in c.execute(sa.select(R.VALUES.c.kod).distinct())}
        orphan = [r.kod for r in c.execute(sa.select(R.ALERT_STATE.c.kod)) if r.kod not in left]
        counts["kenar durumu"] = len(orphan)
        if orphan:
            c.execute(R.ALERT_STATE.delete().where(R.ALERT_STATE.c.kod.in_(orphan)))
    all_ids = risks + items + pols + bcps + reps + act_ids + ev_ids
    by_obj = sa.or_(*[AUDIT.c.object_id == i for i in all_ids], *[AUDIT.c.detail.like(f"%{i}%") for i in risks]) if all_ids else sa.false()
    cond = sa.and_(sa.or_(AUDIT.c.kind.like("risk%"), AUDIT.c.kind.like("compliance%")),
                   sa.or_(by_obj, sa.and_(AUDIT.c.actor == a.actor, AUDIT.c.at >= since, AUDIT.c.kind == "risk_indicator")))
    counts["değişiklik kaydı"] = c.execute(sa.select(sa.func.count()).select_from(AUDIT).where(cond)).scalar()
    if not a.dry:
        c.execute(AUDIT.delete().where(cond))
removed = 0
if not a.dry:
    for p in paths:
        if p and Path(p).exists():
            Path(p).unlink()
            removed += 1
    for sub in ("aksiyon", "uyum", "police"):
        root = R.files_root() / sub
        if root.is_dir():
            for d in root.iterdir():
                if d.is_dir() and not any(d.iterdir()):
                    d.rmdir()
counts["disk dosyası"] = removed if not a.dry else len(paths)
print("silinecek" if a.dry else "silinen", counts)
