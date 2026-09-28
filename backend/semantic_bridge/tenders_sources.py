"""M33 İhale takibi: Logo ve CRM okumaları (yalnız okuma) ve birim maliyet kaynağı.

- **Katalog** = CRM kitap kaydı (`new_kitap`, etkin): stok kodu, ad, yazar, yayınevi, ISBN/barkod (güncel ISBN
  `new_isbn13`, eski ISBN `new_isbn`, güncel barkod `new_ean13`, eski barkod `new_EAN10Barkod`), KDV dahil liste fiyatı
  (`new_kdvdahilfiyat`), KDV oranı (`new_kdvorani`), hedef yaş ve sınıf. CRM'de kartı olmayan Logo malzeme kartları
  (`ITEMS.ACTIVE = 0`) adıyla eklenir; Logo barkodu (`UNITBARCODE`) varsa ISBN anahtarı olur.
- **Stok** = Logo stok bakiyesi, güncel firma, tarih filtresiz: `IOCODE 1,2` giriş − `3,4` çıkış, `LINETYPE 0`,
  `CANCELLED 0`; üretimden girişin **planlanan** fişi (`TRCODE 13`, `STFICHE.PRODSTAT = 1`) sayılmaz (M12 ölçümü:
  planlanan ve gerçek giriş toplanırsa adet iki katına çıkıyor).
- **Logo fiyat listesi** = `PRCLIST` satış (`PTYPE 2`), kullanımda (`ACTIVE 0`), TL (`CURRENCY 160`), bugün geçerli;
  cari özel kodu boş liste önce, yoksa en düşük geçerli liste (Kural 8: hangi liste alındığı yazılır).
- **Kamu kurumlarına satış** = faturalı satış satırı (`STLINE`, `LINETYPE 0`, `CANCELLED 0`, `INVOICEREF <> 0`,
  `TRCODE 7/8/9` satış, `2/3` iade eksi; net ciro `LINENET`) × (CRM `AccountBase.new_KurumRolu` 2 Devlet Kurumu / 3 Resmi
  → `new_logicalref` = Logo cari `LOGICALREF`) ∪ Logo satış kanalı `CLCARD.SPECODE2 = 'KURUM'`. CRM ve Logo iki ayrı
  sorgudur; birleştirme anahtar listesiyle yapılır.
- **Birim maliyet** M9'dan gelecek (M9 henüz main'de değil): `unit_costs()` köprüde kayıtlı bir sağlayıcıya sorar
  (`app.state.unit_cost.unit_costs(codes)`), yoksa boş döner ve ekran «maliyet bilinmiyor» yazar.

Ölçülmemiş varsayımlar (kabul listesinde «ölçülecek»): `new_logicalref`'in güncel firmadaki `CLCARD.LOGICALREF` ile aynı
olduğu; `new_kdvorani`'nin yüzde mi oran mı tutulduğu; `PRCLIST.INCVAT` doluluğu; Logo `UNITBARCODE` tablosunun varlığı.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Callable, Iterable, Optional

from semantic_bridge import budget_sources as bsrc

log = logging.getLogger("semantic.tenders.sources")

SourceError = bsrc.SourceError
Runner = bsrc.Runner
runner = bsrc.runner
firms_by_year = bsrc.firms_by_year

#: SQL `IN (...)` listesi parça büyüklüğü (sürücü parametre sınırı değil, sorgu metni boyu için). Parçalar birleştirilir.
CHUNK = 800


def q(v: str) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def _chunks(items: list[str], n: int = CHUNK) -> Iterable[list[str]]:
    for i in range(0, len(items), n):
        yield items[i:i + n]


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
    return n if n == n else None


def current_firm(run: Runner) -> str:
    firms = firms_by_year(run)
    if not firms:
        raise SourceError("Logo'da dönem tanımı okunamadı.")
    return firms[max(firms)]


# ------------------------------------------------------------------ SQL


def crm_catalog_sql(schema: str) -> str:
    """Etkin CRM kitap kayıtları; ISBN/barkod dört alandan. Parola/iletişim alanı seçilmez."""
    return (f"SELECT new_StokKodu AS stok_kodu, new_name AS ad, new_yazartext AS yazar, new_yayineviidName AS yayinevi, "
            f"new_isbn13 AS isbn13, new_isbn AS isbn_eski, new_ean13 AS barkod, new_EAN10Barkod AS barkod_eski, "
            f"new_kdvdahilfiyat AS liste_fiyati, new_kdvorani AS kdv_orani, new_hedefkitleyasbaslangic AS yas_bas, "
            f"new_hedefkitleyasbitis AS yas_bit, new_siniflartext AS siniflar "
            f"FROM {schema}.new_kitap WHERE statecode = 0")


def logo_items_sql(firm: str) -> str:
    return f"SELECT CODE AS stok_kodu, NAME AS ad, SPECODE AS yayinevi FROM dbo.LG_{firm}_ITEMS WHERE ACTIVE = 0"


def logo_barcodes_sql(firm: str) -> str:
    return (f"SELECT I.CODE AS stok_kodu, B.BARCODE AS barkod FROM dbo.LG_{firm}_UNITBARCODE AS B "
            f"JOIN dbo.LG_{firm}_ITEMS AS I ON I.LOGICALREF = B.ITEMREF WHERE I.ACTIVE = 0")


def stock_sql(firm: str, codes: list[str]) -> str:
    return f"""
