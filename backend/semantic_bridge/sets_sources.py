"""M53 Set, hediye ve promosyon: Logo ve CRM okumaları (yalnız okuma) ve birim maliyet kaynağı.

Tanımlar mevcut ölçülerle aynıdır:

- **Satış satırı** (`budget_sources.sales_sql` ile aynı): `STLINE`, `CANCELLED = 0`, `INVOICEREF <> 0` (faturalı),
  `TRCODE 7/8/9` satış, `2/3` iade (eksi). Net ciro = Σ `VATMATRAH` (KDV matrahı, fatura geneli iskonto dahil; dönem
  fatura tarihi `INVOICE.DATE_` — karar 2026-10-01), net adet = Σ `AMOUNT`. Satır türü ayardır
  (`SETS_SALES_LINETYPES`, varsayılan `0` = malzeme satırı — bütçe ve kokpitle aynı).
- **Set satışı yalnız setin kendi stok koduyla okunur.** Katalog profilinde `ITEMS.CARDTYPE` değerleri 1, 4, 10, 11, 12,
  13, 20, 22'dir; Karma Koli (2) yoktur. Set ayrı bir stok kartıdır; bileşenler CRM «Set İşlemi» (set yapma) ile stoktan
  düşer, satış faturasında set kodu satılır. Bu yüzden set cirosu ile bileşenin tek satışı ayrı kodlardır ve modül ikisini
  hiçbir toplamda birleştirmez (çift sayım yok). Aynı faturada set satırının yanında bileşen satırı olup olmadığı kabul
  betiğinde ölçülür (`scripts/acceptance/M53/kabul.py --olcum`, Ö1–Ö3); ölçüm aksini gösterirse satır türü ayarı değişir.
- **Stok bakiyesi** güncel yıl kopyasından, tarihsiz: `IOCODE 1/2` giriş, `3/4` çıkış (M32 ile aynı tanım).
- **Logo liste fiyatı** `PRCLIST`: satış listesi `PTYPE = 2`, `ACTIVE = 0`, TL, bugün geçerli; birden çok liste varsa
  cariye bağlı olmayan, sonra küçük öncelik, sonra en yeni başlangıç.
- **KDV oranı** kalem başına Logo `ITEMS.SELLVAT` (kitapta 0; kırtasiye/ambalajda farklı olabilir).
- **Set bileşeni** kaynağı ayardır (`SETS_COMPONENT_SOURCE`): `crm` = setin en son etkin «Set Yapma» işleminin alt mamul
  satırları; `logo` = Logo ürün reçetesi (`BOMASTER.MAINPRODREF` = set, geçerli revizyonun `BOMLINE` satırları, ana ürün
  satırı hariç); `auto` (varsayılan) = CRM, CRM'de işlem yoksa Logo reçetesi. Hangisinin esas olduğu kabulde ölçülür.
- **Birlikte alım** yalnız tüketici (B2C) siparişlerinden: sipariş tipi 8 ya da adı «B2C» ile başlayan; taslak ve iptal
  sipariş, iptal satır, promosyon/kesin hediye/bedelsiz satırlar hariç. Bayi siparişi tüketici sepeti değildir.

Yıllar Logo'da ayrı firma numarasıdır (411 = 2026, 211 = 2021–2025); eşleme `L_CAPIPERIOD`'dan (`budget_sources.firms_by_year`).
CRM (`Timas_MSCRM`, .28) yalnız okunur. CRM'e, Logo'ya ve T-soft'a hiçbir şey yazılmaz.

**Birim maliyet** (`unit_costs`): marjın maliyeti M9'dan gelecek. M9 hazır olunca `register_cost_provider` ile bağlanır.
`SETS_COST_SOURCE`: `m9` (varsayılan; sağlayıcı yoksa maliyet «bilinmiyor»), `logo` (Logo'da kitabın en son maliyeti girilmiş
satış satırının `OUTCOST`'u — «tahmini»), `yok`. Maliyet hiçbir yolda uydurulmaz.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from typing import Any, Callable, Iterable, Optional

from semantic_bridge import budget_sources as bsrc
from semantic_bridge import crm_labels

log = logging.getLogger("semantic.sets.sources")

SourceError = bsrc.SourceError
Runner = bsrc.Runner
runner = bsrc.runner
firms_by_year = bsrc.firms_by_year

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FIRM = re.compile(r"^[0-9]{3}$")
_CODE = re.compile(r"^[^'\x00-\x1f]{1,60}$")
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

#: CRM kitap kartı `new_Tip`.
CRM_TIP = crm_labels.Labels("new_kitap", "new_tip", {
    1: "Kitap", 2: "Promosyon", 4: "Set", 5: "Dergi", 7: "Pazarlama Materyalleri", 8: "Ekitap", 9: "SesliKitap",
})
CRM_SET_TIPI = crm_labels.Labels("new_kitap", "new_settipi", {1: "Normal Set", 2: "Toplama Set", 3: "Dergi Set"})
CRM_SATIS_KANALI = crm_labels.Labels("new_kitap", "new_satiskanallari", {
    1: "Timaş Satış Kanalı", 2: "Market", 3: "KDD", 4: "Toplama Set", 6: "Diğer", 7: "Toptan & Eticaret",
    8: "B2C Toplama Set",
})
CRM_PROMOSYON_TIPI = crm_labels.Labels("new_kitap", "new_promosyontipi", {
    1: "Kutu", 2: "Koli", 3: "Değerlendirme Testi", 4: "Bez Çanta", 5: "Bayrak", 6: "Afiş", 7: "Kart Postal",
    8: "Defter", 9: "Gazete", 10: "Ebeveyn Rehberi", 11: "Kalem", 12: "Stand", 13: "Fincan",
})
#: CRM «Paketleme» türleri (`new_paketlemeBase.new_paketlemetipi`).
PAKETLEME = crm_labels.Labels("new_paketleme", "new_paketlemetipi", {
    0: "Shrink", 1: "Şerit çember", 2: "Vakumlu paket", 3: "Kraft paket", 4: "Kutulama", 5: "Kolileme",
}, fixed=True)
HEDIYE_TALEP_DURUM = crm_labels.Labels("new_hediyetalebi", "statuscode", {
    1: "Yeni", 100000000: "Onay bekliyor", 100000001: "Onaylandı", 2: "İptal", 100000002: "Sevk edildi",
})


def prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise SourceError(f"CRM şeması «{schema}» geçerli bir ad değil.")
    if not sch:
        raise SourceError("CRM şeması girilmemiş; CRM okunamıyor.")
    return (f"{db}." if db else "") + f"{sch}."


def _f(firm: str) -> str:
    if not _FIRM.match(firm or ""):
        raise SourceError(f"Logo firma numarası «{firm}» geçersiz.")
    return firm


def code_ok(code: str) -> bool:
    return bool(_CODE.match(code or ""))


def _lit(code: str) -> str:
    if not code_ok(code):
        raise SourceError(f"Stok kodu «{code}» geçersiz.")
    return "N'" + code.replace("'", "''") + "'"


def int_list(raw: str) -> list[int]:
    return [int(x) for x in re.findall(r"-?\d+", raw or "")]


def day(v: Any) -> Optional[date]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        d = v.date()
    elif isinstance(v, date):
        d = v
    else:
        try:
            d = datetime.fromisoformat(str(v)[:19]).date()
        except ValueError:
            return None
    return None if d.year < 1950 else d  # Logo/CRM boş tarihi (1899/1900) tarih değildir


def clean(v: Any, limit: int = 400) -> Optional[str]:
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s[:limit] or None


def num(v: Any) -> Optional[float]:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def strip_html(v: Any, limit: int = 1000) -> Optional[str]:
    if v is None:
        return None
    from semantic_bridge.crm_text import rich_line   # ZEKI-23: bütün HTML varlıkları (&rsquo;, &Scedil;…) çözülür
    return clean(rich_line(v) or "", limit)


def current_firm(firms: dict[int, str]) -> str:
    if not firms:
        raise SourceError("Logo'da dönem bulunamadı.")
    return firms[max(firms)]


def _chunks(items: list[str], n: int = 400) -> Iterable[list[str]]:
    for i in range(0, len(items), n):
        yield items[i:i + n]


# ------------------------------------------------------------------------------------------ Logo SQL


def items_sql(firm: str) -> str:
    """Bütün malzeme kartları: ad, satış KDV oranı, kart türü, kullanım durumu."""
    f = _f(firm)
    return f"SELECT CODE AS stok, NAME AS ad, SELLVAT AS kdv, CARDTYPE AS kart, ACTIVE AS pasif FROM dbo.LG_{f}_ITEMS"


def sales_sql(firm: str, a: date, b: date, linetypes: list[int]) -> str:
    """Stok kodu × ay: net adet ve net ciro, [a, b). Tanım `budget_sources.sales_sql` ile aynı; satır türü ayardan."""
    f = _f(firm)
    lt = ", ".join(str(int(x)) for x in (linetypes or [0]))
    return f"""
