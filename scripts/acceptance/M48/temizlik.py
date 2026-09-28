#!/usr/bin/env python3
"""M48 kabul testinin bıraktığı kayıtları siler (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»).

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M48/temizlik.py --since 2026-09-28T10:00:00+03:00 --actor timasai

Silinenler (yalnız --since sonrası ve --actor'ın): kabul.py --dene'nin «Şimdi dene» denetim satırları (source=manual) ve
bunların değişiklik kaydı (`semantic_audit`, kind itops_check / itops_incident). Zamanlayıcının gerçek denetimleri,
olaylar ve sürüm kayıtları işletim verisidir, silinmez. Bir sürüm kaydı test için elle yazıldıysa kimliği --release ile
verilir. Silinen satır sayıları yazdırılır; günlüğe geçirilir. Logo ve CRM'e dokunulmaz (zaten yazılmaz).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import it_ops as I  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", required=True, help="kabulün başladığı an (ISO, saat dilimiyle)")
    ap.add_argument("--actor", default="timasai")
    ap.add_argument("--release", type=int, action="append", default=[], help="test için yazılmış sürüm kaydı kimliği")
    args = ap.parse_args()
    since = datetime.fromisoformat(args.since)
    if since.tzinfo is None:
        raise SystemExit("--since saat dilimiyle verilmeli (örn. +03:00)")
    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    I.ensure(engine)
    admin_mod.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    with engine.begin() as c:
        n_audit = c.execute(admin_mod.AUDIT.delete().where(
            admin_mod.AUDIT.c.kind.in_(("itops_check", "itops_incident")), admin_mod.AUDIT.c.actor == args.actor,
            admin_mod.AUDIT.c.at >= since)).rowcount
        n_checks = c.execute(I.CHECKS.delete().where(
            I.CHECKS.c.tenant_id == tenant, I.CHECKS.c.source == "manual", I.CHECKS.c.at >= since)).rowcount
        n_rel = 0
        if args.release:
            n_rel = c.execute(I.RELEASES.delete().where(I.RELEASES.c.id.in_(args.release))).rowcount
            c.execute(admin_mod.AUDIT.delete().where(admin_mod.AUDIT.c.kind == "itops_release",
                                                     admin_mod.AUDIT.c.object_id.in_([str(x) for x in args.release])))
    print(json.dumps({"degisiklik_kaydi": n_audit, "elle_denetim": n_checks, "surum_kaydi": n_rel}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
