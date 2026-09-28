#!/usr/bin/env python3
"""M58 kabul testinin bıraktığı kayıtları siler (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»).

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M58/temizlik.py --ids /tmp/claude-<oturum>/m58-ids.json

Silinenler: «KABUL TESTİ M58» adlı yapay birimler, çalışanlar (kabul-m58-* hesapları), şablon, anket ve bunların davet,
basılı kod, cevap, yorum, sonuç satırları; test önerisi ve aksiyon; erişim ve değişiklik kaydı satırları. Cevap satırı kişiye
bağlı olmadığı için anket kimliğiyle silinir. Gerçek kayıtlara dokunulmaz. Silinen satır sayıları yazdırılır; günlüğe geçirilir.
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
from semantic_bridge import hr_engagement as E  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

PREFIX = "KABUL TESTİ M58"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="m58-ids.json")
    args = ap.parse_args()
    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    admin_mod.ensure(engine)
    E.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    ids = json.loads(Path(args.ids).read_text()) if Path(args.ids).exists() else {}
    out: dict[str, int] = {}
    with engine.begin() as c:
        surveys = set(ids.get("surveys") or []) | {r[0] for r in c.execute(sa.select(E.SURVEYS.c.id).where(
            E.SURVEYS.c.tenant_id == tenant, E.SURVEYS.c.title.like(PREFIX + "%"))).all()}
        tpls = set(ids.get("templates") or []) | {r[0] for r in c.execute(sa.select(E.TEMPLATES.c.id).where(
            E.TEMPLATES.c.tenant_id == tenant, E.TEMPLATES.c.title.like(PREFIX + "%"))).all()}
        emps = set(ids.get("employees") or []) | {r[0] for r in c.execute(sa.select(H.EMPLOYEES.c.id).where(
            H.EMPLOYEES.c.tenant_id == tenant, H.EMPLOYEES.c.display_name.like(PREFIX + "%"))).all()}
        units = set(ids.get("units") or []) | {r[0] for r in c.execute(sa.select(H.UNITS.c.id).where(
            H.UNITS.c.tenant_id == tenant, H.UNITS.c.name.like(PREFIX + "%"))).all()}
        suggs = set(ids.get("suggestions") or []) | {r[0] for r in c.execute(sa.select(E.SUGGESTIONS.c.id).where(
            E.SUGGESTIONS.c.tenant_id == tenant, E.SUGGESTIONS.c.text.like(PREFIX + "%"))).all()}
        acts = set(ids.get("actions") or []) | {r[0] for r in c.execute(sa.select(E.ACTIONS.c.id).where(
            E.ACTIONS.c.tenant_id == tenant, E.ACTIONS.c.title.like(PREFIX + "%"))).all()}
        sl = sorted(surveys) or [""]
        for name, table in (("davet", E.INVITES), ("basili_kod", E.PAPER), ("cevap", E.RESPONSES), ("yorum", E.COMMENTS), ("sonuc", E.RESULTS)):
            out[name] = c.execute(table.delete().where(table.c.survey_id.in_(sl))).rowcount or 0
        out["aksiyon"] = c.execute(E.ACTIONS.delete().where(sa.or_(E.ACTIONS.c.id.in_(sorted(acts) or [""]), E.ACTIONS.c.survey_id.in_(sl)))).rowcount or 0
        out["anket"] = c.execute(E.SURVEYS.delete().where(E.SURVEYS.c.id.in_(sl))).rowcount or 0
        out["sablon"] = c.execute(E.TEMPLATES.delete().where(E.TEMPLATES.c.id.in_(sorted(tpls) or [""]))).rowcount or 0
        out["oneri"] = c.execute(E.SUGGESTIONS.delete().where(E.SUGGESTIONS.c.id.in_(sorted(suggs) or [""]))).rowcount or 0
        out["erisim"] = c.execute(H.ACCESS_LOG.delete().where(sa.or_(H.ACCESS_LOG.c.subject_id.in_(sl + sorted(emps)),
                                                                      H.ACCESS_LOG.c.username.like("kabul%")))).rowcount or 0
        out["calisan"] = c.execute(H.EMPLOYEES.delete().where(H.EMPLOYEES.c.id.in_(sorted(emps) or [""]))).rowcount or 0
        out["birim"] = c.execute(H.UNITS.delete().where(H.UNITS.c.id.in_(sorted(units) or [""]))).rowcount or 0
        objs = sorted((surveys | tpls | emps | units | suggs | acts) - {""})
        out["degisiklik_kaydi"] = c.execute(admin_mod.AUDIT.delete().where(
            sa.or_(admin_mod.AUDIT.c.object_id.in_(objs or [""]), admin_mod.AUDIT.c.actor.like("kabul%")))).rowcount or 0
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
