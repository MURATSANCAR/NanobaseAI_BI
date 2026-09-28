"""M35 E-ticaret kampanya yönetimi: Logo ve CRM okumaları (yalnız okuma) ve köprünün kendi tablolarından besleme.

Tanımlar mevcut ölçülerle aynıdır (`budget_sources` başındaki ölçüm, 2026-09-28):

- **Satış satırı** = `STLINE`, `CANCELLED = 0`, `LINETYPE = 0` (malzeme satırı), `INVOICEREF <> 0` (faturalı), `TRCODE 7/8/9`
  satış, `2/3` iade. Net tutar = Σ `LINENET` (iade eksi), net adet = Σ `AMOUNT` (iade eksi).
- **Logo brüt farkı (mevcut marj)** güncel yıl kopyasında kitap başına: Σ `LINENET` − Σ `AMOUNT × OUTCOST`, yalnız satış
  satırları (kabul testi 1 ile birebir). Maliyeti girilmemiş satır (`OUTCOST = 0`) sayısı ayrıca tutulur (kabul testi 2);
  marj oranı yalnız maliyetli satırlardan hesaplanır, maliyetsiz satır varsa ekranda yazılır.
- **Satış hızı** son `KAMPANYA_ADAY_HIZ_AY` tam ay (veri sonu ayı hariç değil: veri sonunun bulunduğu ay dahil, `Yıl*12+Ay`
  penceresi) ve ondan önceki eşit pencere. Satış görünümleri (`V_SatisRaporu_*`) kullanılmaz: satır tanımı kokpit ve bütçeyle
  aynı olsun diye doğrudan `STLINE` okunur; yıl birleştirmesinde kopya yıl kolon kaydırmasın diye her yıl kendi firmasından
  ayrı sorguyla okunur (`SELECT *` birleşimi yok).
- **Stok bakiyesi** güncel yıl kopyasından, tarihsiz: `IOCODE 1/2` giriş, `3/4` çıkış (M32/M53 ile aynı).
- **Logo liste fiyatı** `PRCLIST`: satış listesi `PTYPE = 2`, `ACTIVE = 0`, TL, bugün geçerli; birden çok liste varsa cariye
  bağlı olmayan, sonra küçük öncelik, sonra en yeni başlangıç.
- Kod listesi sorguya `JOIN (VALUES …)` ile girer (uzun `IN` listesi planı bozar — bellek: logo-sales-view-plan-traps).

Yıllar Logo'da ayrı firma numarasıdır (411 = 2026, 211 = 2021–2025); eşleme `L_CAPIPERIOD`'dan (`budget_sources.firms_by_year`).
CRM (`Timas_MSCRM`, .28) yalnız okunur: kitap kartı, Telif Alış sözleşmesinin asgari fiyatı ve telif hesap tipi, bayi
kampanyaları ve kampanya kodlu sipariş satırları. **CRM'e, Logo'ya ve T-soft'a hiçbir şey yazılmaz.**

**M34 bağlantı noktası:** e-ticaret platform modülü (M34) ürün aktifliği ve stok farkını kendi tablosunda tutacak. M34 hazır
olunca `register_platform_items(fn)` ile bağlanır; `fn(stok_kodlari) → {kod: {"aktif": bool, "stok": float|None}}`. Bağlı
değilken aktiflik bilgisi yoktur, stok Logo'dan okunur (analiz §14 «Bağımlılık»).
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional

from semantic_bridge import budget_sources as bsrc

log = logging.getLogger("semantic.kampanya.sources")

SourceError = bsrc.SourceError
Runner = bsrc.Runner
runner = bsrc.runner
firms_by_year = bsrc.firms_by_year

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FIRM = re.compile(r"^[0-9]{3}$")
_CODE = re.compile(r"^[^'\x00-\x1f]{1,60}$")
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

#: CRM `new_sozlesmeBase` seçim listeleri (tablo açıklaması 2026-09-09 ve M6 `contracts_terms`).
TELIF_ALIS = 5
YURURLUKTE = (100000000, 100000006, 100000007)
HESAPLAMA_TIPI = {1: "Toptan satış fiyatı", 2: "Perakende fiyatı", 3: "Perakende oranlı"}
TELIF_TURU = {1: "Brüt (kapak fiyatı)", 2: "Net", 3: "Değişken net/brüt"}
TELIF_ODEME = {3: "Tek ödeme", 1: "Baskıdan", 2: "Satıştan", 7: "Satıştan kademeli", 4: "Baskıdan kademeli", 5: "Baskı + satış",
               8: "Diğer"}
#: Satıştan hesaplanan telif (indirim telife yansıyabilir). Baskıdan ve tek ödemede satış fiyatı telifi değiştirmez.
SATIS_TELIF = (2, 7, 5)
#: CRM bayi kampanyası seçimleri (`new_kampanyaBase`).
KAMPANYA_MECRA = {1: "CRM", 2: "B2B", 3: "CRM & B2B"}
KAMPANYA_TIP = {1: "Kampanya", 2: "Anlaşma"}

_platform_items: Optional[Callable[[list[str]], dict[str, dict[str, Any]]]] = None


def register_platform_items(fn: Optional[Callable[[list[str]], dict[str, dict[str, Any]]]]) -> None:
    """M34 bağlantı noktası: ürün aktifliği ve platform stoğu. `None` bağı kaldırır."""
    global _platform_items
    _platform_items = fn


def platform_items(codes: list[str]) -> dict[str, dict[str, Any]]:
    if _platform_items is None or not codes:
        return {}
    try:
        return _platform_items(codes) or {}
    except Exception as e:  # noqa: BLE001 — M34 okunamazsa Logo'ya düşülür
        log.warning("kampanya: platform ürün bilgisi okunamadı: %s", e)
        return {}


def platform_connected() -> bool:
    return _platform_items is not None


# ------------------------------------------------------------------------------------------ yardımcılar


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


def code_ok(code: Any) -> bool:
    return bool(_CODE.match(str(code or "")))


def guid_ok(v: Any) -> bool:
    return bool(_GUID.match(str(v or "")))


def _lit(code: str) -> str:
    if not code_ok(code):
        raise SourceError(f"Kod «{code}» geçersiz.")
    return "N'" + str(code).replace("'", "''") + "'"


def values(codes: Iterable[str]) -> str:
    """`JOIN (VALUES …) AS K(kod)` gövdesi; boş liste sorgu kurmaz."""
    lits = [f"({_lit(c)})" for c in dict.fromkeys(codes)]
    if not lits:
        raise SourceError("Kod listesi boş.")
    return ", ".join(lits)


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


def iso_day(v: Any) -> Optional[str]:
    d = day(v)
    return d.isoformat() if d else None


def num(v: Any) -> Optional[float]:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def money_text(v: Any) -> Optional[float]:
    """CRM'de metin tutulan tutar («45», «45,50», «1.250,00 TL») → sayı; okunamazsa None."""
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v) if v == v else None
    s = re.sub(r"[^0-9,.\-]", "", str(v))
    if not s or not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        n = float(s)
    except ValueError:
        return None
    return n if n > 0 else None


