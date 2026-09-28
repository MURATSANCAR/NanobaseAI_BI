"""M16 Lansman izlemesinin kaynak okuması (yalnız okuma; CRM'e ve Logo'ya giden tek komut `SELECT`).

Tanımlar mevcut ekranlarla aynıdır, yeniden yazılmadı:

- **Sipariş sinyali (CRM, canlı .28):** `new_siparissatiriBase` × `new_siparisBase`, stok kodu satırdaki
  `new_StokKodu`; sipariş durumu Yönetim → Pazarlama «Sayılmayan sipariş durumları» (`MARKETING_LAUNCH_ORDER_EXCLUDE`,
  varsayılan 1 Taslak, 100000001 İptal Edildi) hariç. Gün = sipariş tarihinin İstanbul günü (CRM UTC saklar, +3 —
  pazarlama çekirdeğinin `_utc_bound` yöntemiyle aynı). Sipariş satış değildir; ekranda «sipariş» diye ayrı etiketlenir.
  Dağılım = sipariş tipi 2.
- **Açık sipariş (bekleyen):** Baskı Öneri'nin `crm_bekleyen_siparis.sql` sorgusu olduğu gibi (kapanmış durumlar, B2C,
  tarihsiz sipariş ve iki iç cari hariç), yalnız lansmandaki stok kodlarıyla süzülür.
- **Bekleyen ürün:** CRM «Bekleyen Ürün» (`new_bekleyenurunBase`, durum 1 = Bekleyen), ürün → stok kodu
  `ProductBase.ProductNumber`. Açık siparişten ayrı satır, ayrı etiket.
- **Faturalı satış (Logo):** M46 `budget_sources.sales_sql` ile aynı satır tanımı (faturalı, iptalsiz malzeme satırı;
  TRCODE 7/8/9 satış, 2/3 iade eksi; net ciro = LINENET), gün kırılımıyla. Yıl → firma `L_CAPIPERIOD`. Stok kodları önce
  `ITEMS`'tan kayıt numarasına çevrilir (satış görünümlerindeki «IN listesi planı bozar» tuzağına düşmemek için STLINE
  `STOCKREF` ile süzülür). Veri sonu = `budget_sources.data_end_sql`.
- **Depo stoku:** Baskı Öneri'nin `logo_depo_stok.sql` görünümü olduğu gibi; yedek sinyal CRM sipariş satırındaki
  «Sipariş anındaki depo stok» (`new_siparisanindakistokadedi`, en son siparişin değeri ve zamanı).
- **Etkinlik:** CRM `new_etkinlik` (ilgili kitap bağı; katılımcı, satılan kitap, gelir, gider, durum). Katılımcının
  kişisel verisi okunmaz, yalnız sayı.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional

from semantic_bridge import budget_sources as bsrc
from semantic_bridge.marketing.sources import SourceError, _d, _s, _utc_bound, code, guid, prefix

Runner = Callable[[str], list[dict[str, Any]]]
#: Sipariş tipi «Dağılım» (CRM `new_siparistipi`).
ORDER_DISTRIBUTION = 2
#: Etkinlik durumu «Tamamlandı» (CRM `new_etkinlik.statuscode`).
EVENT_DONE = 100000002
EVENT_CANCELLED = 100000000
EVENT_STATUS = {1: "Planlandı", 100000002: "Tamamlandı", 100000000: "İptal edildi", 2: "Etkin değil"}


def _codes(codes: Iterable[str]) -> str:
    out = sorted({code(c) for c in codes if c})
    if not out:
        raise SourceError("Stok kodu yok.")
    return ", ".join(f"N'{c}'" for c in out)


def _ints(values: Iterable[Any]) -> str:
    out = sorted({int(v) for v in values})
    return ", ".join(str(v) for v in out) or "-1"


# ------------------------------------------------------------------ CRM SQL


def orders_sql(schema: str, codes: Iterable[str], frm: date, to: date, excluded: Iterable[int]) -> str:
    """Stok kodu × İstanbul günü: sipariş adedi, satır sayısı, dağılım adedi, sevk edilen ve satırdaki bekleyen adet.
    [frm, to] kapalı aralık (İstanbul günü)."""
    p = prefix(schema)
    return f"""
