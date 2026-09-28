"""M21 kabulünün bıraktığı test verisini siler (kural: test verisi bırakılmaz, silinen sayı günlüğe yazılır).

Koşum (test sunucusu, köprünün env'i ile):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && python3 ../scripts/acceptance/M21/cleanup.py [--state m21-kabul-state.json]

Yalnız `kabul.py --write`'ın durum dosyasına yazdığı kimliklere dokunur: kabul hesabı, onun kampanyaları, günlük satırları,
yüklemeleri, bu kampanyalar/hesap için yazılmış öneriler, `semantic_audit`'teki bu nesnelerin satırları; kabulün bağladığı
kitabın satış/stok önbelleği satırları (başka bir kampanya o kitaba bağlı değilse). Gerçek kayıtlara dokunmaz.
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


def _in(c, sql: str, ids: list[str]) -> int:
    if not ids:
        return 0
    return c.execute(sa.text(sql).bindparams(sa.bindparam("ids", expanding=True)), {"ids": ids}).rowcount


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", default="m21-kabul-state.json")
    args = ap.parse_args()
    path = Path(args.state)
    if not path.exists():
        print(json.dumps({"silinen": {}, "not": "durum dosyası yok; kabul yazma yapmamış"}, ensure_ascii=False))
        return 0
    state = json.loads(path.read_text())
    accounts = [a for a in state.get("accounts", []) if a]
    imports = [i for i in state.get("imports", []) if i]
    codes = [c for c in state.get("codes", []) if c]
    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn, create=False)
    out: dict[str, int] = {}
    with store.engine.begin() as c:
        camps = [r[0] for r in c.execute(sa.text("SELECT id FROM semantic_ads_campaigns WHERE account_id IN :ids").bindparams(
            sa.bindparam("ids", expanding=True)), {"ids": accounts}).all()] if accounts else []
        camps = sorted(set(camps) | {x for x in state.get("campaigns", []) if x})
        out["semantic_ads_daily"] = _in(c, "DELETE FROM semantic_ads_daily WHERE campaign_id IN :ids", camps)
        out["semantic_ads_suggestions"] = _in(c, "DELETE FROM semantic_ads_suggestions WHERE campaign_id IN :ids", camps) \
            + _in(c, "DELETE FROM semantic_ads_suggestions WHERE account_id IN :ids", accounts)
        out["semantic_ads_campaigns"] = _in(c, "DELETE FROM semantic_ads_campaigns WHERE id IN :ids", camps)
        out["semantic_ads_imports"] = _in(c, "DELETE FROM semantic_ads_imports WHERE id IN :ids", imports) \
            + _in(c, "DELETE FROM semantic_ads_imports WHERE account_id IN :ids", accounts)
        out["semantic_ads_accounts"] = _in(c, "DELETE FROM semantic_ads_accounts WHERE id IN :ids", accounts)
        still = {r[0] for r in c.execute(sa.text("SELECT DISTINCT stok_kodu FROM semantic_ads_campaigns WHERE stok_kodu IS NOT NULL")).all()}
        free = [x for x in codes if x not in still]
        out["semantic_ads_ecom_book"] = _in(c, "DELETE FROM semantic_ads_ecom_book WHERE stok_kodu IN :ids", free)
        out["semantic_ads_stock"] = _in(c, "DELETE FROM semantic_ads_stock WHERE stok_kodu IN :ids", free)
        out["semantic_audit"] = _in(c, "DELETE FROM semantic_audit WHERE kind IN ('ads_account', 'ads_import', 'ads_campaign', "
                                       "'ads_suggestion') AND object_id IN :ids", accounts + imports + camps)
        if state.get("baslangic") and state.get("kim"):
            # kabulün kendi okuma/yenileme işlemlerinin değişiklik kaydı (nesnesiz satırlar)
            out["semantic_audit"] += c.execute(sa.text(
                "DELETE FROM semantic_audit WHERE kind IN ('ads_refresh', 'ads_report', 'ads_campaign') AND actor = :kim AND at >= :t"),
                {"kim": state["kim"], "t": state["baslangic"]}).rowcount
    path.unlink()
    print(json.dumps({"silinen": out, "hesaplar": accounts, "kampanyalar": camps}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
