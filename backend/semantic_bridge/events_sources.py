"""M27 Fuar, etkinlik ve ödül: CRM ve Logo okuması (yalnız okuma).

Kaynaklar (analiz `docs/analiz/kullanici-ihtiyaclari/M27-fuar-etkinlik-odul.md` §6, §13):

- **Etkinlik** — CRM `new_etkinlikBase` (57 bin kayıt; çoğu satış ziyareti). Tip `new_etkinliktipiid` →
  `new_etkinliktipiBase` (371 tip). Hangi tipin fuar / imza günü / söyleşi / okul etkinliği / satış ziyareti olduğu
  CRM'de yazmaz: eşleme portalın ayarıdır (`semantic_events_type_map`, «Tip eşlemesi» ekranı). Durum `statuscode`
  1 Planlandı / 100000002 Tamamlandı / 100000000 İptal. Gider `new_ToplamEtkinlikGideri` (Kural C10: neredeyse boş).
  Sorumlu `new_sorumlusu` → `SystemUserBase.DomainName` (AD hesabı).
- **Etkinlik ↔ yazar / kitap** — `new_new_etkinlik_contactBase` (%99 yazar), `new_new_etkinlik_new_kitapBase`.
- **Fuar / etkinlik / imza siparişi** — CRM `new_siparisBase.new_siparistipi` (4 Fuar, 5 Etkinlik, 16 İmza siparişi);
  sayılan tipler ve dışlanan durumlar ayardır (`EVENTS_ORDER_TYPES`, `EVENTS_ORDER_EXCLUDED_STATUS`).
- **Fuar satışı** — Logo faturalı satış satırı (`STLINE`, `CANCELLED = 0`, `LINETYPE = 0`, `INVOICEREF <> 0`,
  TRCODE 7/8/9 − 2/3, net ciro = `LINENET`) ⨝ `CLCARD`, cari kanalı `SPECODE2 = <EVENTS_FAIR_CHANNEL>` (varsayılan
  «FUAR»); fuara cari kodu eşlendiyse ayrıca `CLCARD.CODE IN (…)`. Yıllar ayrı firma numarasıdır (`L_CAPIPERIOD`,
  211 = 2021–2025, 411 = 2026); kopya firmalar (`SEMANTIC_EXCLUDE_CONTEXT`) atlanır.
- **Stok** — güncel kopyada malzeme bakiyesi (IOCODE 1/2 giriş, 3/4 çıkış; tarih süzgeçsiz).
- **Veri sonu** — `MAX(DATE_)` iptal edilmemiş fatura (`LG_<firma>_01_INVOICE`).
- **Kitap kartı** — CRM `new_kitap` görünümü (stok kodu, ad, ilk yayın, yayınevi) + `powerbikitap` (yazar).

CRM tarihleri UTC saklanır; gün sınırları İstanbul gününe göre UTC'ye çevrilerek sorulur. Okuma `EVENTS_CACHE_SEC`
saniye bellekte tutulur; «Verileri yenile» yeniden okur. CRM'e ve Logo'ya hiçbir şey yazılmaz.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable, Iterable, Optional
from zoneinfo import ZoneInfo

from semantic_layer.firm_scope import firm_in_scope

log = logging.getLogger("semantic.events.sources")
TZ = ZoneInfo("Europe/Istanbul")
UTC = ZoneInfo("UTC")
MAX_ROWS = 3_000_000  # güvenlik ağı; aşılırsa hata verilir, sessizce kesilmez
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FIRM = re.compile(r"^[0-9]{3}$")
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_CODE = re.compile(r"^[^'\";\\]{1,60}$")
IN_CHUNK = 500

#: CRM etkinlik durumu.
CRM_STATUS = {1: "Planlandı", 100000002: "Tamamlandı", 100000000: "İptal edildi", 2: "Etkin değil"}
CRM_CANCELLED = 100000000
#: CRM sipariş tipi (yalnız bu modülün baktıkları; hangilerinin sayılacağı ayardır).
ORDER_TYPES = {4: "Fuar", 5: "Etkinlik", 16: "İmza siparişi"}


class SourceError(RuntimeError):
    """Kişiye gösterilecek düz Türkçe hata (kaynak okunamadı)."""


def ttl() -> int:
    try:
        return max(0, int(os.environ.get("EVENTS_CACHE_SEC", "600")))
    except ValueError:
        return 600


def prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise SourceError(f"CRM şeması «{schema}» geçerli bir ad değil.")
    if not sch:
        raise SourceError("CRM şeması girilmemiş; CRM okunamıyor.")
    return (f"{db}." if db else "") + f"{sch}."


def _firm(firm: str) -> str:
    if not _FIRM.match(firm or ""):
        raise SourceError("Logo firma numarası geçersiz.")
    return firm


def _ints(values: Iterable[Any]) -> str:
    out = [str(int(v)) for v in values]
    if not out:
        raise SourceError("Boş değer listesi.")
    return ", ".join(out)


def guids(values: Iterable[Any]) -> list[str]:
    out = []
    for v in values or []:
        t = str(v or "").strip().strip("{}").lower()
        if _GUID.match(t) and t not in out:
            out.append(t)
    return out


def _guid_in(values: list[str]) -> str:
    return ", ".join(f"'{g}'" for g in values)


def codes(values: Iterable[Any]) -> list[str]:
    """Logo cari kodları: tırnak/noktalı virgül içermeyen, 60 karakteri aşmayan metinler."""
    out = []
    for v in values or []:
        t = str(v or "").strip()
        if t and _CODE.match(t) and t not in out:
            out.append(t)
    return out


def _code_in(values: list[str]) -> str:
    return ", ".join("N'" + v.replace("'", "''") + "'" for v in values)


def _channel(ch: str) -> str:
    t = (ch or "").strip()
    if not t or not _CODE.match(t):
        raise SourceError("Fuar kanalı kodu geçersiz (EVENTS_FAIR_CHANNEL).")
    return t.replace("'", "''")


def utc_bound(day: date) -> str:
    """İstanbul gününün başlangıcı, CRM'in UTC saklamasına göre (`YYYY-MM-DD HH:MM:SS`)."""
    return datetime(day.year, day.month, day.day, tzinfo=TZ).astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------------------------------ CRM SQL


