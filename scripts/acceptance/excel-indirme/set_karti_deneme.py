"""Set kart listesi ekranı için geçici set: aç → sına → sil (kullanıcı isteği 2026-09-29: «hadi dene»).

Kart listesi yalnız portalda açılmış, «kart bekliyor» ya da «satışta» sette görünür; test sunucusunda böyle set yoktu. Onay
dört göz ister (gönderen onaylayamaz) ve başka bir gerçek kişi taklit edilmez; bu yüzden:
  ac   → taslak set API'den açılır (gerçek iki kitap, fiyat), durum yalnız bu kayıt için «kart-bekliyor» yapılır; id basılır
  sil  → durum «taslak»a döner, uygulamanın kendi silme yolu (`sets.delete_set`) çalışır, kaydın ve bileşenlerinin kalmadığı sayılır
Denetim kayıtları `yerinde.py` sayacına düşer (yazılmaz). Kullanım: python set_karti_deneme.py ac | sil <id>
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sqlalchemy as sa  # noqa: E402

import yerinde as Y  # noqa: E402
from semantic_bridge import sets as S  # noqa: E402

AD = "Excel kabul testi — geçici set (silinecek)"


def engine() -> sa.engine.Engine:
    return sa.create_engine(os.environ.get("SEMANTIC_STORE_DSN") or os.environ["NANOBASE_META_DSN"])


def req(method: str, path: str, body=None):  # noqa: ANN001
    st, _, b = Y.transport("/api/v1/marketing" + path, {"Cookie": Y.COOKIE, "Content-Type": "application/json"}, method,
                           json.dumps(body).encode() if body is not None else None)
    if st >= 300:
        raise SystemExit(f"{method} {path} → {st} {b[:300]!r}")
    return json.loads(b or b"{}")


def ac() -> None:
    # Arama metinsiz boş döner; kitap stok kodları «15201.» ile başlar (Logo kitap grubu).
    books = [b for b in req("GET", "/sets/books?q=15201").get("items", []) if b.get("stok") or b.get("stokKodu")][:2]
    if len(books) < 2:
        raise SystemExit(f"kitap listesi boş: {books}")
    items = [{"stok": b.get("stok") or b.get("stokKodu"), "adet": 1} for b in books]
    s = req("POST", "/sets", {"ad": AD, "tur": "tematik", "bilesenler": items, "setFiyati": 999.9})
    with engine().begin() as c:
        n = c.execute(S.SETS.update().where(S.SETS.c.id == s["id"], S.SETS.c.ad == AD, S.SETS.c.kaynak == "elle")
                      .values(durum="kart-bekliyor")).rowcount
    assert n == 1, n
    print(json.dumps({"id": s["id"], "bilesen": [i["stok"] for i in items]}))


def sil(sid: str) -> None:
    eng = engine()
    with eng.begin() as c:
        r = c.execute(sa.select(S.SETS.c.ad, S.SETS.c.tenant_id).where(S.SETS.c.id == sid)).first()
        if r is None:
            print(json.dumps({"id": sid, "silindi": True, "not": "zaten yok"}))
            return
        assert r.ad == AD, f"{sid} test seti değil: {r.ad}"
        c.execute(S.SETS.update().where(S.SETS.c.id == sid).values(durum="taslak"))
    S.delete_set(eng, r.tenant_id, sid)
    with eng.connect() as c:
        kalan = c.execute(sa.select(sa.func.count()).select_from(S.SETS).where(S.SETS.c.id == sid)).scalar()
        kalan_b = c.execute(sa.select(sa.func.count()).select_from(S.ITEMS).where(S.ITEMS.c.set_id == sid)).scalar()
        adla = c.execute(sa.select(sa.func.count()).select_from(S.SETS).where(S.SETS.c.ad == AD)).scalar()
    print(json.dumps({"id": sid, "silindi": kalan == 0 and kalan_b == 0, "ayniAdlaKalan": adla}))


if __name__ == "__main__":
    if sys.argv[1] == "ac":
        ac()
    else:
        sil(sys.argv[2])
    print("== kayıt çağrıları (yazılmadı): " + ", ".join(f"{k}={v}" for k, v in sorted(Y.calls.items())))
