#!/usr/bin/env python3
"""M9 birim maliyet kabulünün temizlik denetimi (AGENTS.md «Test verisi bırakılmaz»).

kabul.py yalnız okur: analiz, imza, ayar ya da değişiklik kaydı yazmaz; Logo ve CRM'e hiç yazılmaz. Bu betik bunu
denetler: adı «KABUL» ile başlayan fiyat analizi kalmış mı, varsa sayısını ve kimliklerini yazar (silmez — kabul
açmadığına göre elle açılmıştır; kime ait olduğuna bakılmadan silinmez).

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/M9-maliyet/temizlik.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge.pricing import store as S  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def main() -> int:
    engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
    S.ensure(engine)
    with engine.connect() as c:
        left = [r[0] for r in c.execute(sa.select(S.ANALYSES.c.id).where(S.ANALYSES.c.title.like("KABUL%"))).all()]
    print(f"Kabulden kalan analiz: {len(left)} {left if left else ''}".rstrip())
    return 1 if left else 0


if __name__ == "__main__":
    sys.exit(main())
