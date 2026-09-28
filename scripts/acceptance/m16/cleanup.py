"""M16 kabulünün bıraktığı test verisini siler (kural: test verisi bırakılmaz, silinen sayı günlüğe yazılır).

Koşum (test sunucusu, köprünün env'i ile):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && python3 ../scripts/acceptance/m16/cleanup.py [--state m16-kabul-state.json]

Yalnız `accept.py`'nin durum dosyasına yazdığı kabul planına ve lansmanına dokunur: lansman, gün satırları, etkinlik,
medya, değerlendirme; planın satırları, takvimi (lansman maddeleri dahil), materyali, geçmişi, iş kaydı; iki kimliğin
`semantic_audit` satırları; kabul sırasında ilk kez oluşan emsal önbelleği anahtarları. Çıktı: silinen satır sayıları.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def _del(c, sql: str, ids: list[str]) -> int:
    return c.execute(sa.text(sql).bindparams(sa.bindparam("ids", expanding=True)), {"ids": ids}).rowcount


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", default="m16-kabul-state.json")
    args = ap.parse_args()
    path = Path(args.state)
    if not path.exists():
        print(json.dumps({"silinen": {}, "not": "durum dosyası yok; kabul yazma yapmamış"}, ensure_ascii=False))
        return 0
    state = json.loads(path.read_text())
    plans = [p for p in state.get("plans", []) if str(p).startswith("MP-")]
    launches = [x for x in state.get("launches", []) if str(x).startswith("ML-")]
    meta = [k for k in state.get("meta", []) if str(k).startswith("launch-emsal:")]
    store = open_store(SemanticSettings.from_env().store_dsn, create=False)
    out: dict[str, int] = {}
    with store.engine.begin() as c:
        if launches:
            for t in ("semantic_mkt_launch_daily", "semantic_mkt_launch_events", "semantic_mkt_launch_media", "semantic_mkt_launch_reviews"):
                out[t] = _del(c, f"DELETE FROM {t} WHERE launch_id IN :ids", launches)
            out["semantic_mkt_launches"] = _del(c, "DELETE FROM semantic_mkt_launches WHERE id IN :ids", launches)
            out["semantic_audit(lansman)"] = _del(c, "DELETE FROM semantic_audit WHERE kind = 'marketing_launch' AND object_id IN :ids", launches)
            out["semantic_mkt_meta(uyari)"] = _del(c, "DELETE FROM semantic_mkt_meta WHERE key IN :ids",
                                                   [f"launch-stock:{x}" for x in launches])
        if plans:
            for t in ("semantic_mkt_plan_lines", "semantic_mkt_tasks", "semantic_mkt_materials", "semantic_mkt_events", "semantic_mkt_jobs"):
                out[t] = _del(c, f"DELETE FROM {t} WHERE plan_id IN :ids", plans)
            out["semantic_mkt_plans"] = _del(c, "DELETE FROM semantic_mkt_plans WHERE id IN :ids", plans)
            out["semantic_audit(plan)"] = _del(c, "DELETE FROM semantic_audit WHERE kind IN ('marketing_plan', 'marketing_material') "
                                                  "AND object_id IN :ids", plans)
        if meta:
            out["semantic_mkt_meta(emsal)"] = _del(c, "DELETE FROM semantic_mkt_meta WHERE key IN :ids", meta)
    path.unlink()
    print(json.dumps({"silinen": out, "planlar": plans, "lansmanlar": launches}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
