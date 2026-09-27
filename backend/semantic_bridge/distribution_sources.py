"""M29 İlk dağılım: Logo ve CRM okuması (yalnız okuma; CRM'e ve Logo'ya yazılmaz).

Tanımlar mevcut ölçülerle aynıdır; sorgular kabul betiğindeki (`scripts/acceptance/M29/`) doğrudan SQL
referanslarıyla birebir karşılaştırılır.

- **Depoya giriş** = üretimden giriş satırı `STLINE TRCODE 13, IOCODE 1, LINETYPE 0, CANCELLED 0` ve fişi gerçek
  giriş (`STFICHE.PRODSTAT = 0`). M12 ölçümü (2026-09-28): `PRODSTAT 1` planlanan giriştir (ileri tarihli, emir
  başına bir fiş); ikisi toplanırsa adet iki katına çıkar. Yalnız kitap kodları (`15201…`, M10 kararı).
- **Stok bakiyesi** = güncel yılın kopyasında (açılış devri içinde) malzeme bazında `IOCODE 1,2` giriş − `3,4`
  çıkış, tarih süzgeci yok (katalogdaki «stok bakiyesi» ölçüsü). Planlanan üretim girişi fişi fiziksel stok
  değildir, dışarıda tutulur (`DIST_STOCK_EXCLUDE_PLANNED`, varsayılan açık).
- **Satış satırı** = `STLINE`, `CANCELLED 0`, `LINETYPE 0`, `INVOICEREF <> 0`, `TRCODE 7/8/9` satış, `2/3` iade (M46 ile
  aynı). Benzer kitabın ilk 8 haftası = ilk faturalı satış gününden `DIST_WINDOW_DAYS` (56) gün.
- **Sevk** = `STLINE TRCODE 7/8, IOCODE 4` (irsaliye; faturalanmamışı da sayılır). **Faturalanan** = sevkin
  `INVOICEREF <> 0` olan kısmı (+ TRCODE 9). **İade** = `TRCODE 2/3` satırları (fiziksel dönüş, faturasız dahil).
- **Cari** = `CLCARD.CODE` ile anahtarlanır: `LOGICALREF` her yıl kopyasında farklıdır, kod aynıdır. Kişisel veri
  kolonları (TCKNO, telefon, e-posta, adres) okunmaz; yalnız kod, unvan, il (`CITY`), kanal (`SPECODE2`).

CRM: `AccountBase` (dağılım carisi işareti `new_distributionstatus`, cari kodu `new_CariKodu` → Logo `CLCARD.CODE`,
sahibi/BMT `OwnerId` → `SystemUserBase.DomainName`, il `new_cariyeaitil`), geçmiş dağılım siparişi `new_siparisBase`
tip 2 «Dağılım» + `new_siparissatiriBase.new_StokKodu`.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

from semantic_bridge import budget_sources as bsrc
from semantic_bridge.budget_sources import Runner, SourceError, firms_by_year, runner  # noqa: F401 — yeniden kullanım

_CODE_OK = re.compile(r"^[0-9A-Za-z._\-/ ]{1,60}$")
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FIRM = re.compile(r"^[0-9]{3}$")
CHUNK = 900  # IN listesi parça boyu (SQL Server 2.100 parametre sınırının çok altında; sessiz kesme yok)
#: Dağılım tipli CRM siparişi ve iptal durumu.
CRM_ORDER_DISTRIBUTION = 2
CRM_ORDER_CANCELLED = 100000001


def book_prefixes() -> tuple[str, ...]:
    """Kitap kodu önekleri. M10 ölçümü: 15201 = basılı kitap; set, dergi, e-kitap, ticari ürün dışarıda."""
    raw = os.environ.get("DIST_CODE_PREFIXES", "15201")
    out = tuple(p.strip() for p in raw.split(",") if p.strip() and re.fullmatch(r"[0-9A-Za-z.]+", p.strip()))
    return out or ("15201",)


def exclude_planned() -> bool:
    return os.environ.get("DIST_STOCK_EXCLUDE_PLANNED", "1").strip().lower() not in ("0", "false", "hayir", "no")


def q(v: str) -> str:
    """SQL metin sabiti (tek tırnak kaçışı). Yalnız doğrulanmış kod/tarih için."""
    return "'" + str(v).replace("'", "''") + "'"


def codes_ok(codes: Iterable[str]) -> list[str]:
    out = []
    for c in codes:
        s = str(c or "").strip()
        if s and _CODE_OK.match(s) and s not in out:
            out.append(s)
    return out


def chunks(items: list[str], n: int = CHUNK) -> Iterable[list[str]]:
    for i in range(0, len(items), n):
        yield items[i:i + n]


def _f(firm: str) -> str:
    if not _FIRM.match(firm or ""):
        raise SourceError("Logo firma numarası geçersiz.")
    return firm


def _prefix_sql(col: str) -> str:
    return "(" + " OR ".join(f"{col} LIKE {q(p + '%')}" for p in book_prefixes()) + ")"


# ------------------------------------------------------------------ Logo SQL


def depot_entries_sql(firm: str, since: date) -> str:
    """Kitap başına pencere içindeki gerçek üretimden giriş: ilk/son gün, adet, fiş sayısı."""
    f = _f(firm)
    return f"""