-- Lansman sipariş sinyali (CRM, yalnız okuma). Tarih UTC saklanır; gün İstanbul saatine (+3) çevrilir.
SELECT ss.new_StokKodu AS stok_kodu, CAST(DATEADD(HOUR, 3, s.new_siparistarihi) AS DATE) AS gun,
       SUM(ss.new_adet) AS siparis_adet, COUNT(*) AS siparis_satiri,
       SUM(CASE WHEN CAST(s.new_siparistipi AS int) = {ORDER_DISTRIBUTION} THEN ss.new_adet ELSE 0 END) AS dagilim_adet,
       SUM(ISNULL(ss.new_sevkedilenadet, 0)) AS sevk_adet
FROM {p}new_siparissatiriBase AS ss
JOIN {p}new_siparisBase AS s ON s.new_siparisId = ss.new_siparisid
WHERE ss.new_StokKodu IN ({_codes(codes)}) AND s.statuscode NOT IN ({_ints(excluded)})
  AND s.new_siparistarihi >= '{_utc_bound(frm)}' AND s.new_siparistarihi < '{_utc_bound(to + timedelta(days=1))}'
GROUP BY ss.new_StokKodu, CAST(DATEADD(HOUR, 3, s.new_siparistarihi) AS DATE)""".strip()


def distribution_sql(schema: str, codes: Iterable[str], frm: date, to: date, excluded: Iterable[int]) -> str:
    """Pencere boyunca dağılım siparişleri: adet ve bayi (cari) sayısı. Bayi sayısı günlerden toplanamaz, ayrı okunur."""
    p = prefix(schema)
    return f"""
-- Dağılım siparişleri (sipariş tipi 2): adet, sipariş ve bayi sayısı (CRM, yalnız okuma).
SELECT ss.new_StokKodu AS stok_kodu, SUM(ss.new_adet) AS dagilim_adet, COUNT(DISTINCT s.new_siparisId) AS siparis,
       COUNT(DISTINCT s.new_firmaid) AS bayi
FROM {p}new_siparissatiriBase AS ss
JOIN {p}new_siparisBase AS s ON s.new_siparisId = ss.new_siparisid
WHERE ss.new_StokKodu IN ({_codes(codes)}) AND s.statuscode NOT IN ({_ints(excluded)})
  AND CAST(s.new_siparistipi AS int) = {ORDER_DISTRIBUTION}
  AND s.new_siparistarihi >= '{_utc_bound(frm)}' AND s.new_siparistarihi < '{_utc_bound(to + timedelta(days=1))}'
GROUP BY ss.new_StokKodu""".strip()


def open_orders_sql(schema: str, codes: Iterable[str]) -> str:
    """Baskı Öneri'nin açık sipariş sorgusu (değiştirilmeden), lansmandaki stok kodlarıyla süzülür."""
    from semantic_bridge.management import sql_text

    base = sql_text("baski-oneri", "crm_bekleyen_siparis").replace("Timas_MSCRM.dbo.", prefix(schema)).strip().rstrip(";")
    return (f"-- Açık sipariş (Baskı Öneri ile aynı tanım), lansman kitaplarıyla süzüldü.\n"
            f"SELECT b.stok_kodu, b.bekleyen_siparis FROM (\n{base}\n) AS b WHERE b.stok_kodu IN ({_codes(codes)})")


def pending_items_sql(schema: str, codes: Iterable[str]) -> str:
    p = prefix(schema)
    return f"""
-- CRM «Bekleyen Ürün» (durum 1 = Bekleyen), stok kodu = ürün numarası (yalnız okuma).
SELECT pr.ProductNumber AS stok_kodu, SUM(b.new_adet) AS bekleyen_urun
FROM {p}new_bekleyenurunBase AS b
JOIN {p}ProductBase AS pr ON pr.ProductId = b.new_urunid
WHERE b.statuscode = 1 AND pr.ProductNumber IN ({_codes(codes)})
GROUP BY pr.ProductNumber""".strip()


