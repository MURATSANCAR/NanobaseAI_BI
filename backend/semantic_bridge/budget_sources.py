"""M46 Bütçe: gerçekleşmenin Logo'dan ve kitap kartının CRM'den okunması (yalnız okuma).

Tanımlar mevcut ölçülerle aynıdır (doğrudan sorguyla ölçüldü, 2026-09-28):

- **Satış satırı** = `STLINE`, `CANCELLED = 0`, `LINETYPE = 0` (malzeme satırı), `INVOICEREF <> 0` (faturalı;
  faturasız irsaliye satışa girmez), `TRCODE 7/8/9` satış, `2/3` iade (eksi).
- **Net ciro** = Σ `LINENET` (satış) − Σ `LINENET` (iade). 2026 toplamı 837.901.631,04 ₺ — kokpitteki satır seviyesi
  net ciroyla birebir.
- **Net adet** = Σ `AMOUNT` (satış) − Σ `AMOUNT` (iade).
- **Maliyet** = Σ `AMOUNT × OUTCOST` (iade eksi), yalnız maliyeti girilmiş satırlarda (`OUTCOST <> 0`); marj bu
  satırların net cirosuna bölünür (`maliyetli_ciro`). 2026 satış satırlarının ~%20'sinde maliyet yok; marj kapsamı ayrıca
  gösterilir.
- **Gider** = muhasebe fiş satırı (`EMFLINE`), 7 ile başlayan gider hesapları; yansıtma hesapları (`7x1`) ve dönem
  sonu kapanış satırları (aynı fişte bir yansıtma hesabının borç satırı olan satırlar) hariç. Borç artı, alacak eksi.
  Departman = masraf merkezi (`EMCENTER`); harfle başlayan kodlar departmandır (B01-GMD-01 Genel Müdürlük …), rakamla
  başlayanlar kitaba/ürüne açılmış merkezlerdir ve tek satırda toplanır.

Yıllar Logo'da ayrı firma numarasıdır (411 = 2026, 211 = 2021–2025 …); eşleme `L_CAPIPERIOD`'dan okunur, kopya
yıllar (`SEMANTIC_EXCLUDE_CONTEXT`, 015/016) atlanır. Satış görünümleri (`V_SatisRaporu_*`) kullanılmaz: satır tanımı
katalogdaki net ciroyla aynı olsun diye doğrudan `STLINE` okunur.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger("semantic.budget.sources")

QUERY_TIMEOUT = int(os.environ.get("BUDGET_QUERY_TIMEOUT_SEC", "1800"))
MAX_ROWS = 2_000_000  # güvenlik ağı; aşılırsa hata verilir, sessizce kesilmez

#: Departman kodu harfle başlar; rakamla başlayan merkez kitaba/ürüne açılmıştır.
BOOK_CENTER = "#KITAP"
NO_CENTER = "#YOK"
CENTER_LABELS = {BOOK_CENTER: "Kitap ve ürün bazlı merkezler (telif, baskı)", NO_CENTER: "Masraf merkezi atanmamış"}


class SourceError(RuntimeError):
    pass


Runner = Callable[[str], list[dict[str, Any]]]


def _connector(path: str, timeout: Optional[int] = None):
    from semantic_layer.profiler.connectors import connector_from_file

    if not path or not Path(path).exists():
        raise SourceError("Veri bağlantısı bu kurulumda tanımlı değil.")
    conn = connector_from_file(path)
    conn.query_timeout = timeout or QUERY_TIMEOUT
    return conn


def runner(path: str, timeout: Optional[int] = None) -> Runner:
    """Bir bağlantı dosyası için sorgu çalıştırıcı. Her çağrıda yeni bağlantı: arka plan iş parçacığında da güvenli.
    `timeout` verilmezse bütçenin süresi (`BUDGET_QUERY_TIMEOUT_SEC`); M45 kendi süresini verir (ortak yardımcı)."""
    limit = timeout or QUERY_TIMEOUT
    conn = _connector(path, limit)

    def run(sql: str) -> list[dict[str, Any]]:
        try:
            _cols, rows, truncated = conn.execute(sql, MAX_ROWS)
        except Exception as e:  # noqa: BLE001 — sürücü metni loga, ekrana düz cümle
            state = str(getattr(e, "args", [""])[0])
            log.warning("budget source failed (%s): %s", state, str(e)[:300])
            if state in ("HYT00", "HYT01"):
                raise SourceError(f"Sorgu {limit} saniyede bitmedi.") from None
            if state in ("08S01", "08001"):
                raise SourceError("Veritabanına şu an ulaşılamıyor.") from None
            raise SourceError(f"Sorgu hata verdi: {str(e)[:200]}") from None
        if truncated:
            raise SourceError("Sonuç beklenenden büyük; eksik okunmasın diye durduruldu.")
        return rows

    return run


# ------------------------------------------------------------------ yıl → Logo firması


def _excluded_firms() -> set[int]:
    raw = os.environ.get("SEMANTIC_EXCLUDE_CONTEXT", "015,016")
    out = set()
    for part in raw.split(","):
        part = part.strip()
        if part.isdigit():
            out.add(int(part))
    return out


def firms_by_year(run: Runner) -> dict[int, str]:
    """Her yıl hangi firma numarasında: `L_CAPIPERIOD` dönemleri. Aynı yılı iki firma tutuyorsa (2015/2016 kopyaları)
    dışlanan kopya atlanır, yine iki kalırsa büyük numara (sonraki düzeltmeler onda) alınır."""
    rows = run("SELECT FIRMNR, BEGDATE, ENDDATE FROM L_CAPIPERIOD WHERE ACTIVE = 1")
    skip = _excluded_firms()
    out: dict[int, int] = {}
    for r in rows:
        firm = int(r["FIRMNR"])
        if firm in skip:
            continue
        beg, end = _day(r["BEGDATE"]), _day(r["ENDDATE"])
        if not beg or not end:
            continue
        for y in range(beg.year, end.year + 1):
            if y not in out or firm > out[y]:
                out[y] = firm
    return {y: f"{f:03d}" for y, f in sorted(out.items())}


def _day(v: Any) -> Optional[date]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return datetime.fromisoformat(str(v)[:19]).date()
    except ValueError:
        return None


def _firm(firms: dict[int, str], year: int) -> str:
    firm = firms.get(year)
    if not firm:
        raise SourceError(f"Logo'da {year} yılının dönemi yok.")
    return firm


# ------------------------------------------------------------------ SQL


def sales_sql(firm: str, year: int) -> str:
    """Kitap (stok kodu) × ay: net adet, net ciro, maliyet ve maliyeti olan satırların net cirosu."""
    return f"""
