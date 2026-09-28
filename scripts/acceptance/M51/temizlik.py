#!/usr/bin/env python3
"""M51 kabul testinin bıraktığı izleri siler (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»).

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M51/temizlik.py --actor timasai --since '2026-09-28T10:00:00+03:00'

Kabul yalnız okur; iz olarak kalan tek şey değişiklik kaydıdır (`semantic_audit`: bağlam ve bayi okuması, `support_*`).
`--since` sonrası `--actor` adına yazılmış `support_*` satırları silinir; sayısı yazılır ve günlüğe geçirilir. Kabul
sırasında elle bir talep sınıflandı ya da taslak üretildiyse (`--ticket`), o talebin Zeki AI satırı da silinir.
timasai oturum satırı giriş servisinde ayrıca silinir (bellek: test-login-as-timasai). CRM, Logo ve masaya dokunulmaz.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import support as S  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--actor", default="timasai")
    ap.add_argument("--since", required=True, help="ISO zaman; kabulün başladığı an")
    ap.add_argument("--ticket", action="append", default=[], help="kabulde sınıflanan/taslak üretilen talep numarası")
    args = ap.parse_args()
    since = datetime.fromisoformat(args.since)
    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    S.ensure(engine)
    admin_mod.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    with engine.begin() as c:
        n_a = c.execute(admin_mod.AUDIT.delete().where(admin_mod.AUDIT.c.actor == args.actor,
                                                       admin_mod.AUDIT.c.kind.like("support%"),
                                                       admin_mod.AUDIT.c.at >= since)).rowcount
        n_i = c.execute(S.INSIGHTS.delete().where(S.INSIGHTS.c.tenant_id == tenant,
                                                  S.INSIGHTS.c.ticket_ref.in_(args.ticket))).rowcount if args.ticket else 0
    print(json.dumps({"degisiklik_kaydi": n_a, "zeki_satiri": n_i}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
