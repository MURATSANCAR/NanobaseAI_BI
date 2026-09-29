#!/usr/bin/env python3
"""Hız 2. tur — kişi → CRM kullanıcısı eşlemesi: eski kural (kişi başına canlı sorgu) = yeni (tek sorgu + bellek).

Test sunucusunda, köprünün sanal ortamında ve env dosyasıyla koşturulur. Yalnız okur (CRM ve portal); hiçbir tabloya
yazmaz, temizlik gerekmez.

    set -a; . /etc/nanobase/semantic-bridge.env; set +a
    cd <kaynak>/backend && python3 ../scripts/acceptance/hiz2-ilk-acilis/kisi_esleme.py --out /tmp/claude-<oturum>/kisi.json

Kontroller (her biri OK / FARK / DOĞRULANAMADI):
  K1  Tek sorgunun satır sayısı = bağımsız COUNT(*) (DomainName dolu bütün kullanıcılar, pasifler dahil).
  K2  Etkin kullanıcı sayısı = bağımsız COUNT(*) WHERE IsDisabled = 0.
  K3  Her hesap için eski `crm_me` (kişi başına `me_sql`, canlı) = yeni `crm_kisi.eslestir` (tek okumadan). Hesaplar:
      CRM'deki bütün hesap kısımları + yetki üye görüntüsündeki (AD grubu/OU/CRM rolü) bütün hesaplar — CRM'de
      karşılığı olmayanlar da (None = None). Eşlemeye uygun olmayan ad (ASCII dışı, boşluklu, >80) canlı yola düşer; sayılır.
  K4  Aynı hesaba birden çok ETKİN CRM kullanıcısı: eski sorgunun sırası belirsizdi; liste (varsa) ve eski/yeni seçim.
  K5  Portal tablosundaki saklanmış eşleme (varsa) bugünkü CRM ile aynı sonucu veriyor mu (okunma zamanıyla).
  S   Süre: kişi başına eski sorgu ortalaması / tek sorgu.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_bridge import admin as admin_mod  # noqa: E402
from semantic_bridge import budget_sources as bsrc  # noqa: E402
from semantic_bridge import crm_kisi as K  # noqa: E402
from semantic_bridge import editorial_assign as M2  # noqa: E402
from semantic_bridge.editorial import _prefix  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

RESULTS: list[dict] = []


def record(name: str, status: str, **detail) -> None:
    RESULTS.append({"kontrol": name, "durum": status, **detail})
    print(f"[{status:>13}] {name}  {json.dumps(detail, ensure_ascii=False, default=str)[:600]}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="kisi-esleme.json")
    args = ap.parse_args()

    tenant = os.environ.get("SEMANTIC_TENANT_ID", "default")
    crm_file = os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
    schema = admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"
    p = _prefix(schema)
    run = bsrc.runner(crm_file)

    # ------------------------------------------------------------------ yeni: tek sorgu
    t0 = time.monotonic()
    raw = run(K.all_users_sql(schema))
    bulk_ms = int((time.monotonic() - t0) * 1000)
    rows = [K._norm(r) for r in raw]
    dizin = K.dizin_kur(rows)

    ref_all = run(f"SELECT COUNT(*) AS v FROM {p}SystemUserBase WHERE DomainName IS NOT NULL AND DomainName <> ''")[0]["v"]
    record("K1 tek sorgu satırı = COUNT(*)", "OK" if int(ref_all) == len(rows) else "FARK", yeni=len(rows), referans=ref_all)
    ref_on = run(f"SELECT COUNT(*) AS v FROM {p}SystemUserBase WHERE DomainName IS NOT NULL AND DomainName <> ''"
                 f" AND IsDisabled = 0")[0]["v"]
    on = sum(1 for r in rows if not r["IsDisabled"])
    record("K2 etkin kullanıcı", "OK" if int(ref_on) == on else "FARK", yeni=on, referans=ref_on)

    # ------------------------------------------------------------------ hesap listesi
    accounts = {a for a in dizin if a}
    engine = None
    try:
        engine = open_store(os.environ["SEMANTIC_STORE_DSN"], create=False).engine
        with engine.connect() as c:
            for (m,) in c.execute(sa.text("SELECT members FROM semantic_access_members")).all():
                for x in json.loads(m or "[]"):
                    if str(x).strip():
                        accounts.add(str(x).strip().lower())
    except Exception as e:  # noqa: BLE001
        record("yetki üye görüntüsü", "DOĞRULANAMADI", hata=str(e)[:300])

    # ------------------------------------------------------------------ K3: eski = yeni, her hesap
    ok, diffs, live, per_ms = 0, [], [], []
    for acct in sorted(accounts):
        t1 = time.monotonic()
        old = M2.crm_me(schema, lambda sql: {"records": run(sql)}, acct)
        per_ms.append((time.monotonic() - t1) * 1000)
        if not K.uygun(acct):
            live.append(acct)
            continue
        new = K.eslestir(dizin, acct)
        if new == old:
            ok += 1
        else:
            diffs.append({"hesap": acct, "eski": old, "yeni": new})
    record("K3 eski kural = yeni kural (her hesap)", "OK" if not diffs else "FARK", hesap=len(accounts), ayni=ok,
           fark=len(diffs), farklar=diffs[:50], canli_yola_duser=live[:50])

    # ------------------------------------------------------------------ K4: aynı hesaba birden çok etkin kullanıcı
    multi = []
    for acct, rs in dizin.items():
        hit = [r for r in rs if K._like_tutar(r, acct) and not r["IsDisabled"]] if K.uygun(acct) else []
        if len(hit) > 1:
            multi.append({"hesap": acct, "adaylar": [r["SystemUserId"] for r in hit],
                          "yeni_secim": (K.eslestir(dizin, acct) or {}).get("id")})
    record("K4 aynı hesaba birden çok etkin CRM kullanıcısı", "OK" if not multi else "FARK", sayi=len(multi), liste=multi[:50],
           not_="FARK ise: eski sorgunun sırası belirsizdi; K3'te aynı çıktıysa pratikte aynı, değilse iş kararı gerekir.")

    # ------------------------------------------------------------------ K5: saklanmış eşleme
    if engine is not None:
        try:
            with engine.connect() as c:
                r = c.execute(sa.select(K.OKUMA.c.okundu_at, K.OKUMA.c.rows_json).where(K.OKUMA.c.tenant_id == tenant)).first()
            if r is None:
                record("K5 saklanmış eşleme", "DOĞRULANAMADI", neden="portal tablosunda okuma yok (gece turu ya da ilk açılış bekleniyor)")
            else:
                stored = K.dizin_kur(json.loads(r[1] or "[]"))
                bad = [a for a in sorted(accounts) if K.uygun(a) and K.eslestir(stored, a) != K.eslestir(dizin, a)]
                record("K5 saklanmış eşleme = bugünkü CRM", "OK" if not bad else "FARK", okundu=str(r[0]), fark=len(bad),
                       farkli_hesaplar=bad[:50], not_="FARK, okunduktan sonra CRM'de değişen kullanıcıdır (10 dk'da yenilenir).")
        except Exception as e:  # noqa: BLE001
            record("K5 saklanmış eşleme", "DOĞRULANAMADI", hata=str(e)[:300])

    avg = sum(per_ms) / len(per_ms) if per_ms else 0
    record("S süre", "OK", tek_sorgu_ms=bulk_ms, kisi_basina_eski_ort_ms=round(avg, 1), hesap=len(per_ms))

    Path(args.out).write_text(json.dumps(RESULTS, ensure_ascii=False, indent=1, default=str))
    bad = [x for x in RESULTS if x["durum"] == "FARK"]
    print(f"\n{len(RESULTS)} kontrol, {len(bad)} FARK → {args.out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