-- Faturalı satış satırları; iade eksi. Net ciro = LINENET (satır iskontosu düşülmüş).
SELECT I.CODE AS stok_kodu, MONTH(S.DATE_) AS ay,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS ciro,
  SUM(CASE WHEN S.OUTCOST <> 0 THEN (CASE WHEN S.TRCODE IN (7,8,9) THEN 1 ELSE -1 END) * S.AMOUNT * S.OUTCOST ELSE 0 END) AS maliyet,
  SUM(CASE WHEN S.OUTCOST <> 0 THEN (CASE WHEN S.TRCODE IN (7,8,9) THEN 1 ELSE -1 END) * S.LINENET ELSE 0 END) AS maliyetli_ciro
FROM dbo.LG_{firm}_01_STLINE AS S
JOIN dbo.LG_{firm}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{year}-01-01' AND S.DATE_ < '{year + 1}-01-01'
GROUP BY I.CODE, MONTH(S.DATE_)""".strip()


def data_end_sql(firm: str) -> str:
    return (f"SELECT MAX(DATE_) AS son FROM dbo.LG_{firm}_01_STLINE "
            f"WHERE CANCELLED = 0 AND LINETYPE = 0 AND INVOICEREF <> 0 AND TRCODE IN (7,8,9)")


def item_names_sql(firm: str) -> str:
    return f"SELECT CODE AS stok_kodu, NAME AS ad FROM dbo.LG_{firm}_ITEMS"


_CLOSE = "('711','721','731','741','751','761','771','781','791')"


def expense_sql(firm: str, year: int) -> str:
    """Masraf merkezi (departman) × ana gider hesabı × ay."""
    return f"""