-- Üretimden giriş (TRCODE 13, IOCODE 1), yalnız gerçek giriş fişi (PRODSTAT 0); planlanan fiş (1) sayılmaz.
SELECT I.CODE AS stok_kodu, MAX(I.NAME) AS ad, MIN(L.DATE_) AS ilk, MAX(L.DATE_) AS son,
  SUM(L.AMOUNT) AS adet, COUNT(DISTINCT L.STFICHEREF) AS fis
FROM dbo.LG_{f}_01_STLINE AS L
JOIN dbo.LG_{f}_01_STFICHE AS F ON F.LOGICALREF = L.STFICHEREF
JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = L.STOCKREF
WHERE L.TRCODE = 13 AND L.IOCODE = 1 AND L.LINETYPE = 0 AND L.CANCELLED = 0
  AND F.CANCELLED = 0 AND F.PRODSTAT = 0
  AND L.DATE_ >= '{since.isoformat()}' AND {_prefix_sql('I.CODE')}
GROUP BY I.CODE""".strip()


def first_entry_sql(firm: str, codes: list[str]) -> str:
    """Kodların bu yıl kopyasındaki ilk gerçek üretimden giriş günü (ilk baskı / baskı tekrarı ayrımı)."""
    f = _f(firm)
    return (f"SELECT I.CODE AS stok_kodu, MIN(L.DATE_) AS ilk FROM dbo.LG_{f}_01_STLINE AS L "
            f"JOIN dbo.LG_{f}_01_STFICHE AS F ON F.LOGICALREF = L.STFICHEREF "
            f"JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = L.STOCKREF "
            f"WHERE L.TRCODE = 13 AND L.IOCODE = 1 AND L.LINETYPE = 0 AND L.CANCELLED = 0 AND F.PRODSTAT = 0 "
            f"AND I.CODE IN ({', '.join(q(c) for c in codes)}) GROUP BY I.CODE")


def stock_sql(firm: str, codes: list[str]) -> str:
    """Stok bakiyesi (tarih süzgeci yok, güncel kopya). Planlanan üretim girişi fişi (PRODSTAT 1) ayarla dışarıda."""
    f = _f(firm)
    planned = ("LEFT JOIN dbo.LG_{f}_01_STFICHE AS F ON F.LOGICALREF = L.STFICHEREF ".format(f=f)
               if exclude_planned() else "")
    cond = "AND NOT (L.TRCODE = 13 AND ISNULL(F.PRODSTAT, 0) = 1) " if exclude_planned() else ""
    return (f"SELECT I.CODE AS stok_kodu, SUM(CASE WHEN L.IOCODE IN (1,2) THEN L.AMOUNT ELSE -L.AMOUNT END) AS bakiye "
            f"FROM dbo.LG_{f}_01_STLINE AS L JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = L.STOCKREF {planned}"
            f"WHERE L.LINETYPE = 0 AND L.CANCELLED = 0 AND L.IOCODE IN (1,2,3,4) {cond}"
            f"AND I.CODE IN ({', '.join(q(c) for c in codes)}) GROUP BY I.CODE")


def first_sale_sql(firm: str, codes: list[str]) -> str:
    """Kodların bu yıl kopyasındaki ilk faturalı satış günü (benzer kitabın 8 haftalık penceresinin başı)."""
    f = _f(firm)
    return (f"SELECT I.CODE AS stok_kodu, MIN(L.DATE_) AS ilk FROM dbo.LG_{f}_01_STLINE AS L "
            f"JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = L.STOCKREF "
            f"WHERE L.CANCELLED = 0 AND L.LINETYPE = 0 AND L.INVOICEREF <> 0 AND L.TRCODE IN (7,8) "
            f"AND I.CODE IN ({', '.join(q(c) for c in codes)}) GROUP BY I.CODE")


def comp_window_sql(firm: str, windows: list[tuple[str, date, date]]) -> str:
    """Benzer kitap × cari: penceredeki faturalı satış adedi, iade adedi, net ciro. Pencereler VALUES tablosunda
    (kitap başına ayrı başlangıç); cari kodla anahtarlanır."""
    f = _f(firm)
    vals = ", ".join(f"({q(k)}, {q(a.isoformat())}, {q(b.isoformat())})" for k, a, b in windows)
    return f"""
