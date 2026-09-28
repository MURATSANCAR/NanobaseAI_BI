#!/usr/bin/env python3
"""M53 kabul testinin bıraktığı kayıtları siler (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»).

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M53/temizlik.py --ids /tmp/claude-<oturum>/m53-ids.json

Silinenler: kabul.py --yazma'nın açtığı set ve teklifler (kimlik dosyasından), adı «KABUL TESTİ» ile başlayan artık set ya da
firma adı «KABUL TESTİ» ile başlayan teklif, bunların bileşen satırları, taslağa alınan önerinin geri açılması ve değişiklik
kaydı (`semantic_audit`) satırları. Silinen satır sayıları ekrana yazılır; günlüğe geçirilir. Logo ve CRM'e dokunulmaz (zaten
yazılmaz). Gece işinin okuduğu tablolar (kitap, satış, çift, promosyon) gerçek veridir; silinmez.
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
from semantic_bridge import sets as S  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="m53-ids.json")
    args = ap.parse_args()
    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    S.ensure(engine)
    admin_mod.ensure(engine)
    ids = json.loads(Path(args.ids).read_text()) if Path(args.ids).exists() else {"sets": [], "offers": []}
    with engine.begin() as c:
        left_sets = [r[0] for r in c.execute(sa.select(S.SETS.c.id).where(S.SETS.c.ad.like("KABUL TESTİ%"), S.SETS.c.kaynak != "crm")).all()]
        left_offers = [r[0] for r in c.execute(sa.select(S.OFFERS.c.id).where(S.OFFERS.c.firma_adi.like("KABUL TESTİ%"))).all()]
        sets_ = sorted(set(ids.get("sets") or []) | set(left_sets))
        offers = sorted(set(ids.get("offers") or []) | set(left_offers))
        n_s = n_i = n_o = n_g = n_a = 0
        if sets_:
            n_g = c.execute(S.SUGG.update().where(S.SUGG.c.set_id.in_(sets_)).values(durum="yeni", set_id=None, karar_by=None)).rowcount
            n_i = c.execute(S.ITEMS.delete().where(S.ITEMS.c.set_id.in_(sets_))).rowcount
            n_s = c.execute(S.SETS.delete().where(S.SETS.c.id.in_(sets_), S.SETS.c.kaynak != "crm")).rowcount
        if offers:
            n_o = c.execute(S.OFFERS.delete().where(S.OFFERS.c.id.in_(offers))).rowcount
        objs = sets_ + offers
        if objs:
            n_a = c.execute(admin_mod.AUDIT.delete().where(
                admin_mod.AUDIT.c.kind.in_(("mkt_set", "mkt_set_export", "mkt_gift_offer", "mkt_gift_offer_doc", "mkt_suggestion")),
                admin_mod.AUDIT.c.object_id.in_(objs))).rowcount
    print(json.dumps({"set": n_s, "bilesen_satiri": n_i, "teklif": n_o, "oneri_geri_acildi": n_g, "degisiklik_kaydi": n_a},
                     ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
