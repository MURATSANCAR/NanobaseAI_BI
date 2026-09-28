#!/usr/bin/env python3
"""M35 kabul testinin bıraktığı kayıtları siler (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»).

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M35/temizlik.py --ids /tmp/claude-<oturum>/m35-ids.json

Silinenler: kabul.py --yazma'nın açtığı kampanyalar (kimlik dosyasından) ve adı «KABUL TESTİ» ile başlayan artık kampanya ya da
takvim kaydı; bunların kitap, sonuç ve öğrenim satırları ve değişiklik kaydı (`semantic_audit`) satırları. Silinen satır
sayıları ekrana yazılır; günlüğe geçirilir. Gece işinin okuduğu tablolar (kitap, fiyat kaydı, CRM türü) gerçek veridir; silinmez.
Logo ve CRM'e dokunulmaz (zaten yazılmaz).
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
from semantic_bridge import kampanya as K  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="m35-ids.json")
    args = ap.parse_args()
    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    K.ensure(engine)
    admin_mod.ensure(engine)
    ids = json.loads(Path(args.ids).read_text()) if Path(args.ids).exists() else {}
    with engine.begin() as c:
        left = [r[0] for r in c.execute(sa.select(K.CAMPAIGNS.c.id).where(K.CAMPAIGNS.c.ad.like("KABUL TESTİ%"))).all()]
        camps = sorted(set(ids.get("campaigns") or []) | set(left))
        cals = sorted(set(ids.get("calendar") or []) | {r[0] for r in c.execute(
            sa.select(K.CALENDAR.c.id).where(K.CALENDAR.c.ad.like("KABUL TESTİ%"))).all()})
        n = {"kampanya": 0, "kitap_satiri": 0, "sonuc_satiri": 0, "ogrenim": 0, "takvim": 0, "degisiklik_kaydi": 0}
        lids: list[str] = []
        if camps:
            lids = [r[0] for r in c.execute(sa.select(K.LEARNINGS.c.id).where(K.LEARNINGS.c.campaign_id.in_(camps))).all()]
            n["kitap_satiri"] = c.execute(K.ITEMS.delete().where(K.ITEMS.c.campaign_id.in_(camps))).rowcount
            n["sonuc_satiri"] = c.execute(K.RESULTS.delete().where(K.RESULTS.c.campaign_id.in_(camps))).rowcount
            n["ogrenim"] = c.execute(K.LEARNINGS.delete().where(K.LEARNINGS.c.campaign_id.in_(camps))).rowcount
            n["kampanya"] = c.execute(K.CAMPAIGNS.delete().where(K.CAMPAIGNS.c.id.in_(camps))).rowcount
        if cals:
            n["takvim"] = c.execute(K.CALENDAR.delete().where(K.CALENDAR.c.id.in_(cals))).rowcount
        objs = camps + cals + lids
        if objs:
            n["degisiklik_kaydi"] = c.execute(admin_mod.AUDIT.delete().where(
                admin_mod.AUDIT.c.kind.in_(("kampanya", "kampanya_takvim", "kampanya_ogrenim", "kampanya_sonuc", "kampanya_export")),
                admin_mod.AUDIT.c.object_id.in_(objs))).rowcount
    print(json.dumps(n, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
