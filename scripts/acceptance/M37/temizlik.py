#!/usr/bin/env python3
"""M37 kabul testinin bıraktığı kayıtları siler (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»).

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <aday ağaç>/backend && python3 ../scripts/acceptance/M37/temizlik.py --ids /tmp/claude-<oturum>/m37-kimlikler.json \
        --actor timasai --since 2026-09-28T10:00 [--dry]

Silinenler: kabul.py'nin açtığı segment (ölçüm geçmişi dahil) ve program; adı «KABUL TESTİ» ile başlayan artık segment ve
program; `--actor/--since` verilirse o kişinin o andan sonraki `okur_*` değişiklik kaydı satırları. İlgi alanı KVKK kararı,
yorum durumu ve gece anlık görüntüsü kabulde yazılmaz, bu betik onlara dokunmaz. Silinen sayılar ekrana yazılır; günlüğe
geçirilir. CRM'e ve T-soft'a dokunulmaz (zaten yazılmaz).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.environ.get("M37_BACKEND", str(Path(__file__).resolve().parents[3] / "backend")))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import okur as O  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="")
    ap.add_argument("--actor", default="")
    ap.add_argument("--since", default="")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    ids = json.loads(Path(a.ids).read_text()) if a.ids and Path(a.ids).exists() else {}
    engine = open_store(SemanticSettings.from_env().store_dsn).engine
    O.ensure(engine)
    counts: dict[str, int] = {}
    with engine.begin() as c:
        segs = set(ids.get("segments") or []) | {r[0] for r in c.execute(sa.select(O.SEGMENTS.c.id).where(O.SEGMENTS.c.ad.like("KABUL TESTİ%")))}
        progs = set(ids.get("programs") or []) | {r[0] for r in c.execute(sa.select(O.PROGRAMS.c.id).where(O.PROGRAMS.c.ad.like("KABUL TESTİ%")))}
        if segs:
            counts["segment ölçümü"] = c.execute(sa.select(sa.func.count()).select_from(O.SEGMENT_SIZES).where(O.SEGMENT_SIZES.c.segment_id.in_(segs))).scalar()
            counts["segment"] = c.execute(sa.select(sa.func.count()).select_from(O.SEGMENTS).where(O.SEGMENTS.c.id.in_(segs))).scalar()
            if not a.dry:
                c.execute(O.PROGRAMS.update().where(O.PROGRAMS.c.segment_id.in_(segs)).values(segment_id=None))
                c.execute(O.SEGMENT_SIZES.delete().where(O.SEGMENT_SIZES.c.segment_id.in_(segs)))
                c.execute(O.SEGMENTS.delete().where(O.SEGMENTS.c.id.in_(segs)))
        if progs:
            counts["program"] = c.execute(sa.select(sa.func.count()).select_from(O.PROGRAMS).where(O.PROGRAMS.c.id.in_(progs))).scalar()
            if not a.dry:
                c.execute(O.PROGRAMS.delete().where(O.PROGRAMS.c.id.in_(progs)))
        # program hatırlatma işaretinde kalan deneme kimlikleri
        meta = c.execute(sa.select(O.META).where(O.META.c.key == "program_hatirlatma")).mappings().all()
        for m in meta:
            keys = json.loads(m["value"] or "[]")
            keep = [k for k in keys if k.split(":")[0] not in progs]
            if len(keep) != len(keys):
                counts["hatırlatma işareti"] = counts.get("hatırlatma işareti", 0) + len(keys) - len(keep)
                if not a.dry:
                    c.execute(O.META.update().where(O.META.c.tenant_id == m["tenant_id"], O.META.c.key == m["key"])
                              .values(value=json.dumps(keep)))
        audit = sa.Table("semantic_audit", sa.MetaData(), autoload_with=c)
        oids = list(segs | progs)
        cond = [audit.c.kind.like("okur%")]
        by_obj = audit.c.object_id.in_(oids) if oids else sa.false()
        if a.actor and a.since:
            by_actor = sa.and_(audit.c.actor == a.actor, audit.c.at >= datetime.fromisoformat(a.since))
            where = sa.and_(*cond, sa.or_(by_obj, by_actor))
        else:
            where = sa.and_(*cond, by_obj)
        counts["değişiklik kaydı"] = c.execute(sa.select(sa.func.count()).select_from(audit).where(where)).scalar()
        if not a.dry:
            c.execute(audit.delete().where(where))
    print(("(deneme, silinmedi) " if a.dry else "") + "silinen: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