-- Benzer kitapların ilk faturalı satış gününden itibaren pencere; iade eksi (M46 satış satırı tanımı).
WITH W AS (SELECT kod, CAST(bas AS date) AS bas, CAST(bitis AS date) AS bitis FROM (VALUES {vals}) AS v(kod, bas, bitis))
SELECT W.kod AS comp, C.CODE AS cari_kodu,
  SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.AMOUNT ELSE 0 END) AS satis_adet,
  SUM(CASE WHEN L.TRCODE IN (2,3) THEN L.AMOUNT ELSE 0 END) AS iade_adet,
  SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.LINENET ELSE -L.LINENET END) AS net_ciro
FROM dbo.LG_{f}_01_STLINE AS L
JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = L.STOCKREF
JOIN W ON W.kod = I.CODE
JOIN dbo.LG_{f}_CLCARD AS C ON C.LOGICALREF = L.CLIENTREF
WHERE L.CANCELLED = 0 AND L.LINETYPE = 0 AND L.INVOICEREF <> 0 AND L.TRCODE IN (2,3,7,8,9)
  AND L.DATE_ >= W.bas AND L.DATE_ < W.bitis
GROUP BY W.kod, C.CODE""".strip()


def clients_sql(firm: str, codes: list[str]) -> str:
    """Cari kartın paylaşılabilir alanları. Kişisel veri kolonları okunmaz (Logo Kural 3)."""
    f = _f(firm)
    return (f"SELECT CODE AS cari_kodu, DEFINITION_ AS unvan, CITY AS il, SPECODE2 AS kanal FROM dbo.LG_{f}_CLCARD "
            f"WHERE CODE IN ({', '.join(q(c) for c in codes)})")


def tracking_sql(firm: str, code: str, start: date, end: date) -> str:
    """Onaylı planın takibi: cari × hafta (onay gününden) sevk, faturalanan, iade adedi."""
    f = _f(firm)
    d0 = start.isoformat()
    week = f"DATEDIFF(day, '{d0}', L.DATE_) / 7 + 1"
    return f"""
SELECT C.CODE AS cari_kodu, {week} AS hafta,
  SUM(CASE WHEN L.TRCODE IN (7,8) AND L.IOCODE = 4 THEN L.AMOUNT ELSE 0 END) AS sevk,
  SUM(CASE WHEN L.TRCODE IN (7,8,9) AND L.INVOICEREF <> 0 THEN L.AMOUNT ELSE 0 END) AS fatura,
  SUM(CASE WHEN L.TRCODE IN (2,3) THEN L.AMOUNT ELSE 0 END) AS iade
FROM dbo.LG_{f}_01_STLINE AS L
JOIN dbo.LG_{f}_ITEMS AS I ON I.LOGICALREF = L.STOCKREF
JOIN dbo.LG_{f}_CLCARD AS C ON C.LOGICALREF = L.CLIENTREF
WHERE L.CANCELLED = 0 AND L.LINETYPE = 0 AND L.TRCODE IN (2,3,7,8,9)
  AND I.CODE = {q(code)} AND L.DATE_ >= '{d0}' AND L.DATE_ < '{end.isoformat()}'
