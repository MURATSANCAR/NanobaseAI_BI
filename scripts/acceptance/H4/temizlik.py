#!/usr/bin/env python3
"""H4 kabul testinin bıraktığı kayıtları siler (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»).

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/H4/temizlik.py --ids /tmp/claude-<oturum>/h4-ids.json --by timasai

Silinenler: kabul.py --yazma'nın yazdığı etiketler (yalnız --by hesabının), notu «KABUL TESTİ» ile başlayan taslak kural
sürümü, bunların değişiklik kaydı (`semantic_audit`) satırları. Kutudan okunmuş gerçek iletilere ve olaylarına dokunulmaz
(müşteri verisi; bellek: kurulum veri silmez). Silinen satır sayıları ekrana yazılır; günlüğe geçirilir.
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
from semantic_bridge import mailbox as M  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="h4-ids.json")
    ap.add_argument("--by", required=True, help="kabulde kullanılan hesap (timasai)")
    args = ap.parse_args()
    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    M.ensure(engine)
    admin_mod.ensure(engine)
    ids = json.loads(Path(args.ids).read_text()) if Path(args.ids).exists() else {"labels": [], "draft": []}
    by = args.by.strip().lower()
    with engine.begin() as c:
        labels = sorted(set(ids.get("labels") or []))
        n_l = c.execute(M.LABELS.delete().where(M.LABELS.c.by == by, M.LABELS.c.message_id.in_(labels))).rowcount if labels else 0
        drafts = [(r.tenant_id, r.version) for r in c.execute(sa.select(M.RULESETS.c.tenant_id, M.RULESETS.c.version).where(
            M.RULESETS.c.status == "taslak", M.RULESETS.c.note.like("KABUL TESTİ%"))).all()]
        n_d = 0
        for tenant, v in drafts:
            for t in (M.CATEGORIES, M.ROUTES, M.SLA, M.TEMPLATES):
                c.execute(t.delete().where(t.c.tenant_id == tenant, t.c.version == v))
            n_d += c.execute(M.RULESETS.delete().where(M.RULESETS.c.tenant_id == tenant, M.RULESETS.c.version == v)).rowcount
        versions = sorted({str(v) for _, v in drafts} | {str(v) for v in ids.get("draft") or []})
        n_a = c.execute(admin_mod.AUDIT.delete().where(admin_mod.AUDIT.c.actor == by, admin_mod.AUDIT.c.kind == "mail_rules",
                                                       admin_mod.AUDIT.c.object_id.in_(versions))).rowcount if versions else 0
        n_c = c.execute(admin_mod.AUDIT.delete().where(admin_mod.AUDIT.c.actor == by,
                                                       admin_mod.AUDIT.c.kind == "mailbox_connection")).rowcount
    print(json.dumps({"etiket": n_l, "taslak_surum": n_d, "degisiklik_kaydi": n_a + n_c}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