def types_sql(schema: str) -> str:
    """371 etkinlik tipi ve kullanımı (etkin etkinlik sayısı, son başlangıç): eşleme ekranı en çok kullanılanı önce gösterir."""
    p = prefix(schema)
    return (
        "SELECT t.new_etkinliktipiId AS id, t.new_name AS ad, CAST(t.statecode AS int) AS durum,"
        " COUNT(e.new_etkinlikId) AS adet, MAX(e.new_BalangTarihi) AS son"
        f" FROM {p}new_etkinliktipiBase t"
        f" LEFT JOIN {p}new_etkinlikBase e ON e.new_etkinliktipiid = t.new_etkinliktipiId AND e.statecode = 0"
        " GROUP BY t.new_etkinliktipiId, t.new_name, t.statecode"
    )


_EVENT_COLS = (
    "SELECT e.new_etkinlikId AS id, e.new_name AS ad, e.new_etkinliktipiid AS tip_id, t.new_name AS tip,"
    " e.new_BalangTarihi AS baslangic, e.new_BitiTarihi AS bitis, e.new_yer AS yer, i.new_name AS il,"
    " CAST(e.statuscode AS int) AS durum, CAST(e.new_ziyarettipi AS int) AS ziyaret_tipi,"
    " e.new_katilimcisayisi AS katilimci, e.new_SatilanKitapAd AS satilan, e.new_etkinlikgeliri AS gelir,"
    " e.new_ToplamEtkinlikGideri AS gider, e.new_dl AS oduller, e.new_etkinlikurladres AS url,"
    " su.DomainName AS sorumlu_hesap, su.FullName AS sorumlu_ad"
)


def _event_from(p: str) -> str:
    return (
        f" FROM {p}new_etkinlikBase e"
        f" LEFT JOIN {p}new_etkinliktipiBase t ON t.new_etkinliktipiId = e.new_etkinliktipiid"
        f" LEFT JOIN {p}new_illerBase i ON i.new_illerId = e.new_il"
        f" LEFT JOIN {p}SystemUserBase su ON su.SystemUserId = e.new_sorumlusu"
    )


def events_sql(schema: str, frm: date, to: date) -> str:
    """Başlangıcı [frm, to) aralığında olan etkin etkinlikler (İstanbul günü). Tip süzgeci Python'da, eşlemeye göre."""
    p = prefix(schema)
    return (_EVENT_COLS + _event_from(p)
            + f" WHERE e.statecode = 0 AND e.new_BalangTarihi >= '{utc_bound(frm)}' AND e.new_BalangTarihi < '{utc_bound(to)}'")


