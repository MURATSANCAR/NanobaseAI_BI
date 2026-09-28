#!/usr/bin/env python3
"""M34 kabul testinin bıraktığı izleri geri alır (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»).

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <aday ağaç>/backend && python3 ../scripts/acceptance/M34/temizlik.py --ids /tmp/claude-<oturum>/m34-ids.json [--kullanici timasai]

Geri alınanlar: `kabul.py --yazma`'nın işaretlediği farkın önceki durumu, sahibi, notu ve işaret alanları; kabul başladıktan sonra o
fark için yazılan günlük satırları (`semantic_eticaret_diff_log`) ve değişiklik kaydı satırları (`semantic_audit`, tür
`eticaret_diff` / `eticaret_export` / `eticaret_refresh`, kabul kullanıcısı). Silinen satır sayıları ekrana yazılır; günlüğe geçirilir.
Gece okumasının yazdığı kitap ve fark satırları gerçek veridir; silinmez. CRM, Logo ve T-soft'a dokunulmaz (zaten yazılmaz).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import eticaret as E  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def _dt(v):
    if not v:
        return None
    d = datetime.fromisoformat(str(v))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="m34-ids.json")
    ap.add_argument("--kullanici", default="timasai")
    args = ap.parse_args()
    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    E.ensure(engine)
    admin_mod.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    path = Path(args.ids)
    saved = json.loads(path.read_text()) if path.exists() else {}
    start = datetime.fromtimestamp(saved.get("baslangic") or 0, tz=timezone.utc) if saved else None
    user = args.kullanici.lower()
    out = {"fark_geri_alindi": 0, "gunluk": 0, "degisiklik_kaydi": 0}
    with engine.begin() as c:
        d = saved.get("diff")
        if d:
            out["fark_geri_alindi"] = c.execute(E.DIFFS.update().where(E.DIFFS.c.tenant_id == tenant, E.DIFFS.c.id == d["id"]).values(
                durum=d["durum"], sahip=d.get("sahip"), not_=d.get("not"), isaretleyen=d.get("isaretleyen"),
                isaretlendi_at=_dt(d.get("isaretlendi")), kapatan=d.get("kapatan"), kapandi_at=_dt(d.get("kapandi")),
                ertele_bitis=_dt(d.get("erteleBitis")))).rowcount
            out["gunluk"] = c.execute(E.DIFF_LOG.delete().where(E.DIFF_LOG.c.tenant_id == tenant, E.DIFF_LOG.c.diff_id == d["id"],
                                                                E.DIFF_LOG.c.kullanici == user, E.DIFF_LOG.c.zaman >= start)).rowcount
        if start:
            out["degisiklik_kaydi"] = c.execute(admin_mod.AUDIT.delete().where(
                admin_mod.AUDIT.c.kind.in_(("eticaret_diff", "eticaret_export", "eticaret_refresh")),
                sa.func.lower(admin_mod.AUDIT.c.actor) == user, admin_mod.AUDIT.c.at >= start)).rowcount
    print(json.dumps(out, ensure_ascii=False))
    if path.exists():
        path.unlink()
    return 0


if __name__ == "__main__":
    sys.exit(main())