def clean(v: Any, limit: int = 400) -> Optional[str]:
    if v is None:
        return None
    s = re.sub(r"\s+", " ", str(v)).strip()
    return s[:limit] or None


def ean_of(v: Any) -> Optional[str]:
    s = re.sub(r"[^0-9]", "", str(v or ""))
    return s[:20] if len(s) >= 8 else None


def current_firm(firms: dict[int, str]) -> str:
    if not firms:
        raise SourceError("Logo'da dönem bulunamadı.")
    return firms[max(firms)]


def year_spans(firms: dict[int, str], a: date, b: date) -> list[tuple[str, date, date]]:
    """[a, b) aralığını yıllara böler: (firma, başlangıç, bitiş hariç). Dönemi olmayan yıl atlanır."""
    out = []
    for y in range(a.year, b.year + 1):
        firm = firms.get(y)
        lo, hi = max(a, date(y, 1, 1)), min(b, date(y + 1, 1, 1))
        if firm and lo < hi:
            out.append((firm, lo, hi))
    return out


# ------------------------------------------------------------------------------------------ Logo SQL


def items_sql(firm: str) -> str:
    f = _f(firm)
    return f"SELECT CODE AS stok, NAME AS ad, SELLVAT AS kdv, ACTIVE AS pasif FROM dbo.LG_{f}_ITEMS"


def stock_sql(firm: str) -> str:
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
SELECT I.CODE AS stok, P.PRICE AS fiyat, P.PRIORITY AS oncelik, P.INCVAT AS kdv_dahil, P.CLIENTCODE AS cari,
  P.CLSPECODE AS cari_ozel, P.BEGDATE AS bas
