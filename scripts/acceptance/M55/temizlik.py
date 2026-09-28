#!/usr/bin/env python3
"""M55 kabul testinin bıraktığı kayıtları siler (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»).

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M55/temizlik.py --ids /tmp/claude-<oturum>/m55-ids.json

Silinenler: kabul.py --yazma'nın açtığı geçici rol ve kişi bağı, yapay pozisyon ve adaylar (adı «KABUL TESTİ» ile başlayan
artıklar dahil) ile bunların dosya, kanıt, mülakat, not, yazışma, aşama kaydı, hatırlatma, iş, erişim kaydı ve değişiklik
kaydı (`semantic_audit`) satırları. Gerçek zamanlayıcı ucunun yazdığı imha tutanağı (sıfır ya da gerçek silme) bir iş
kaydıdır, silinmez. CRM'e ve Logo'ya dokunulmaz (zaten yazılmaz). Silinen satır sayıları yazdırılır; günlüğe geçirilir.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import access as A  # noqa: E402
from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import hr_core as H  # noqa: E402
from semantic_bridge import hr_recruit as R  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

PREFIX = "KABUL TESTİ M55"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="m55-ids.json")
    args = ap.parse_args()
    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    admin_mod.ensure(engine)
    R.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    ids = json.loads(Path(args.ids).read_text()) if Path(args.ids).exists() else {}
    out: dict[str, int] = {}
    with engine.begin() as c:
        cands = set(ids.get("candidates") or []) | {r[0] for r in c.execute(
            sa.select(R.CANDIDATES.c.id).where(R.CANDIDATES.c.tenant_id == tenant, R.CANDIDATES.c.full_name.like(PREFIX + "%"))).all()}
        poss = set(ids.get("positions") or []) | {r[0] for r in c.execute(
            sa.select(R.POSITIONS.c.id).where(R.POSITIONS.c.tenant_id == tenant, R.POSITIONS.c.title.like(PREFIX + "%"))).all()}
        cl = sorted(cands) or [""]
        ivs = [r[0] for r in c.execute(sa.select(R.INTERVIEWS.c.id).where(R.INTERVIEWS.c.candidate_id.in_(cl))).all()]
        msgs = [r[0] for r in c.execute(sa.select(R.MESSAGES.c.id).where(R.MESSAGES.c.candidate_id.in_(cl))).all()]
        for name, table, col in (("dosya", R.FILES, R.FILES.c.candidate_id), ("kanit", R.EVIDENCE, R.EVIDENCE.c.candidate_id),
                                 ("not", R.NOTES, R.NOTES.c.candidate_id), ("mulakat", R.INTERVIEWS, R.INTERVIEWS.c.candidate_id),
                                 ("yazisma", R.MESSAGES, R.MESSAGES.c.candidate_id), ("asama", R.STAGE_LOG, R.STAGE_LOG.c.candidate_id),
                                 ("hatirlatma", R.REMINDERS, R.REMINDERS.c.candidate_id), ("riza", H.CONSENTS, H.CONSENTS.c.subject_id),
                                 ("erisim", H.ACCESS_LOG, H.ACCESS_LOG.c.subject_id), ("is", H.JOBS, H.JOBS.c.subject_id)):
            out[name] = c.execute(table.delete().where(col.in_(cl))).rowcount or 0
        out["aday"] = c.execute(R.CANDIDATES.delete().where(R.CANDIDATES.c.id.in_(cl))).rowcount or 0
        out["pozisyon"] = c.execute(R.POSITIONS.delete().where(R.POSITIONS.c.id.in_(sorted(poss) or [""]))).rowcount or 0
        objs = sorted((set(cl) | poss | set(ivs) | set(msgs)) - {""})
        out["degisiklik_kaydi"] = c.execute(admin_mod.AUDIT.delete().where(
            admin_mod.AUDIT.c.kind.in_(("hr_candidate", "hr_position", "hr_interview", "hr_message", "hr_consent")),
            admin_mod.AUDIT.c.object_id.in_(objs or [""]))).rowcount or 0
    roles = list(ids.get("roles") or [])
    for rl in A.list_roles(engine, tenant):
        if rl["name"].startswith(PREFIX) and rl["id"] not in roles:
            roles.append(rl["id"])
    out["rol"] = 0
    for rid in roles:
        if A.delete_role(engine, tenant, rid):
            out["rol"] += 1
    with engine.begin() as c:
        out["rol_kaydi"] = c.execute(admin_mod.AUDIT.delete().where(admin_mod.AUDIT.c.kind == "access",
                                                                    admin_mod.AUDIT.c.title.like(PREFIX + "%"))).rowcount or 0
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