-- Stok bakiyesi (tarih filtresiz): giriş (IOCODE 1,2) − çıkış (3,4); planlanan üretim girişi (PRODSTAT 1) hariç.
SELECT I.CODE AS stok_kodu, SUM(CASE WHEN L.IOCODE IN (1,2) THEN L.AMOUNT ELSE -L.AMOUNT END) AS stok
FROM dbo.LG_{firm}_01_STLINE AS L
JOIN dbo.LG_{firm}_ITEMS AS I ON I.LOGICALREF = L.STOCKREF
LEFT JOIN dbo.LG_{firm}_01_STFICHE AS F ON F.LOGICALREF = L.STFICHEREF
WHERE L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.IOCODE IN (1,2,3,4)
  AND NOT (L.TRCODE = 13 AND ISNULL(F.PRODSTAT, 0) = 1)
  AND I.CODE IN ({', '.join(q(c) for c in codes)})
GROUP BY I.CODE""".strip()


def price_sql(firm: str, codes: list[str]) -> str:
    return f"""
-- Bugün geçerli TL satış fiyat listeleri (Kural 8). Birden çok liste olabilir; seçim kodda, gerekçesiyle.
SELECT I.CODE AS stok_kodu, P.PRICE AS fiyat, P.CLSPECODE AS cari_ozel_kod, P.PRIORITY AS oncelik, P.INCVAT AS kdv_dahil,
  P.BEGDATE AS baslangic, P.ENDDATE AS bitis
FROM dbo.LG_{firm}_PRCLIST AS P
JOIN dbo.LG_{firm}_ITEMS AS I ON I.LOGICALREF = P.CARDREF
WHERE P.PTYPE = 2 AND P.ACTIVE = 0 AND P.CURRENCY = 160
  AND P.BEGDATE <= CAST(GETDATE() AS date) AND P.ENDDATE >= CAST(GETDATE() AS date)
  AND I.CODE IN ({', '.join(q(c) for c in codes)})""".strip()


def crm_public_accounts_sql(schema: str) -> str:
    """Kamu kurumu işaretli etkin firmalar. Yalnız kimlik, ad, rol ve Logo bağı seçilir."""
    return (f"SELECT AccountId AS id, Name AS ad, new_KurumRolu AS rol, new_logicalref AS logo_ref "
            f"FROM {schema}.AccountBase WHERE StateCode = 0 AND new_KurumRolu IN (2,3)")


def crm_role_counts_sql(schema: str) -> str:
    return (f"SELECT new_KurumRolu AS rol, COUNT(*) AS sayi FROM {schema}.AccountBase "
            f"WHERE StateCode = 0 AND new_KurumRolu IN (2,3,4) GROUP BY new_KurumRolu")


def public_sales_sql(firm: str, year: int, refs: list[int], channel: str) -> str:
    ref_cond = f" OR L.CLIENTREF IN ({', '.join(str(r) for r in refs)})" if refs else ""
    return f"""
-- Faturalı satış satırı; iade eksi. Kamu = Logo kanalı ya da CRM'de kamu kurumu işaretli cari.
SELECT C.LOGICALREF AS ref, C.CODE AS kod, C.DEFINITION_ AS unvan, C.CITY AS il, C.SPECODE2 AS kanal,
  SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.LINENET ELSE -L.LINENET END) AS ciro,
  SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.AMOUNT ELSE -L.AMOUNT END) AS adet,
  COUNT(DISTINCT L.INVOICEREF) AS fatura