FROM dbo.LG_{f}_PRCLIST AS P
JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = P.CARDREF
WHERE P.PTYPE = 2 AND P.ACTIVE = 0 AND P.CURRENCY = 160 AND P.BEGDATE <= '{t}'
  AND (P.ENDDATE >= '{t}' OR P.ENDDATE IS NULL)""".strip()


def monthly_sql(firm: str, a: date, b: date) -> str:
    """Stok kodu × ay: satış adedi, iade adedi, net tutar (iade eksi), [a, b)."""
    f = _f(firm)
    return f"""
SELECT I.CODE AS stok, YEAR(S.DATE_) AS yil, MONTH(S.DATE_) AS ay,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE 0 END) AS satis_adet,
  SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.AMOUNT ELSE 0 END) AS iade_adet,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS net_tutar
FROM dbo.LG_{f}_01_STLINE AS S
JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{a.isoformat()}' AND S.DATE_ < '{b.isoformat()}'
GROUP BY I.CODE, YEAR(S.DATE_), MONTH(S.DATE_)""".strip()


def margin_sql(firm: str, a: date, b: date) -> str:
    """Kitap başına Logo brüt farkı (satış satırları): ciro, maliyet, maliyetli ciro/adet, maliyetsiz satır sayısı."""
    f = _f(firm)
    return f"""
SELECT I.CODE AS stok,
  SUM(S.LINENET) AS ciro,
  SUM(S.AMOUNT * S.OUTCOST) AS maliyet,
  SUM(CASE WHEN S.OUTCOST <> 0 THEN S.LINENET ELSE 0 END) AS maliyetli_ciro,
  SUM(CASE WHEN S.OUTCOST <> 0 THEN S.AMOUNT ELSE 0 END) AS maliyetli_adet,
  SUM(S.AMOUNT) AS adet,
  SUM(CASE WHEN S.OUTCOST = 0 THEN 1 ELSE 0 END) AS maliyetsiz_satir,
  COUNT(*) AS satir
FROM dbo.LG_{f}_01_STLINE AS S
JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (7,8,9)
  AND S.DATE_ >= '{a.isoformat()}' AND S.DATE_ < '{b.isoformat()}'
GROUP BY I.CODE""".strip()


def daily_sql(firm: str, codes: list[str], a: date, b: date, cari: Optional[list[str]] = None) -> str:
    """Kampanya kitapları × gün: satış adedi, iade adedi, net tutar, maliyet (maliyetli satırlar) ve maliyetli net tutar.
    `cari` verilirse yalnız o cari kodlarının faturaları (kanal ayrımı; `KAMPANYA_KANAL_CARI`)."""
    f = _f(firm)
    cari_join = ""
    if cari:
        cari_join = (f"\nJOIN dbo.LG_{f}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF"
                     f"\nJOIN (VALUES {values(cari)}) AS CK(kod) ON CK.kod = C.CODE")
    return f"""
SELECT K.kod AS stok, CAST(S.DATE_ AS date) AS gun,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE 0 END) AS adet,
  SUM(CASE WHEN S.TRCODE IN (2,3) THEN S.AMOUNT ELSE 0 END) AS iade_adet,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS net_tutar,
  SUM(CASE WHEN S.OUTCOST <> 0 THEN (CASE WHEN S.TRCODE IN (7,8,9) THEN 1 ELSE -1 END) * S.AMOUNT * S.OUTCOST ELSE 0 END) AS maliyet,
  SUM(CASE WHEN S.OUTCOST <> 0 THEN (CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) ELSE 0 END) AS maliyetli_tutar
FROM dbo.LG_{f}_01_STLINE AS S
JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
JOIN (VALUES {values(codes)}) AS K(kod) ON K.kod = I.CODE{cari_join}
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '{a.isoformat()}' AND S.DATE_ < '{b.isoformat()}'
GROUP BY K.kod, CAST(S.DATE_ AS date)""".strip()


# ------------------------------------------------------------------------------------------ CRM SQL


def crm_books_sql(schema: str) -> str:
    """Etkin kitap kartları (stok kodlu): ad, barkod, KDV dahil fiyat, yazar, yayıncılık statüsü, T-soft'ta aktif mi."""
    p = prefix(schema)
    return (
        "SELECT k.new_kitapId AS id, k.new_StokKodu AS stok, k.new_name AS ad, k.new_ean13 AS ean,"
        " k.new_kdvdahilfiyat AS fiyat, k.new_yazartext AS yazar, CAST(k.new_Tip AS int) AS tip,"
        " k.new_kitap_yayincilikstatusu AS yayin, CAST(ISNULL(k.new_tsoftaktif, 0) AS int) AS tsoft"
        f" FROM {p}new_kitapBase k WHERE k.statecode = 0 AND k.new_StokKodu IS NOT NULL"
    )