-- 7 ile başlayan gider hesapları; yansıtma (7x1) ve dönem sonu kapanış satırları hariç. Borç artı, alacak eksi.
SELECT MONTH(F.DATE_) AS ay,
  CASE WHEN C.CODE IS NULL OR C.CODE = '.' OR C.CODE = '' THEN '{NO_CENTER}'
       WHEN C.CODE LIKE '[0-9]%' THEN '{BOOK_CENTER}' ELSE C.CODE END AS merkez_kodu,
  MAX(CASE WHEN C.CODE LIKE '[0-9]%' THEN NULL ELSE C.DEFINITION_ END) AS merkez_adi,
  LEFT(A.CODE, 3) AS hesap,
  MAX(H.DEFINITION_) AS hesap_adi,
  SUM(CASE WHEN F.SIGN = 0 THEN F.DEBIT ELSE -F.CREDIT END) AS tutar
FROM dbo.LG_{firm}_01_EMFLINE AS F
JOIN dbo.LG_{firm}_EMUHACC AS A ON A.LOGICALREF = F.ACCOUNTREF
LEFT JOIN dbo.LG_{firm}_EMUHACC AS H ON H.CODE = LEFT(A.CODE, 3)
LEFT JOIN dbo.LG_{firm}_EMCENTER AS C ON C.LOGICALREF = F.CENTERREF
WHERE F.CANCELLED = 0 AND A.CODE LIKE '7%' AND LEFT(A.CODE, 3) NOT IN {_CLOSE}
  AND F.DATE_ >= '{year}-01-01' AND F.DATE_ < '{year + 1}-01-01'
  AND NOT EXISTS (
    SELECT 1 FROM dbo.LG_{firm}_01_EMFLINE AS K
    JOIN dbo.LG_{firm}_EMUHACC AS KA ON KA.LOGICALREF = K.ACCOUNTREF
    WHERE K.ACCFICHEREF = F.ACCFICHEREF AND K.CANCELLED = 0 AND K.SIGN = 0 AND LEFT(KA.CODE, 3) IN {_CLOSE})
GROUP BY MONTH(F.DATE_),
  CASE WHEN C.CODE IS NULL OR C.CODE = '.' OR C.CODE = '' THEN '{NO_CENTER}'
       WHEN C.CODE LIKE '[0-9]%' THEN '{BOOK_CENTER}' ELSE C.CODE END,
  LEFT(A.CODE, 3)""".strip()


def crm_books_sql(schema: str = "Timas_MSCRM.dbo") -> str:
    """Kitap kartı: CRM'in raporlama görünümü (yayınevi, kitaplık, yazar, liste fiyatı, statü)."""
    return (f"SELECT StokKodu AS stok_kodu, [Ürün Adı] AS ad, Yazar AS yazar, Yayınevi AS yayinevi, "
            f"Kitaplık AS kitaplik, Üzeri_Fiyat AS liste_fiyati, Statü AS statu FROM {schema}.powerbikitap")


def crm_first_pub_sql(schema: str = "Timas_MSCRM.dbo") -> str:
    """İlk yayın tarihi ve yayınevi: planlanan (henüz raporlama görünümünde olmayan) kitaplar dahil."""
    return (f"SELECT new_stokkodu AS stok_kodu, new_name AS ad, new_ilkyayintarihi AS ilk_yayin, "
            f"new_yayineviidName AS yayinevi FROM {schema}.new_kitap "
            f"WHERE new_stokkodu IS NOT NULL AND statecode = 0")


# ------------------------------------------------------------------ okuma


def read_sales(run: Runner, firms: dict[int, str], year: int) -> list[dict[str, Any]]:
    rows = run(sales_sql(_firm(firms, year), year))
    out = []
    for r in rows:
        code = str(r.get("stok_kodu") or "").strip()
        if not code:
            continue
        out.append({"year": year, "month": int(r["ay"]), "stok_kodu": code[:60],
                    "adet": float(r.get("adet") or 0), "ciro": float(r.get("ciro") or 0),
                    "maliyet": float(r.get("maliyet") or 0), "maliyetli_ciro": float(r.get("maliyetli_ciro") or 0)})
    return out