-- Faturalı satış satırları; iade eksi. Net ciro = VATMATRAH.
SELECT I.CODE AS stok, YEAR(SH.DATE_) AS yil, MONTH(SH.DATE_) AS ay,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.VATMATRAH ELSE -S.VATMATRAH END) AS ciro
FROM dbo.LG_{f}_01_STLINE AS S
JOIN dbo.LG_{f}_01_INVOICE AS SH ON SH.LOGICALREF = S.INVOICEREF AND SH.CANCELLED = 0
JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
WHERE S.CANCELLED = 0 AND S.LINETYPE IN ({lt}) AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND SH.DATE_ >= '{a.isoformat()}' AND SH.DATE_ < '{b.isoformat()}'
GROUP BY I.CODE, YEAR(SH.DATE_), MONTH(SH.DATE_)""".strip()


def stock_sql(firm: str) -> str:
    """Stok kodu başına bakiye (tarihsiz, güncel yıl kopyası)."""
    f = _f(firm)
    return f"""
SELECT I.CODE AS stok, SUM(CASE WHEN S.IOCODE IN (1,2) THEN S.AMOUNT ELSE -S.AMOUNT END) AS bakiye
FROM dbo.LG_{f}_01_STLINE AS S
JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
WHERE S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.IOCODE IN (1,2,3,4)
GROUP BY I.CODE""".strip()


def prices_sql(firm: str, today: date) -> str:
    f = _f(firm)
    t = today.isoformat()
    return f"""
