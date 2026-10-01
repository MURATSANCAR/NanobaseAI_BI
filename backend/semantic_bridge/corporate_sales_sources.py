"""M32 Kurumsal satış ve B2B: Logo ve CRM okumaları (yalnız okuma) ve birim maliyet kaynağı.

Tanımlar mevcut ölçülerle aynıdır (logo-erp.md Kural 8, 11; metrics/logo-timas.md stok bakiyesi):

- **Net ciro** = faturalı satış satırı `STLINE` (`LINETYPE = 0`, `CANCELLED = 0`, `INVOICEREF <> 0`) `VATMATRAH` (KDV
  matrahı, fatura geneli iskonto dahil; dönem fatura tarihi `INVOICE.DATE_` — karar 2026-10-01);
  `TRCODE 7/8/9` satış artı, `2/3` iade eksi.
- **Satış faturası sayısı** fatura başlığından: `INVOICE`, `TRCODE 7/8/9`, `CANCELLED = 0` (satıra JOIN yok).
- **Kanal** = `CLCARD.SPECODE2` (KURUM, BAYI, KITAPCI …). Kanal adları ayardır (`CORP_CHANNEL`, `CORP_DEALER_CHANNELS`).
- **Stok bakiyesi** yalnız güncel yıl kopyasından, tarih süzgeçsiz: `IOCODE 1/2` giriş, `3/4` çıkış.
- **Liste fiyatı** `PRCLIST`: satış listesi `PTYPE = 2`, `ACTIVE = 0`, TL `CURRENCY = 160`, bugün geçerli (`BEGDATE ≤ bugün ≤
  ENDDATE`). Birden çok geçerli liste varsa: cariye/cari özel koduna bağlı olmayan liste, sonra en küçük `PRIORITY`, sonra en
  yeni `BEGDATE`; seçilen listenin kodu ve geçerli liste sayısı saklanır, ekranda yazılır.

Yıllar Logo'da ayrı firma numarasıdır (411 = 2026, 211 = 2021–2025); eşleme `L_CAPIPERIOD`'dan (`budget_sources.firms_by_year`).
Bir tarih aralığı birden çok firmaya düşerse her firma kendi aralığıyla okunur, cari **kodu** (`CLCARD.CODE`) ile birleştirilir;
`LOGICALREF` firmadan firmaya aynı olmayabilir.

CRM (`Timas_MSCRM`, .28) yalnız okunur; bayi web kullanıcı tablosundan yalnız **sayı** okunur (kullanıcı adı/şifre kolonları
seçilmez).

**Birim maliyet** (`unit_costs`): marjın maliyeti M9'dan gelecek. M9 hazır olunca `register_cost_provider` ile bağlanır.
`CORP_COST_SOURCE`: `m9` (varsayılan; sağlayıcı yoksa maliyet «bilinmiyor»), `logo` (Logo'da kitabın en son maliyeti girilmiş
satış satırının `OUTCOST`'u — «tahmini» etiketiyle), `yok`. Maliyet hiçbir yolda uydurulmaz.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional

from semantic_bridge import budget_sources as bsrc

log = logging.getLogger("semantic.corporate.sources")

SourceError = bsrc.SourceError
Runner = bsrc.Runner
runner = bsrc.runner
firms_by_year = bsrc.firms_by_year

_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FIRM = re.compile(r"^[0-9]{3}$")
#: Kanal (SPECODE2) değerleri ayardan gelir; SQL'e girmeden önce bu kalıba uymalı.
_CHANNEL = re.compile(r"^[A-Za-z0-9ÇĞİÖŞÜçğıöşü _.\-]{1,24}$")
_CODE = re.compile(r"^[^'\x00-\x1f]{1,40}$")

#: CRM kanal tipi (`AccountBase.new_cariozelKod2`) 100000007 = KURUM.
CRM_KURUM_KANAL = 100000007
#: CRM kurum rolü → segment (1 = «Müşteri» segment bilgisi taşımaz).
CRM_ROLE_SEGMENT = {2: "kamu", 3: "kamu", 4: "vakif"}
CRM_ROLE_LABEL = {1: "Müşteri", 2: "Devlet kurumu", 3: "Resmi", 4: "Özel STK"}


def prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise SourceError(f"CRM şeması «{schema}» geçerli bir ad değil.")
    if not sch:
        raise SourceError("CRM şeması girilmemiş; CRM okunamıyor.")
    return (f"{db}." if db else "") + f"{sch}."


def channel_list(raw: str) -> list[str]:
    out = []
    for part in (raw or "").replace(";", ",").split(","):
        p = part.strip()
        if not p:
            continue
        if not _CHANNEL.match(p):
            raise SourceError(f"Kanal adı «{p}» geçersiz.")
        out.append(p)
    if not out:
        raise SourceError("Kanal ayarı boş.")
    return out


def _in(channels: Iterable[str]) -> str:
    return ", ".join("N'" + c.replace("'", "''") + "'" for c in channels)


def _f(firm: str) -> str:
    if not _FIRM.match(firm or ""):
        raise SourceError(f"Logo firma numarası «{firm}» geçersiz.")
    return firm


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


def firm_ranges(firms: dict[int, str], since: date, until: date) -> list[tuple[str, date, date]]:
    """[since, until) aralığının firma parçaları: (firma, başlangıç, bitiş). Firması olmayan yıl atlanır."""
    by_firm: dict[str, list[int]] = {}
    for y in range(since.year, until.year + 1):
        f = firms.get(y)
        if f and date(y, 1, 1) < until:
            by_firm.setdefault(f, []).append(y)
    out = []
    for f, ys in by_firm.items():
        a = max(since, date(min(ys), 1, 1))
        b = min(until, date(max(ys) + 1, 1, 1))
        if a < b:
            out.append((f, a, b))
    return sorted(out, key=lambda x: x[1])


def current_firm(firms: dict[int, str]) -> str:
    if not firms:
        raise SourceError("Logo'da dönem bulunamadı.")
    return firms[max(firms)]


# ------------------------------------------------------------------------------------------ Logo SQL


def accounts_sql(firm: str, channel: str) -> str:
    f = _f(firm)
    return (f"SELECT LOGICALREF AS ref, CODE AS kod, DEFINITION_ AS unvan, CITY AS il, SPECODE2 AS kanal, "
            f"DISCRATE AS iskonto, ACTIVE AS pasif FROM dbo.LG_{f}_CLCARD WHERE SPECODE2 = {_in([channel])}")


def channel_sales_sql(firm: str, channels: list[str], a: date, b: date) -> str:
    """Kanal carileri × ay: net ciro ve net adet (faturalı satır; iade eksi)."""
    f = _f(firm)
    return f"""