def order_time_stock_sql(schema: str, codes: Iterable[str], since: date) -> str:
    """Yedek depo sinyali: her kitabın en son siparişindeki «sipariş anındaki depo stok» değeri ve zamanı."""
    p = prefix(schema)
    return f"""
-- Sipariş anındaki depo stoku (CRM sipariş satırı), kitap başına en son sipariş (yalnız okuma).
SELECT x.stok_kodu, x.stok, x.zaman FROM (
  SELECT ss.new_StokKodu AS stok_kodu, ss.new_siparisanindakistokadedi AS stok, s.new_siparistarihi AS zaman,
         ROW_NUMBER() OVER (PARTITION BY ss.new_StokKodu ORDER BY s.new_siparistarihi DESC) AS rn
  FROM {p}new_siparissatiriBase AS ss
  JOIN {p}new_siparisBase AS s ON s.new_siparisId = ss.new_siparisid
  WHERE ss.new_StokKodu IN ({_codes(codes)}) AND ss.new_siparisanindakistokadedi IS NOT NULL
    AND s.new_siparistarihi >= '{_utc_bound(since)}'
) AS x WHERE x.rn = 1""".strip()


def events_sql(schema: str, kitap_id: str) -> str:
    p = prefix(schema)
    return f"""
-- Kitaba bağlı CRM etkinlikleri (katılımcı kişisel verisi okunmaz, yalnız sayı).
SELECT e.new_etkinlikId AS id, e.new_name AS ad, e.new_etkinliktipiidName AS tur,
       CAST(DATEADD(HOUR, 3, e.new_BalangTarihi) AS DATE) AS tarih, e.new_yer AS yer, e.new_sehirName AS sehir,
       e.new_katilimcisayisi AS katilimci, e.new_SatilanKitapAd AS satilan,
       COALESCE(e.new_etkinlikgeliri_Base, e.new_etkinlikgeliri) AS gelir,
       COALESCE(e.new_toplametkinlikgideri_Base, e.new_ToplamEtkinlikGideri) AS gider,
       CAST(e.statuscode AS int) AS durum, e.new_lgiliYazarName AS yazar
FROM {p}new_etkinlik AS e
WHERE e.new_lgiliKitap = '{guid(kitap_id)}'""".strip()


# ------------------------------------------------------------------ Logo SQL


def items_sql(firm: str, codes: Iterable[str]) -> str:
    return f"SELECT LOGICALREF AS ref, CODE AS stok_kodu FROM dbo.LG_{firm}_ITEMS WHERE CODE IN ({_codes(codes)})"


def daily_sales_sql(firm: str, refs: Iterable[int], frm: date, to: date) -> str:
    """Kitap × gün faturalı net adet ve net ciro; [frm, to] kapalı aralık. Satır tanımı M46 `sales_sql` ile aynı."""
    return f"""
-- Faturalı satış satırları (M46 tanımı), gün kırılımı; iade eksi. Net ciro = LINENET.
SELECT S.STOCKREF AS ref, CAST(S.DATE_ AS DATE) AS gun,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet,
  SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS ciro
FROM dbo.LG_{firm}_01_STLINE AS S
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.STOCKREF IN ({_ints(refs)})
  AND S.DATE_ >= '{frm.isoformat()}' AND S.DATE_ < '{(to + timedelta(days=1)).isoformat()}'
GROUP BY S.STOCKREF, CAST(S.DATE_ AS DATE)""".strip()


def depot_sql(codes: Iterable[str]) -> str:
    """Baskı Öneri'nin depo stoku sorgusu (değiştirilmeden), lansman kitaplarıyla süzülür."""
    from semantic_bridge.management import sql_text

    base = sql_text("baski-oneri", "logo_depo_stok").strip().rstrip(";")
    return (f"-- Depo stoku (Baskı Öneri ile aynı görünüm), lansman kitaplarıyla süzüldü.\n"
            f"SELECT d.stok_kodu, d.depo_stok FROM (\n{base}\n) AS d WHERE d.stok_kodu IN ({_codes(codes)})")


