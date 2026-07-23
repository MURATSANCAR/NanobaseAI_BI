#!/usr/bin/env python3
"""Idempotent ERP Neon seed: 2026 AR/PO/GL + active price lists for complex smoke.

Connects with owner creds from /data/nanobaseai/bi/secrets/connection.local.json.
Safe to re-run: deletes prior DEMO26-* / FL-2026 rows then re-inserts.
"""

from __future__ import annotations

import json
import random
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    print("psycopg2 required", file=sys.stderr)
    sys.exit(2)

SECRETS = Path("/data/nanobaseai/bi/secrets")
TAG = "DEMO26"
N_INVOICES = 360  # ~50/month across Jan–Jul 2026
N_POS = 80
RNG = random.Random(20260719)


def connect():
    src = json.loads((SECRETS / "connection.local.json").read_text())["sources"]["erp"]
    return psycopg2.connect(
        host=src["host"],
        port=int(src.get("port") or 5432),
        dbname=src["database"],
        user=src.get("username") or src.get("user"),
        password=src["password"],
        sslmode="require",
    )


def cleanup(cur) -> None:
    # children first
    cur.execute(
        """
        DELETE FROM fiyat_listesi_kalemleri
        WHERE liste_id IN (SELECT id FROM fiyat_listeleri WHERE kod LIKE 'FL-2026%%')
        """
    )
    cur.execute("DELETE FROM fiyat_listeleri WHERE kod LIKE 'FL-2026%%'")
    cur.execute(
        """
        DELETE FROM yevmiye_kalemleri
        WHERE fis_id IN (SELECT id FROM yevmiye_fisleri WHERE fis_no LIKE %s)
        """,
        (f"{TAG}-YF-%",),
    )
    cur.execute("DELETE FROM yevmiye_fisleri WHERE fis_no LIKE %s", (f"{TAG}-YF-%",))
    cur.execute("DELETE FROM hesap_planlari WHERE kod LIKE %s", (f"{TAG}-%",))
    cur.execute(
        """
        DELETE FROM tahsilatlar WHERE tahsilat_no LIKE %s
           OR fatura_id IN (SELECT id FROM faturalar WHERE fatura_no LIKE %s)
        """,
        (f"{TAG}-TH-%", f"{TAG}-FT-%"),
    )
    cur.execute(
        """
        DELETE FROM fatura_kalemleri
        WHERE fatura_id IN (SELECT id FROM faturalar WHERE fatura_no LIKE %s)
        """,
        (f"{TAG}-FT-%",),
    )
    cur.execute("DELETE FROM faturalar WHERE fatura_no LIKE %s", (f"{TAG}-FT-%",))
    cur.execute(
        """
        DELETE FROM satis_siparis_kalemleri
        WHERE siparis_id IN (SELECT id FROM satis_siparisleri WHERE siparis_no LIKE %s)
        """,
        (f"{TAG}-SS-%",),
    )
    cur.execute("DELETE FROM satis_siparisleri WHERE siparis_no LIKE %s", (f"{TAG}-SS-%",))
    # unlink seed AP from DEMO POs then delete POs
    cur.execute(
        """
        UPDATE alis_faturalari SET siparis_id = NULL
        WHERE siparis_id IN (SELECT id FROM satin_alma_siparisleri WHERE siparis_no LIKE %s)
        """,
        (f"{TAG}-PO-%",),
    )
    cur.execute(
        """
        DELETE FROM satin_alma_kalemleri
        WHERE siparis_id IN (SELECT id FROM satin_alma_siparisleri WHERE siparis_no LIKE %s)
        """,
        (f"{TAG}-PO-%",),
    )
    cur.execute("DELETE FROM satin_alma_siparisleri WHERE siparis_no LIKE %s", (f"{TAG}-PO-%",))
    cur.execute("DELETE FROM stok_hareketleri WHERE referans_no LIKE %s", (f"{TAG}-%",))
    # remove prior DEMO AP rows (optional extras)
    cur.execute(
        """
        DELETE FROM alis_fatura_kalemleri
        WHERE alis_fatura_id IN (SELECT id FROM alis_faturalari WHERE fatura_no LIKE %s)
        """,
        (f"{TAG}-AF-%",),
    )
    cur.execute("DELETE FROM alis_faturalari WHERE fatura_no LIKE %s", (f"{TAG}-AF-%",))


