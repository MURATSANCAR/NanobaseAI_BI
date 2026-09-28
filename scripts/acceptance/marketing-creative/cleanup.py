#!/usr/bin/env python3
"""M19 kabulünün bıraktığı test verisini siler (AGENTS.md: test verisi bırakılmaz; silinen sayı günlüğe yazılır).

Koşum (test sunucusu, köprünün env'iyle):
    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \\
      && python3 ../scripts/acceptance/marketing-creative/cleanup.py --evidence /data/nanobaseai/bi/logs/accept-m19-….json
    (ya da --request MC-2026-0001 [--request …])

Siler: talebin varlıkları (+ arşivdeki PNG ve yüklenen kapak dosyası), işleri, talebin kendisi, bunlara ait
`semantic_audit` satırları. Yalnız verilen talep kimliklerine dokunur; kampanya adı `KABUL-M19-` ile başlamayan talebi
`--force` olmadan silmez. Stüdyodaki kitapsız pazarlama işinin klasörü GPU'dadır; komutu ekrana yazar (GPU'da elle).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import marketing_creative as M  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--evidence", default="")
    ap.add_argument("--request", action="append", default=[])
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    rids = list(args.request)
    jobs: list[str] = []
    if args.evidence:
        ev = json.loads(Path(args.evidence).read_text())
        created = ev.get("created") or {}
        if created.get("request"):
            rids.append(created["request"])
        if created.get("studioJob"):
            jobs.append(created["studioJob"])
    if not rids:
        print("silinecek talep yok")
        return 0
    s = SemanticSettings.from_env()
    eng = open_store(s.store_dsn, create=False).engine
    counts = {"talep": 0, "varlik": 0, "is": 0, "audit": 0, "dosya": 0}
    with eng.begin() as c:
        for rid in rids:
            r = c.execute(sa.select(M.REQUESTS).where(M.REQUESTS.c.id == rid)).mappings().first()
            if r is None:
                continue
            if not (r["kampanya"] or "").startswith("KABUL-M19-") and not args.force:
                print(f"{rid}: kabul talebi değil (kampanya «{r['kampanya']}»); --force olmadan silinmez")
                continue
            if r["studio_job"] and r["studio_kind"] == "pazarlama" and r["studio_job"] not in jobs:
                jobs.append(r["studio_job"])
            assets = c.execute(sa.select(M.ASSETS.c.id, M.ASSETS.c.dosya_yolu).where(M.ASSETS.c.request_id == rid)).all()
            for aid, path in assets:
                if path and Path(path).is_file():
                    Path(path).unlink()
                    counts["dosya"] += 1
            cover = M.assets_dir() / "kapak" / f"{rid}.img"
            if cover.is_file():
                cover.unlink()
                counts["dosya"] += 1
            ids = [a[0] for a in assets] + [rid]
            counts["audit"] += c.execute(sa.text("DELETE FROM semantic_audit WHERE kind LIKE 'mkt_creative%' AND object_id IN :ids")
                                         .bindparams(sa.bindparam("ids", expanding=True)), {"ids": ids}).rowcount
            counts["varlik"] += c.execute(M.ASSETS.delete().where(M.ASSETS.c.request_id == rid)).rowcount
            counts["is"] += c.execute(M.JOBS.delete().where(M.JOBS.c.request_id == rid)).rowcount
            counts["talep"] += c.execute(M.REQUESTS.delete().where(M.REQUESTS.c.id == rid)).rowcount
    print(json.dumps({"silinen": counts, "talepler": rids}, ensure_ascii=False))
    root = os.environ.get("EDITOR_STORAGE_HINT", "<editör depolama kökü>/production")
    for j in jobs:
        # Aynı stok kodunun kitapsız işi başka (gerçek) taleplerce de kullanılıyor olabilir: önce denetle.
        print(f"GPU'da (başka talep bu işi kullanmıyorsa): sudo rm -rf {root}/{j}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
