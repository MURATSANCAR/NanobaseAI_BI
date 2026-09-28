#!/usr/bin/env python3
"""M59 kabul sonrası temizlik (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»).

`write_check.py`'nin yazdığı kimlik dosyasındaki not (ortak ziyaret tablosu), aksiyon ve kural taslağı kayıtlarını ve
bunların `semantic_audit` satırlarını siler; silinen sayıyı yazar (günlüğe geçirilir). Başka hiçbir satıra dokunmaz. Skor,
seri, öneri ve brif tabloları günlük turun ürettiği türetilmiş veridir; silinmez (test verisi değildir). Giriş servisindeki
kısa ömürlü `timasai` oturum satırı bu betiğin dışında, oturumu açan komutla silinir.

  set -a; . /etc/nanobase/semantic-bridge.env; set +a
  python3 scripts/acceptance/M59/cleanup.py --ids /tmp/claude-<oturum>/m59-ids.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import sqlalchemy as sa


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    a = ap.parse_args()
    ids = json.load(open(a.ids))
    dsn = os.environ.get("SEMANTIC_STORE_DSN") or os.environ.get("NANOBASE_META_DSN")
    if not dsn:
        print("SEMANTIC_STORE_DSN yok")
        return 2
    eng = sa.create_engine(dsn)
    table = {"notes": ("semantic_saha_ziyaret", "saha_ziyaret"), "actions": ("semantic_dealer_actions", "bayi_aksiyon"),
             "rules": ("semantic_dealer_rules", "bayi_kural")}
    total: dict[str, int] = {}
    with eng.begin() as c:
        for key, (tbl, kind) in table.items():
            for i in ids.get(key) or []:
                if key == "rules":
                    # Yalnız taslak silinir: yürürlüğe girmiş bir sürüm test kaydı olamaz.
                    n = c.execute(sa.text(f"DELETE FROM {tbl} WHERE id = :i AND durum IN ('taslak', 'onayda')"), {"i": i}).rowcount
                else:
                    n = c.execute(sa.text(f"DELETE FROM {tbl} WHERE id = :i"), {"i": i}).rowcount
                m = c.execute(sa.text("DELETE FROM semantic_audit WHERE kind = :k AND object_id = :i"), {"k": kind, "i": i}).rowcount
                total[tbl] = total.get(tbl, 0) + int(n or 0)
                total["semantic_audit"] = total.get("semantic_audit", 0) + int(m or 0)
    print("silinen:", json.dumps(total, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
