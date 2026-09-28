#!/usr/bin/env python3
"""M38 kabul sonrası temizlik (AGENTS.md «Test kullanıcısı ve test verisi bırakılmaz»).

`write_check.py`'nin yazdığı kimlik dosyasındaki aksiyonları ve bunların `semantic_audit` satırlarını siler; işaretlenip
geri alınan bulgunun işaret alanlarını (durum, not, işaretleyen, zaman) kabul öncesi hâline getirir ve o bulgunun
değişiklik kaydı satırlarını siler. Özet/cari görüntüleme kayıtları (`musteri_ozet`, `musteri_telefon`) kabulü yapan
oturumun adıyla yazıldıysa `--actor` verilince silinir. Gece turunun ürettiği tablolar (cari, bulgu, puan, segment)
türetilmiş veridir; silinmez. Silinen sayı yazdırılır (günlüğe geçirilir). Giriş servisindeki kısa ömürlü `timasai`
oturum satırı bu betiğin dışında, oturumu açan komutla silinir.

  set -a; . /etc/nanobase/semantic-bridge.env; set +a
  python3 scripts/acceptance/M38/cleanup.py --ids /tmp/claude-<oturum>/m38-ids.json [--actor timasai]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

import sqlalchemy as sa


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", required=True)
    ap.add_argument("--actor", default="", help="kabulü yapan hesap: onun musteri_* görüntüleme/tur kayıtları da silinir")
    a = ap.parse_args()
    ids = json.load(open(a.ids))
    dsn = os.environ.get("SEMANTIC_STORE_DSN") or os.environ.get("NANOBASE_META_DSN")
    if not dsn:
        print("SEMANTIC_STORE_DSN yok")
        return 2
    eng = sa.create_engine(dsn)
    total: dict[str, int] = {}

    def add(k: str, n) -> None:
        total[k] = total.get(k, 0) + int(n or 0)

    with eng.begin() as c:
        for i in ids.get("actions") or []:
            add("semantic_musteri_actions", c.execute(sa.text("DELETE FROM semantic_musteri_actions WHERE id = :i"), {"i": i}).rowcount)
            add("semantic_audit", c.execute(sa.text("DELETE FROM semantic_audit WHERE kind = 'musteri_aksiyon' AND object_id = :i"),
                                            {"i": i}).rowcount)
        for f in ids.get("findings") or []:
            at = datetime.fromisoformat(f["isaretZamani"]) if f.get("isaretZamani") else None
            add("semantic_musteri_health_findings (geri alınan)", c.execute(sa.text(
                "UPDATE semantic_musteri_health_findings SET durum = :d, isaret_notu = :n, isaretleyen = :u, isaret_zamani = :t"
                " WHERE id = :i"), {"d": f["durum"], "n": f.get("not"), "u": f.get("isaretleyen"), "t": at, "i": f["id"]}).rowcount)
            add("semantic_audit", c.execute(sa.text("DELETE FROM semantic_audit WHERE kind = 'musteri_bulgu' AND object_id = :i"),
                                            {"i": f["id"]}).rowcount)
        if a.actor:
            add("semantic_audit", c.execute(sa.text(
                "DELETE FROM semantic_audit WHERE actor = :a AND kind IN ('musteri_ozet', 'musteri_telefon', 'musteri_disa', 'musteri_tur')"),
                {"a": a.actor}).rowcount)
    print("silinen/geri alınan:", json.dumps(total, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