def events_by_id_sql(schema: str, ids: list[str]) -> str:
    p = prefix(schema)
    return _EVENT_COLS + _event_from(p) + f" WHERE e.new_etkinlikId IN ({_guid_in(ids)})"


def event_authors_sql(schema: str, ids: list[str]) -> str:
    p = prefix(schema)
    return (
        "SELECT ec.new_etkinlikid AS etkinlik_id, c.ContactId AS kisi_id, c.FullName AS ad"
        f" FROM {p}new_new_etkinlik_contactBase ec JOIN {p}ContactBase c ON c.ContactId = ec.contactid"
        f" WHERE ec.new_etkinlikid IN ({_guid_in(ids)})"
    )


def event_books_sql(schema: str, ids: list[str]) -> str:
    p = prefix(schema)
    return (
        "SELECT ek.new_etkinlikid AS etkinlik_id, k.new_kitapId AS kitap_id, k.new_name AS ad, k.new_StokKodu AS stok_kodu"
        f" FROM {p}new_new_etkinlik_new_kitapBase ek JOIN {p}new_kitapBase k ON k.new_kitapId = ek.new_kitapid"
        f" WHERE ek.new_etkinlikid IN ({_guid_in(ids)})"
    )


def author_events_sql(schema: str, contact_id: str, frm: date, to: date) -> str:
    """Yazarın [frm, to) aralığındaki etkinlikleri (iptal hariç) — «[yazar] bu yıl kaç etkinliğe katıldı»."""
    p = prefix(schema)
    g = guids([contact_id])
    if not g:
        raise SourceError("Yazar kimliği geçersiz.")
    return (_EVENT_COLS + _event_from(p)
            + f" JOIN {p}new_new_etkinlik_contactBase ec ON ec.new_etkinlikid = e.new_etkinlikId"
            + f" WHERE ec.contactid = '{g[0]}' AND e.new_BalangTarihi >= '{utc_bound(frm)}'"
            + f" AND e.new_BalangTarihi < '{utc_bound(to)}' AND e.statuscode <> {CRM_CANCELLED}")


def orders_sql(schema: str, frm: date, to: date, types: Iterable[int], excluded_status: Iterable[int]) -> str:
    """Sipariş tarihi [frm, to) aralığında (İstanbul günü) olan fuar/etkinlik/imza siparişleri; firma ve cari kodu ile."""
    p = prefix(schema)
    ex = list(excluded_status)
    return (
        "SELECT s.new_siparisId AS id, s.new_name AS no, CAST(s.new_siparistipi AS int) AS tip, CAST(s.statuscode AS int) AS durum,"
        " s.new_siparistarihi AS tarih, s.new_toplamsatistutari AS tutar, s.new_siparisadeti AS adet,"
        " a.Name AS firma, a.new_CariKodu AS cari_kodu"
        f" FROM {p}new_siparisBase s LEFT JOIN {p}AccountBase a ON a.AccountId = s.new_firmaid"
        f" WHERE s.statecode = 0 AND s.new_siparistipi IN ({_ints(types)})"
        f" AND s.new_siparistarihi >= '{utc_bound(frm)}' AND s.new_siparistarihi < '{utc_bound(to)}'"
        + (f" AND s.statuscode NOT IN ({_ints(ex)})" if ex else "")
    )


def books_sql(schema: str) -> str:
    """Kitap kartı: kimlik, ad, stok kodu, ilk yayın, yayınevi (planlılar dahil etkin kayıtlar)."""
    p = prefix(schema)
    # CRM harmanlaması Türkçe: «I» küçülünce «ı» olur, new_kitapid ≠ new_kitapId (207). Kolon adları CRM'deki yazımla.
    return (f"SELECT k.new_kitapId AS id, k.new_name AS ad, k.new_StokKodu AS stok_kodu, k.new_ilkyayintarihi AS ilk_yayin,"
            f" k.new_yayineviidName AS yayinevi FROM {p}new_kitap k WHERE k.statecode = 0")


def book_authors_sql(schema: str) -> str:
    p = prefix(schema)
    return f"SELECT StokKodu AS stok_kodu, Yazar AS yazar FROM {p}powerbikitap"