def ensure_accounts(cur) -> dict[str, int]:
    rows = [
        (f"{TAG}-600", "Yurtiçi Satış Gelirleri", "gelir", True),
        (f"{TAG}-601", "Yurtdışı Satış Gelirleri", "gelir", True),
        (f"{TAG}-120", "Ticari Alacaklar", "varlik", True),
        (f"{TAG}-153", "Ticari Mallar", "varlik", True),
        (f"{TAG}-320", "Ticari Borçlar", "yukumluluk", True),
    ]
    execute_values(
        cur,
        """
        INSERT INTO hesap_planlari (kod, ad, tip, aktif) VALUES %s
        ON CONFLICT (kod) DO UPDATE SET ad=EXCLUDED.ad, tip=EXCLUDED.tip, aktif=true
        """,
        rows,
    )
    cur.execute(
        "SELECT kod, id FROM hesap_planlari WHERE kod LIKE %s",
        (f"{TAG}-%",),
    )
    return {k: i for k, i in cur.fetchall()}


def seed_price_lists(cur, product_ids: list[int]) -> int:
    cur.execute(
        """
        INSERT INTO fiyat_listeleri (kod, ad, para_id, aktif)
        VALUES
          ('FL-2026-STD', '2026 Standart Liste', 1, true),
          ('FL-2026-VIP', '2026 VIP Liste', 1, true)
        RETURNING id, kod
        """
    )
    lists = cur.fetchall()
    items = []
    for liste_id, kod in lists:
        for uid in product_ids:
            cur.execute("SELECT satis_fiyat FROM urunler WHERE id=%s", (uid,))
            base = cur.fetchone()[0] or Decimal("100")
            # VIP slightly lower list; STD = list; invoices will undersell STD for leakage
            mult = Decimal("1.05") if kod.endswith("STD") else Decimal("0.98")
            items.append((liste_id, uid, round(Decimal(base) * mult, 2)))
    execute_values(
        cur,
        "INSERT INTO fiyat_listesi_kalemleri (liste_id, urun_id, fiyat) VALUES %s",
        items,
    )
    return len(items)