SELECT C.CODE AS kod, YEAR(SH.DATE_) AS yil, MONTH(SH.DATE_) AS ay,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.VATMATRAH ELSE -S.VATMATRAH END) AS ciro,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet
FROM dbo.LG_{f}_01_STLINE AS S
JOIN dbo.LG_{f}_01_INVOICE AS SH ON SH.LOGICALREF = S.INVOICEREF AND SH.CANCELLED = 0
JOIN dbo.LG_{f}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
WHERE C.SPECODE2 IN ({_in(channels)}) AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0
  AND S.TRCODE IN (2,3,7,8,9) AND SH.DATE_ >= '{a.isoformat()}' AND SH.DATE_ < '{b.isoformat()}'
GROUP BY C.CODE, YEAR(SH.DATE_), MONTH(SH.DATE_)""".strip()


def channel_invoices_sql(firm: str, channels: list[str], a: date, b: date) -> str:
    """Kanal carileri × ay: satış faturası sayısı (başlıktan) ve son fatura günü."""
    f = _f(firm)
    return f"""
SELECT C.CODE AS kod, MAX(C.DEFINITION_) AS unvan, MAX(C.SPECODE2) AS kanal, MAX(C.CITY) AS il, MAX(C.LOGICALREF) AS ref,
  YEAR(I.DATE_) AS yil, MONTH(I.DATE_) AS ay, COUNT(*) AS fatura, MAX(I.DATE_) AS son