def authors_sql(schema: str) -> str:
    p = prefix(schema)
    return (f"SELECT c.ContactId AS id, c.FullName AS ad FROM {p}ContactBase c"
            " WHERE c.statecode = 0 AND c.new_yazarmi = 1 AND c.FullName IS NOT NULL")


# ------------------------------------------------------------------------------------------ Logo SQL


def periods_sql() -> str:
    return "SELECT FIRMNR, BEGDATE, ENDDATE FROM L_CAPIPERIOD WHERE ACTIVE = 1"


def fair_sales_sql(firm: str, frm: date, to: date, channel: str, client_codes: Optional[list[str]] = None) -> str:
    """Fuar kanalı faturalı satış satırı: cari × kitap, net adet ve net ciro (iade eksi), [frm, to) günleri."""
    f = _firm(firm)
    cc = codes(client_codes or [])
    return (
        "SELECT C.CODE AS cari_kodu, MAX(C.DEFINITION_) AS cari_adi, I.CODE AS stok_kodu, MAX(I.NAME) AS ad,"
        " SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet,"
        " SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.LINENET ELSE -S.LINENET END) AS ciro"
        f" FROM dbo.LG_{f}_01_STLINE S"
        f" JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = S.CLIENTREF"
        f" JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = S.STOCKREF"
        " WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)"
        f" AND C.SPECODE2 = '{_channel(channel)}'"
        f" AND S.DATE_ >= '{frm.isoformat()}' AND S.DATE_ < '{to.isoformat()}'"
        + (f" AND C.CODE IN ({_code_in(cc)})" if cc else "")
        + " GROUP BY C.CODE, I.CODE"
    )


def channel_clients_sql(firm: str, channel: str) -> str:
    f = _firm(firm)
    return (f"SELECT C.CODE AS kod, C.DEFINITION_ AS ad, C.CITY AS sehir, CAST(C.ACTIVE AS int) AS pasif"
            f" FROM dbo.LG_{f}_CLCARD C WHERE C.SPECODE2 = '{_channel(channel)}'")


def stock_sql(firm: str) -> str:
    """Güncel kopyada malzeme stok bakiyesi (tarih süzgeçsiz durum ölçüsü)."""
    f = _firm(firm)
    return (
        "SELECT I.CODE AS stok_kodu, SUM(CASE WHEN S.IOCODE IN (1,2) THEN S.AMOUNT ELSE -S.AMOUNT END) AS bakiye"
        f" FROM dbo.LG_{f}_01_STLINE S JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = S.STOCKREF"
        " WHERE S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.IOCODE IN (1,2,3,4)"
        " GROUP BY I.CODE"
    )


def data_end_sql(firm: str) -> str:
    return f"SELECT MAX(DATE_) AS son FROM dbo.LG_{_firm(firm)}_01_INVOICE WHERE CANCELLED = 0"


# ------------------------------------------------------------------------------------------ yardımcılar


def rows(result: Any) -> list[dict[str, Any]]:
    _, rs, truncated = result
    if truncated:
        raise SourceError("Sonuç beklenenden büyük; eksik okunmasın diye durduruldu.")
    return [{str(k).lower(): v for k, v in r.items()} for r in rs]


def s(v: Any) -> Optional[str]:
    if v is None:
        return None
    t = re.sub(r"\s+", " ", str(v)).strip()
    return t or None


def num(v: Any) -> Optional[float]:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return n if n == n else None


def ival(v: Any) -> Optional[int]:
    n = num(v)
    return int(n) if n is not None else None


def guid(v: Any) -> Optional[str]:
    t = s(v)
    return t.strip("{}").lower() if t else None


def dayiso(v: Any) -> Optional[str]:
    """CRM tarihleri UTC: saatli değer İstanbul gününe çevrilir. Logo tarihleri saatsizdir. 1900 ve öncesi boştur."""
    if v is None or v == "":
        return None
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.strip().replace(" ", "T", 1).replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(v, datetime):
        if v.hour or v.minute or v.tzinfo is not None:
            v = (v.replace(tzinfo=UTC) if v.tzinfo is None else v).astimezone(TZ)
        d = v.date()
    elif isinstance(v, date):
        d = v
    else:
        return None
    return None if d.year < 1901 else d.isoformat()


