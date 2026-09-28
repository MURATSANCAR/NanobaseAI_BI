"""M20 kabulünün bıraktığı test verisini siler (kural: test verisi bırakılmaz, silinen sayı günlüğe yazılır).

Koşum (test sunucusu, köprünün env'i ile):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && python3 ../scripts/acceptance/m20/cleanup.py [--state m20-kabul-state.json]

Yalnız `accept.py --write`'ın durum dosyasına yazdığı PR dosyası kimliklerine dokunur: dosya, gönderim satırları,
dosyaya bağlanan yansımalar, geçmiş, Zeki AI iş kaydı ve `semantic_audit`'teki o dosyaların satırları. Başka dosyalara,
medya kişilerine ve gerçek kullanıcı kayıtlarına dokunmaz. Çıktı: silinen satır sayıları (JSON).
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


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", default="m20-kabul-state.json")
    args = ap.parse_args()
    path = Path(args.state)
    if not path.exists():
        print(json.dumps({"silinen": {}, "not": "durum dosyası yok; kabul yazma yapmamış"}, ensure_ascii=False))
        return 0
    state = json.loads(path.read_text())
    kits = [k for k in state.get("kits", []) if str(k).startswith("PR-")]
    store = open_store(SemanticSettings.from_env().store_dsn, create=False)
    out: dict[str, int] = {}

    def delete(c, sql: str, ids: list[str]) -> int:
        if not ids:
            return 0
        return c.execute(sa.text(sql).bindparams(sa.bindparam("ids", expanding=True)), {"ids": ids}).rowcount

    with store.engine.begin() as c:
        if kits:
            sends = [r[0] for r in c.execute(sa.text("SELECT id FROM semantic_pr_sends WHERE kit_id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)), {"ids": kits}).all()]
            covs = [r[0] for r in c.execute(sa.text("SELECT id FROM semantic_pr_coverage WHERE kit_id IN :ids").bindparams(
                sa.bindparam("ids", expanding=True)), {"ids": kits}).all()]
            refs = kits + sends + covs
            out["semantic_pr_events"] = delete(c, "DELETE FROM semantic_pr_events WHERE ref_id IN :ids", refs)
            out["semantic_pr_jobs"] = delete(c, "DELETE FROM semantic_pr_jobs WHERE ref_id IN :ids", refs)
            out["semantic_pr_coverage"] = delete(c, "DELETE FROM semantic_pr_coverage WHERE id IN :ids", covs)
            out["semantic_pr_sends"] = delete(c, "DELETE FROM semantic_pr_sends WHERE id IN :ids", sends)
            out["semantic_pr_kits"] = delete(c, "DELETE FROM semantic_pr_kits WHERE id IN :ids", kits)
            out["semantic_audit"] = delete(c, "DELETE FROM semantic_audit WHERE kind IN ('pr_kit', 'pr_send', 'pr_coverage') "
                                              "AND object_id IN :ids", refs)
    path.unlink()
    print(json.dumps({"silinen": out, "dosyalar": kits}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