FROM dbo.LG_{f}_01_INVOICE AS I
JOIN dbo.LG_{f}_CLCARD AS C ON C.LOGICALREF = I.CLIENTREF
WHERE C.SPECODE2 IN ({_in(channels)}) AND I.CANCELLED = 0 AND I.TRCODE IN (7,8,9)
  AND I.DATE_ >= '{a.isoformat()}' AND I.DATE_ < '{b.isoformat()}'
GROUP BY C.CODE, YEAR(I.DATE_), MONTH(I.DATE_)""".strip()


def invoice_discount_sql(firm: str, channels: list[str], a: date, b: date) -> str:
    """Kanal faturası başına toplam adet, brüt (TOTAL) ve net (VATMATRAH): hacme göre gerçekleşen iskonto."""
    f = _f(firm)
    return f"""
SELECT S.INVOICEREF AS fatura, SUM(S.AMOUNT) AS adet, SUM(S.TOTAL) AS brut, SUM(S.VATMATRAH) AS net
FROM dbo.LG_{f}_01_STLINE AS S
JOIN dbo.LG_{f}_01_INVOICE AS SH ON SH.LOGICALREF = S.INVOICEREF AND SH.CANCELLED = 0
JOIN dbo.LG_{f}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
WHERE C.SPECODE2 IN ({_in(channels)}) AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0
  AND S.TRCODE IN (7,8,9) AND SH.DATE_ >= '{a.isoformat()}' AND SH.DATE_ < '{b.isoformat()}'
GROUP BY S.INVOICEREF""".strip()


def stock_sql(firm: str) -> str:
    """Kitap başına stok bakiyesi (tarihsiz, güncel kopya) ve bu yıl net satış adedi (faturalı)."""
    f = _f(firm)
    return f"""
SELECT I.CODE AS stok, MAX(I.NAME) AS ad,
  SUM(CASE WHEN S.IOCODE IN (1,2) THEN S.AMOUNT ELSE -S.AMOUNT END) AS bakiye,
  SUM(CASE WHEN S.INVOICEREF <> 0 AND S.TRCODE IN (7,8,9) THEN S.AMOUNT
           WHEN S.INVOICEREF <> 0 AND S.TRCODE IN (2,3) THEN -S.AMOUNT ELSE 0 END) AS yil_adet
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


def channel_items_sql(firm: str, channels: list[str], a: date, mid: date, b: date) -> str:
    """Kanal (bayi) satışlarında kitap başına net adet: [mid, b) son dönem, [a, mid) önceki dönem."""
    f = _f(firm)
    net = "CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END"
    return f"""
SELECT I.CODE AS stok,
  SUM(CASE WHEN SH.DATE_ >= '{mid.isoformat()}' THEN {net} ELSE 0 END) AS son,
  SUM(CASE WHEN SH.DATE_ < '{mid.isoformat()}' THEN {net} ELSE 0 END) AS onceki
FROM dbo.LG_{f}_01_STLINE AS S
JOIN dbo.LG_{f}_01_INVOICE AS SH ON SH.LOGICALREF = S.INVOICEREF AND SH.CANCELLED = 0
JOIN dbo.LG_{f}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
WHERE C.SPECODE2 IN ({_in(channels)}) AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0
  AND S.TRCODE IN (2,3,7,8,9) AND SH.DATE_ >= '{a.isoformat()}' AND SH.DATE_ < '{b.isoformat()}'
GROUP BY I.CODE""".strip()


