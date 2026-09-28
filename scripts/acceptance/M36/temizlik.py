#!/usr/bin/env python3
"""M36 kabul/deneme sırasında yazılan kayıtları siler (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»).

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M36/temizlik.py --ids /tmp/claude-<oturum>/m36-ids.json [--dry-run]

Kimlik dosyası (denemede not edilenler): {"imports": ["DR-2026-0001"], "platforms": [3], "listings": [12],
"decisions": [4], "prices": ["<kitap_id>"]}. Ayrıca adı «KABUL TESTİ» ile başlayan platform (ve ona bağlı yükleme,
satır, platform kaydı), notu/gerekçesi «KABUL TESTİ» ile başlayan platform kaydı ve hak kararı, gerekçesi «KABUL TESTİ»
ile başlayan dijital fiyat kararı ve bunların değişiklik kaydı (`semantic_audit`) satırları silinir. Silinen sayılar
ekrana yazılır ve günlüğe geçirilir. Gece okumasının yazdığı kitap satırları gerçek veridir, silinmez. CRM'e, Logo'ya ve
platformlara dokunulmaz (zaten yazılmaz).
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
from semantic_bridge import dijital as D  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

TAG = "KABUL TESTİ"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", default="m36-ids.json")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    D.ensure(engine)
    admin_mod.ensure(engine)
    ids = json.loads(Path(args.ids).read_text()) if Path(args.ids).exists() else {}
    out: dict[str, int] = {}
    with engine.begin() as c:
        plats = set(ids.get("platforms") or []) | {r[0] for r in c.execute(sa.select(D.PLATFORMS.c.id).where(D.PLATFORMS.c.ad.like(TAG + "%"))).all()}
        imps = set(ids.get("imports") or [])
        if plats:
            imps |= {r[0] for r in c.execute(sa.select(D.IMPORTS.c.id).where(D.IMPORTS.c.platform_id.in_(plats))).all()}
        listings = set(ids.get("listings") or []) | {r[0] for r in c.execute(sa.select(D.LISTINGS.c.id).where(
            sa.or_(D.LISTINGS.c.notlar.like(TAG + "%"), D.LISTINGS.c.platform_id.in_(plats or [-1])))).all()}
        decisions = set(ids.get("decisions") or []) | {r[0] for r in c.execute(sa.select(D.DECISIONS.c.id).where(D.DECISIONS.c.gerekce.like(TAG + "%"))).all()}
        prices = set(ids.get("prices") or []) | {r[0] for r in c.execute(sa.select(D.TITLES.c.kitap_id).where(D.TITLES.c.fiyat_gerekce.like(TAG + "%"))).all()}
        list_rows = c.execute(sa.select(D.LISTINGS.c.kitap_id, D.LISTINGS.c.platform_id).where(D.LISTINGS.c.id.in_(listings or [-1]))).all()
        dec_rows = c.execute(sa.select(D.DECISIONS.c.kitap_id).where(D.DECISIONS.c.id.in_(decisions or [-1]))).all()
        objs = sorted(imps) + [str(p) for p in plats] + [f"{k}:{p}" for k, p in list_rows] + sorted(prices)
        if args.dry_run:
            print(json.dumps({"yukleme": sorted(imps), "platform": sorted(plats), "platform_kaydi": sorted(listings),
                              "hak_karari": sorted(decisions), "fiyat": sorted(prices)}, ensure_ascii=False))
            return 0
        out["satis_satiri"] = c.execute(D.SALES.delete().where(D.SALES.c.import_id.in_(imps or ["-"]))).rowcount
        out["yukleme"] = c.execute(D.IMPORTS.delete().where(D.IMPORTS.c.id.in_(imps or ["-"]))).rowcount
        out["platform_kaydi"] = c.execute(D.LISTINGS.delete().where(D.LISTINGS.c.id.in_(listings or [-1]))).rowcount
        out["hak_karari"] = c.execute(D.DECISIONS.delete().where(D.DECISIONS.c.id.in_(decisions or [-1]))).rowcount
        out["fiyat"] = c.execute(D.TITLES.update().where(D.TITLES.c.kitap_id.in_(prices or ["-"])).values(
            dijital_fiyat=None, fiyat_gerekce=None, fiyat_onaylayan=None, fiyat_tarih=None)).rowcount
        out["platform"] = c.execute(D.PLATFORMS.delete().where(D.PLATFORMS.c.id.in_(plats or [-1]))).rowcount
        rights_objs = [r[0] for r in dec_rows]
        cond = sa.and_(admin_mod.AUDIT.c.kind.in_(("dijital_import", "dijital_platform", "dijital_listing", "dijital_price")),
                       admin_mod.AUDIT.c.object_id.in_(objs or ["-"]))
        cond_r = sa.and_(admin_mod.AUDIT.c.kind == "dijital_rights",
                         sa.or_(*[admin_mod.AUDIT.c.object_id.like(k + ":%") for k in rights_objs]) if rights_objs else sa.false())
        out["degisiklik_kaydi"] = c.execute(admin_mod.AUDIT.delete().where(sa.or_(cond, cond_r))).rowcount
    print(json.dumps(out, ensure_ascii=False))
    print("Not: silinen hak kararının kitabı bir sonraki gece okumasında (ya da «Yenile») yeniden hesaplanır.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