def crm_contracts_sql(schema: str) -> str:
    """Kitap ↔ yürürlükteki Telif Alış sözleşmesi: asgari perakende fiyat (metin), hesaplama tipi, telif türü ve ödeme şekli,
    karton telif oranı. Kişi bilgisi seçilmez."""
    p = prefix(schema)
    codes = ", ".join(str(c) for c in YURURLUKTE)
    return (
        "SELECT k.new_StokKodu AS stok, s.new_sozlesmeId AS sozlesme, s.new_name AS ad,"
        " s.new_MinimumPerakendeSatFiyat AS asgari, CAST(s.new_HesaplamaTipi AS int) AS hesaplama,"
        " CAST(s.new_telifturu AS int) AS tur, CAST(s.new_TelifTipi AS int) AS odeme, s.new_Telif AS oran"
        f" FROM {p}new_new_sozlesme_new_kitapBase sk"
        f" JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = sk.new_sozlesmeid"
        f" JOIN {p}new_kitapBase k ON k.new_kitapId = sk.new_kitapid"
        f" WHERE s.statecode = 0 AND s.new_SozlesmeTipi = {TELIF_ALIS} AND s.statuscode IN ({codes})"
        " AND k.statecode = 0 AND k.new_StokKodu IS NOT NULL"
    )


def crm_campaigns_sql(schema: str, page: int, size: int, only_active: bool) -> str:
    """CRM bayi kampanyaları (salt okunur), en yeni başlangıç önce; sayfalı."""
    p = prefix(schema)
    where = "WHERE k.statecode = 0" if only_active else ""
    return (
        "SELECT k.new_kampanyaId AS id, k.new_name AS ad, k.new_baslangictarihi AS bas, k.new_bitistarihi AS bit,"
        " CAST(k.new_kampanyamecra AS int) AS mecra, CAST(k.new_tip AS int) AS tip, k.new_ekiskonto AS ek_iskonto,"
        " k.new_netiskonto AS net_iskonto, k.new_minimumalisverissarti AS asgari_tutar,"
        " k.new_minimumalisverisadedi AS asgari_adet, k.new_opsiyonelhediyeadedi AS hediye_adet,"
        " CASE WHEN k.new_netvade IS NULL THEN 0 ELSE 1 END AS vadeli,"
        " CAST(ISNULL(k.new_butunkullanicilarauygulayabilir, 0) AS int) AS herkes,"
        " LEFT(CAST(k.new_aciklama AS nvarchar(max)), 600) AS aciklama, CAST(k.statecode AS int) AS durum"
        f" FROM {p}new_kampanyaBase k {where}"
        f" ORDER BY k.new_baslangictarihi DESC, k.new_name OFFSET {max(0, int(page)) * int(size)} ROWS"
        f" FETCH NEXT {int(size)} ROWS ONLY"
    )


def crm_campaigns_count_sql(schema: str, only_active: bool) -> str:
    p = prefix(schema)
    where = " WHERE statecode = 0" if only_active else ""
    return f"SELECT COUNT(*) AS n FROM {p}new_kampanyaBase{where}"


def crm_campaign_effect_sql(schema: str, ids: list[str]) -> str:
    """Kampanyaya bağlı sipariş satırları: satır, sipariş, adet, kampanya indirim tutarı, indirimli toplam."""
    p = prefix(schema)
    ok = [i for i in ids if guid_ok(i)]
    if not ok:
        raise SourceError("Kampanya kimliği yok.")
    inlist = ", ".join(f"'{i}'" for i in ok)
    return (
        "SELECT ss.new_kampanyaid AS id, COUNT(*) AS satir, COUNT(DISTINCT ss.new_siparisid) AS siparis,"
        " SUM(ss.new_adet) AS adet, SUM(ss.new_kampanyaindirimtutari) AS indirim,"
        " SUM(ss.new_indirimlitoplamtutar) AS tutar"
        f" FROM {p}new_siparissatiriBase ss WHERE ss.new_kampanyaid IN ({inlist}) GROUP BY ss.new_kampanyaid"
    )