def client_items_sql(firm: str, code: str, a: date, b: date) -> str:
    """Tek carinin kitap karması (bayi ayrıntısı, anlık)."""
    f = _f(firm)
    if not _CODE.match(code or ""):
        raise SourceError("Cari kodu geçersiz.")
    c = code.replace("'", "''")
    return f"""
SELECT I.CODE AS stok, MAX(I.NAME) AS ad,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.VATMATRAH ELSE -S.VATMATRAH END) AS ciro,
  MAX(SH.DATE_) AS son
FROM dbo.LG_{f}_01_STLINE AS S
JOIN dbo.LG_{f}_01_INVOICE AS SH ON SH.LOGICALREF = S.INVOICEREF AND SH.CANCELLED = 0
JOIN dbo.LG_{f}_CLCARD AS C ON C.LOGICALREF = S.CLIENTREF
JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = S.STOCKREF
WHERE C.CODE = N'{c}' AND S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.INVOICEREF <> 0
  AND S.TRCODE IN (2,3,7,8,9) AND SH.DATE_ >= '{a.isoformat()}' AND SH.DATE_ < '{b.isoformat()}'
GROUP BY I.CODE""".strip()


def last_cost_sql(firm: str) -> str:
    """Kitabın en son maliyeti girilmiş satış satırı (`OUTCOST <> 0`): «tahmini maliyet» sağlayıcısı."""
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
    f = _f(firm)
    return (f"SELECT MAX(DATE_) AS son FROM dbo.LG_{f}_01_INVOICE WHERE CANCELLED = 0 AND TRCODE IN (7,8,9)")


# ------------------------------------------------------------------------------------------ CRM SQL


def crm_accounts_sql(schema: str) -> str:
    p = prefix(schema)
    return (
        "SELECT a.AccountId AS id, a.Name AS unvan, a.new_CariKodu AS kod, a.new_logicalref AS ref,"
        " CAST(a.new_KurumRolu AS int) AS rol, CAST(a.new_cariozelKod2 AS int) AS kanal,"
        " u.FullName AS temsilci, u.DomainName AS temsilci_hesap, o.FullName AS sahip, o.DomainName AS sahip_hesap,"
        " CAST(a.obs_sendtoemailiys AS int) AS iys, CAST(a.DoNotEMail AS int) AS eposta_yok"
        f" FROM {p}AccountBase a"
        f" LEFT JOIN {p}SystemUserBase u ON u.SystemUserId = a.new_KurumunTemsilcisi"
        f" LEFT JOIN {p}SystemUserBase o ON o.SystemUserId = a.OwnerId"
        f" WHERE a.StateCode = 0 AND (a.new_cariozelKod2 = {CRM_KURUM_KANAL} OR a.new_KurumRolu IN (2,3,4))"
    )


def crm_b2b_orders_sql(schema: str, days: int) -> str:
    """Bayi başına B2B portal siparişi (son `days` gün): `new_yenib2b = 1`, etkin sipariş."""
    p = prefix(schema)
    return (
        "SELECT a.new_CariKodu AS kod, a.new_logicalref AS ref, COUNT(*) AS siparis, MAX(s.CreatedOn) AS son"
        f" FROM {p}new_siparisBase s JOIN {p}AccountBase a ON a.AccountId = s.new_firmaid"
        f" WHERE s.statecode = 0 AND s.new_yenib2b = 1 AND s.CreatedOn >= DATEADD(day, -{int(days)}, GETDATE())"
        " GROUP BY a.new_CariKodu, a.new_logicalref"
    )


def crm_webusers_sql(schema: str) -> str:
    """Bayi başına etkin web kullanıcısı SAYISI (kullanıcı adı/şifre kolonları seçilmez)."""
    p = prefix(schema)
    return (
        "SELECT a.new_CariKodu AS kod, a.new_logicalref AS ref, COUNT(*) AS kullanici"
        f" FROM {p}new_webuserBase w JOIN {p}AccountBase a ON a.AccountId = w.new_firmaid"
        " WHERE w.statecode = 0 GROUP BY a.new_CariKodu, a.new_logicalref"
    )