# ------------------------------------------------------------------ okuma


def _num(v: Any) -> float:
    return float(bsrc._num(v) or 0.0)


def _day(v: Any) -> Optional[str]:
    d = bsrc._day(v)
    return d.isoformat() if d else None


class Sources:
    """CRM ve Logo okuyucuları. `crm()` / `logo()` her çağrıda yeni salt okunur bağlantı verir (iş parçacığında güvenli)."""

    def __init__(self, schema: Callable[[], str], crm: Callable[[], Runner], logo: Callable[[], Runner]):
        self.schema = schema
        self._crm = crm
        self._logo = logo

    def _run(self, which: Callable[[], Runner], sql: str) -> list[dict[str, Any]]:
        try:
            return which()(sql)
        except bsrc.SourceError as e:
            raise SourceError(str(e)) from None

    # ---- CRM
    def orders(self, codes: list[str], frm: date, to: date, excluded: list[int]) -> tuple[dict[tuple[str, str], dict[str, float]], str]:
        sql = orders_sql(self.schema(), codes, frm, to, excluded)
        out: dict[tuple[str, str], dict[str, float]] = {}
        for r in self._run(self._crm, sql):
            k, g = _s(r.get("stok_kodu")), _day(r.get("gun"))
            if not k or not g:
                continue
            cur = out.setdefault((k, g), {"siparis_adet": 0.0, "siparis_satiri": 0.0, "dagilim_adet": 0.0, "sevk_adet": 0.0})
            for f in cur:
                cur[f] += _num(r.get(f))
        return out, sql

    def distribution(self, codes: list[str], frm: date, to: date, excluded: list[int]) -> tuple[dict[str, dict[str, float]], str]:
        sql = distribution_sql(self.schema(), codes, frm, to, excluded)
        return {str(_s(r.get("stok_kodu"))): {"adet": _num(r.get("dagilim_adet")), "siparis": _num(r.get("siparis")),
                                             "bayi": _num(r.get("bayi"))}
                for r in self._run(self._crm, sql) if _s(r.get("stok_kodu"))}, sql

    def open_orders(self, codes: list[str]) -> tuple[dict[str, float], str]:
        sql = open_orders_sql(self.schema(), codes)
        out: dict[str, float] = {}
        for r in self._run(self._crm, sql):
            k = _s(r.get("stok_kodu"))
            if k:
                out[k] = out.get(k, 0.0) + _num(r.get("bekleyen_siparis"))
        return out, sql

    def pending_items(self, codes: list[str]) -> tuple[dict[str, float], str]:
        sql = pending_items_sql(self.schema(), codes)
        return {str(_s(r.get("stok_kodu"))): _num(r.get("bekleyen_urun")) for r in self._run(self._crm, sql) if _s(r.get("stok_kodu"))}, sql

    def order_time_stock(self, codes: list[str], since: date) -> tuple[dict[str, dict[str, Any]], str]:
        sql = order_time_stock_sql(self.schema(), codes, since)
        out: dict[str, dict[str, Any]] = {}
        for r in self._run(self._crm, sql):
            k = _s(r.get("stok_kodu"))
            if not k:
                continue
            z = r.get("zaman")
            when = (z + timedelta(hours=3)).isoformat() if isinstance(z, datetime) else (str(z)[:19] if z else None)
            out[k] = {"stok": _num(r.get("stok")), "zaman": when}
        return out, sql

    def events(self, kitap_id: str) -> tuple[list[dict[str, Any]], str]:
        sql = events_sql(self.schema(), kitap_id)
        rows = []
        for r in self._run(self._crm, sql):
            st = r.get("durum")
            rows.append({"crmId": (_s(r.get("id")) or "").lower(), "ad": _s(r.get("ad")), "tur": _s(r.get("tur")),
                         "tarih": _d(r.get("tarih")), "yer": " · ".join(x for x in (_s(r.get("yer")), _s(r.get("sehir"))) if x) or None,
                         "katilimci": bsrc._num(r.get("katilimci")), "satilan": bsrc._num(r.get("satilan")),
                         "gelir": bsrc._num(r.get("gelir")), "gider": bsrc._num(r.get("gider")),
                         "durum": int(st) if st is not None else None, "durumAdi": EVENT_STATUS.get(int(st)) if st is not None else None,
                         "yazar": _s(r.get("yazar"))})
        rows.sort(key=lambda x: (x["tarih"] or "", x["ad"] or ""))
        return rows, sql

    # ---- Logo
    def firms(self) -> dict[int, str]:
        try:
            return bsrc.firms_by_year(self._logo())
        except bsrc.SourceError as e:
            raise SourceError(str(e)) from None

    def data_end(self, firms: dict[int, str]) -> Optional[date]:
        try:
            return bsrc.read_data_end(self._logo(), firms) if firms else None
        except bsrc.SourceError as e:
            raise SourceError(str(e)) from None

    def daily_sales(self, firms: dict[int, str], codes: list[str], frm: date, to: date) -> tuple[dict[tuple[str, str], dict[str, float]], list[str]]:
        """Pencere yıllara bölünür (her yıl ayrı firma). Dönen: {(stok, gün): {adet, ciro}}, koşulan SQL'ler."""
        out: dict[tuple[str, str], dict[str, float]] = {}
        sqls: list[str] = []
        for y in range(frm.year, to.year + 1):
            firm = firms.get(y)
            if not firm:
                continue
            a, b = max(frm, date(y, 1, 1)), min(to, date(y, 12, 31))
            isql = items_sql(firm, codes)
            refs = {int(r["ref"]): str(r["stok_kodu"]).strip() for r in self._run(self._logo, isql) if r.get("ref") is not None}
            if not refs:
                continue
            ssql = daily_sales_sql(firm, refs, a, b)
            sqls += [isql, ssql]
            for r in self._run(self._logo, ssql):
                k, g = refs.get(int(r["ref"])), _day(r.get("gun"))
                if not k or not g:
                    continue
                cur = out.setdefault((k, g), {"adet": 0.0, "ciro": 0.0})
                cur["adet"] += _num(r.get("adet"))
                cur["ciro"] += _num(r.get("ciro"))
        return out, sqls

    def depot(self, codes: list[str]) -> tuple[dict[str, float], str]:
        sql = depot_sql(codes)
        out: dict[str, float] = {}
        for r in self._run(self._logo, sql):
            k = _s(r.get("stok_kodu"))
            if k:
                out[k] = out.get(k, 0.0) + _num(r.get("depo_stok"))
        return out, sql


def first_days(daily: dict[str, float], start: date, days: int, data_end: Optional[date]) -> dict[str, Any]:
    """Emsal kitabın ilk satış gününden itibaren ilk `days` gün: gün gün net adet, 7 ve 30 gün toplamı.
    İlk satış günü = penceredeki net adedi sıfırdan büyük ilk gün."""
    ordered = sorted((d, v) for d, v in daily.items() if d >= start.isoformat())
    first = next((date.fromisoformat(d) for d, v in ordered if v > 0), None)
    if first is None:
        return {"ilkGun": None, "gunluk": [], "ilk7": None, "ilk30": None, "tam": False}
    series = [round(daily.get((first + timedelta(days=i)).isoformat(), 0.0), 2) for i in range(days)]
    seen = (data_end - first).days + 1 if data_end else days
    return {"ilkGun": first.isoformat(), "gunluk": series[:max(0, min(days, seen))],
            "ilk7": round(sum(series[:7]), 2) if seen >= 7 else None,
            "ilk30": round(sum(series[:30]), 2) if seen >= 30 else None, "tam": seen >= days}
