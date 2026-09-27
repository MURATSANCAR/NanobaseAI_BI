#!/usr/bin/env python3
"""M32 kabul testinin bıraktığı kayıtları siler (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»).

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M32/temizlik.py --ids /tmp/claude-<oturum>/m32-ids.json

Silinenler: kabul.py --yazma'nın açtığı fırsat ve teklifler, bunlara bağlı hatırlatma bağı ve değişiklik kaydı
(`semantic_audit`) satırları. Ayrıca adı «KABUL TESTİ» ile başlayan artık fırsat kalmışsa o da silinir. Silinen satır
sayıları ekrana yazılır; günlüğe geçirilir. Logo ve CRM'e dokunulmaz (zaten yazılmaz).
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
from semantic_bridge import corporate_sales as C  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="m32-ids.json")
    args = ap.parse_args()
    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    C.ensure(engine)
    admin_mod.ensure(engine)
    ids = json.loads(Path(args.ids).read_text()) if Path(args.ids).exists() else {"opportunities": [], "quotes": []}
    with engine.begin() as c:
        leftovers = [r[0] for r in c.execute(sa.select(C.OPPS.c.id).where(C.OPPS.c.kurum.like("KABUL TESTİ%"))).all()]
        opps = sorted(set(ids.get("opportunities") or []) | set(leftovers))
        quotes = set(ids.get("quotes") or [])
        if opps:
            quotes |= {r[0] for r in c.execute(sa.select(C.QUOTES.c.id).where(C.QUOTES.c.firsat_id.in_(opps))).all()}
        n_q = c.execute(C.QUOTES.delete().where(C.QUOTES.c.id.in_(sorted(quotes)))).rowcount if quotes else 0
        n_r = c.execute(C.REMINDERS.update().where(C.REMINDERS.c.firsat_id.in_(opps)).values(durum="acik", firsat_id=None)).rowcount if opps else 0
        n_o = c.execute(C.OPPS.delete().where(C.OPPS.c.id.in_(opps))).rowcount if opps else 0
        objs = sorted(set(opps) | quotes)
        n_a = c.execute(admin_mod.AUDIT.delete().where(admin_mod.AUDIT.c.kind.in_(("corp_quote", "corp_opportunity", "corp_quote_export")),
                                                       admin_mod.AUDIT.c.object_id.in_(objs))).rowcount if objs else 0
    print(json.dumps({"teklif": n_q, "firsat": n_o, "hatirlatma_geri_acildi": n_r, "degisiklik_kaydi": n_a}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