def seed_sales_2026(cur, customers: list[int], products: list[int], branches: list[int]) -> tuple[int, int, int]:
    inv_rows = []
    line_rows = []  # (fatura_no, urun_id, miktar, birim_fiyat, kdv, tutar)
    order_rows = []
    order_lines = []
    tahsil_rows = []

    # map product -> list price for discount leakage
    cur.execute(
        """
        SELECT flk.urun_id, flk.fiyat
        FROM fiyat_listesi_kalemleri flk
        JOIN fiyat_listeleri fl ON fl.id=flk.liste_id
        WHERE fl.kod='FL-2026-STD'
        """
    )
    list_price = {u: p for u, p in cur.fetchall()}

    start = date(2026, 1, 5)
    for i in range(1, N_INVOICES + 1):
        d = start + timedelta(days=RNG.randint(0, 195))  # through ~Jul 19
        if d > date(2026, 7, 19):
            d = date(2026, 7, 18)
        mid = customers[(i * 17) % len(customers)]
        sid = branches[(i * 3) % len(branches)]
        fno = f"{TAG}-FT-{i:05d}"
        sno = f"{TAG}-SS-{i:05d}"
        n_lines = RNG.randint(1, 3)
        ara = Decimal("0")
        kdv = Decimal("0")
        chosen = []
        for li in range(n_lines):
            uid = products[(i * 11 + li * 5) % len(products)]
            qty = Decimal(RNG.randint(2, 40))
            lp = list_price.get(uid) or Decimal("100")
            # ~40% of lines undersell by >10% for P09
            if RNG.random() < 0.4:
                unit = (lp * Decimal("0.82")).quantize(Decimal("0.01"))
            else:
                unit = (lp * Decimal("0.97")).quantize(Decimal("0.01"))
            line_tutar = (qty * unit).quantize(Decimal("0.01"))
            kdv_orani = Decimal("20")
            ara += line_tutar
            kdv += (line_tutar * kdv_orani / Decimal("100")).quantize(Decimal("0.01"))
            chosen.append((uid, qty, unit, kdv_orani, line_tutar))
            order_lines.append((sno, uid, qty, unit, kdv_orani, line_tutar))
            line_rows.append((fno, uid, qty, unit, kdv_orani, line_tutar))
        genel = ara + kdv
        durum = "Ödendi" if RNG.random() < 0.55 else "Açık"
        # some overdue open for P01 risk
        if durum == "Açık" and RNG.random() < 0.35:
            vade = d - timedelta(days=RNG.randint(15, 60))
        else:
            vade = d + timedelta(days=30)
        order_rows.append((sno, mid, sid, 4, 1, d, ara, kdv, genel))
        inv_rows.append((fno, mid, sno, sid, "satış", durum, d, vade, ara, kdv, genel))
        if durum == "Ödendi" or RNG.random() < 0.35:
            pay = genel if durum == "Ödendi" else (genel * Decimal("0.5")).quantize(Decimal("0.01"))
            tahsil_rows.append(
                (f"{TAG}-TH-{i:05d}", mid, fno, pay, d + timedelta(days=RNG.randint(1, 25)), "havale", "tamam")
            )

    execute_values(
        cur,
        """
        INSERT INTO satis_siparisleri
          (siparis_no, musteri_id, sube_id, durum_id, para_id, siparis_tarihi,
           ara_toplam, kdv_toplam, genel_toplam, created_at)
        VALUES %s
        """,
        [(a, b, c, d, e, f, g, h, i, f) for a, b, c, d, e, f, g, h, i in order_rows],
        template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::date)",
    )
    cur.execute(
        "SELECT siparis_no, id FROM satis_siparisleri WHERE siparis_no LIKE %s",
        (f"{TAG}-SS-%",),
    )
    ss_map = dict(cur.fetchall())
    execute_values(
        cur,
        """
        INSERT INTO satis_siparis_kalemleri
          (siparis_id, urun_id, miktar, birim_fiyat, kdv_orani, tutar) VALUES %s
        """,
        [(ss_map[sno], uid, qty, unit, kdv_o, tut) for sno, uid, qty, unit, kdv_o, tut in order_lines],
    )

    execute_values(
        cur,
        """
        INSERT INTO faturalar
          (fatura_no, musteri_id, siparis_id, sube_id, tip, durum, fatura_tarihi, vade_tarihi,
           ara_toplam, kdv_toplam, genel_toplam, created_at)
        VALUES %s
        """,
        [
            (fno, mid, ss_map[sno], sid, tip, durum, d, vade, ara, kdv, genel, d)
            for fno, mid, sno, sid, tip, durum, d, vade, ara, kdv, genel in inv_rows
        ],
        template="(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::date)",
    )
    cur.execute(
        "SELECT fatura_no, id, musteri_id FROM faturalar WHERE fatura_no LIKE %s",
        (f"{TAG}-FT-%",),
    )
    ft_map = {no: (fid, mid) for no, fid, mid in cur.fetchall()}
    execute_values(
        cur,
        """
        INSERT INTO fatura_kalemleri
          (fatura_id, urun_id, miktar, birim_fiyat, kdv_orani, tutar) VALUES %s
        """,
        [(ft_map[fno][0], uid, qty, unit, kdv_o, tut) for fno, uid, qty, unit, kdv_o, tut in line_rows],
    )
    execute_values(
        cur,
        """
        INSERT INTO tahsilatlar
          (tahsilat_no, musteri_id, fatura_id, tutar, odeme_tarihi, yontem, durum, created_at)
        VALUES %s
        """,
        [
            (tno, mid, ft_map[fno][0], tut, od, yontem, durum, od)
            for tno, mid, fno, tut, od, yontem, durum in tahsil_rows
            if fno in ft_map
        ],
        template="(%s,%s,%s,%s,%s,%s,%s,%s::date)",
    )
    return len(inv_rows), len(line_rows), len(tahsil_rows)


