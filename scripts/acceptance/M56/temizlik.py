#!/usr/bin/env python3
"""M56 kabul testinin bıraktığı kayıtları siler (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»).

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M56/temizlik.py --ids /tmp/claude-<oturum>/m56-ids.json

Silinenler: «KABUL TESTİ M56» adlı yapay birim, çalışanlar, hedefler (check-in, revizyon), form, dönem, değerlendirmeler,
iş kayıtları özetleri; bunların erişim kaydı (`semantic_hr_access_log`, «kabul-*» hesapları dahil) ve değişiklik kaydı
satırları. Gerçek kayıtlara dokunulmaz. Silinen satır sayıları yazdırılır; günlüğe geçirilir.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import hr_core as H  # noqa: E402
from semantic_bridge import hr_performance as P  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

PREFIX = "KABUL TESTİ M56"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="m56-ids.json")
    args = ap.parse_args()
    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    admin_mod.ensure(engine)
    P.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    ids = json.loads(Path(args.ids).read_text()) if Path(args.ids).exists() else {}
    out: dict[str, int] = {}
    with engine.begin() as c:
        emps = set(ids.get("employees") or []) | {r[0] for r in c.execute(sa.select(H.EMPLOYEES.c.id).where(
            H.EMPLOYEES.c.tenant_id == tenant, H.EMPLOYEES.c.display_name.like(PREFIX + "%"))).all()}
        units = set(ids.get("units") or []) | {r[0] for r in c.execute(sa.select(H.UNITS.c.id).where(
            H.UNITS.c.tenant_id == tenant, H.UNITS.c.name.like(PREFIX + "%"))).all()}
        cycles = set(ids.get("cycles") or []) | {r[0] for r in c.execute(sa.select(P.CYCLES.c.id).where(
            P.CYCLES.c.tenant_id == tenant, P.CYCLES.c.name.like(PREFIX + "%"))).all()}
        forms = set(ids.get("forms") or []) | {r[0] for r in c.execute(sa.select(P.FORMS.c.id).where(
            P.FORMS.c.tenant_id == tenant, P.FORMS.c.name.like(PREFIX + "%"))).all()}
        el, cl = sorted(emps) or [""], sorted(cycles) or [""]
        goals = set(ids.get("goals") or []) | {r[0] for r in c.execute(sa.select(P.GOALS.c.id).where(
            sa.or_(P.GOALS.c.owner_employee_id.in_(el), P.GOALS.c.title.like(PREFIX + "%")))).all()}
        gl = sorted(goals) or [""]
        reviews = {r[0] for r in c.execute(sa.select(P.REVIEWS.c.id).where(sa.or_(P.REVIEWS.c.cycle_id.in_(cl), P.REVIEWS.c.employee_id.in_(el)))).all()}
        out["checkin"] = c.execute(P.CHECKINS.delete().where(P.CHECKINS.c.goal_id.in_(gl))).rowcount or 0
        out["revizyon"] = c.execute(P.REVISIONS.delete().where(P.REVISIONS.c.goal_id.in_(gl))).rowcount or 0
        out["hedef"] = c.execute(P.GOALS.delete().where(P.GOALS.c.id.in_(gl))).rowcount or 0
        out["ozet"] = c.execute(P.WORK.delete().where(sa.or_(P.WORK.c.employee_id.in_(el), P.WORK.c.cycle_id.in_(cl)))).rowcount or 0
        out["degerlendirme"] = c.execute(P.REVIEWS.delete().where(P.REVIEWS.c.id.in_(sorted(reviews) or [""]))).rowcount or 0
        out["donem"] = c.execute(P.CYCLES.delete().where(P.CYCLES.c.id.in_(cl))).rowcount or 0
        out["form"] = c.execute(P.FORMS.delete().where(P.FORMS.c.id.in_(sorted(forms) or [""]))).rowcount or 0
        out["erisim"] = c.execute(H.ACCESS_LOG.delete().where(sa.or_(H.ACCESS_LOG.c.subject_id.in_(el),
                                                                      H.ACCESS_LOG.c.username.like("kabul%")))).rowcount or 0
        out["calisan"] = c.execute(H.EMPLOYEES.delete().where(H.EMPLOYEES.c.id.in_(el))).rowcount or 0
        out["birim"] = c.execute(H.UNITS.delete().where(H.UNITS.c.id.in_(sorted(units) or [""]))).rowcount or 0
        objs = sorted((emps | units | cycles | forms | goals | reviews) - {""})
        out["degisiklik_kaydi"] = c.execute(admin_mod.AUDIT.delete().where(
            sa.or_(admin_mod.AUDIT.c.object_id.in_(objs or [""]), admin_mod.AUDIT.c.actor.like("kabul%")))).rowcount or 0
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