def crm_books_sql(schema: str) -> str:
    p = prefix(schema)
    return (
        "SELECT k.new_StokKodu AS stok, k.new_name AS ad, k.new_yayineviidName AS yayinevi, k.new_kitaplikidName AS kitaplik,"
        " k.new_turlertext AS turler, k.new_yaslartext AS yaslar, CAST(k.new_hedefkitle AS int) AS hedef,"
        " k.new_hedefkitleyasbaslangic AS yas_min, k.new_hedefkitleyasbitis AS yas_max, k.new_ilkyayintarihi AS ilk_yayin,"
        " k.new_PerakendeBirimFiyat AS crm_fiyat, CAST(k.new_ozet AS nvarchar(1200)) AS ozet"
        f" FROM {p}new_kitap k WHERE k.statecode = 0 AND k.new_StokKodu IS NOT NULL"
    )


def crm_authors_sql(schema: str) -> str:
    p = prefix(schema)
    return f"SELECT StokKodu AS stok, Yazar AS yazar, Üzeri_Fiyat AS liste_fiyati FROM {p}powerbikitap"


def crm_book_themes_sql(schema: str) -> str:
    p = prefix(schema)
    return (
        "SELECT k.new_StokKodu AS stok, t.new_name AS tema"
        f" FROM {p}new_new_kitap_new_temaBase x"
        f" JOIN {p}new_kitapBase k ON k.new_kitapId = x.new_kitapid"
        f" JOIN {p}new_temaBase t ON t.new_temaId = x.new_temaid"
        " WHERE k.new_StokKodu IS NOT NULL AND t.statecode = 0"
    )


def crm_theme_names_sql(schema: str) -> str:
    p = prefix(schema)
    return f"SELECT new_name AS tema FROM {p}new_temaBase WHERE statecode = 0"


def crm_user_emails_sql(schema: str) -> str:
    p = prefix(schema)
    return (f"SELECT DomainName AS hesap, InternalEMailAddress AS eposta FROM {p}SystemUserBase"
            " WHERE IsDisabled = 0 AND InternalEMailAddress IS NOT NULL")


# ------------------------------------------------------------------------------------------ okuma


def read_data_end(run: Runner, firms: dict[int, str]) -> Optional[date]:
    rows = run(data_end_sql(current_firm(firms)))
    return day(rows[0].get("son")) if rows else None


def read_accounts(run: Runner, firms: dict[int, str], channel: str) -> list[dict[str, Any]]:
    out = []
    for r in run(accounts_sql(current_firm(firms), channel)):
        code = clean(r.get("kod"), 40)
        if not code:
            continue
        out.append({"kod": code, "ref": int(r["ref"]) if r.get("ref") is not None else None,
                    "unvan": clean(r.get("unvan")), "il": clean(r.get("il"), 80), "kanal": clean(r.get("kanal"), 24),
                    "iskonto": num(r.get("iskonto")), "pasif": bool(r.get("pasif"))})
    return out


def read_channel_sales(run: Runner, firms: dict[int, str], channels: list[str], since: date, until: date, *,
                       invoices: bool = True) -> list[dict[str, Any]]:
    """Kod × yıl × ay: ciro, adet, satış faturası sayısı ve son fatura günü. Birden çok firmadaki aynı kod toplanır."""
    merged: dict[tuple[str, int, int], dict[str, Any]] = {}

    def slot(r: dict[str, Any]) -> Optional[dict[str, Any]]:
        code = clean(r.get("kod"), 40)
        if not code:
            return None
        k = (code, int(r["yil"]), int(r["ay"]))
        return merged.setdefault(k, {"kod": k[0], "yil": k[1], "ay": k[2], "ciro": 0.0, "adet": 0.0, "fatura": 0, "son": None})

    for firm, a, b in firm_ranges(firms, since, until):
        for r in run(channel_sales_sql(firm, channels, a, b)):
            cur = slot(r)
            if cur is not None:
                cur["ciro"] += num(r.get("ciro")) or 0.0
                cur["adet"] += num(r.get("adet")) or 0.0
        if not invoices:
            continue
        for r in run(channel_invoices_sql(firm, channels, a, b)):
            cur = slot(r)
            if cur is None:
                continue
            cur["fatura"] += int(r.get("fatura") or 0)
            d = day(r.get("son"))
            if d and (cur["son"] is None or d > cur["son"]):
                cur["son"] = d
    return list(merged.values())