SELECT I.CODE AS stok, P.PRICE AS fiyat, P.CODE AS liste, P.PRIORITY AS oncelik, P.INCVAT AS kdv_dahil,
  P.CLSPECODE AS cari_ozel, P.CLIENTCODE AS cari, P.BEGDATE AS bas
FROM dbo.LG_{f}_PRCLIST AS P
JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = P.CARDREF
WHERE P.PTYPE = 2 AND P.ACTIVE = 0 AND P.CURRENCY = 160 AND P.BEGDATE <= '{t}'
  AND (P.ENDDATE >= '{t}' OR P.ENDDATE IS NULL)""".strip()


def bom_sql(firm: str, set_codes: list[str], linetypes: list[int]) -> str:
    """Set kodu → reçete bileşenleri: geçerli revizyonun satırları, ana ürün satırı hariç."""
    f = _f(firm)
    codes = ", ".join(_lit(c) for c in set_codes)
    lt = f" AND L.LINETYPE IN ({', '.join(str(int(x)) for x in linetypes)})" if linetypes else ""
    return f"""
SELECT M.CODE AS set_kodu, C.CODE AS bilesen, SUM(L.AMOUNT) AS adet, MAX(B.CODE) AS recete
FROM dbo.LG_{f}_BOMASTER AS B
JOIN dbo.LG_{f}_ITEMS AS M ON M.LOGICALREF = B.MAINPRODREF
JOIN dbo.LG_{f}_BOMLINE AS L ON L.BOMMASTERREF = B.LOGICALREF AND L.BOMREVREF = B.VALIDREVREF
JOIN dbo.LG_{f}_ITEMS AS C ON C.LOGICALREF = L.ITEMREF
WHERE B.ACTIVE = 0 AND L.ITEMREF <> B.MAINPRODREF AND M.CODE IN ({codes}){lt}
GROUP BY M.CODE, C.CODE""".strip()


def last_cost_sql(firm: str) -> str:
    """Kitabın en son maliyeti girilmiş satış satırı (`OUTCOST <> 0`): «tahmini maliyet» kaynağı."""
    f = _f(firm)
    return f"""