def read_expenses(run: Runner, firms: dict[int, str], year: int) -> list[dict[str, Any]]:
    rows = run(expense_sql(_firm(firms, year), year))
    merged: dict[tuple[int, str, str], dict[str, Any]] = {}
    for r in rows:
        center = str(r.get("merkez_kodu") or NO_CENTER).strip() or NO_CENTER
        key = (int(r["ay"]), center[:60], str(r.get("hesap") or "")[:3])
        cur = merged.setdefault(key, {"year": year, "month": key[0], "merkez_kodu": key[1], "hesap": key[2],
                                      "merkez_adi": CENTER_LABELS.get(center) or _clean(r.get("merkez_adi")) or center,
                                      "hesap_adi": _clean(r.get("hesap_adi")) or key[2], "tutar": 0.0})
        cur["tutar"] += float(r.get("tutar") or 0)
    return list(merged.values())


def read_data_end(run: Runner, firms: dict[int, str]) -> Optional[date]:
    last = max(firms)
    rows = run(data_end_sql(firms[last]))
    return _day(rows[0].get("son")) if rows else None


def read_item_names(run: Runner, firms: dict[int, str]) -> dict[str, str]:
    last = max(firms)
    return {str(r["stok_kodu"]).strip(): _clean(r.get("ad")) or "" for r in run(item_names_sql(firms[last]))
            if r.get("stok_kodu")}


def read_books(run: Runner, schema: str = "Timas_MSCRM.dbo") -> dict[str, dict[str, Any]]:
    """Stok kodu → kitap kartı. Raporlama görünümündeki alanlar önce; ilk yayın ve (görünümde olmayan) planlı
    kitaplar kitap kaydından. Logo'nun boş tarihi (1899/1900) tarih sayılmaz."""
    books: dict[str, dict[str, Any]] = {}
    for r in run(crm_books_sql(schema)):
        code = str(r.get("stok_kodu") or "").strip()
        if not code:
            continue
        books[code] = {"ad": _clean(r.get("ad")), "yazar": _clean(r.get("yazar")), "yayinevi": _clean(r.get("yayinevi")),
                       "kitaplik": _clean(r.get("kitaplik")), "liste_fiyati": _num(r.get("liste_fiyati")),
                       "statu": _clean(r.get("statu")), "ilk_yayin": None}
    for r in run(crm_first_pub_sql(schema)):
        code = str(r.get("stok_kodu") or "").strip()
        if not code:
            continue
        d = _day(r.get("ilk_yayin"))
        if d and d.year < 1950:
            d = None
        b = books.setdefault(code, {"ad": _clean(r.get("ad")), "yazar": None, "yayinevi": _clean(r.get("yayinevi")),
                                    "kitaplik": None, "liste_fiyati": None, "statu": None, "ilk_yayin": None})
        if not b.get("yayinevi"):
            b["yayinevi"] = _clean(r.get("yayinevi"))
        if not b.get("ad"):
            b["ad"] = _clean(r.get("ad"))
        if d and (b["ilk_yayin"] is None or d.isoformat() < b["ilk_yayin"]):
            b["ilk_yayin"] = d.isoformat()
    return books


def _clean(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s or None


def _num(v: Any) -> Optional[float]:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n else None  # NaN


# ------------------------------------------------------------------ ZEKİ AI tahmini (Baskı Öneri'nin girdisi)


def read_forecast() -> dict[str, Any]:
    """Baskı Öneri'nin 12 aylık kitap tahmini (yönetim raporları önbelleği). Yoksa boş sözlük."""
    root = Path(os.environ.get("MANAGEMENT_REPORT_CACHE_DIR", "/data/nanobaseai/bi/var/management-reports"))
    try:
        snap = json.loads((root / "baski-oneri-tahmin.json").read_text())
    except (OSError, ValueError):
        return {}
    data = snap.get("data") or {}
    fc = data.get("forecasts") or {}
    if not fc or not data.get("forecastStart"):
        return {}
    return {"start": data["forecastStart"], "updatedAt": snap.get("updatedAt"),
            "p50": {k: [max(0.0, float(x or 0)) for x in (v.get("p50") or [])] for k, v in fc.items()}}


def timed(fn: Callable[[], Any]) -> tuple[Any, int]:
    t = time.monotonic()
    out = fn()
    return out, int((time.monotonic() - t) * 1000)