def read_dealer_invoices(run: Runner, firms: dict[int, str], channels: list[str], since: date, until: date) -> dict[str, dict[str, Any]]:
    """Kod → {unvan, kanal, il, son, fatura, ay_fatura}: pencere içindeki satış faturaları."""
    out: dict[str, dict[str, Any]] = {}
    for firm, a, b in firm_ranges(firms, since, until):
        for r in run(channel_invoices_sql(firm, channels, a, b)):
            code = clean(r.get("kod"), 40)
            if not code:
                continue
            cur = out.setdefault(code, {"kod": code, "unvan": None, "kanal": None, "il": None, "son": None, "fatura": 0, "ref": None})
            if firm == current_firm(firms) and r.get("ref") is not None:
                cur["ref"] = int(r["ref"])
            cur["unvan"] = clean(r.get("unvan")) or cur["unvan"]
            cur["kanal"] = clean(r.get("kanal"), 24) or cur["kanal"]
            cur["il"] = clean(r.get("il"), 80) or cur["il"]
            cur["fatura"] += int(r.get("fatura") or 0)
            d = day(r.get("son"))
            if d and (cur["son"] is None or d > cur["son"]):
                cur["son"] = d
    return out


def read_invoice_discounts(run: Runner, firms: dict[int, str], channels: list[str], since: date, until: date) -> list[dict[str, float]]:
    out = []
    for firm, a, b in firm_ranges(firms, since, until):
        for r in run(invoice_discount_sql(firm, channels, a, b)):
            brut, net, adet = num(r.get("brut")) or 0.0, num(r.get("net")) or 0.0, num(r.get("adet")) or 0.0
            if brut > 0 and adet > 0:
                out.append({"adet": adet, "brut": brut, "net": net})
    return out


def read_stock(run: Runner, firms: dict[int, str]) -> dict[str, dict[str, Any]]:
    return {str(r["stok"]).strip(): {"ad": clean(r.get("ad")), "bakiye": num(r.get("bakiye")) or 0.0,
                                     "yil_adet": num(r.get("yil_adet")) or 0.0}
            for r in run(stock_sql(current_firm(firms))) if r.get("stok")}


