"""M17 kabulünün bıraktığı test verisini siler (kural: test verisi bırakılmaz, silinen sayı günlüğe yazılır).

Koşum (test sunucusu, köprünün env'i ile):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && python3 ../scripts/acceptance/m17/cleanup.py [--state m17-kabul-state.json]

Yalnız `accept.py --write`'ın durum dosyasına yazdığı plan kimliklerine dokunur: plan, kitaplar, satır, takvim, materyal,
geçmiş, iş kaydı ve `semantic_audit`'teki o planların satırları. Backlist listesi (`semantic_mkt_backlist*`) gece koşusunun
ürünüdür, test verisi değildir; silinmez. Çıktı: silinen satır sayıları (JSON).
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

TABLES = ("semantic_mkt_plan_books", "semantic_mkt_plan_lines", "semantic_mkt_tasks", "semantic_mkt_materials",
          "semantic_mkt_events", "semantic_mkt_jobs")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", default="m17-kabul-state.json")
    args = ap.parse_args()
    path = Path(args.state)
    if not path.exists():
        print(json.dumps({"silinen": {}, "not": "durum dosyası yok; kabul yazma yapmamış"}, ensure_ascii=False))
        return 0
    plans = [p for p in json.loads(path.read_text()).get("plans", []) if str(p).startswith("MP-")]
    store = open_store(SemanticSettings.from_env().store_dsn, create=False)
    names = set(sa.inspect(store.engine).get_table_names())
    out: dict[str, int] = {}
    if plans:
        with store.engine.begin() as c:
            for table in TABLES:
                if table in names:
                    out[table] = c.execute(sa.text(f"DELETE FROM {table} WHERE plan_id IN :ids").bindparams(
                        sa.bindparam("ids", expanding=True)), {"ids": plans}).rowcount
            out["semantic_mkt_plans"] = c.execute(sa.text("DELETE FROM semantic_mkt_plans WHERE id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)), {"ids": plans}).rowcount
            out["semantic_audit"] = c.execute(sa.text(
                "DELETE FROM semantic_audit WHERE kind = 'marketing_plan' AND object_id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)), {"ids": plans}).rowcount
    path.unlink()
    print(json.dumps({"silinen": out, "planlar": plans}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