GROUP BY C.CODE, {week}""".strip()


def depot_end_sql(firm: str) -> str:
    f = _f(firm)
    return (f"SELECT MAX(L.DATE_) AS son FROM dbo.LG_{f}_01_STLINE AS L JOIN dbo.LG_{f}_01_STFICHE AS F "
            f"ON F.LOGICALREF = L.STFICHEREF WHERE L.TRCODE = 13 AND L.IOCODE = 1 AND L.CANCELLED = 0 AND F.PRODSTAT = 0")


# ------------------------------------------------------------------ CRM SQL


def crm_prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise SourceError(f"CRM şeması «{schema}» geçerli bir ad değil.")
    if not sch:
        raise SourceError("CRM şeması girilmemiş; CRM okunamıyor.")
    return (f"{db}." if db else "") + f"{sch}."


def crm_accounts_sql(schema: str) -> str:
    """Etkin cariler: dağılım işareti, Logo cari kodu, sahibi (BMT) ve ili. Kişisel veri kolonu yok."""
    p = crm_prefix(schema)
    return (
        "SELECT CAST(a.AccountId AS nvarchar(40)) AS id, a.Name AS ad, a.new_CariKodu AS cari_kodu, "
        "CAST(ISNULL(a.new_distributionstatus, 0) AS int) AS dagilim, CAST(a.new_FirmaKanal AS int) AS firma_kanal, "
        "u.FullName AS bmt_ad, u.DomainName AS bmt_domain, il.new_name AS il "
        f"FROM {p}AccountBase a LEFT JOIN {p}SystemUserBase u ON u.SystemUserId = a.OwnerId "
        f"LEFT JOIN {p}new_illerBase il ON il.new_illerId = a.new_cariyeaitil "
        "WHERE a.StateCode = 0 AND ((a.new_CariKodu IS NOT NULL AND a.new_CariKodu <> '') OR a.new_distributionstatus = 1)"
    )


def crm_dist_orders_sql(schema: str, codes: list[str]) -> str:
    """Geçmiş ilk dağılım: CRM «Dağılım» tipli (2) etkin, iptal edilmemiş siparişlerin satır adedi, stok kodu başına."""
    p = crm_prefix(schema)
    return (
        "SELECT ss.new_StokKodu AS stok_kodu, SUM(ss.new_siparisadedi) AS adet, COUNT(DISTINCT s.new_siparisId) AS siparis, "
        "COUNT(DISTINCT s.new_firmaid) AS cari, MIN(s.CreatedOn) AS ilk "
        f"FROM {p}new_siparisBase s JOIN {p}new_siparissatiriBase ss ON ss.new_siparisid = s.new_siparisId "
        f"WHERE s.new_siparistipi = {CRM_ORDER_DISTRIBUTION} AND s.statecode = 0 AND ss.statecode = 0 "
        f"AND ISNULL(s.statuscode, 0) <> {CRM_ORDER_CANCELLED} "
        f"AND ss.new_StokKodu IN ({', '.join(q(c) for c in codes)}) GROUP BY ss.new_StokKodu"
    )


# ------------------------------------------------------------------ okuma


def day(v: Any) -> Optional[date]:
    return bsrc._day(v)


def num(v: Any) -> float:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return 0.0
    return n if n == n else 0.0


def clean(v: Any) -> Optional[str]:
    return bsrc._clean(v)


class Logo:
    """Logo okuması; yıl → firma eşlemesi bir kez okunur."""

    def __init__(self, run: Runner):
        self.run = run
        self._firms: Optional[dict[int, str]] = None

    @property
    def firms(self) -> dict[int, str]:
        if self._firms is None:
            self._firms = firms_by_year(self.run)
            if not self._firms:
                raise SourceError("Logo'da dönem tanımı okunamadı.")
        return self._firms

    @property
    def current(self) -> str:
        return self.firms[max(self.firms)]

    def firms_between(self, a: date, b: date) -> list[str]:
        out = []
        for y in range(a.year, b.year + 1):
            f = self.firms.get(y)
            if f and f not in out:
                out.append(f)
        return out

    def first_year(self) -> int:
        return min(self.firms)

    def data_end(self) -> Optional[date]:
        rows = self.run(bsrc.data_end_sql(self.current))
        return day(rows[0].get("son")) if rows else None

    def depot_end(self) -> Optional[date]:
        rows = self.run(depot_end_sql(self.current))
        return day(rows[0].get("son")) if rows else None

    def depot_entries(self, since: date) -> list[dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for f in self.firms_between(since, max(since, date.today())):
            for r in self.run(depot_entries_sql(f, since)):
                code = str(r.get("stok_kodu") or "").strip()
                if not code:
                    continue
                cur = out.setdefault(code, {"stok_kodu": code, "ad": clean(r.get("ad")), "ilk": None, "son": None,
                                            "adet": 0.0, "fis": 0})
                a, b = day(r.get("ilk")), day(r.get("son"))
                cur["ilk"] = min(x for x in (cur["ilk"], a) if x) if (cur["ilk"] or a) else None
                cur["son"] = max(x for x in (cur["son"], b) if x) if (cur["son"] or b) else None
                cur["adet"] += num(r.get("adet"))
                cur["fis"] += int(num(r.get("fis")))
        return list(out.values())

    def first_entries(self, codes: list[str]) -> dict[str, date]:
        """Kodların okunabilen bütün yıllardaki ilk gerçek üretimden giriş günü."""
        out: dict[str, date] = {}
        codes = codes_ok(codes)
        for f in sorted(set(self.firms.values())):
            for part in chunks(codes):
                for r in self.run(first_entry_sql(f, part)):
                    d = day(r.get("ilk"))
                    k = str(r.get("stok_kodu") or "").strip()
                    if d and k and (k not in out or d < out[k]):
                        out[k] = d
        return out

    def stock(self, codes: list[str]) -> dict[str, float]:
        out: dict[str, float] = {}
        for part in chunks(codes_ok(codes)):
            for r in self.run(stock_sql(self.current, part)):
                out[str(r["stok_kodu"]).strip()] = num(r.get("bakiye"))
        return out

    def first_sales(self, codes: list[str], since_year: int) -> dict[str, date]:
        out: dict[str, date] = {}
        codes = codes_ok(codes)
        for y in sorted(self.firms):
            if y < since_year:
                continue
            f = self.firms[y]
            for part in chunks(codes):
                for r in self.run(first_sale_sql(f, part)):
                    d = day(r.get("ilk"))
                    k = str(r.get("stok_kodu") or "").strip()
                    if d and k and (k not in out or d < out[k]):
                        out[k] = d
        return out

    def comp_windows(self, windows: list[tuple[str, date, date]]) -> list[dict[str, Any]]:
        """Her pencere düştüğü yıl kopyalarında okunur (yıl sınırını aşan pencere iki kopyadan)."""
        by_firm: dict[str, list[tuple[str, date, date]]] = {}
        for k, a, b in windows:
            for f in self.firms_between(a, b - timedelta(days=1)):
                by_firm.setdefault(f, []).append((k, a, b))
        out: list[dict[str, Any]] = []
        for f, ws in by_firm.items():
            for i in range(0, len(ws), 200):
                for r in self.run(comp_window_sql(f, ws[i:i + 200])):
                    out.append({"comp": str(r["comp"]).strip(), "cari_kodu": str(r.get("cari_kodu") or "").strip(),
                                "satis": num(r.get("satis_adet")), "iade": num(r.get("iade_adet")),
                                "ciro": num(r.get("net_ciro"))})
        return out

    def clients(self, codes: list[str]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for part in chunks(codes_ok(codes)):
            for r in self.run(clients_sql(self.current, part)):
                k = str(r.get("cari_kodu") or "").strip()
                if k:
                    out[k] = {"unvan": clean(r.get("unvan")), "il": clean(r.get("il")), "kanal": clean(r.get("kanal"))}
        return out

    def tracking(self, code: str, start: date, end: date) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for f in self.firms_between(start, end - timedelta(days=1)):
            for r in self.run(tracking_sql(f, code, start, end)):
                out.append({"cari_kodu": str(r.get("cari_kodu") or "").strip(), "hafta": int(num(r.get("hafta"))),
                            "sevk": num(r.get("sevk")), "fatura": num(r.get("fatura")), "iade": num(r.get("iade"))})
        return out


def read_accounts(run: Runner, schema: str) -> list[dict[str, Any]]:
    from semantic_bridge.people import account

    out = []
    for r in run(crm_accounts_sql(schema)):
        out.append({"id": clean(r.get("id")), "ad": clean(r.get("ad")), "cari_kodu": clean(r.get("cari_kodu")),
                    "dagilim": int(num(r.get("dagilim"))) == 1, "bmt_ad": clean(r.get("bmt_ad")),
                    "bmt_hesap": account(clean(r.get("bmt_domain")) or "") or None, "il": clean(r.get("il"))})
    return out


def read_dist_orders(run: Runner, schema: str, codes: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for part in chunks(codes_ok(codes)):
        for r in run(crm_dist_orders_sql(schema, part)):
            k = str(r.get("stok_kodu") or "").strip()
            if k:
                d = day(r.get("ilk"))
                out[k] = {"adet": num(r.get("adet")), "siparis": int(num(r.get("siparis"))), "cari": int(num(r.get("cari"))),
                          "ilk": d.isoformat() if d else None}
    return out


def today_tr() -> date:
    from zoneinfo import ZoneInfo

    return datetime.now(ZoneInfo("Europe/Istanbul")).date()