FROM dbo.LG_{firm}_01_STLINE AS L
JOIN dbo.LG_{firm}_CLCARD AS C ON C.LOGICALREF = L.CLIENTREF
WHERE L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.INVOICEREF <> 0 AND L.TRCODE IN (2,3,7,8,9)
  AND L.DATE_ >= '{year}-01-01' AND L.DATE_ < '{year + 1}-01-01'
  AND (C.SPECODE2 = {q(channel)}{ref_cond})
GROUP BY C.LOGICALREF, C.CODE, C.DEFINITION_, C.CITY, C.SPECODE2""".strip()


# ------------------------------------------------------------------ okuma


def read_catalog(crm: Runner, logo: Runner, schema: str) -> dict[str, Any]:
    """Kitap kataloğu: CRM etkin kitapları + CRM'de olmayan Logo malzeme kartları. Logo barkodu okunamazsa not düşülür."""
    books: dict[str, dict[str, Any]] = {}
    notes: list[str] = []
    for r in crm(crm_catalog_sql(schema)):
        code = _clean(r.get("stok_kodu"))
        key = code or f"crm:{len(books)}"
        isbns = [x for x in (r.get("isbn13"), r.get("isbn_eski"), r.get("barkod"), r.get("barkod_eski")) if x]
        cur = books.get(key)
        if cur:  # aynı stok koduyla ikinci CRM kaydı: ISBN'leri birleşir
            cur["isbn_ham"].extend(str(x) for x in isbns)
            continue
        books[key] = {"kod": code, "ad": _clean(r.get("ad")), "yazar": _clean(r.get("yazar")),
                      "yayinevi": _clean(r.get("yayinevi")), "isbn_ham": [str(x) for x in isbns],
                      "liste_fiyati": _num(r.get("liste_fiyati")), "kdv_orani": _num(r.get("kdv_orani")),
                      "yas": [_num(r.get("yas_bas")), _num(r.get("yas_bit"))], "siniflar": _clean(r.get("siniflar")),
                      "kaynak": "crm"}
    try:
        firm = current_firm(logo)
        for r in logo(logo_items_sql(firm)):
            code = _clean(r.get("stok_kodu"))
            if not code or code in books:
                continue
            books[code] = {"kod": code, "ad": _clean(r.get("ad")), "yazar": None, "yayinevi": _clean(r.get("yayinevi")),
                           "isbn_ham": [], "liste_fiyati": None, "kdv_orani": None, "yas": [None, None], "siniflar": None,
                           "kaynak": "logo"}
        try:
            for r in logo(logo_barcodes_sql(firm)):
                code = _clean(r.get("stok_kodu"))
                if code in books and r.get("barkod"):
                    books[code]["isbn_ham"].append(str(r["barkod"]))
        except SourceError as e:
            notes.append(f"Logo barkodları okunamadı ({e}); eşleştirme CRM ISBN'leriyle yapıldı.")
    except SourceError as e:
        notes.append(f"Logo malzeme kartları okunamadı ({e}); katalog yalnız CRM kitaplarından.")
    return {"books": list(books.values()), "notes": notes}


def read_stock(logo: Runner, codes: Iterable[str]) -> dict[str, float]:
    codes = sorted({c for c in codes if c})
    if not codes:
        return {}
    firm = current_firm(logo)
    out: dict[str, float] = {}
    for part in _chunks(codes):
        for r in logo(stock_sql(firm, part)):
            out[str(r["stok_kodu"]).strip()] = float(r.get("stok") or 0)
    return out