def crm_code_effect_sql(schema: str) -> str:
    """Kampanya kodlu sipariş satırları, koda göre (kabul testi 5 ile aynı süzgeç)."""
    p = prefix(schema)
    return (
        "SELECT ss.new_kampanyakodu AS kod, COUNT(*) AS satir, SUM(ss.new_kampanyaindirimtutari) AS indirim,"
        " SUM(ss.new_adet) AS adet"
        f" FROM {p}new_siparissatiriBase ss WHERE ss.new_kampanyakodu IS NOT NULL AND ss.new_kampanyakodu <> ''"
        " GROUP BY ss.new_kampanyakodu"
    )


# ------------------------------------------------------------------------------------------ okuyucular


def read_items(run: Runner, firms: dict[int, str]) -> dict[str, dict[str, Any]]:
    out = {}
    for r in run(items_sql(current_firm(firms))):
        code = clean(r.get("stok"), 60)
        if code:
            out[code] = {"ad": clean(r.get("ad"), 400), "kdv": num(r.get("kdv")) or 0.0, "pasif": bool(r.get("pasif"))}
    return out


def read_stock(run: Runner, firms: dict[int, str]) -> dict[str, float]:
    return {clean(r["stok"], 60): num(r.get("bakiye")) or 0.0 for r in run(stock_sql(current_firm(firms))) if clean(r.get("stok"), 60)}


def read_prices(run: Runner, firms: dict[int, str], today: date) -> dict[str, dict[str, Any]]:
    """Kitap başına tek fiyat: cariye bağlı olmayan liste önce, sonra küçük öncelik, sonra en yeni başlangıç."""
    best: dict[str, tuple[tuple, dict[str, Any]]] = {}
    for r in run(prices_sql(current_firm(firms), today)):
        code = clean(r.get("stok"), 60)
        price = num(r.get("fiyat"))
        if not code or not price or price <= 0:
            continue
        generic = not (clean(r.get("cari"), 60) or clean(r.get("cari_ozel"), 60))
        bas = day(r.get("bas")) or date(1950, 1, 1)
        key = (0 if generic else 1, int(num(r.get("oncelik")) or 0), -bas.toordinal())
        if code not in best or key < best[code][0]:
            best[code] = (key, {"fiyat": price, "kdvDahil": bool(r.get("kdv_dahil"))})
    return {k: v for k, (_, v) in best.items()}


def read_data_end(run: Runner, firms: dict[int, str]) -> Optional[date]:
    rows = run(bsrc.data_end_sql(current_firm(firms)))
    return day(rows[0].get("son")) if rows and rows[0] else None


def read_monthly(run: Runner, firms: dict[int, str], a: date, b: date) -> list[dict[str, Any]]:
    out = []
    for firm, lo, hi in year_spans(firms, a, b):
        for r in run(monthly_sql(firm, lo, hi)):
            code = clean(r.get("stok"), 60)
            if code:
                out.append({"stok": code, "yil": int(r["yil"]), "ay": int(r["ay"]), "adet": num(r.get("satis_adet")) or 0.0,
                            "iade": num(r.get("iade_adet")) or 0.0, "tutar": num(r.get("net_tutar")) or 0.0})
    return out


def read_margins(run: Runner, firms: dict[int, str], year: int, end: date) -> dict[str, dict[str, float]]:
    firm = firms.get(year)
    if not firm:
        return {}
    out = {}
    for r in run(margin_sql(firm, date(year, 1, 1), min(end + timedelta(days=1), date(year + 1, 1, 1)))):
        code = clean(r.get("stok"), 60)
        if code:
            out[code] = {k: num(r.get(k)) or 0.0 for k in ("ciro", "maliyet", "maliyetli_ciro", "maliyetli_adet", "adet",
                                                            "maliyetsiz_satir", "satir")}
    return out


def read_daily(run: Runner, firms: dict[int, str], codes: list[str], a: date, b: date,
               cari: Optional[list[str]] = None) -> list[dict[str, Any]]:
    """Kampanya kitaplarının günlük satışı; kod listesi 400'lük parçalarla."""
    out = []
    codes = [c for c in dict.fromkeys(codes) if code_ok(c)]
    for i in range(0, len(codes), 400):
        part = codes[i:i + 400]
        for firm, lo, hi in year_spans(firms, a, b):
            for r in run(daily_sql(firm, part, lo, hi, cari)):
                g = day(r.get("gun"))
                if g:
                    out.append({"stok": clean(r.get("stok"), 60), "gun": g, "adet": num(r.get("adet")) or 0.0,
                                "iade": num(r.get("iade_adet")) or 0.0, "tutar": num(r.get("net_tutar")) or 0.0,
                                "maliyet": num(r.get("maliyet")) or 0.0, "maliyetliTutar": num(r.get("maliyetli_tutar")) or 0.0})
    return out