def seed_po_2026(cur, suppliers: list[int], products: list[int], branches: list[int]) -> int:
    # Create POs; link some to existing CAPEX/OPEX AP by updating siparis_id
    po_rows = []
    po_lines = []
    for i in range(1, N_POS + 1):
        d = date(2026, 1, 10) + timedelta(days=RNG.randint(0, 180))
        tid = suppliers[(i * 13) % len(suppliers)]
        sid = branches[i % len(branches)]
        sno = f"{TAG}-PO-{i:04d}"
        uid = products[(i * 7) % len(products)]
        qty = Decimal(RNG.randint(5, 50))
        unit = Decimal(RNG.randint(80, 4000))
        tut = (qty * unit).quantize(Decimal("0.01"))
        kdv = (tut * Decimal("0.20")).quantize(Decimal("0.01"))
        genel = tut + kdv
        po_rows.append((sno, tid, sid, 2 if i % 5 else 4, d, tut, kdv, genel))
        po_lines.append((sno, uid, qty, unit, tut))

    execute_values(
        cur,
        """
        INSERT INTO satin_alma_siparisleri
          (siparis_no, tedarikci_id, sube_id, durum_id, siparis_tarihi,
           ara_toplam, kdv_toplam, genel_toplam)
        VALUES %s
        """,
        po_rows,
    )
    cur.execute(
        "SELECT siparis_no, id, siparis_tarihi FROM satin_alma_siparisleri WHERE siparis_no LIKE %s",
        (f"{TAG}-PO-%",),
    )
    po_map = {no: (pid, dt) for no, pid, dt in cur.fetchall()}
    execute_values(
        cur,
        """
        INSERT INTO satin_alma_kalemleri (siparis_id, urun_id, miktar, birim_fiyat, tutar)
        VALUES %s
        """,
        [(po_map[sno][0], uid, qty, unit, tut) for sno, uid, qty, unit, tut in po_lines],
    )

    # Link first 6 seed AP invoices to first 6 POs (with lag) for P04/P10
    cur.execute(
        """
        SELECT id, fatura_tarihi, butce_kodu FROM alis_faturalari
        WHERE fatura_no LIKE 'AF-SEED-%%' ORDER BY id LIMIT 6
        """
    )
    aps = cur.fetchall()
    for idx, (ap_id, fat_dt, _bk) in enumerate(aps):
        sno = f"{TAG}-PO-{idx+1:04d}"
        if sno not in po_map:
            continue
        pid, po_dt = po_map[sno]
        # ensure PO date before invoice
        if po_dt >= fat_dt:
            cur.execute(
                "UPDATE satin_alma_siparisleri SET siparis_tarihi=%s WHERE id=%s",
                (fat_dt - timedelta(days=RNG.randint(7, 35)), pid),
            )
        cur.execute("UPDATE alis_faturalari SET siparis_id=%s WHERE id=%s", (pid, ap_id))

    # Extra DEMO AP linked to later POs for CAPEX open-PO remaining
    for i, bk in enumerate(("IT-HW", "IT-ENDPOINT", "IT-SW-CAP"), start=1):
        sno = f"{TAG}-PO-{20+i:04d}"
        if sno not in po_map:
            continue
        pid, po_dt = po_map[sno]
        fno = f"{TAG}-AF-{bk}-{i}"
        cur.execute(
            """
            INSERT INTO alis_faturalari
              (fatura_no, tedarikci_id, siparis_id, sube_id, butce_kodu, departman_kod,
               durum, fatura_tarihi, vade_tarihi, ara_toplam, kdv_toplam, genel_toplam)
            SELECT %s, tedarikci_id, %s, sube_id, %s, 'IT-CAPEX', 'acik',
                   siparis_tarihi + 20, siparis_tarihi + 50,
                   100000, 20000, 120000
            FROM satin_alma_siparisleri WHERE id=%s
            """,
            (fno, pid, bk, pid),
        )
    return len(po_rows)