def stamp(v: Any) -> Optional[str]:
    """CRM tarih-saati → İstanbul yerel `YYYY-MM-DDTHH:MM` (saat yoksa yalnız gün)."""
    if v is None or v == "":
        return None
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.strip().replace(" ", "T", 1).replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(v, datetime):
        loc = (v.replace(tzinfo=UTC) if v.tzinfo is None else v).astimezone(TZ)
        if loc.year < 1901:
            return None
        return loc.strftime("%Y-%m-%dT%H:%M")
    if isinstance(v, date):
        return None if v.year < 1901 else v.isoformat()
    return None


def account(domain_name: Any) -> Optional[str]:
    """`TIMAS\\ahmety` ya da `ahmety@timas.com.tr` → `ahmety` (portal oturumundaki kullanıcı adı)."""
    t = s(domain_name)
    if not t:
        return None
    return t.rsplit("\\", 1)[-1].split("@", 1)[0].strip().lower() or None


def firms_by_year(period_rows: list[dict[str, Any]]) -> dict[int, str]:
    """Her yıl hangi Logo firmasında (yıllar ayrı firma numarasıdır; kopya firmalar dışlanır, çakışmada büyük numara)."""
    out: dict[int, int] = {}
    for r in period_rows:
        firm = ival(r.get("firmnr"))
        if firm is None or not firm_in_scope(firm):
            continue
        beg, end = dayiso(r.get("begdate")), dayiso(r.get("enddate"))
        if not beg or not end:
            continue
        for y in range(int(beg[:4]), int(end[:4]) + 1):
            if y not in out or firm > out[y]:
                out[y] = firm
    return {y: f"{f:03d}" for y, f in sorted(out.items())}


def year_slices(frm: date, to: date) -> list[tuple[int, date, date]]:
    """[frm, to) aralığını takvim yıllarına böler: her yıl ayrı Logo firmasında okunur."""
    out = []
    y = frm.year
    while date(y, 1, 1) < to:
        a, b = max(frm, date(y, 1, 1)), min(to, date(y + 1, 1, 1))
        if a < b:
            out.append((y, a, b))
        y += 1
    return out


def event_row(r: dict[str, Any]) -> dict[str, Any]:
    """CRM etkinlik satırı → ekran kaydı (tip sınıfı burada değil, eşlemeyle eklenir)."""
    bas, bit = dayiso(r.get("baslangic")), dayiso(r.get("bitis"))
    if bas and bit and bit < bas:
        bit = bas
    durum = ival(r.get("durum"))
    return {
        "id": guid(r.get("id")), "ad": s(r.get("ad")), "tipId": guid(r.get("tip_id")), "tip": s(r.get("tip")),
        "baslangic": bas, "bitis": bit or bas, "saat": stamp(r.get("baslangic")), "yer": s(r.get("yer")), "il": s(r.get("il")),
        "durum": durum, "durumAdi": CRM_STATUS.get(durum or 0, "—"), "iptal": durum == CRM_CANCELLED,
        "katilimci": ival(r.get("katilimci")), "satilan": ival(r.get("satilan")), "gelir": num(r.get("gelir")),
        "gider": num(r.get("gider")), "oduller": s(r.get("oduller")), "url": s(r.get("url")),
        "sorumlu": account(r.get("sorumlu_hesap")), "sorumluAd": s(r.get("sorumlu_ad")),
    }


def _close(conn: Any) -> None:
    try:
        conn.close()
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------------------------------ okuma