SELECT stok, maliyet, gun FROM (
  SELECT I.CODE AS stok, S.OUTCOST AS maliyet, S.DATE_ AS gun,
    ROW_NUMBER() OVER (PARTITION BY S.STOCKREF ORDER BY S.DATE_ DESC, S.LOGICALREF DESC) AS sira
  FROM dbo.LG_{f}_01_STLINE AS S
  JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
  WHERE S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (7,8,9) AND S.OUTCOST <> 0
) AS x WHERE sira = 1""".strip()


def data_end_sql(firm: str) -> str:
    return bsrc.data_end_sql(_f(firm))


def item_exists_sql(firm: str, code: str) -> str:
    return f"SELECT CODE AS stok, NAME AS ad, CARDTYPE AS kart FROM dbo.LG_{_f(firm)}_ITEMS WHERE CODE = {_lit(code)}"


# ------------------------------------------------------------------------------------------ CRM SQL


def crm_books_sql(schema: str) -> str:
    """Etkin kitap/ürün kartları: tür, liste fiyatı, yazar, dizi, hedef kitle, arka kapak (kısaltılmış)."""
    p = prefix(schema)
    return (
        "SELECT k.new_kitapId AS id, k.new_StokKodu AS stok, k.new_name AS ad, CAST(k.new_Tip AS int) AS tip,"
        " k.new_kdvdahilfiyat AS kdv_dahil_fiyat, k.new_PerakendeBirimFiyat AS perakende, k.new_yazartext AS yazar,"
        " k.new_diziidName AS dizi, k.new_turlertext AS turler, k.new_yaslartext AS yaslar, CAST(k.new_hedefkitle AS int) AS hedef,"
        " k.new_hedefkitleyasbaslangic AS yas_min, k.new_hedefkitleyasbitis AS yas_max,"
        " CAST(k.new_promosyontipi AS int) AS promosyon_tipi, CAST(k.new_ozet AS nvarchar(900)) AS ozet,"
        " CAST(k.new_kitapspotu AS nvarchar(600)) AS spot"
        f" FROM {p}new_kitap k WHERE k.statecode = 0 AND k.new_StokKodu IS NOT NULL"
    )


def crm_sets_sql(schema: str) -> str:
    """CRM set kartları (`new_Tip = 4`) ve bağlı proje kartının set alanları."""
    p = prefix(schema)
    return (
        "SELECT k.new_kitapId AS id, k.new_StokKodu AS stok, k.new_name AS ad, CAST(k.new_SetTipi AS int) AS set_tipi,"
        " k.new_setozellikleri AS ozellik, k.new_setadetmiktari AS set_adet, CAST(k.new_satiskanallari AS int) AS kanal,"
        " k.new_kdvdahilfiyat AS kdv_dahil_fiyat, k.new_PerakendeBirimFiyat AS perakende, k.CreatedOn AS olusturma,"
        " pr.new_setadi AS proje_set_adi, pr.new_SetBarkodu AS proje_set_barkodu, CAST(pr.new_SetTipi AS int) AS proje_set_tipi,"
        " pr.new_setkitapadedi AS proje_kitap_adedi"
        f" FROM {p}new_kitapBase k LEFT JOIN {p}new_projeBase pr ON pr.new_projeId = k.new_projekarti"
        " WHERE k.statecode = 0 AND k.new_Tip = 4"
    )


def crm_set_components_sql(schema: str) -> str:
    """Her set ürünü için en son etkin «Set Yapma» işleminin alt mamul satırları (`new_tip = 2`)."""
    p = prefix(schema)
    return (
        "WITH son AS ("
        " SELECT si.new_setislemiId AS islem, ps.ProductNumber AS set_kodu, si.CreatedOn AS tarih, si.new_adet AS islem_adet,"
        " CAST(si.statuscode AS int) AS durum,"
        " ROW_NUMBER() OVER (PARTITION BY ps.ProductNumber ORDER BY si.CreatedOn DESC) AS sira"
        f" FROM {p}new_setislemiBase si JOIN {p}ProductBase ps ON ps.ProductId = si.new_urunid"
        " WHERE si.statecode = 0 AND si.new_islemtipi = 1 AND ps.ProductNumber IS NOT NULL)"
        " SELECT son.set_kodu, son.tarih, son.islem_adet, son.durum, p.ProductNumber AS bilesen, SUM(sl.new_adet) AS adet"
        f" FROM son JOIN {p}new_setislemisatiriBase sl ON sl.new_setislemiid = son.islem"
        f" JOIN {p}ProductBase p ON p.ProductId = sl.new_urunid"
        " WHERE son.sira = 1 AND sl.new_tip = 2 AND sl.statecode = 0 AND p.ProductNumber IS NOT NULL"
        " GROUP BY son.set_kodu, son.tarih, son.islem_adet, son.durum, p.ProductNumber"
    )


def crm_packaging_sql(schema: str) -> str:
    p = prefix(schema)
    return (
        "SELECT CAST(new_paketlemetipi AS int) AS tip, new_kaclipaket AS kacli, new_paketlemebirimmaliyeti AS birim,"
        f" CreatedOn AS tarih FROM {p}new_paketlemeBase WHERE statecode = 0"
    )


def crm_special_days_sql(schema: str) -> str:
    p = prefix(schema)
    return f"SELECT new_ozelgunlerId AS id, new_name AS ad, new_Tarih AS tarih FROM {p}new_ozelgunlerBase WHERE statecode = 0"


def crm_basket_pairs_sql(schema: str, since: date, types: list[int], name_prefix: str, min_orders: int) -> str:
    """B2C siparişlerinde birlikte alınan stok kodu çiftleri (sıralı çift, a < b) ve sipariş sayısı."""
    p = prefix(schema)
    return f"""