def seed_gl_2026(cur, accounts: dict[str, int]) -> int:
    gelir_id = accounts[f"{TAG}-600"]
    alacak_id = accounts[f"{TAG}-120"]
    n = 0
    for month in range(1, 8):
        fis_no = f"{TAG}-YF-{month:02d}"
        fis_dt = date(2026, month, 28 if month != 2 else 27)
        cur.execute(
            """
            SELECT COALESCE(SUM(genel_toplam),0) FROM faturalar
            WHERE EXTRACT(YEAR FROM fatura_tarihi)=2026
              AND EXTRACT(MONTH FROM fatura_tarihi)=%s
              AND fatura_no LIKE %s
            """,
            (month, f"{TAG}-FT-%"),
        )
        total = cur.fetchone()[0] or Decimal("0")
        if total <= 0:
            total = Decimal("500000")
        cur.execute(
            """
            INSERT INTO yevmiye_fisleri (fis_no, fis_tarihi, aciklama, created_at)
            VALUES (%s, %s, %s, %s) RETURNING id
            """,
            (fis_no, fis_dt, f"2026/{month} satış tahakkuk", fis_dt),
        )
        fis_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO yevmiye_kalemleri (fis_id, hesap_id, borc, alacak) VALUES
              (%s, %s, %s, 0),
              (%s, %s, 0, %s)
            """,
            (fis_id, alacak_id, total, fis_id, gelir_id, total),
        )
        n += 1
    return n


def seed_stock_moves(cur, products: list[int], warehouses: list[int]) -> int:
    # Recent exits for ~half of sampled products so P05 still has dead stock
    rows = []
    today = date(2026, 7, 19)
    for i, uid in enumerate(products[:80]):
        if i % 2 == 0:
            continue
        depo = warehouses[i % len(warehouses)]
        rows.append(
            (
                depo,
                uid,
                "cikis",
                Decimal(RNG.randint(1, 20)),
                f"{TAG}-SH-{i:04d}",
                today - timedelta(days=RNG.randint(1, 60)),
            )
        )
    execute_values(
        cur,
        """
        INSERT INTO stok_hareketleri
          (depo_id, urun_id, hareket_tipi, miktar, referans_no, hareket_tarihi, created_at)
        VALUES %s
        """,
        [(a, b, c, d, e, f, f) for a, b, c, d, e, f in rows],
        template="(%s,%s,%s,%s,%s,%s,%s::date)",
    )
    return len(rows)


def bump_risk_limits(cur) -> int:
    """Ensure some 2026 top customers can trip risk_limit vs open balance."""
    cur.execute(
        """
        WITH topm AS (
          SELECT musteri_id, SUM(genel_toplam) AS ciro
          FROM faturalar
          WHERE fatura_no LIKE %s
          GROUP BY 1 ORDER BY 2 DESC LIMIT 8
        )
        UPDATE musteriler m
        SET risk_limit = LEAST(COALESCE(m.risk_limit, 50000), 25000)
        FROM topm t WHERE m.id=t.musteri_id
        RETURNING m.id
        """,
        (f"{TAG}-FT-%",),
    )
    return len(cur.fetchall())


def main() -> int:
    conn = connect()
    conn.autocommit = False
    cur = conn.cursor()
    try:
        print("cleanup…")
        cleanup(cur)

        cur.execute("SELECT id FROM musteriler WHERE aktif IS TRUE ORDER BY id LIMIT 400")
        customers = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT id FROM urunler WHERE aktif IS TRUE ORDER BY id LIMIT 200")
        products = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT id FROM subeler ORDER BY id")
        branches = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT id FROM tedarikciler WHERE aktif IS TRUE ORDER BY id LIMIT 200")
        suppliers = [r[0] for r in cur.fetchall()]
        cur.execute("SELECT id FROM depolar ORDER BY id LIMIT 24")
        warehouses = [r[0] for r in cur.fetchall()]
        if not all([customers, products, branches, suppliers, warehouses]):
            raise RuntimeError("missing master data")

        print("accounts…")
        accounts = ensure_accounts(cur)
        print("price lists…")
        n_fl = seed_price_lists(cur, products[:120])
        print("sales 2026…")
        n_inv, n_lines, n_tah = seed_sales_2026(cur, customers, products[:120], branches)
        print("PO 2026…")
        n_po = seed_po_2026(cur, suppliers, products[:120], branches)
        print("GL 2026…")
        n_gl = seed_gl_2026(cur, accounts)
        print("stock moves…")
        n_sh = seed_stock_moves(cur, products[:120], warehouses)
        n_risk = bump_risk_limits(cur)
        conn.commit()

        # verify
        cur.execute(
            """
            SELECT
              (SELECT count(*) FROM faturalar WHERE EXTRACT(YEAR FROM fatura_tarihi)=2026),
              (SELECT coalesce(sum(genel_toplam),0) FROM faturalar WHERE EXTRACT(YEAR FROM fatura_tarihi)=2026),
              (SELECT count(*) FROM fiyat_listeleri WHERE aktif),
              (SELECT count(*) FROM fiyat_listesi_kalemleri),
              (SELECT count(*) FROM satin_alma_siparisleri WHERE EXTRACT(YEAR FROM siparis_tarihi)=2026),
              (SELECT count(*) FROM yevmiye_fisleri WHERE EXTRACT(YEAR FROM fis_tarihi)=2026),
              (SELECT count(*) FROM tahsilatlar WHERE EXTRACT(YEAR FROM odeme_tarihi)=2026)
            """
        )
        v = cur.fetchone()
        print(
            json.dumps(
                {
                    "ok": True,
                    "inserted": {
                        "invoices": n_inv,
                        "invoice_lines": n_lines,
                        "collections": n_tah,
                        "pos": n_po,
                        "price_list_items": n_fl,
                        "gl_docs": n_gl,
                        "stock_moves": n_sh,
                        "risk_bumped": n_risk,
                    },
                    "verify_2026": {
                        "faturalar": int(v[0]),
                        "ciro": float(v[1]),
                        "aktif_fiyat_listeleri": int(v[2]),
                        "fiyat_kalem": int(v[3]),
                        "po": int(v[4]),
                        "yevmiye": int(v[5]),
                        "tahsilat": int(v[6]),
                    },
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    except Exception as exc:
        conn.rollback()
        print(f"FAIL: {exc}", file=sys.stderr)
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