class Source:
    """CRM + Logo okuması. Bağlantı okuma başına açılıp kapanır; sonuç anahtar başına `ttl()` saniye bellekte.
    `fresh=True` önbelleği atlar (ekrandaki «Verileri yenile»)."""

    def __init__(self, crm_connect: Callable[[], Any], logo_connect: Callable[[], Any], schema: Callable[[], str]):
        self._crm = crm_connect
        self._logo = logo_connect
        self._schema = schema
        self._lock = threading.Lock()
        self._cache: dict[tuple, tuple[float, Any]] = {}

    # -------------------------------------------------------------- önbellek
    def _memo(self, key: tuple, fresh: bool, fn: Callable[[], Any]) -> Any:
        with self._lock:
            hit = self._cache.get(key)
            if hit and not fresh and time.time() - hit[0] < ttl():
                return hit[1]
        val = fn()
        with self._lock:
            self._cache[key] = (time.time(), val)
        return val

    def firms(self) -> dict[int, str]:
        """Önbellekteki yıl → Logo firma eşlemesi (sorgu bilgisi çalışan metni kurmak için; okuma yapmaz)."""
        with self._lock:
            hit = self._cache.get(("firms",))
        return dict(hit[1]) if hit else {}

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()

    def _crm_rows(self, sqls: list[str]) -> list[list[dict[str, Any]]]:
        conn = self._crm()
        try:
            return [rows(conn.execute(q, MAX_ROWS)) for q in sqls]
        finally:
            _close(conn)

    def _logo_rows(self, fn: Callable[[Any, dict[int, str]], Any]) -> Any:
        conn = self._logo()
        try:
            firms = self._memo(("firms",), False, lambda: firms_by_year(rows(conn.execute(periods_sql(), 10_000))))
            if not firms:
                raise SourceError("Logo dönem listesi boş.")
            return fn(conn, firms)
        finally:
            _close(conn)

    # -------------------------------------------------------------- CRM
    def types(self, fresh: bool = False) -> list[dict[str, Any]]:
        def read():
            out = []
            for r in self._crm_rows([types_sql(self._schema())])[0]:
                out.append({"id": guid(r.get("id")), "ad": s(r.get("ad")) or "—", "etkin": ival(r.get("durum")) == 0,
                            "adet": ival(r.get("adet")) or 0, "son": dayiso(r.get("son"))})
            return out
        return self._memo(("types",), fresh, read)

    def events(self, frm: date, to: date, fresh: bool = False) -> list[dict[str, Any]]:
        return self._memo(("events", frm, to), fresh,
                          lambda: [event_row(r) for r in self._crm_rows([events_sql(self._schema(), frm, to)])[0]])

    def events_by_id(self, ids: list[str]) -> list[dict[str, Any]]:
        ids = guids(ids)
        out: list[dict[str, Any]] = []
        for i in range(0, len(ids), IN_CHUNK):
            out += [event_row(r) for r in self._crm_rows([events_by_id_sql(self._schema(), ids[i:i + IN_CHUNK])])[0]]
        return out

    def links(self, ids: list[str]) -> dict[str, dict[str, list[dict[str, Any]]]]:
        """Etkinlik kimliği → {"yazarlar": [...], "kitaplar": [...]}."""
        ids = guids(ids)
        out: dict[str, dict[str, list[dict[str, Any]]]] = {i: {"yazarlar": [], "kitaplar": []} for i in ids}
        for i in range(0, len(ids), IN_CHUNK):
            part = ids[i:i + IN_CHUNK]
            authors, books = self._crm_rows([event_authors_sql(self._schema(), part), event_books_sql(self._schema(), part)])
            for r in authors:
                e = guid(r.get("etkinlik_id"))
                if e in out:
                    out[e]["yazarlar"].append({"id": guid(r.get("kisi_id")), "ad": s(r.get("ad"))})
            for r in books:
                e = guid(r.get("etkinlik_id"))
                if e in out:
                    out[e]["kitaplar"].append({"id": guid(r.get("kitap_id")), "ad": s(r.get("ad")), "stokKodu": s(r.get("stok_kodu"))})
        return out

    def author_events(self, contact_id: str, frm: date, to: date) -> list[dict[str, Any]]:
        return [event_row(r) for r in self._crm_rows([author_events_sql(self._schema(), contact_id, frm, to)])[0]]

    def orders(self, frm: date, to: date, types: list[int], excluded: list[int], fresh: bool = False) -> list[dict[str, Any]]:
        def read():
            out = []
            for r in self._crm_rows([orders_sql(self._schema(), frm, to, types, excluded)])[0]:
                t = ival(r.get("tip"))
                out.append({"id": guid(r.get("id")), "no": s(r.get("no")), "tip": t, "tipAdi": ORDER_TYPES.get(t or 0, str(t)),
                            "durum": ival(r.get("durum")), "tarih": dayiso(r.get("tarih")), "tutar": num(r.get("tutar")) or 0.0,
                            "adet": num(r.get("adet")) or 0.0, "firma": s(r.get("firma")), "cariKodu": s(r.get("cari_kodu"))})
            return out
        return self._memo(("orders", frm, to, tuple(types), tuple(excluded)), fresh, read)

    def books(self, fresh: bool = False) -> dict[str, dict[str, Any]]:
        """Stok kodu (büyük harf) → kitap kartı."""
        def read():
            books, authors = self._crm_rows([books_sql(self._schema()), book_authors_sql(self._schema())])
            yazar = {str(r.get("stok_kodu") or "").strip().upper(): s(r.get("yazar")) for r in authors if r.get("stok_kodu")}
            out: dict[str, dict[str, Any]] = {}
            for r in books:
                code = (s(r.get("stok_kodu")) or "").upper()
                if not code:
                    continue
                ilk = dayiso(r.get("ilk_yayin"))
                if ilk and ilk < "1950":
                    ilk = None
                cur = out.get(code)
                if cur and cur.get("ilkYayin") and (not ilk or cur["ilkYayin"] <= ilk):
                    continue
                out[code] = {"id": guid(r.get("id")), "stokKodu": s(r.get("stok_kodu")), "ad": s(r.get("ad")),
                             "yazar": yazar.get(code), "yayinevi": s(r.get("yayinevi")), "ilkYayin": ilk}
            return out
        return self._memo(("books",), fresh, read)

    def authors(self, fresh: bool = False) -> list[dict[str, Any]]:
        return self._memo(("authors",), fresh, lambda: [
            {"id": guid(r.get("id")), "ad": s(r.get("ad"))} for r in self._crm_rows([authors_sql(self._schema())])[0]
            if s(r.get("ad"))])

    # -------------------------------------------------------------- Logo
    def fair_sales(self, frm: date, to: date, channel: str, client_codes: Optional[list[str]] = None,
                   fresh: bool = False) -> dict[str, Any]:
        """Fuar kanalı satışı [frm, to): satırlar (cari × kitap) ve okunamayan yılların uyarısı."""
        cc = tuple(codes(client_codes or []))

        def read():
            def run(conn, firms):
                out: list[dict[str, Any]] = []
                warn: list[str] = []
                sqls: list[str] = []
                for y, a, b in year_slices(frm, to):
                    firm = firms.get(y)
                    if not firm:
                        warn.append(f"Logo'da {y} yılının dönemi yok; o yılın fuar satışı okunmadı.")
                        continue
                    q = fair_sales_sql(firm, a, b, channel, list(cc))
                    sqls.append(q)
                    for r in rows(conn.execute(q, MAX_ROWS)):
                        out.append({"cariKodu": s(r.get("cari_kodu")), "cariAdi": s(r.get("cari_adi")),
                                    "stokKodu": s(r.get("stok_kodu")), "ad": s(r.get("ad")),
                                    "adet": num(r.get("adet")) or 0.0, "ciro": num(r.get("ciro")) or 0.0})
                return {"rows": out, "warnings": warn, "sql": sqls}
            return self._logo_rows(run)
        return self._memo(("fair_sales", frm, to, channel, cc), fresh, read)

    def channel_clients(self, channel: str, fresh: bool = False) -> list[dict[str, Any]]:
        def read():
            def run(conn, firms):
                return [{"kod": s(r.get("kod")), "ad": s(r.get("ad")), "sehir": s(r.get("sehir")), "pasif": bool(ival(r.get("pasif")))}
                        for r in rows(conn.execute(channel_clients_sql(firms[max(firms)], channel), MAX_ROWS)) if s(r.get("kod"))]
            return self._logo_rows(run)
        return self._memo(("clients", channel), fresh, read)

    def stock(self, fresh: bool = False) -> dict[str, float]:
        def read():
            def run(conn, firms):
                out: dict[str, float] = {}
                for r in rows(conn.execute(stock_sql(firms[max(firms)]), MAX_ROWS)):
                    code = s(r.get("stok_kodu"))
                    if code:
                        out[code.upper()] = float(r.get("bakiye") or 0)
                return out
            return self._logo_rows(run)
        return self._memo(("stock",), fresh, read)

    def data_end(self, fresh: bool = False) -> Optional[str]:
        def read():
            def run(conn, firms):
                r = rows(conn.execute(data_end_sql(firms[max(firms)]), 10))
                return dayiso(r[0].get("son")) if r else None
            return self._logo_rows(run)
        return self._memo(("data_end",), fresh, read)


def istanbul_today() -> date:
    return datetime.now(TZ).date()


def plus_days(d: date, n: int) -> date:
    return d + timedelta(days=n)
