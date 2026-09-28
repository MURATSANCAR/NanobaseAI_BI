"""M22 kabulünün bıraktığı test verisini siler (kural: test verisi bırakılmaz, silinen sayı günlüğe yazılır).

Koşum (test sunucusu, köprünün env'i ile):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && python3 ../scripts/acceptance/m22/cleanup.py [--state m22-kabul-state.json]

Yalnız `accept.py --write`'ın durum dosyasına yazdığı kimliklere dokunur: kabul hesabı, o hesabın gönderileri (geçmiş,
iş kaydı, ölçü), içe aktarmaları ve `semantic_audit`'teki bu kimliklerin satırları. Durum dosyası yoksa ya da kayıp
kaldıysa `--handle` ile kabul hesabının adıyla da bulunur (`@m22-kabul-hesabi`). Gerçek kullanıcı kayıtlarına dokunmaz.
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


def _in(sql: str) -> sa.TextClause:
    return sa.text(sql).bindparams(sa.bindparam("ids", expanding=True))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", default="m22-kabul-state.json")
    ap.add_argument("--handle", default="@m22-kabul-hesabi", help="durum dosyası yoksa kabul hesabı bu adla aranır")
    args = ap.parse_args()
    path = Path(args.state)
    state = json.loads(path.read_text()) if path.exists() else {"accounts": [], "posts": [], "imports": []}
    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn, create=False)
    out: dict[str, int] = {}
    with store.engine.begin() as c:
        try:
            found = [r[0] for r in c.execute(sa.text("SELECT id FROM semantic_social_accounts WHERE tenant_id = :t AND handle = :h"),
                                             {"t": s.tenant_id, "h": args.handle}).all()]
        except Exception:  # noqa: BLE001 — tablo hiç kurulmamış
            print(json.dumps({"silinen": {}, "not": "sosyal medya tabloları yok"}, ensure_ascii=False))
            return 0
        accounts = sorted(set(state.get("accounts", [])) | set(found))
        posts = set(state.get("posts", []))
        imports = set(state.get("imports", []))
        if accounts:
            posts |= {r[0] for r in c.execute(_in("SELECT id FROM semantic_social_posts WHERE account_id IN :ids"), {"ids": accounts}).all()}
            imports |= {r[0] for r in c.execute(_in("SELECT id FROM semantic_social_imports WHERE account_id IN :ids"), {"ids": accounts}).all()}
        posts_l, imports_l = sorted(posts), sorted(imports)
        if posts_l:
            for table in ("semantic_social_post_events", "semantic_social_jobs"):
                out[table] = c.execute(_in(f"DELETE FROM {table} WHERE post_id IN :ids"), {"ids": posts_l}).rowcount
            out["semantic_social_metrics(gonderi)"] = c.execute(_in("DELETE FROM semantic_social_metrics WHERE post_id IN :ids"),
                                                                {"ids": posts_l}).rowcount
            out["semantic_social_posts"] = c.execute(_in("DELETE FROM semantic_social_posts WHERE id IN :ids"), {"ids": posts_l}).rowcount
        if imports_l:
            out["semantic_social_metrics(dosya)"] = c.execute(_in("DELETE FROM semantic_social_metrics WHERE import_id IN :ids"),
                                                              {"ids": imports_l}).rowcount
            out["semantic_social_imports"] = c.execute(_in("DELETE FROM semantic_social_imports WHERE id IN :ids"), {"ids": imports_l}).rowcount
        if accounts:
            out["semantic_social_metrics(hesap)"] = c.execute(_in("DELETE FROM semantic_social_metrics WHERE account_id IN :ids"),
                                                              {"ids": accounts}).rowcount
            out["semantic_social_accounts"] = c.execute(_in("DELETE FROM semantic_social_accounts WHERE id IN :ids"),
                                                        {"ids": accounts}).rowcount
        ids = accounts + posts_l + imports_l
        if ids:
            out["semantic_audit"] = c.execute(_in(
                "DELETE FROM semantic_audit WHERE kind IN ('social_account', 'social_post', 'social_import', 'social_metric') "
                "AND object_id IN :ids"), {"ids": ids}).rowcount
    if path.exists():
        path.unlink()
    print(json.dumps({"silinen": out, "hesap": accounts, "gonderi": posts_l, "iceAktarma": imports_l}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
