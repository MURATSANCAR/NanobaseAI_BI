"""M54 kabulünün bıraktığı test verisini siler (kural: test verisi bırakılmaz, silinen sayı günlüğe yazılır).

Koşum (test sunucusu, köprünün env'i ile):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && python3 ../scripts/acceptance/m54/cleanup.py [--state m54-kabul-state.json]

Yalnız `accept.py`'nin durum dosyasına yazdığı kimliklere dokunur:
- test koşuları: `semantic_royalty_runs`, satırları, hak sahibi beyannameleri, `semantic_audit`'teki o koşuların satırları;
- `--approve-sample` onayında oluşan M6 hakedişleri ve ödeme satırları (`statements`);
- onay sırasında ilk kez portala alınan CRM sözleşmeleri (`adopted`: onaydan önce olmayan kayıt kimlikleri) — kayıt,
  geçmişi, zeyilnamesi, ödemesi, hakedişi. Onaydan önce var olan hiçbir sözleşme kaydına dokunulmaz.
Çıktı: silinen satır sayıları (JSON).
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
    if not ids:
        return 0
    return c.execute(sa.text(sql).bindparams(sa.bindparam("ids", expanding=True)), {"ids": ids}).rowcount


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", default="m54-kabul-state.json")
    args = ap.parse_args()
    path = Path(args.state)
    if not path.exists():
        print(json.dumps({"silinen": {}, "not": "durum dosyası yok; kabul yazma yapmamış"}, ensure_ascii=False))
        return 0
    state = json.loads(path.read_text())
    runs = [r for r in state.get("runs", []) if len(str(r)) == 32]
    stmts = [s for s in state.get("statements", []) if s]
    adopted = [a for a in state.get("adopted", []) if len(str(a)) == 32]
    touched = [x for x in state.get("statementContracts", []) if len(str(x)) == 32 and x not in adopted]
    since = state.get("approveStartedAt")
    store = open_store(SemanticSettings.from_env().store_dsn, create=False)
    out: dict[str, int] = {}
    with store.engine.begin() as c:
        out["semantic_contract_payments(hakedis)"] = _del(c, "DELETE FROM semantic_contract_payments WHERE statement_id IN :ids", stmts)
        out["semantic_contract_statements"] = _del(c, "DELETE FROM semantic_contract_statements WHERE id IN :ids", stmts)
        if touched and since:
            # önceden var olan sözleşmelerin geçmişine onayın yazdığı hakediş olayları (yalnız kabul sırasında, timasai)
            out["semantic_contract_events(hakedis)"] = c.execute(sa.text(
                "DELETE FROM semantic_contract_events WHERE contract_id IN :ids AND action = 'hakedis' AND actor = 'timasai'"
                " AND at >= :since").bindparams(sa.bindparam("ids", expanding=True)), {"ids": touched, "since": since}).rowcount
        for table in ("semantic_contract_payments", "semantic_contract_statements", "semantic_contract_addenda", "semantic_contract_events"):
            out[f"{table}(alinan)"] = _del(c, f"DELETE FROM {table} WHERE contract_id IN :ids", adopted)
        out["semantic_contracts(alinan)"] = _del(c, "DELETE FROM semantic_contracts WHERE id IN :ids", adopted)
        out["semantic_royalty_party_statements"] = _del(c, "DELETE FROM semantic_royalty_party_statements WHERE run_id IN :ids", runs)
        out["semantic_royalty_run_lines"] = _del(c, "DELETE FROM semantic_royalty_run_lines WHERE run_id IN :ids", runs)
        out["semantic_royalty_notices"] = _del(c, "DELETE FROM semantic_royalty_notices WHERE ref IN :ids", runs)
        out["semantic_royalty_runs"] = _del(c, "DELETE FROM semantic_royalty_runs WHERE id IN :ids", runs)
        out["semantic_audit"] = _del(c, "DELETE FROM semantic_audit WHERE kind LIKE 'royalty%' AND object_id IN :ids", runs)
        if runs and state.get("startedAt"):
            # satır kararları (hariç tut) satır kimliğiyle yazılır; yalnız kabul hesabının kabul süresindeki satırları
            out["semantic_audit(satir)"] = c.execute(sa.text(
                "DELETE FROM semantic_audit WHERE kind = 'royalty_line' AND actor = 'timasai' AND at >= :since"),
                {"since": state["startedAt"]}).rowcount
    path.unlink()
    print(json.dumps({"silinen": out, "kosular": runs, "alinanKayit": len(adopted)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
