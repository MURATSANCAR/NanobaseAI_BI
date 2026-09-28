#!/usr/bin/env python3
"""M39 kabul temizliği: test hesabının (varsayılan timasai) kabul sırasında açtığı pazar kayıtlarını ve değişiklik
kaydı satırlarını siler (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»). Önce listeler; `--uygula` ile siler.

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M39/temizlik.py --since 2026-09-29T08:00:00+03:00
    python3 ../scripts/acceptance/M39/temizlik.py --since … --uygula

Silinen: bu kişinin yüklediği raporlar (dosyasıyla) ve rakamları, yazdığı/düzenlediği özetler, izleme kayıtları, elle
girdiği rakamlar, verdiği eşleme kararları (öneriye geri döner), `semantic_audit`'te `pazar_*` satırları. Zamanlayıcının
(«sistem», «Zeki AI …») yazdığı anlık görüntü ve öneriler gerçek modül verisidir, silinmez. Silinen sayılar günlüğe
yazılır.
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
from semantic_bridge import pazar as P  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--actor", default="timasai")
    ap.add_argument("--since", required=True, help="kabulün başladığı an (ISO, saat dilimiyle)")
    ap.add_argument("--uygula", action="store_true")
    a = ap.parse_args()
    since = datetime.fromisoformat(a.since)
    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    P.ensure(engine)
    admin_mod.ensure(engine)
    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    who = a.actor.lower()
    R, F, B, W, M = P.REPORTS.c, P.FIGURES.c, P.BRIEFS.c, P.WATCHLIST.c, P.CATEGORY_MAP.c
    with engine.connect() as c:
        reports = c.execute(sa.select(R.id, R.dosya_yolu, R.baslik).where(
            R.tenant_id == tenant, sa.func.lower(R.yukleyen) == who, R.yuklendi_at >= since)).all()
        rids = [r.id for r in reports]
        figs_manual = c.execute(sa.select(F.id).where(F.tenant_id == tenant, F.yontem == "elle", sa.func.lower(F.onaylayan) == who,
                                                      F.olusturuldu_at >= since)).all()
        figs_decided = c.execute(sa.select(F.id).where(F.tenant_id == tenant, F.yontem == "zeki", sa.func.lower(F.onaylayan) == who,
                                                       F.karar_at >= since)).all()
        briefs = c.execute(sa.select(B.id, B.donem).where(B.tenant_id == tenant, sa.or_(
            sa.and_(sa.func.lower(B.yazan) == who, B.yazildi_at >= since),
            sa.and_(sa.func.lower(B.guncelleyen) == who, B.guncellendi_at >= since)))).all()
        watch = c.execute(sa.select(W.id).where(W.tenant_id == tenant, sa.func.lower(W.ekleyen) == who, W.eklendi_at >= since)).all()
        maps = c.execute(sa.select(M.kategori_ham).where(M.tenant_id == tenant, sa.func.lower(M.onaylayan) == who, M.karar_at >= since)).all()
        audit = c.execute(sa.select(sa.func.count()).select_from(admin_mod.AUDIT).where(
            sa.func.lower(admin_mod.AUDIT.c.actor) == who, admin_mod.AUDIT.c.kind.like("pazar_%"), admin_mod.AUDIT.c.at >= since)).scalar()
    plan = {"rapor": [r.baslik for r in reports], "elle_rakam": len(figs_manual), "karar_geri": len(figs_decided),
            "ozet": [b.donem for b in briefs], "izleme": len(watch), "esleme_karari": len(maps), "audit": audit}
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    if not a.uygula:
        print("Yalnız listelendi; silmek için --uygula.")
        return 0
    with engine.begin() as c:
        if rids:
            c.execute(P.FIGURES.delete().where(F.report_id.in_(rids)))
            c.execute(P.REPORTS.delete().where(R.id.in_(rids)))
        if figs_manual:
            c.execute(P.FIGURES.delete().where(F.id.in_([x.id for x in figs_manual])))
        if figs_decided:
            c.execute(P.FIGURES.update().where(F.id.in_([x.id for x in figs_decided])).values(
                durum="oneri", onaylayan=None, karar_at=None, not_=None, deger=F.deger_oneri))
        if briefs:
            c.execute(P.BRIEFS.delete().where(B.id.in_([x.id for x in briefs])))
        if watch:
            c.execute(P.WATCHLIST.delete().where(W.id.in_([x.id for x in watch])))
        if maps:
            hams = [x.kategori_ham for x in maps]
            c.execute(P.CATEGORY_MAP.update().where(M.tenant_id == tenant, M.kategori_ham.in_(hams)).values(
                durum=sa.case((M.oneri_kategori_id.isnot(None), "oneri"), else_="yeni"), kategori_id=None, onaylayan=None,
                karar_at=None, not_=None))
            c.execute(P.COMPETITORS.update().where(P.COMPETITORS.c.tenant_id == tenant, P.COMPETITORS.c.kategori_ham.in_(hams))
                      .values(kategori_id=None))
        c.execute(admin_mod.AUDIT.delete().where(sa.func.lower(admin_mod.AUDIT.c.actor) == who,
                                                 admin_mod.AUDIT.c.kind.like("pazar_%"), admin_mod.AUDIT.c.at >= since))
    for r in reports:
        Path(r.dosya_yolu).unlink(missing_ok=True)
    print("Silindi.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