def read_crm_books(run: Runner, schema: str) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for r in run(crm_books_sql(schema)):
        code = clean(r.get("stok"), 60)
        if not code:
            continue
        cur = out.get(code)
        row = {"id": str(r.get("id") or ""), "ad": clean(r.get("ad"), 400), "ean": ean_of(r.get("ean")), "fiyat": num(r.get("fiyat")),
               "yazar": clean(r.get("yazar"), 300), "tip": int(r["tip"]) if r.get("tip") is not None else None,
               "yayin": clean(r.get("yayin"), 60), "tsoft": bool(r.get("tsoft"))}
        # Aynı stok kodu iki kartta olabilir (kitap + e-kitap değil; eski kart): kitap türü ve fiyatı dolu olan kalır.
        if cur is None or (cur.get("tip") != 1 and row["tip"] == 1) or (not cur.get("fiyat") and row["fiyat"]):
            out[code] = row
    return out


def read_contracts(run: Runner, schema: str) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for r in run(crm_contracts_sql(schema)):
        code = clean(r.get("stok"), 60)
        if not code:
            continue
        out.setdefault(code, []).append({
            "sozlesme": str(r.get("sozlesme") or ""), "ad": clean(r.get("ad"), 200), "asgari": money_text(r.get("asgari")),
            "hesaplama": int(r["hesaplama"]) if r.get("hesaplama") is not None else None,
            "tur": int(r["tur"]) if r.get("tur") is not None else None,
            "odeme": int(r["odeme"]) if r.get("odeme") is not None else None,
            "oran": num(r.get("oran")),
        })
    return out


def read_crm_campaigns(run: Runner, schema: str, page: int, size: int, only_active: bool) -> dict[str, Any]:
    total = int((run(crm_campaigns_count_sql(schema, only_active)) or [{"n": 0}])[0].get("n") or 0)
    rows = run(crm_campaigns_sql(schema, page, size, only_active))
    items = []
    for r in rows:
        items.append({"id": str(r.get("id") or "").lower(), "ad": clean(r.get("ad"), 300),
                      "baslangic": iso_day(r.get("bas")), "bitis": iso_day(r.get("bit")),
                      "mecra": KAMPANYA_MECRA.get(int(r["mecra"])) if r.get("mecra") is not None else None,
                      "tip": KAMPANYA_TIP.get(int(r["tip"])) if r.get("tip") is not None else None,
                      "ekIskonto": num(r.get("ek_iskonto")), "netIskonto": num(r.get("net_iskonto")),
                      "asgariTutar": num(r.get("asgari_tutar")), "asgariAdet": num(r.get("asgari_adet")),
                      "hediyeAdet": num(r.get("hediye_adet")), "vadeli": bool(r.get("vadeli")), "herkes": bool(r.get("herkes")),
                      "aciklama": clean(r.get("aciklama"), 600), "etkin": int(r.get("durum") or 0) == 0})
    return {"items": items, "total": total, "page": page, "pageSize": size}


def read_campaign_effect(run: Runner, schema: str, ids: list[str]) -> dict[str, dict[str, float]]:
    ok = [i for i in ids if guid_ok(i)]
    if not ok:
        return {}
    out = {}
    for r in run(crm_campaign_effect_sql(schema, ok)):
        out[str(r.get("id") or "").lower()] = {k: num(r.get(k)) or 0.0 for k in ("satir", "siparis", "adet", "indirim", "tutar")}
    return out


def crm_campaign_exists(run: Runner, schema: str, crm_id: str) -> bool:
    if not guid_ok(crm_id):
        return False
    p = prefix(schema)
    return bool(run(f"SELECT COUNT(*) AS n FROM {p}new_kampanyaBase WHERE new_kampanyaId = '{crm_id}'")[0].get("n"))


def read_all_crm_campaigns(run: Runner, schema: str, size: int = 500) -> list[dict[str, Any]]:
    """Bütün bayi kampanyaları (tür sınıflaması için), sayfa sayfa; sessiz tavan yok."""
    out: list[dict[str, Any]] = []
    page = 0
    while True:
        got = read_crm_campaigns(run, schema, page, size, False)
        out += got["items"]
        if len(got["items"]) < size:
            return out
        page += 1
