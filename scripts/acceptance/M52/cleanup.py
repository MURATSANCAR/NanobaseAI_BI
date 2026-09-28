#!/usr/bin/env python3
"""M52 kabul sonrası temizlik (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz").

`kabul.py --yaz`'ın yazdığı kimlik dosyasındaki taslak/öneri kayıtlarını (`semantic_supply_suggestions`) ve bunların
`semantic_audit` satırlarını siler; ayrıca elle yapılan denemenin kimlikleri verilirse kapasite (`capacity`), fatura bağı
(`links`) ve eşleme (`maps`) kayıtlarını siler. Silinen sayıyı yazar (günlüğe geçirilir). Başka hiçbir satıra dokunmaz:
gece işinin ürettiği öneriler test verisi değildir. Giriş servisindeki kısa ömürlü `timasai` oturumu bu betiğin dışında,
oturumu açan komutla silinir.

  set -a; . /etc/nanobase/semantic-bridge.env; set +a
  python3 scripts/acceptance/M52/cleanup.py --ids /tmp/claude-<oturum>/m52-ids.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys

import sqlalchemy as sa

TABLES = {
    "suggestions": ("semantic_supply_suggestions", ("supply_draft", "supply_suggestion")),
    "capacity": ("semantic_supply_capacity", ("supply_capacity",)),
    "links": ("semantic_supply_invoice_links", ("supply_link",)),
    "maps": ("semantic_supply_supplier_map", ()),
}


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
    total: dict[str, int] = {}
    with eng.begin() as c:
        for key, (table, kinds) in TABLES.items():
            for i in ids.get(key) or []:
                n = c.execute(sa.text(f"DELETE FROM {table} WHERE id = :i"), {"i": i}).rowcount
                total[table] = total.get(table, 0) + int(n or 0)
                for k in kinds:
                    m = c.execute(sa.text("DELETE FROM semantic_audit WHERE kind = :k AND object_id = :i"), {"k": k, "i": i}).rowcount
                    total["semantic_audit"] = total.get("semantic_audit", 0) + int(m or 0)
    print("silinen:", json.dumps(total, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