WITH l AS (
  SELECT DISTINCT s.new_siparisId AS sid, pr.ProductNumber AS kod
  FROM {p}new_siparisBase s
  JOIN {p}new_siparissatiriBase ss ON ss.new_siparisid = s.new_siparisId
  JOIN {p}ProductBase pr ON pr.ProductId = ss.new_urunid
  WHERE {_b2c_where(types, name_prefix)} AND s.statuscode NOT IN (1, 100000001)
    AND s.new_siparistarihi >= '{since.isoformat()}' AND pr.ProductNumber IS NOT NULL
    AND ss.statuscode <> 100000001 AND ISNULL(ss.new_promosyon, 0) = 0 AND ISNULL(ss.new_kesinhediye, 0) = 0
    AND ISNULL(ss.new_bedelsiz, 0) = 0
)
SELECT a.kod AS kod_a, b.kod AS kod_b, COUNT(*) AS siparis
FROM l a JOIN l b ON b.sid = a.sid AND a.kod < b.kod
GROUP BY a.kod, b.kod
HAVING COUNT(*) >= {max(1, int(min_orders))}""".strip()


def crm_basket_items_sql(schema: str, since: date, types: list[int], name_prefix: str) -> str:
    """Aynı B2C sipariş kümesinde stok kodu başına sipariş sayısı ve toplam sipariş (birliktelik oranı için)."""
    p = prefix(schema)
    return f"""
