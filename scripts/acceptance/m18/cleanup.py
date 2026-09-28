"""M18 kabulünün bıraktığı test verisini siler (kural: test verisi bırakılmaz, silinen sayı günlüğe yazılır).

Koşum (test sunucusu, köprünün env'i ile):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && python3 ../scripts/acceptance/m18/cleanup.py [--state m18-kabul-state.json]

Yalnız `accept.py`'nin `m18-kabul-state.json`'a yazdığı kimliklere dokunur: kabulün kurduğu ay planı (plan, bütçe
satırı, ay kalemi, bütçe payı, geçmiş, iş kaydı ve `semantic_audit`'teki satırları) ve kabul sırasında ilk kez açılan föy
satırları (+ o föylerin değişiklik kaydı). Kabulden önce var olan plan ve föylere dokunmaz. Çıktı: silinen sayılar (JSON).
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


def _in(sql: str):
    return sa.text(sql).bindparams(sa.bindparam("ids", expanding=True))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", default="m18-kabul-state.json")
    args = ap.parse_args()
    path = Path(args.state)
    if not path.exists():
        print(json.dumps({"silinen": {}, "not": "durum dosyası yok; kabul veri bırakmamış"}, ensure_ascii=False))
        return 0
    state = json.loads(path.read_text())
    plans = [p for p in state.get("plans", []) if str(p).startswith("MP-")]
    foys = [f for f in state.get("foy", []) if f]
    store = open_store(SemanticSettings.from_env().store_dsn, create=False)
    out: dict[str, int] = {}
    with store.engine.begin() as c:
        if plans:
            for table in ("semantic_mkt_plan_lines", "semantic_mkt_tasks", "semantic_mkt_materials", "semantic_mkt_events",
                          "semantic_mkt_jobs", "semantic_mkt_month_items", "semantic_mkt_month_budget"):
                out[table] = c.execute(_in(f"DELETE FROM {table} WHERE plan_id IN :ids"), {"ids": plans}).rowcount
            out["semantic_mkt_plans"] = c.execute(_in("DELETE FROM semantic_mkt_plans WHERE id IN :ids"), {"ids": plans}).rowcount
            out["semantic_audit(plan)"] = c.execute(_in("DELETE FROM semantic_audit WHERE kind = 'marketing_plan' AND object_id IN :ids"),
                                                    {"ids": plans}).rowcount
        if foys:
            out["semantic_audit(foy)"] = c.execute(_in("DELETE FROM semantic_audit WHERE kind = 'marketing_foy' AND object_id IN :ids"),
                                                   {"ids": foys}).rowcount
            out["semantic_mkt_foy"] = c.execute(_in("DELETE FROM semantic_mkt_foy WHERE id IN :ids"), {"ids": foys}).rowcount
        if state.get("ay") and state.get("since"):
            from datetime import datetime

            out["semantic_audit(paket)"] = c.execute(sa.text(
                "DELETE FROM semantic_audit WHERE kind = 'marketing_foy' AND object_id = :ay AND actor = :actor AND at >= :since"),
                {"ay": state["ay"], "actor": state.get("actor") or "timasai",
                 "since": datetime.fromisoformat(state["since"])}).rowcount
    path.unlink()
    print(json.dumps({"silinen": out, "planlar": plans, "foy": len(foys)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