def read_prices(logo: Runner, codes: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Stok kodu → seçilen geçerli Logo satış fiyatı ve gerekçesi (genel liste önce, yoksa en düşük)."""
    codes = sorted({c for c in codes if c})
    if not codes:
        return {}
    firm = current_firm(logo)
    by: dict[str, list[dict[str, Any]]] = {}
    for part in _chunks(codes):
        for r in logo(price_sql(firm, part)):
            by.setdefault(str(r["stok_kodu"]).strip(), []).append(r)
    out: dict[str, dict[str, Any]] = {}
    for code, rows in by.items():
        general = [r for r in rows if not _clean(r.get("cari_ozel_kod"))]
        pool = general or rows
        best = min(pool, key=lambda r: (float(r.get("fiyat") or 0), int(r.get("oncelik") or 0)))
        out[code] = {"fiyat": _num(best.get("fiyat")), "kdvDahil": bool(best.get("kdv_dahil")) if best.get("kdv_dahil") is not None else None,
                     "liste": "genel satış listesi" if general else f"cari özel kod {(_clean(best.get('cari_ozel_kod')) or '')} listesi",
                     "gecerliListe": len(rows)}
    return out


def read_public_sales(logo: Runner, crm: Runner, schema: str, year: int, channel: str = "KURUM") -> dict[str, Any]:
    """Yılın kamu kurumlarına satışı cari bazında. `kaynak` her satırda: crm (kurum rolü), kanal, ikisi."""
    accounts = crm(crm_public_accounts_sql(schema))
    counts = {int(r["rol"]): int(r["sayi"]) for r in crm(crm_role_counts_sql(schema)) if r.get("rol") is not None}
    crm_by_ref: dict[int, dict[str, Any]] = {}
    unlinked = 0
    for a in accounts:
        digits = re.sub(r"\D", "", str(a.get("logo_ref") or ""))
        if not digits:
            unlinked += 1
            continue
        crm_by_ref[int(digits)] = {"ad": _clean(a.get("ad")), "rol": int(a["rol"]) if a.get("rol") is not None else None}
    firms = firms_by_year(logo)
    firm = firms.get(year)
    if not firm:
        raise SourceError(f"Logo'da {year} yılının dönemi yok.")
    refs = sorted(crm_by_ref)
    rows: dict[int, dict[str, Any]] = {}
    parts = list(_chunks([str(r) for r in refs])) or [[]]
    for part in parts:
        for r in logo(public_sales_sql(firm, year, [int(x) for x in part], channel)):
            ref = int(r["ref"])
            if ref in rows:  # kanal koşulu her parçada tekrar gelir; bir kez sayılır
                continue
            in_crm = ref in crm_by_ref
            in_channel = (_clean(r.get("kanal")) or "").upper() == channel.upper()
            rows[ref] = {"ref": ref, "kod": _clean(r.get("kod")), "unvan": _clean(r.get("unvan")), "il": _clean(r.get("il")),
                         "kanal": _clean(r.get("kanal")), "ciro": float(r.get("ciro") or 0), "adet": float(r.get("adet") or 0),
                         "fatura": int(r.get("fatura") or 0),
                         "kaynak": "ikisi" if in_crm and in_channel else ("crm" if in_crm else "kanal"),
                         "crmRol": (crm_by_ref.get(ref) or {}).get("rol")}
    return {"year": year, "firm": firm, "rows": sorted(rows.values(), key=lambda x: -x["ciro"]),
            "crmKurum": len(accounts), "crmLogoBagsiz": unlinked, "rolSayilari": counts, "kanal": channel}


# ------------------------------------------------------------------ birim maliyet (M9)


CostProvider = Callable[[list[str]], dict[str, dict[str, Any]]]


def unit_costs(provider: Optional[Any], codes: Iterable[str]) -> dict[str, dict[str, Any]]:
    """Stok kodu → {"maliyet": birim maliyet (KDV hariç), "kaynak": metin}. Sağlayıcı yoksa ya da hata verirse boş:
    ekran «maliyet bilinmiyor» yazar, marj hesaplanmaz. Sağlayıcı M9'un köprüde kaydettiği nesnedir
    (`unit_costs(codes)` yöntemi) ya da doğrudan bir işlev."""
    codes = sorted({c for c in codes if c})
    if provider is None or not codes:
        return {}
    fn = getattr(provider, "unit_costs", provider)
    if not callable(fn):
        return {}
    try:
        raw = fn(codes) or {}
    except Exception as e:  # noqa: BLE001 — maliyet yoksa teklif yine hazırlanır
        log.warning("ihale: birim maliyet okunamadı: %s", e)
        return {}
    out = {}
    for k, v in raw.items():
        if isinstance(v, dict):
            m = _num(v.get("maliyet"))
            src = str(v.get("kaynak") or "birim maliyet")
        else:
            m, src = _num(v), "birim maliyet"
        if m is not None and m >= 0:
            out[str(k)] = {"maliyet": m, "kaynak": src}
    return out