WITH l AS (
  SELECT DISTINCT s.new_siparisId AS sid, pr.ProductNumber AS kod
  FROM {p}new_siparisBase s
  JOIN {p}new_siparissatiriBase ss ON ss.new_siparisid = s.new_siparisId
  JOIN {p}ProductBase pr ON pr.ProductId = ss.new_urunid
  WHERE {_b2c_where(types, name_prefix)} AND s.statuscode NOT IN (1, 100000001)
    AND s.new_siparistarihi >= '{since.isoformat()}' AND pr.ProductNumber IS NOT NULL
    AND ss.statuscode <> 100000001 AND ISNULL(ss.new_promosyon, 0) = 0 AND ISNULL(ss.new_kesinhediye, 0) = 0
    AND ISNULL(ss.new_bedelsiz, 0) = 0
)
SELECT kod, COUNT(*) AS siparis, (SELECT COUNT(DISTINCT sid) FROM l) AS toplam FROM l GROUP BY kod""".strip()


def _b2c_where(types: list[int], name_prefix: str) -> str:
    parts = []
    if types:
        parts.append(f"s.new_siparistipi IN ({', '.join(str(int(t)) for t in types)})")
    pre = (name_prefix or "").strip()
    if pre:
        if not re.match(r"^[A-Za-z0-9]{1,8}$", pre):
            raise SourceError("B2C sipariş adı öneki geçersiz.")
        parts.append(f"LEFT(s.new_name, {len(pre)}) = N'{pre}'")
    if not parts:
        raise SourceError("B2C sipariş tanımı boş (tip ya da ad öneki gerekli).")
    return "(" + " OR ".join(parts) + ")"


def crm_account_search_sql(schema: str, q: str, offset: int, size: int) -> str:
    p = prefix(schema)
    t = (q or "").replace("'", "''").replace("%", "[%]").replace("_", "[_]")[:80]
    return (
        "SELECT a.AccountId AS id, a.Name AS unvan, a.new_CariKodu AS kod, COUNT(*) OVER () AS toplam"
        f" FROM {p}AccountBase a WHERE a.StateCode = 0 AND (a.Name LIKE N'%{t}%' OR a.new_CariKodu LIKE N'{t}%')"
        f" ORDER BY a.Name OFFSET {max(0, int(offset))} ROWS FETCH NEXT {max(1, int(size))} ROWS ONLY"
    )


def crm_account_sql(schema: str, account_id: str) -> str:
    if not _GUID.match(account_id or ""):
        raise SourceError("Firma kimliği geçersiz.")
    p = prefix(schema)
    return (f"SELECT a.AccountId AS id, a.Name AS unvan, a.new_CariKodu AS kod FROM {p}AccountBase a"
            f" WHERE a.AccountId = '{account_id}'")


def crm_gift_history_sql(schema: str, account_id: str) -> str:
    """Firmaya geçmiş hediye talepleri: yalnız talep no, tutar, tarih, durum (kişi bilgisi seçilmez — KVKK)."""
    if not _GUID.match(account_id or ""):
        raise SourceError("Firma kimliği geçersiz.")
    p = prefix(schema)
    return (
        "SELECT h.new_name AS no, h.new_hediyetutari AS hediye_tutari, h.new_toplamtutar AS toplam, h.new_gonderitarihi AS gonderi,"
        " h.CreatedOn AS tarih, CAST(h.statuscode AS int) AS durum"
        f" FROM {p}new_hediyetalebiBase h WHERE h.new_hediyeverilecekfirma = '{account_id}' ORDER BY h.CreatedOn DESC"
    )


def crm_card_sql(schema: str, code: str) -> str:
    p = prefix(schema)
    return (f"SELECT k.new_kitapId AS id, k.new_name AS ad, CAST(k.new_Tip AS int) AS tip, k.new_kdvdahilfiyat AS kdv_dahil_fiyat"
            f" FROM {p}new_kitapBase k WHERE k.statecode = 0 AND k.new_StokKodu = {_lit(code)}")


# ------------------------------------------------------------------------------------------ okuma


def read_data_end(run: Runner, firms: dict[int, str]) -> Optional[date]:
    rows = run(data_end_sql(current_firm(firms)))
    return day(rows[0].get("son")) if rows else None


def read_items(run: Runner, firms: dict[int, str]) -> dict[str, dict[str, Any]]:
    out = {}
    for r in run(items_sql(current_firm(firms))):
        code = clean(r.get("stok"), 60)
        if code:
            out[code] = {"ad": clean(r.get("ad")), "kdv": num(r.get("kdv")), "kart": int(r["kart"]) if r.get("kart") is not None else None,
                         "pasif": bool(r.get("pasif"))}
    return out


def read_sales(run: Runner, firms: dict[int, str], year: int, linetypes: list[int]) -> list[dict[str, Any]]:
    """Bir takvim yılının stok kodu × ay satışı (yılın firmasından)."""
    firm = firms.get(year)
    if not firm:
        raise SourceError(f"Logo'da {year} yılının dönemi yok.")
    out = []
    for r in run(sales_sql(firm, date(year, 1, 1), date(year + 1, 1, 1), linetypes)):
        code = clean(r.get("stok"), 60)
        if code:
            out.append({"stok": code, "yil": int(r["yil"]), "ay": int(r["ay"]), "adet": num(r.get("adet")) or 0.0,
                        "ciro": num(r.get("ciro")) or 0.0})
    return out


def read_stock(run: Runner, firms: dict[int, str]) -> dict[str, float]:
    return {str(r["stok"]).strip(): num(r.get("bakiye")) or 0.0 for r in run(stock_sql(current_firm(firms))) if r.get("stok")}


def pick_price(rows: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    ok = [r for r in rows if (num(r.get("fiyat")) or 0) > 0]
    if not ok:
        return None

    def key(r: dict[str, Any]) -> tuple:
        general = 0 if not (clean(r.get("cari")) or clean(r.get("cari_ozel"))) else 1
        beg = day(r.get("bas")) or date(1900, 1, 1)
        return (general, int(num(r.get("oncelik")) or 0), -beg.toordinal())

    best = sorted(ok, key=key)[0]
    return {"fiyat": float(num(best["fiyat"])), "liste": clean(best.get("liste"), 40), "kdvDahil": bool(best.get("kdv_dahil"))}


def read_prices(run: Runner, firms: dict[int, str], today: date) -> dict[str, dict[str, Any]]:
    by: dict[str, list[dict[str, Any]]] = {}
    for r in run(prices_sql(current_firm(firms), today)):
        if r.get("stok"):
            by.setdefault(str(r["stok"]).strip(), []).append(r)
    return {c: p for c, p in ((c, pick_price(rows)) for c, rows in by.items()) if p}


def read_bom(run: Runner, firms: dict[int, str], set_codes: list[str], linetypes: list[int]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    codes = [c for c in dict.fromkeys(set_codes) if code_ok(c)]
    for part in _chunks(codes):
        for r in run(bom_sql(current_firm(firms), part, linetypes)):
            s, c = clean(r.get("set_kodu"), 60), clean(r.get("bilesen"), 60)
            if s and c:
                out.setdefault(s, []).append({"stok": c, "adet": num(r.get("adet")) or 0.0, "recete": clean(r.get("recete"), 60)})
    return out


def read_last_costs(run: Runner, firms: dict[int, str]) -> dict[str, dict[str, Any]]:
    out = {}
    for r in run(last_cost_sql(current_firm(firms))):
        code = str(r.get("stok") or "").strip()
        c = num(r.get("maliyet"))
        if code and c and c > 0:
            d = day(r.get("gun"))
            out[code] = {"birim": c, "tarih": d.isoformat() if d else None}
    return out


def read_item(run: Runner, firms: dict[int, str], code: str) -> Optional[dict[str, Any]]:
    rows = run(item_exists_sql(current_firm(firms), code))
    return {"ad": clean(rows[0].get("ad")), "kart": rows[0].get("kart")} if rows else None


def read_crm_books(run: Runner, schema: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in run(crm_books_sql(schema)):
        code = clean(r.get("stok"), 60)
        if not code:
            continue
        ymin, ymax = num(r.get("yas_min")), num(r.get("yas_max"))
        out[code] = {"id": str(r.get("id") or "").lower() or None, "ad": clean(r.get("ad")), "tip": r.get("tip"),
                     "fiyat": num(r.get("kdv_dahil_fiyat")) or num(r.get("perakende")),
                     "yazar": clean(r.get("yazar"), 300), "dizi": clean(r.get("dizi"), 200), "turler": clean(r.get("turler"), 400),
                     "yaslar": clean(r.get("yaslar"), 200), "hedef": {1: "Çocuk", 2: "Genç", 3: "Yetişkin"}.get(r.get("hedef")),
                     "yasMin": int(ymin) if ymin else None, "yasMax": int(ymax) if ymax else None,
                     "promosyonTipi": CRM_PROMOSYON_TIPI.get(r.get("promosyon_tipi")),
                     "ozet": strip_html(r.get("ozet"), 900), "spot": strip_html(r.get("spot"), 600)}
    return out


def read_crm_sets(run: Runner, schema: str) -> list[dict[str, Any]]:
    out = []
    for r in run(crm_sets_sql(schema)):
        code = clean(r.get("stok"), 60)
        out.append({"id": str(r.get("id") or "").lower(), "stok": code, "ad": clean(r.get("ad")) or clean(r.get("proje_set_adi")),
                    "setTipi": CRM_SET_TIPI.get(r.get("set_tipi")), "ozellik": clean(r.get("ozellik"), 400),
                    "setAdet": num(r.get("set_adet")), "kanal": CRM_SATIS_KANALI.get(r.get("kanal")),
                    "fiyat": num(r.get("kdv_dahil_fiyat")) or num(r.get("perakende")),
                    "olusturma": (day(r.get("olusturma")) or None),
                    "projeSetAdi": clean(r.get("proje_set_adi")), "projeSetBarkodu": clean(r.get("proje_set_barkodu"), 60),
                    "projeKitapAdedi": num(r.get("proje_kitap_adedi"))})
    return out


def read_crm_components(run: Runner, schema: str) -> dict[str, dict[str, Any]]:
    """Set kodu → {tarih, islemAdet, durum, bilesenler: [{stok, adet}]}."""
    out: dict[str, dict[str, Any]] = {}
    for r in run(crm_set_components_sql(schema)):
        s, c = clean(r.get("set_kodu"), 60), clean(r.get("bilesen"), 60)
        if not s or not c:
            continue
        d = day(r.get("tarih"))
        cur = out.setdefault(s, {"tarih": d.isoformat() if d else None, "islemAdet": num(r.get("islem_adet")),
                                 "durum": r.get("durum"), "bilesenler": []})
        cur["bilesenler"].append({"stok": c, "adet": num(r.get("adet")) or 0.0})
    return out


def read_crm_packaging(run: Runner, schema: str) -> list[dict[str, Any]]:
    """Paketleme türü başına son girilen birim maliyet ve kayıt sayısı."""
    by: dict[int, dict[str, Any]] = {}
    for r in run(crm_packaging_sql(schema)):
        t = r.get("tip")
        if t is None or int(t) not in PAKETLEME:
            continue
        t = int(t)
        d = day(r.get("tarih"))
        cur = by.setdefault(t, {"tur": PAKETLEME[t], "kod": t, "birim": None, "tarih": None, "kayit": 0})
        cur["kayit"] += 1
        b = num(r.get("birim"))
        if b and b > 0 and (cur["tarih"] is None or (d and d.isoformat() > cur["tarih"])):
            cur["birim"], cur["tarih"] = b, d.isoformat() if d else None
    return [by.get(k) or {"tur": v, "kod": k, "birim": None, "tarih": None, "kayit": 0} for k, v in PAKETLEME.items()]


def read_crm_special_days(run: Runner, schema: str) -> list[dict[str, Any]]:
    out = []
    for r in run(crm_special_days_sql(schema)):
        d = day(r.get("tarih"))
        name = clean(r.get("ad"), 200)
        if name:
            out.append({"id": str(r.get("id") or "").lower(), "ad": name, "tarih": d.isoformat() if d else None})
    return sorted(out, key=lambda x: (x["tarih"] or "9999", x["ad"]))


def read_basket(run: Runner, schema: str, since: date, types: list[int], name_prefix: str,
                min_orders: int) -> tuple[list[dict[str, Any]], dict[str, int], int]:
    pairs = []
    for r in run(crm_basket_pairs_sql(schema, since, types, name_prefix, min_orders)):
        a, b = clean(r.get("kod_a"), 60), clean(r.get("kod_b"), 60)
        if a and b:
            pairs.append({"a": a, "b": b, "n": int(r.get("siparis") or 0)})
    counts: dict[str, int] = {}
    total = 0
    for r in run(crm_basket_items_sql(schema, since, types, name_prefix)):
        k = clean(r.get("kod"), 60)
        if k:
            counts[k] = int(r.get("siparis") or 0)
        total = int(r.get("toplam") or total)
    return pairs, counts, total


def search_accounts(run: Runner, schema: str, q: str, page: int, size: int) -> dict[str, Any]:
    rows = run(crm_account_search_sql(schema, q, page * size, size))
    total = int(rows[0].get("toplam") or 0) if rows else 0
    return {"items": [{"id": str(r.get("id") or "").lower(), "unvan": clean(r.get("unvan")), "kod": clean(r.get("kod"), 40)} for r in rows],
            "total": total, "page": page, "pageSize": size}


def read_account(run: Runner, schema: str, account_id: str) -> Optional[dict[str, Any]]:
    rows = run(crm_account_sql(schema, account_id))
    if not rows:
        return None
    r = rows[0]
    return {"id": str(r.get("id") or "").lower(), "unvan": clean(r.get("unvan")), "kod": clean(r.get("kod"), 40)}


def read_gift_history(run: Runner, schema: str, account_id: str) -> list[dict[str, Any]]:
    out = []
    for r in run(crm_gift_history_sql(schema, account_id)):
        d = day(r.get("gonderi")) or day(r.get("tarih"))
        out.append({"no": clean(r.get("no"), 60), "hediyeTutari": num(r.get("hediye_tutari")), "toplam": num(r.get("toplam")),
                    "tarih": d.isoformat() if d else None, "durum": HEDIYE_TALEP_DURUM.get(r.get("durum"), "—")})
    return out


def read_card(run: Runner, schema: str, code: str) -> Optional[dict[str, Any]]:
    rows = run(crm_card_sql(schema, code))
    if not rows:
        return None
    r = rows[0]
    return {"id": str(r.get("id") or "").lower(), "ad": clean(r.get("ad")), "tip": r.get("tip"),
            "tipAdi": CRM_TIP.get(r.get("tip")), "fiyat": num(r.get("kdv_dahil_fiyat"))}


# ------------------------------------------------------------------------------------------ birim maliyet

#: M9 bağlandığında: fn(stok_kodlari) → {stok: {"birim": float, "tarih": "YYYY-MM-DD" | None}} (KDV hariç birim maliyet).
_COST_PROVIDER: Optional[Callable[[list[str]], dict[str, dict[str, Any]]]] = None

COST_SOURCES = {"m9": "Birim maliyet (M9)", "logo": "Logo son maliyetli satış satırı (tahmini)", "yok": "Maliyet kullanılmaz"}


def register_cost_provider(fn: Optional[Callable[[list[str]], dict[str, dict[str, Any]]]]) -> None:
    """M9 kendi modülü yüklenirken çağırır. None bağı kaldırır."""
    global _COST_PROVIDER
    _COST_PROVIDER = fn


def cost_provider_ready() -> bool:
    return _COST_PROVIDER is not None


def unit_costs(codes: Iterable[str], source: str, logo_costs: Optional[dict[str, dict[str, Any]]] = None) -> dict[str, dict[str, Any]]:
    """Stok kodu → {"birim": float | None, "kaynak": str, "tarih": str | None, "tahmini": bool}. Bilinmeyen maliyet None'dır;
    hiçbir yolda varsayılan maliyet üretilmez."""
    codes = [c for c in dict.fromkeys(codes) if c]
    out = {c: {"birim": None, "kaynak": "bilinmiyor", "tarih": None, "tahmini": False} for c in codes}
    src = (source or "m9").strip().lower()
    if src == "m9":
        if _COST_PROVIDER is None:
            return out
        try:
            got = _COST_PROVIDER(codes) or {}
        except Exception as e:  # noqa: BLE001 — maliyet okunamazsa bilinmiyor
            log.warning("sets: M9 maliyeti okunamadı: %s", e)
            return out
        for c in codes:
            v = got.get(c) or {}
            b = num(v.get("birim"))
            if b is not None and b > 0:
                out[c] = {"birim": b, "kaynak": "m9", "tarih": v.get("tarih"), "tahmini": False}
        return out
    if src == "logo":
        for c in codes:
            v = (logo_costs or {}).get(c)
            if v and v.get("birim"):
                out[c] = {"birim": float(v["birim"]), "kaynak": "logo", "tarih": v.get("tarih"), "tahmini": True}
    return out