def pick_price(rows: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Geçerli listelerden biri: cariye bağlı olmayan, sonra küçük öncelik, sonra en yeni başlangıç."""
    ok = [r for r in rows if (num(r.get("fiyat")) or 0) > 0]
    if not ok:
        return None

    def key(r: dict[str, Any]) -> tuple:
        general = 0 if not (clean(r.get("cari")) or clean(r.get("cari_ozel"))) else 1
        beg = day(r.get("bas")) or date(1900, 1, 1)
        return (general, int(num(r.get("oncelik")) or 0), -beg.toordinal())

    best = sorted(ok, key=key)[0]
    return {"fiyat": float(num(best["fiyat"])), "liste": clean(best.get("liste"), 40), "kdvDahil": bool(best.get("kdv_dahil")),
            "listeSayisi": len(ok), "genel": key(best)[0] == 0}


def read_prices(run: Runner, firms: dict[int, str], today: date) -> dict[str, dict[str, Any]]:
    by: dict[str, list[dict[str, Any]]] = {}
    for r in run(prices_sql(current_firm(firms), today)):
        if r.get("stok"):
            by.setdefault(str(r["stok"]).strip(), []).append(r)
    out = {}
    for code, rows in by.items():
        p = pick_price(rows)
        if p:
            out[code] = p
    return out


def read_channel_items(run: Runner, firms: dict[int, str], channels: list[str], end: date, days: int) -> dict[str, dict[str, float]]:
    """Kitap → {son, onceki}: kanal satışında son `days` gün ve ondan önceki `days` gün net adet."""
    b = end + timedelta(days=1)
    mid = b - timedelta(days=days)
    a = mid - timedelta(days=days)
    out: dict[str, dict[str, float]] = {}
    for firm, fa, fb in firm_ranges(firms, a, b):
        for r in run(channel_items_sql(firm, channels, fa, mid, fb)):
            code = str(r.get("stok") or "").strip()
            if not code:
                continue
            cur = out.setdefault(code, {"son": 0.0, "onceki": 0.0})
            cur["son"] += num(r.get("son")) or 0.0
            cur["onceki"] += num(r.get("onceki")) or 0.0
    return out


def read_client_items(run: Runner, firms: dict[int, str], code: str, since: date, until: date) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for firm, a, b in firm_ranges(firms, since, until):
        for r in run(client_items_sql(firm, code, a, b)):
            stok = str(r.get("stok") or "").strip()
            if not stok:
                continue
            cur = out.setdefault(stok, {"stok": stok, "ad": clean(r.get("ad")), "adet": 0.0, "ciro": 0.0, "son": None})
            cur["adet"] += num(r.get("adet")) or 0.0
            cur["ciro"] += num(r.get("ciro")) or 0.0
            d = day(r.get("son"))
            if d and (cur["son"] is None or d > cur["son"]):
                cur["son"] = d
    return out


def read_crm_accounts(run: Runner, schema: str) -> list[dict[str, Any]]:
    from semantic_bridge.people import account as account_name

    out = []
    for r in run(crm_accounts_sql(schema)):
        rep, rep_acc = clean(r.get("temsilci")), r.get("temsilci_hesap")
        if not rep:  # kurum temsilcisi boşsa kaydın sahibi
            rep, rep_acc = clean(r.get("sahip")), r.get("sahip_hesap")
        ref = clean(r.get("ref"), 20)
        out.append({"id": str(r.get("id") or "").strip().lower(), "unvan": clean(r.get("unvan")), "kod": clean(r.get("kod"), 40),
                    "ref": int(ref) if ref and ref.isdigit() else None, "rol": r.get("rol"), "kanal": r.get("kanal"),
                    "temsilci": rep, "temsilciHesap": account_name(rep_acc) if rep_acc else None,
                    "iys": bool(r.get("iys")), "epostaYok": bool(r.get("eposta_yok"))})
    return out


def _by_code_or_ref(rows: list[dict[str, Any]], field: str) -> tuple[dict[str, float], dict[int, float]]:
    by_code: dict[str, float] = {}
    by_ref: dict[int, float] = {}
    for r in rows:
        v = num(r.get(field)) or 0.0
        code = clean(r.get("kod"), 40)
        ref = clean(r.get("ref"), 20)
        if code:
            by_code[code] = by_code.get(code, 0.0) + v
        elif ref and ref.isdigit():
            by_ref[int(ref)] = by_ref.get(int(ref), 0.0) + v
    return by_code, by_ref


def read_crm_b2b(run: Runner, schema: str, days: int) -> tuple[dict[str, float], dict[int, float]]:
    return _by_code_or_ref(run(crm_b2b_orders_sql(schema, days)), "siparis")


def read_crm_webusers(run: Runner, schema: str) -> tuple[dict[str, float], dict[int, float]]:
    return _by_code_or_ref(run(crm_webusers_sql(schema)), "kullanici")


def read_crm_books(run: Runner, schema: str) -> dict[str, dict[str, Any]]:
    books: dict[str, dict[str, Any]] = {}
    for r in run(crm_books_sql(schema)):
        code = clean(r.get("stok"), 60)
        if not code:
            continue
        ymin, ymax = num(r.get("yas_min")), num(r.get("yas_max"))
        b = books.setdefault(code, {})
        b.update({"ad": clean(r.get("ad")), "yayinevi": clean(r.get("yayinevi"), 200), "kitaplik": clean(r.get("kitaplik"), 200),
                  "turler": clean(r.get("turler"), 400), "yaslar": clean(r.get("yaslar"), 200),
                  "hedef": {1: "Çocuk", 2: "Genç", 3: "Yetişkin"}.get(r.get("hedef")),
                  "yasMin": int(ymin) if ymin else None, "yasMax": int(ymax) if ymax else None,
                  "ilkYayin": (day(r.get("ilk_yayin")) or None), "crmFiyat": num(r.get("crm_fiyat")),
                  "ozet": _strip_html(r.get("ozet"))})
    try:
        for r in run(crm_authors_sql(schema)):
            code = clean(r.get("stok"), 60)
            if code and code in books:
                books[code]["yazar"] = clean(r.get("yazar"), 300)
                if books[code].get("crmFiyat") is None:
                    books[code]["crmFiyat"] = num(r.get("liste_fiyati"))
    except SourceError as e:  # raporlama görünümü yoksa yazar boş kalır
        log.info("corporate: yazar görünümü okunamadı: %s", e)
    return books


def _strip_html(v: Any) -> Optional[str]:
    if v is None:
        return None
    from semantic_bridge.crm_text import rich_line   # ZEKI-23: bütün HTML varlıkları (&rsquo;, &Scedil;…) çözülür
    return clean(rich_line(v) or "", 1000)


def read_crm_book_themes(run: Runner, schema: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for r in run(crm_book_themes_sql(schema)):
        code, theme = clean(r.get("stok"), 60), clean(r.get("tema"), 120)
        if code and theme and theme not in out.setdefault(code, []):
            out[code].append(theme)
    return out


def read_crm_theme_names(run: Runner, schema: str) -> list[str]:
    return sorted({t for t in (clean(r.get("tema"), 120) for r in run(crm_theme_names_sql(schema))) if t})


def read_user_emails(run: Runner, schema: str) -> dict[str, str]:
    from semantic_bridge.people import account as account_name

    out = {}
    for r in run(crm_user_emails_sql(schema)):
        acc = account_name(r.get("hesap") or "")
        mail = clean(r.get("eposta"), 200)
        if acc and mail and "@" in mail:
            out[acc] = mail
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


# ------------------------------------------------------------------------------------------ birim maliyet

#: M9 bağlandığında: fn(stok_kodlari) → {stok: {"birim": float, "tarih": "YYYY-MM-DD" | None}}.
_COST_PROVIDER: Optional[Callable[[list[str]], dict[str, dict[str, Any]]]] = None

COST_SOURCES = {"m9": "Birim maliyet (M9)", "logo": "Logo son maliyetli satış satırı (tahmini)", "yok": "Maliyet kullanılmaz"}


def register_cost_provider(fn: Optional[Callable[[list[str]], dict[str, dict[str, Any]]]]) -> None:
    """M9 kendi modülü yüklenirken çağırır. None bağı kaldırır."""
    global _COST_PROVIDER
    _COST_PROVIDER = fn


def unit_costs(codes: Iterable[str], source: str, logo_costs: Optional[dict[str, dict[str, Any]]] = None) -> dict[str, dict[str, Any]]:
    """Stok kodu → {"birim": float | None, "kaynak": str, "tarih": str | None, "tahmini": bool}. Bilinmeyen maliyet None'dır;
    hiçbir yolda varsayılan maliyet üretilmez."""
    codes = [c for c in dict.fromkeys(codes) if c]
    unknown = {c: {"birim": None, "kaynak": "bilinmiyor", "tarih": None, "tahmini": False} for c in codes}
    src = (source or "m9").strip().lower()
    if src == "m9":
        if _COST_PROVIDER is None:
            return unknown
        try:
            got = _COST_PROVIDER(codes) or {}
        except Exception as e:  # noqa: BLE001 — maliyet okunamazsa bilinmiyor
            log.warning("corporate: M9 maliyeti okunamadı: %s", e)
            return unknown
        for c in codes:
            v = got.get(c) or {}
            b = num(v.get("birim"))
            if b is not None and b > 0:
                unknown[c] = {"birim": b, "kaynak": "m9", "tarih": v.get("tarih"), "tahmini": False}
        return unknown
    if src == "logo":
        for c in codes:
            v = (logo_costs or {}).get(c)
            if v and v.get("birim"):
                unknown[c] = {"birim": float(v["birim"]), "kaynak": "logo", "tarih": v.get("tarih"), "tahmini": True}
        return unknown
    return unknown
