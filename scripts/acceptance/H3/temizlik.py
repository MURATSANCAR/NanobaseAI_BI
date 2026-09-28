"""H3 E-ticaret müşteri kabulünün temizliği — test sunucusunda. `kabul.py`'nin kimlik dosyasıyla:

- kabulün açtığı tetikler, listeleri, liste üyeleri ve (varsa) o listelerden açılmış kampanyalar
  (`semantic_commerce_triggers`, `_trigger_runs`, `_run_members`, `_campaigns`);
- o listelerin H2 dışa aktarım defterindeki satırları (kabul dışa aktarım yapmaz; yine de denetlenir);
- kabul başladıktan sonra `--actor` (varsayılan timasai) adına yazılmış commerce_* değişiklik kaydı satırları.

Sipariş, müşteri, geçiş ve görüntülenme tabloları modülün kendi durumudur (T-soft'tan türer), silinmez. Silinen satır
sayıları JSON olarak yazılır; günlüğe geçirin. Başka oturumun kaydına dokunulmaz.

    python3 scripts/acceptance/H3/temizlik.py --ids /tmp/claude-h3/kabul-kimlikler.json [--actor timasai]
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import commerce as C  # noqa: E402
from semantic_bridge import readers_segments as S  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ids", required=True)
    ap.add_argument("--actor", default="timasai")
    args = ap.parse_args()
    ev = json.loads(Path(args.ids).read_text())
    since = datetime.fromisoformat(ev["startedAt"])
    st = SemanticSettings.from_env()
    engine = open_store(st.store_dsn, create=False).engine
    tenant = ev.get("tenant") or st.tenant_id
    trig = ev.get("triggers") or []
    with engine.connect() as c:
        runs = sorted(set(ev.get("runs") or []) | {r.id for r in c.execute(sa.select(C.RUNS.c.id).where(
            C.RUNS.c.tenant_id == tenant, C.RUNS.c.trigger_id.in_(trig or ["-"])))})
        exports = [r.export_id for r in c.execute(sa.select(C.RUNS.c.export_id).where(C.RUNS.c.id.in_(runs or ["-"]))) if r.export_id]
    out: dict = {"since": ev["startedAt"]}
    with engine.begin() as c:
        out["kampanya"] = c.execute(C.CAMPAIGNS.delete().where(C.CAMPAIGNS.c.tenant_id == tenant,
                                                               C.CAMPAIGNS.c.trigger_run_id.in_(runs or ["-"]))).rowcount
        out["listeUyesi"] = c.execute(C.RUN_MEMBERS.delete().where(C.RUN_MEMBERS.c.run_id.in_(runs or ["-"]))).rowcount
        out["liste"] = c.execute(C.RUNS.delete().where(C.RUNS.c.tenant_id == tenant, C.RUNS.c.id.in_(runs or ["-"]))).rowcount
        out["tetik"] = c.execute(C.TRIGGERS.delete().where(C.TRIGGERS.c.tenant_id == tenant, C.TRIGGERS.c.id.in_(trig or ["-"]))).rowcount
        out["disaAktarimUyesi"] = c.execute(S.EXPORT_MEMBERS.delete().where(S.EXPORT_MEMBERS.c.export_id.in_(exports or ["-"]))).rowcount
        out["disaAktarim"] = c.execute(S.EXPORTS.delete().where(S.EXPORTS.c.id.in_(exports or ["-"]))).rowcount
        A = admin_mod.AUDIT.c
        out["degisiklikKaydi"] = c.execute(admin_mod.AUDIT.delete().where(
            A.actor == args.actor, A.at >= since, A.kind.like("commerce_%"))).rowcount
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
