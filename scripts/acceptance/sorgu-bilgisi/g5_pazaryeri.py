"""G5 · M40 Trendyol ve M41 Amazon/yurtdışı sorgu bilgisi kabulü (yalnız okuma). `kabul_g5.py` çağırır.

K1–K3 her uçta; doğrudan SQL referansları:
  T1  Trendyol özeti «ürün toplamı» = portalda ürün dosyası satır sayısı;
  T2  Amazon konsinye: kalan kitap sayısı, gösterilen konsinye SQL'inin satırlarından fazla olamaz.
"""
from __future__ import annotations

import sqlalchemy as sa

import kabul as KB
from semantic_bridge.channels import kaynak_pazaryeri as KP


def kabul(heavy: bool) -> None:
    st, ov = KB.http("/api/v1/channels/trendyol/overview", 900)
    if st == 200:
        k = KB.contract("trendyol /overview", ov, KP.NOT_RAKAM)
        KB.run_all("trendyol /overview", k, heavy)
        with KB.portal().connect() as c:
            n = c.execute(sa.text("SELECT COUNT(*) FROM semantic_trendyol_products")).scalar()
        KB.check("T1 trendyol: ürün toplamı = doğrudan sayım", int(n or 0) == int((ov.get("urun") or {}).get("toplam") or 0),
                 f"{n} · {(ov.get('urun') or {}).get('toplam')}")
    else:
        KB.check("trendyol /overview", None, f"HTTP {st}")
    for path in ("products", "stock-diff", "price-diff", "orders", "claims", "questions", "reviews", "showcase",
                 "suggestions", "imports", "weekly", "accounts", "meta"):
        st, out = KB.http(f"/api/v1/channels/trendyol/{path}", 900)
        if st != 200:
            KB.check(f"trendyol /{path}", None, f"HTTP {st}")
            continue
        KB.run_all(f"trendyol /{path}", KB.contract(f"trendyol /{path}", out, KP.NOT_RAKAM), heavy)
    for path in ("overview", "accounts", "books", "consignment", "international", "international/books", "rights",
                 "params", "drafts", "market-cards", "meta"):
        st, out = KB.http(f"/api/v1/channels/amazon/{path}", 900)
        if st != 200:
            KB.check(f"amazon /{path}", None, f"HTTP {st}")
            continue
        k = KB.contract(f"amazon /{path}", out, KP.NOT_RAKAM)
        got = KB.run_all(f"amazon /{path}", k, heavy)
        if path == "consignment" and (out.get("toplam") or {}).get("kitap") is not None:
            rows = [r for sid, rs in got.items() if "semantic_intl_consignment" in k["sources"][sid]["sql"] for r in rs]
            KB.check("T2 amazon: konsinye kitap sayısı ≤ konsinye tablosunun satırı (gösterilen SQL)",
                     len(rows) >= int(out["toplam"]["kitap"]), f"satır {len(rows)} · kitap {out['toplam']['kitap']}")
