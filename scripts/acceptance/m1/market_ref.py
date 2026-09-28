"""Bağımsız referans: bir kitaplığın kohort ilk yıl net satışı ve son 36 ay kanal toplamı, doğrudan DB'den.
Uygulamadan farklı yol: ilk yıl penceresi ve iade işareti SQL tarafında hesaplanır; çeyrekler statistics ile.

Kullanım (test sunucusu): python market_ref.py "Tarih Kitaplığı"

2026-09-28 düzeltmesi (kabulde iki hata): çok komutlu CRM sorgusu (DECLARE + SELECT) `SET NOCOUNT ON` olmadan sürücüye
önce satırsız sonuç kümesi döndürüyordu; sürücü tarih kolonunu metin döndürünce `.year` yoktu ve bütün kohort düşüyordu.
Tarih artık date/datetime/metin (ISO ya da gg.aa.yyyy) hepsinden okunur; okunamayan tarih sayılıp ekrana yazılır.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
import time
from datetime import date, datetime
from typing import Any, Optional

SERVER_BACKEND = "/data/nanobaseai/bi/frontend/backend"
CRM_CONN = "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"
LOGO_CONN = "/data/nanobaseai/bi/secrets/logo-mssql-connection.json"

_ISO = re.compile(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})")
_TR = re.compile(r"^\s*(\d{1,2})[./](\d{1,2})[./](\d{4})")


def month_index(v: Any) -> Optional[int]:
    """Tarih → yıl*12 + ay - 1. date/datetime ya da metin («2023-05-01», «2023-05-01 00:00:00.000», «2023-05-01T..»,
    «01.05.2023»); okunamazsa None."""
    if v is None:
        return None
    if isinstance(v, (date, datetime)):
        return v.year * 12 + v.month - 1
    if isinstance(v, bytes):
        v = v.decode("utf-8", "replace")
    s = str(v)
    m = _ISO.match(s)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
    else:
        m = _TR.match(s)
        if not m:
            return None
        y, mo = int(m.group(3)), int(m.group(2))
    if not 1 <= mo <= 12:
        return None
    return y * 12 + mo - 1


def cohort_sql(cat: str) -> str:
    """Kohort sorgusu. DECLARE + SELECT iki komut: `SET NOCOUNT ON` başta, yoksa ilk sonuç kümesi satırsız döner."""
    safe = cat.replace("'", "''")
    return ("SET NOCOUNT ON; "
            "DECLARE @m0 date = DATEFROMPARTS(YEAR(GETDATE()), MONTH(GETDATE()), 1); "
            "SELECT LTRIM(RTRIM(k.new_StokKodu)) AS kod, MIN(CAST(k.new_ilkyayintarihi AS date)) AS ilk "
            "FROM dbo.new_kitapBase k JOIN dbo.new_kitaplikBase kl ON kl.new_kitaplikId = k.new_kitaplikid "
            f"WHERE kl.new_name = N'{safe}' AND k.statecode = 0 AND LTRIM(RTRIM(ISNULL(k.new_StokKodu,''))) <> '' "
            "AND k.new_ilkyayintarihi >= DATEADD(month, -48, @m0) AND k.new_ilkyayintarihi < DATEADD(month, -12, @m0) "
            "GROUP BY LTRIM(RTRIM(k.new_StokKodu))")


def cohort_index(rows: list[dict[str, Any]]) -> tuple[dict[str, int], list[str]]:
    """(kod → ilk yayın ay endeksi, tarihi okunamayan kodlar)."""
    idx: dict[str, int] = {}
    bad: list[str] = []
    for r in rows:
        i = month_index(r.get("ilk"))
        if i is None:
            bad.append(str(r.get("kod")))
        else:
            idx[str(r["kod"])] = i
    return idx, bad


def sales_sql(year: int, vals: str, now_i: int) -> str:
    return ("SELECT s.[Malzeme/Hizmet Kodu] AS kod, s.KANAL AS kanal, COUNT(*) AS n, "
            "SUM(CASE WHEN (s.[Yıl]*12 + s.[Ay] - 1) - c.i BETWEEN 0 AND 11 THEN "
            "  CASE WHEN UPPER(s.Satis_Iade) LIKE N'%ADE%' THEN -ABS(s.Miktar) ELSE s.Miktar END ELSE 0 END) AS ilk_yil, "
            f"SUM(CASE WHEN (s.[Yıl]*12 + s.[Ay] - 1) BETWEEN {now_i - 35} AND {now_i} THEN "
            "  CASE WHEN UPPER(s.Satis_Iade) LIKE N'%ADE%' THEN -ABS(s.Miktar) ELSE s.Miktar END ELSE 0 END) AS son36 "
            f"FROM dbo.V_SatisRaporu_{year} s JOIN (VALUES {vals}) AS c(k, i) ON c.k = s.[Malzeme/Hizmet Kodu] "
            "WHERE s.[Malzeme/Hizmet Kodu] NOT LIKE '157%' AND s.[KDVli Tutar] <> 0 "
            "GROUP BY s.[Malzeme/Hizmet Kodu], s.KANAL")


def main(cat: str) -> None:
    sys.path.insert(0, SERVER_BACKEND)
    from semantic_layer.profiler.connectors import connector_from_file

    crm = connector_from_file(CRM_CONN)
    logo = connector_from_file(LOGO_CONN)
    crm.query_timeout = logo.query_timeout = 900

    t = time.time()
    _, rows, _ = crm.execute(cohort_sql(cat), 100000)
    idx, bad = cohort_index(rows)
    print("kohort", len(rows), "kitap", round(time.time() - t, 1), "sn", f"(tarihi okunamayan {len(bad)}: {bad})" if bad else "")
    if not idx:
        print(json.dumps({"books": 0, "unreadableDates": len(bad), "not": "kohort boş"}, ensure_ascii=False))
        return
    vals = ", ".join("(N'%s', %d)" % (k.replace("'", "''"), v) for k, v in idx.items())
    now = time.localtime()
    now_i = now.tm_year * 12 + now.tm_mon - 1
    first = {k: 0.0 for k in idx}
    lines = {k: 0 for k in idx}
    chan: dict[str, float] = {}
    for y in range(min(idx.values()) // 12, now.tm_year + 1):
        t = time.time()
        try:
            _, r2, _ = logo.execute(sales_sql(y, vals, now_i), 1000000)
        except Exception as e:  # noqa: BLE001 — yıl görünümü yoksa sonraki yıla geç, hatayı yaz
            print(y, "HATA", str(e)[:200])
            continue
        for r in r2:
            kod = str(r["kod"]).strip()
            if kod not in first:
                continue
            first[kod] += float(r["ilk_yil"] or 0)
            lines[kod] += int(r["n"] or 0)
            name = (r["kanal"] or "").strip() or "Belirtilmemiş"
            chan[name] = chan.get(name, 0.0) + float(r["son36"] or 0)
        print(y, len(r2), "satır", round(time.time() - t, 1), "sn")
    sold = [first[k] for k in idx if lines[k] > 0]
    q = statistics.quantiles(sold, n=4, method="inclusive") if len(sold) >= 2 else [None] * 3
    print(json.dumps({"books": len(idx), "withSales": len(sold), "unreadableDates": len(bad),
                      "p25": round(q[0]) if q[0] is not None else None,
                      "p50": round(statistics.median(sold)) if sold else None, "p75": round(q[2]) if q[2] is not None else None,
                      "channels": {k: round(v) for k, v in sorted(chan.items(), key=lambda kv: -kv[1])},
                      "last36": round(sum(chan.values()))}, ensure_ascii=False))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("kullanım: market_ref.py <kitaplık adı>")
    main(sys.argv[1])
