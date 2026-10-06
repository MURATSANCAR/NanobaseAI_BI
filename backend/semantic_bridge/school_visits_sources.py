"""M31 Okul tanıtım ve ziyaret: CRM ve Logo okuması (yalnız okuma).

Kaynaklar (analiz `docs/analiz/kullanici-ihtiyaclari/M31-okul-tanitim-ziyaret.md` §6, §13):

- **Okul listesi ve profili** — CRM `new_ziyaretyerleriBase` (68.713 ziyaret yeri; kurum tipi 1 = Okul, 3 = Üniversite …).
  Öğrenci/öğretmen/derslik/kitap sayısı **metin** kolonudur; sayıya çevirme SQL'de `TRY_CAST(... AS int)` ile yapılır
  (kabul testi aynı ifadeyi kullanır; çevrilemeyen değer «bilinmiyor» kalır, 0 yazılmaz). İl/ilçe `new_illerBase`,
  `new_ilceBase`; ilin müşteri temsilcisi `new_illerBase.new_musteritemsilcisi`.
- **Geçmiş okul ziyaretleri** — CRM `new_etkinlikBase`, ziyaret tipi 1 MEB okulları / 2 özel okullar / 3 üniversiteler;
  şekli 1 «Cari ile ziyaret» (aracı müşteri = bayi) / 2 doğrudan; durum 1 Planlandı / 100000002 Tamamlandı /
  100000000 İptal. Okul bağı `new_ZiyaretYeri` (kayıt), yoksa serbest metin `new_Okul`.
- **Okul örneği / öğretmen örneği / okul satışı** — CRM `new_siparisBase` tip 10 / 11 / 13.
- **Bayi ve kitapçı** — CRM `AccountBase` (`new_FirmaKanal` 100000008 Bayi, 100000001 Kitapçı; Logo bağı
  `new_CariKodu` ve `new_logicalref`, il `new_cariyeaitil`, ilçe birincil adresten `new_adresBase.new_ilceid`);
  Logo `CLCARD` (CITY, TOWN, telefon). Bayinin satışı Logo faturalı satış satırından (`STLINE`, `INVOICEREF <> 0`,
  TRCODE 7/8/9 − 2/3), yıl kopyası `L_CAPIPERIOD`'dan; cari, yıllar arasında cari koduyla eşlenir.
- **Katalog** — CRM `new_kitapBase` (sınıf bitleri `new_1Sinif…new_12Sinif`, `new_OkulOncesi`, yaş bitleri, ağırlıklı
  hedef yaş aralığı, fiyat, sayfa); Logo stok bakiyesi (güncel kopya, tarih filtresiz: IOCODE 1/2 giriş, 3/4 çıkış)
  ve geçerli satış fiyatı (`PRCLIST` PTYPE 2, ACTIVE 0, bugün BEGDATE–ENDDATE arasında).
- **Kişiler** — CRM `SystemUserBase` (DomainName → AD hesabı, ad, iç e-posta).

CRM tarihleri UTC saklanır; ekranda İstanbul gününe çevrilir. CRM'e ve Logo'ya hiçbir şey yazılmaz.

Hız (2026-09-29): bir okuma 35–177 sn sürüyor (test sunucusu ölçümü); istek onu beklemez. Son okuma bellekte ve portal
tablosunda (`semantic_school_snapshot`; köprü yeniden başlasa da kaybolmaz) durur, istek onu hemen alır. `TTL`'den
eskiyse ya da «Verileri yenile» (X-Data-Refresh) geldiyse yenisi ARKADA okunur; okuma bitince okul dizini ve puanlar
arkada hazırlanır, modülün hazır cevapları düşer. İstek yalnız hiç okuma yokken (ilk kurulum ya da okuma sorgularının
şekli değişti) kaynağı bekler; gece zamanlayıcısı (`run-due`) da bekleyerek okur.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import threading
import time
import uuid
import zlib
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from semantic_layer.firm_scope import firm_in_scope
from semantic_bridge import crm_labels

log = logging.getLogger("semantic.school_visits.sources")
TZ = ZoneInfo("Europe/Istanbul")
UTC = ZoneInfo("UTC")
TTL = int(os.environ.get("SCHOOLS_CACHE_SEC", "600"))
#: «Verileri yenile»: bu kadar saniye içinde başlamış okuma varken yenisi açılmaz (ekranın 5–6 ucu aynı anda ister).
FRESH_MIN_SEC = int(os.environ.get("SCHOOLS_FRESH_MIN_SEC", "60"))
MAX_ROWS = 3_000_000  # güvenlik ağı; aşılırsa hata verilir, sessizce kesilmez
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_FIRM = re.compile(r"^[0-9]{3}$")

#: Ziyaret tipi (etkinlik `new_ziyarettipi`) — okul ziyareti sayılanlar.
VISIT_TYPES = crm_labels.Labels("new_etkinlik", "new_ziyarettipi", {
    1: "MEB okulları", 2: "Özel okullar", 3: "Üniversiteler",
}, fixed=True)
VISIT_FORMS = crm_labels.Labels("new_etkinlik", "new_ziyaretsekli", {1: "Cari ile ziyaret", 2: "Doğrudan ziyaret"})
VISIT_STATUS = crm_labels.Labels("new_etkinlik", "statuscode", {
    1: "Planlandı", 100000002: "Tamamlandı", 100000000: "İptal edildi",
})
VISIT_DONE = 100000002
#: Sipariş tipi: okul örneği, öğretmen örneği, okul satışı.
ORDER_TYPES = {10: "Okul örneği", 11: "Öğretmen örneği", 13: "Okul satışı"}
#: Firma kanalı: bayi ve kitapçı okul yönlendirmesinde aday olur.
DEALER_CHANNELS = {100000008: "Bayi", 100000001: "Kitapçı"}
KURUM_TIPI = crm_labels.Labels("new_ziyaretyerleri", "new_kurumtipi", {
    1: "Okul", 3: "Üniversite", 5: "Milli Eğitim", 6: "Belediye", 7: "Kaymakamlık", 8: "Valilik", 4: "Diğer",
})
KURUM_TURU = crm_labels.Labels("new_ziyaretyerleri", "new_kurumturu", {1: "Devlet", 2: "Özel", 3: "Vakıf"})
OKUL_TURU = crm_labels.Labels("new_ziyaretyerleri", "new_okulturu", {
    1: "Okul Öncesi", 2: "Anadolu Lisesi", 3: "Eğitim Merkezleri", 4: "Fen Lisesi", 5: "Fen ve Teknoloji Lisesi",
    6: "İmam Hatip", 7: "Meslek Lisesi", 8: "Sosyal Bilimler Lisesi", 9: "Temel Eğitim", 10: "Yatılı Bölge Okulu",
})
KADEME = crm_labels.Labels("new_ziyaretyerleri", "new_okulkademesi", {
    1: "Anaokulu", 2: "Bilim ve Sanat Merkezi", 3: "İlkokul", 4: "Lise", 5: "Ortaokul",
    6: "Rehberlik ve Araştırma Merkezi",
})
#: Kitabın yayıncılık statüsü: bu statülerdeki kitap tanıtım kataloğuna girmez (iptal, ertelendi, artık bizim değil,
#: hakları devredildi). Baskısı biten (YS07) stokta kaldıkça girer — stok süzgeci ayrıca uygulanır.
BOOK_EXCLUDED_STATUS = (100000001, 100000003, 100000005, 100000006)


class SourceError(RuntimeError):
    """Kişiye gösterilecek düz Türkçe hata (kaynak okunamadı)."""


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


def _in(values: Any) -> str:
    return ", ".join(str(int(v)) for v in values)


# ------------------------------------------------------------------------------------------ CRM SQL


def schools_sql(schema: str, kurum_tipleri: tuple[int, ...] = (1,)) -> str:
    """Etkin ziyaret yerleri; sayılar TRY_CAST ile (çevrilemeyen NULL = bilinmiyor)."""
    p = prefix(schema)
    return (
        "SELECT z.new_ziyaretyerleriId AS id, z.new_id AS kod, z.new_okuladi AS okul_adi, z.new_kurumadi AS kurum_adi,"
        " CAST(z.new_KurumTipi AS int) AS kurum_tipi, CAST(z.new_kurumturu AS int) AS kurum_turu,"
        " CAST(z.new_okulturu AS int) AS okul_turu, CAST(z.new_okulkademesi AS int) AS kademe,"
        " TRY_CAST(z.new_renciSays AS int) AS ogrenci, TRY_CAST(z.new_ogretmensayisi AS int) AS ogretmen,"
        " TRY_CAST(z.new_dersliksayisi AS int) AS derslik, TRY_CAST(z.new_kitapsayisi AS int) AS kitap_sayisi,"
        " TRY_CAST(z.new_toplamogrencisayisi AS int) AS toplam_ogrenci,"
        " z.new_KonferansSalonu AS konferans, z.new_Telefon AS telefon, z.new_acikadres AS adres,"
        " z.new_ili AS il_id, i.new_name AS il, z.new_ilcesi AS ilce_id, c.new_name AS ilce, c.new_ilcekodu AS ilce_kodu,"
        " su.DomainName AS sahip_hesap, iu.DomainName AS il_temsilci_hesap, z.ModifiedOn AS degisti, z.CreatedOn AS olustu"
        f" FROM {p}new_ziyaretyerleriBase z"
        f" LEFT JOIN {p}new_illerBase i ON i.new_illerId = z.new_ili"
        f" LEFT JOIN {p}new_ilceBase c ON c.new_ilceId = z.new_ilcesi"
        f" LEFT JOIN {p}SystemUserBase su ON su.SystemUserId = z.OwnerId"
        f" LEFT JOIN {p}SystemUserBase iu ON iu.SystemUserId = i.new_musteritemsilcisi"
        f" WHERE z.statecode = 0 AND z.new_KurumTipi IN ({_in(kurum_tipleri)})"
    )


def visits_sql(schema: str) -> str:
    """Okul ziyareti tipli bütün etkinlikler (tarih süzgeçsiz: okul kartındaki geçmiş sayısı kabul testiyle aynı)."""
    p = prefix(schema)
    return (
        "SELECT e.new_etkinlikId AS id, e.new_name AS ad, CAST(e.new_ziyarettipi AS int) AS tip,"
        " CAST(e.new_ziyaretsekli AS int) AS sekil, CAST(e.statuscode AS int) AS durum,"
        " e.new_ZiyaretYeri AS ziyaret_yeri, e.new_Okul AS okul_metni, e.new_AracMteriId AS bayi_id, a.Name AS bayi_adi,"
        " a.new_CariKodu AS bayi_kodu, e.new_GercZiyTarihi AS gerceklesen, e.new_BalangTarihi AS baslangic,"
        " e.new_katilimcisayisi AS katilimci, e.new_SatilanKitapAd AS satilan, e.new_DagitilanKumbaraAdedi AS kumbara,"
        " e.new_il AS il_id, e.new_ilce AS ilce_id, su.DomainName AS sorumlu_hesap, su.FullName AS sorumlu_ad,"
        " ou.DomainName AS sahip_hesap, e.CreatedOn AS olustu"
        f" FROM {p}new_etkinlikBase e"
        f" LEFT JOIN {p}AccountBase a ON a.AccountId = e.new_AracMteriId"
        f" LEFT JOIN {p}SystemUserBase su ON su.SystemUserId = e.new_sorumlusu"
        f" LEFT JOIN {p}SystemUserBase ou ON ou.SystemUserId = e.OwnerId"
        f" WHERE e.statecode = 0 AND e.new_ziyarettipi IN ({_in(VISIT_TYPES)})"
    )


def dealer_history_sql(schema: str) -> str:
    """Geçmiş okul–bayi bağı: «Cari ile ziyaret» etkinliklerinde ziyaret yeri + aracı müşteri (kabul testi 6)."""
    p = prefix(schema)
    return (
        "SELECT e.new_ZiyaretYeri AS ziyaret_yeri, e.new_AracMteriId AS bayi_id, COUNT(*) AS adet,"
        " MAX(COALESCE(e.new_GercZiyTarihi, e.new_BalangTarihi, e.CreatedOn)) AS son"
        f" FROM {p}new_etkinlikBase e"
        " WHERE e.statecode = 0 AND e.new_ziyaretsekli = 1 AND e.new_AracMteriId IS NOT NULL AND e.new_ZiyaretYeri IS NOT NULL"
        " GROUP BY e.new_ZiyaretYeri, e.new_AracMteriId"
    )


def orders_sql(schema: str, since: date) -> str:
    p = prefix(schema)
    return (
        "SELECT s.new_siparisId AS id, s.new_name AS no, CAST(s.new_siparistipi AS int) AS tip, CAST(s.statuscode AS int) AS durum,"
        " s.new_siparistarihi AS tarih, s.CreatedOn AS olustu, s.new_firmaid AS firma_id, a.Name AS firma, a.new_CariKodu AS cari_kodu,"
        " a.new_cariyeaitil AS il_id, s.new_siparisadeti AS adet, s.new_indirimlitoplamtutar AS tutar"
        f" FROM {p}new_siparisBase s"
        f" LEFT JOIN {p}AccountBase a ON a.AccountId = s.new_firmaid"
        f" WHERE s.statecode = 0 AND s.new_siparistipi IN ({_in(ORDER_TYPES)}) AND s.CreatedOn >= '{since.isoformat()}'"
    )


def dealers_sql(schema: str) -> str:
    """Etkin bayi ve kitapçılar; ilçe birincil (yoksa ilk) adresten."""
    p = prefix(schema)
    return (
        "SELECT a.AccountId AS id, a.Name AS ad, a.new_CariKodu AS cari_kodu, a.new_logicalref AS logicalref,"
        " CAST(a.new_FirmaKanal AS int) AS kanal, a.new_cariyeaitil AS il_id, i.new_name AS il,"
        " ad.new_ilceid AS ilce_id, c.new_name AS ilce, a.Telephone1 AS telefon, a.EMailAddress1 AS eposta,"
        " ou.DomainName AS sahip_hesap"
        f" FROM {p}AccountBase a"
        f" LEFT JOIN {p}new_illerBase i ON i.new_illerId = a.new_cariyeaitil"
        f" OUTER APPLY (SELECT TOP 1 x.new_ilceid FROM {p}new_adresBase x WHERE x.new_Firma = a.AccountId AND x.statecode = 0"
        " ORDER BY x.new_birincil DESC, x.CreatedOn) ad"
        f" LEFT JOIN {p}new_ilceBase c ON c.new_ilceId = ad.new_ilceid"
        f" LEFT JOIN {p}SystemUserBase ou ON ou.SystemUserId = a.OwnerId"
        f" WHERE a.StateCode = 0 AND a.new_FirmaKanal IN ({_in(DEALER_CHANNELS)})"
    )


_GRADE_COLS = ["new_OkulOncesi"] + [f"new_{n}Sinif" for n in range(1, 13)]
_AGE_COLS = [f"new_{n}Yas" for n in range(1, 15)]


def books_sql(schema: str) -> str:
    p = prefix(schema)
    bits = ", ".join(f"CAST(k.{c} AS int) AS {c.lower()}" for c in _GRADE_COLS + _AGE_COLS)
    return (
        "SELECT k.new_kitapId AS id, k.new_name AS ad, k.new_StokKodu AS stok_kodu, k.new_PerakendeBirimFiyat AS crm_fiyat,"
        " k.new_sayfasayisi AS sayfa, k.new_yaslartext AS yaslar, k.new_siniflartext AS siniflar,"
        " CAST(k.new_hedefkitle AS int) AS hedef_kitle, k.new_hedefkitleyasbaslangic AS yas_bas, k.new_hedefkitleyasbitis AS yas_bit,"
        " k.new_turlertext AS turler, CAST(k.new_kitap_yayincilikstatusu AS int) AS statu,"
        f" {bits}"
        f" FROM {p}new_kitapBase k"
        " WHERE k.statecode = 0 AND k.new_StokKodu IS NOT NULL AND k.new_StokKodu <> ''"
        f" AND ISNULL(CAST(k.new_kitap_yayincilikstatusu AS int), 0) NOT IN ({_in(BOOK_EXCLUDED_STATUS)})"
    )


def users_sql(schema: str) -> str:
    p = prefix(schema)
    return (f"SELECT u.SystemUserId AS id, u.DomainName AS hesap, u.FullName AS ad, u.InternalEMailAddress AS eposta"
            f" FROM {p}SystemUserBase u WHERE u.DomainName IS NOT NULL AND u.DomainName <> ''")


def districts_sql(schema: str) -> str:
    p = prefix(schema)
    return (f"SELECT c.new_ilceId AS id, c.new_name AS ilce, c.new_ilcekodu AS kod, i.new_illerId AS il_id, i.new_name AS il"
            f" FROM {p}new_ilceBase c LEFT JOIN {p}new_illerBase i ON i.new_illerId = c.new_ilid WHERE c.statecode = 0")


# ------------------------------------------------------------------------------------------ Logo SQL


def periods_sql() -> str:
    return "SELECT FIRMNR, BEGDATE, ENDDATE FROM L_CAPIPERIOD WHERE ACTIVE = 1"


def stock_sql(firm: str) -> str:
    """Güncel kopyada malzeme stok bakiyesi (tarih filtresiz durum ölçüsü; katalog metriği «stok bakiyesi»)."""
    f = _firm(firm)
    return (
        "SELECT I.CODE AS stok_kodu, SUM(CASE WHEN S.IOCODE IN (1,2) THEN S.AMOUNT ELSE -S.AMOUNT END) AS bakiye"
        f" FROM dbo.LG_{f}_01_STLINE S JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = S.STOCKREF"
        " WHERE S.LINETYPE = 0 AND S.CANCELLED = 0 AND S.IOCODE IN (1,2,3,4)"
        " GROUP BY I.CODE"
    )


def price_sql(firm: str, day: date) -> str:
    """Bugün geçerli satış fiyat listeleri (PTYPE 2, ACTIVE 0, TL). Genel liste = cari özel kodu boş olan."""
    f = _firm(firm)
    d = day.isoformat()
    return (
        "SELECT I.CODE AS stok_kodu, P.PRICE AS fiyat, P.CLSPECODE AS cari_kodu_ozel, P.PRIORITY AS oncelik, P.CODE AS liste"
        f" FROM dbo.LG_{f}_PRCLIST P JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = P.CARDREF"
        f" WHERE P.PTYPE = 2 AND P.ACTIVE = 0 AND P.CURRENCY IN (0, 160) AND P.BEGDATE <= '{d}' AND P.ENDDATE >= '{d}'"
    )


def clcard_sql(firm: str) -> str:
    f = _firm(firm)
    return (f"SELECT C.LOGICALREF AS ref, C.CODE AS kod, C.DEFINITION_ AS ad, C.CITY AS sehir, C.TOWN AS ilce,"
            f" C.TELNRS1 AS telefon FROM dbo.LG_{f}_CLCARD C WHERE C.ACTIVE = 0")


def dealer_sales_sql(firm: str, since: date, until: date) -> str:
    """Cari kodu × stok kodu: faturalı net adet (iade eksi) — bayinin kademeye uygun kitap satışı için."""
    f = _firm(firm)
    return (
        "SELECT C.CODE AS cari_kodu, I.CODE AS stok_kodu,"
        " SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet"
        f" FROM dbo.LG_{f}_01_STLINE S JOIN dbo.LG_{f}_ITEMS I ON I.LOGICALREF = S.STOCKREF"
        f" JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = S.CLIENTREF"
        " WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)"
        f" AND S.DATE_ >= '{since.isoformat()}' AND S.DATE_ < '{until.isoformat()}'"
        " GROUP BY C.CODE, I.CODE"
    )


def dealer_months_sql(firm: str, since: date, until: date) -> str:
    """Cari kodu × ay: faturalı net adet ve net ciro (VATMATRAH) — ziyaret sonrası dönüşüm karşılaştırması için."""
    f = _firm(firm)
    return (
        "SELECT C.CODE AS cari_kodu, YEAR(SH.DATE_) * 100 + MONTH(SH.DATE_) AS ay,"
        " SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.AMOUNT ELSE -S.AMOUNT END) AS adet,"
        " SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN S.VATMATRAH ELSE -S.VATMATRAH END) AS ciro"
        f" FROM dbo.LG_{f}_01_STLINE S"
        f" JOIN dbo.LG_{f}_01_INVOICE SH ON SH.LOGICALREF = S.INVOICEREF AND SH.CANCELLED = 0"
        f" JOIN dbo.LG_{f}_CLCARD C ON C.LOGICALREF = S.CLIENTREF"
        " WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)"
        f" AND SH.DATE_ >= '{since.isoformat()}' AND SH.DATE_ < '{until.isoformat()}'"
        " GROUP BY C.CODE, YEAR(SH.DATE_) * 100 + MONTH(SH.DATE_)"
    )


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
    return t.lower() if t else None


def dayiso(v: Any) -> Optional[str]:
    """CRM tarihleri UTC (İstanbul gece yarısı = önceki gün 21:00): saatli değer İstanbul gününe çevrilir.
    Logo tarihleri saatsizdir. 1900 ve öncesi «boş» değerdir."""
    if v is None or v == "":
        return None
    if isinstance(v, str):
        try:
            v = datetime.fromisoformat(v.strip().replace(" ", "T", 1).replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(v, datetime):
        if v.hour or v.minute:
            v = (v.replace(tzinfo=UTC) if v.tzinfo is None else v).astimezone(TZ)
        d = v.date()
    elif isinstance(v, date):
        d = v
    else:
        return None
    return None if d.year < 1901 else d.isoformat()


def firms_by_year(period_rows: list[dict[str, Any]]) -> dict[int, str]:
    """Her yıl hangi Logo firmasında (yıllar ayrı firma numarasıdır; 015/016 kopyaları dışlanır)."""
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


class _Logged:
    """Sorgu bilgisi: bağlantının çalıştırdığı her SQL'i (metin, satır, süre, an) kaydeder; okumaya karışmaz."""

    def __init__(self, conn_name: str, conn: Any, sink: list[dict[str, Any]]):
        self._name, self._conn, self._sink = conn_name, conn, sink
        cfg = getattr(conn, "cfg", None)
        # Yalnız veritabanı ADI (sorgu bilgisinde USE satırı); bağlantının öteki değerleri kayda girmez.
        self._db = cfg.get("database") if isinstance(cfg, dict) and isinstance(cfg.get("database"), str) else None

    def execute(self, sql: str, limit: int, key: str = "") -> Any:
        t = time.monotonic()
        res = self._conn.execute(sql, limit)
        try:
            n = len(res[1])
        except Exception:  # noqa: BLE001
            n = None
        self._sink.append({"conn": self._name, "db": self._db, "key": key, "sql": sql, "rows": n, "dbMs": int((time.monotonic() - t) * 1000),
                           "at": datetime.now(TZ).isoformat(timespec="seconds")})
        return res

    def close(self) -> None:
        self._conn.close()


def _close(conn: Any) -> None:
    try:
        conn.close()
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------------------------------ okuma


# ------------------------------------------------------------------------------------------ okumanın saklanması

#: Paketleme sürümü; `shape()` ile birlikte saklanan okumanın biçimini belirler.
PACK_VERSION = "1"


def shape() -> str:
    """Okuma sorgularının ŞEKLİ (sabit girdilerle üretilen SQL metinleri) + paketleme sürümü. Sorgular değişince saklanan
    eski okuma kullanılmaz (yeni kolon eksik kalmasın); tarih ve ayar değişimi şekli değiştirmez (onu `TTL` tazeler)."""
    d = date(2000, 1, 1)
    parts = [schools_sql("S.dbo", (1,)), visits_sql("S.dbo"), dealer_history_sql("S.dbo"), orders_sql("S.dbo", d),
             dealers_sql("S.dbo"), books_sql("S.dbo"), users_sql("S.dbo"), districts_sql("S.dbo"), periods_sql(),
             stock_sql("000"), price_sql("000", d), clcard_sql("000"), dealer_sales_sql("000", d, d),
             dealer_months_sql("000", d, d), PACK_VERSION]
    return hashlib.sha1("\n".join(parts).encode("utf-8")).hexdigest()


_TAGS = ("$n", "$t", "$d", "$u", "$b")


def _enc(o: Any) -> Any:
    """JSON'un tanımadığı değer tür etiketiyle yazılır; açılınca aynı tür, aynı değer (Decimal metinle, tam)."""
    if isinstance(o, Decimal):
        return {"$n": str(o)}
    if isinstance(o, datetime):
        return {"$t": o.isoformat()}
    if isinstance(o, date):
        return {"$d": o.isoformat()}
    if isinstance(o, uuid.UUID):
        return {"$u": str(o)}
    if isinstance(o, (bytes, bytearray)):
        return {"$b": base64.b64encode(bytes(o)).decode("ascii")}
    raise TypeError(f"okuma saklanamıyor: {type(o).__name__}")


def _dec(d: dict[str, Any]) -> Any:
    if len(d) == 1:
        k, v = next(iter(d.items()))
        if k in _TAGS and isinstance(v, str):
            if k == "$n":
                return Decimal(v)
            if k == "$t":
                return datetime.fromisoformat(v)
            if k == "$d":
                return date.fromisoformat(v)
            if k == "$u":
                return uuid.UUID(v)
            return base64.b64decode(v)
    return d


_CHUNK = 50_000


def pack(snap: dict[str, Any]) -> bytes:
    """Okuma → sıkıştırılmış JSON. Satırlar olduğu gibi (sayı, tarih, GUID türüyle) saklanır: saklanan okumadan kurulan
    dizin ve rakamlar canlı okumadakiyle birebir aynıdır. Yıl → firma sözlüğünün anahtarı sayıdır; çift listesi yazılır.
    Büyük listeler (bayi × kitap satışı milyonlarca satır olabilir) parça parça yazılır: bellekte tam JSON metni oluşmaz."""
    body = dict(snap)
    body["firms"] = [[k, v] for k, v in (snap.get("firms") or {}).items()]
    z = zlib.compressobj(3)
    out: list[bytes] = []

    def put(text: str) -> None:
        out.append(z.compress(text.encode("utf-8")))

    def dump(v: Any) -> str:
        return json.dumps(v, default=_enc, ensure_ascii=False, separators=(",", ":"))

    put("{")
    for i, (k, v) in enumerate(body.items()):
        put(("," if i else "") + json.dumps(str(k)) + ":")
        if isinstance(v, list) and len(v) > _CHUNK:
            put("[")
            for j in range(0, len(v), _CHUNK):
                put(("," if j else "") + dump(v[j:j + _CHUNK])[1:-1])
            put("]")
        else:
            put(dump(v))
    put("}")
    out.append(z.flush())
    return b"".join(out)


def unpack(data: bytes) -> dict[str, Any]:
    body = json.loads(zlib.decompress(data).decode("utf-8"), object_hook=_dec)
    body["firms"] = {int(k): v for k, v in body.get("firms") or []}
    return body


class Source:
    """CRM + Logo okuması. Bağlantı okuma başına açılıp kapanır; aynı anda tek okuma.

    İstek okumayı beklemez: bellekteki (yoksa saklanan) son okuma hemen döner; `TTL`'den eskiyse ya da «Verileri
    yenile» geldiyse yenisi arkada okunur. `store` (isteğe bağlı) `load() → okuma | None` ve `save(okuma)` verir: köprü
    yeniden başlasa da son okuma kaybolmaz. Logo'ya ulaşılamazsa CRM ile devam edilir, uyarı ekranda yazılır."""

    def __init__(self, crm_connect: Callable[[], Any], logo_connect: Callable[[], Any], schema: Callable[[], str],
                 settings: Callable[[], dict[str, Any]], store: Any = None):
        self._crm = crm_connect
        self._logo = logo_connect
        self._schema = schema
        self._settings = settings
        self._store = store
        self._lock = threading.Lock()          # canlı okuma: aynı anda tek
        self._restore_lock = threading.Lock()
        self._bg_lock = threading.Lock()
        self._restored = False
        self._snap: Optional[dict[str, Any]] = None
        self._at = 0.0
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self._bg: Optional[threading.Thread] = None
        self.started = 0.0                     # son okumanın başladığı an (arkadaki dahil)
        self.last_error: Optional[str] = None

    def on_read(self, fn: Callable[[dict[str, Any]], None]) -> None:
        """Yeni okuma (canlı ya da saklanandan açılan) geldiğinde çağrılır; okuyan iş parçacığında çalışır."""
        self._listeners.append(fn)

    def cached(self) -> Optional[dict[str, Any]]:
        return self._snap

    @property
    def busy(self) -> bool:
        """Arkada okuma sürüyor mu."""
        return bool(self._bg is not None and self._bg.is_alive())

    def snapshot(self, fresh: bool = False, wait: bool = False) -> dict[str, Any]:
        """Son okuma hemen döner. Eskiyse (`TTL`) ya da `fresh` ise yenisi arkada okunur. Kaynak yalnız hiç okuma yokken
        ya da `wait` (zamanlayıcı) istendiğinde beklenir."""
        snap = self._snap if self._snap is not None else self.restore()
        if snap is None or wait:
            return self._read_now(since=time.time() if wait else None)
        now = time.time()
        if now - self._at >= TTL or (fresh and now - self.started >= FRESH_MIN_SEC):
            self.refresh_async()
        return snap

    def restore(self) -> Optional[dict[str, Any]]:
        """Saklanan son okuma (süreçte bir kez denenir; şekli bugünkü sorgulardan farklıysa `store` vermez)."""
        if self._store is None or self._restored:
            return self._snap
        with self._restore_lock:
            if self._restored:
                return self._snap
            try:
                snap = self._store.load()
            except Exception as e:  # noqa: BLE001 — saklanan okuma açılamazsa canlı okunur
                log.warning("school_visits: saklanan okuma açılamadı: %s", e)
                snap = None
            if snap is not None and self._snap is None:
                # Dinleyiciye haber verilmez: saklanan okuma yeni veri değildir (hazır cevaplar düşmez).
                self._snap, self._at = snap, float(snap.get("at") or 0.0)
            self._restored = True
            return self._snap

    def refresh_async(self) -> bool:
        """Arkada yeni okuma başlatır; okuma sürüyorsa yenisini açmaz."""
        with self._bg_lock:
            if self._bg is not None and self._bg.is_alive():
                return False
            self.started = time.time()
            self._bg = threading.Thread(target=self._bg_read, args=(self.started,), name="schools-read", daemon=True)
            self._bg.start()
            return True

    def _bg_read(self, since: float) -> None:
        try:
            self._read_now(since=since)
            self.last_error = None
        except Exception as e:  # noqa: BLE001 — eski okuma yerinde kalır, ekran onu gösterir
            self.last_error = str(e)
            log.warning("school_visits: arka plan okuması başarısız: %s", e)

    def _read_now(self, since: Optional[float] = None) -> dict[str, Any]:
        """Tek okuma. Beklerken başka çağrı okumayı bitirdiyse (`since`'ten sonra) onun sonucu döner."""
        with self._lock:
            if self._snap is not None and (since is None or self._at >= since):
                return self._snap
            self.started = time.time()
            snap = self.read()
            self._snap, self._at = snap, float(snap.get("at") or time.time())
            self._notify(snap)                  # önce dizin ve puan (ekran), sonra saklama
            if self._store is not None:
                try:
                    self._store.save(snap)
                except Exception as e:  # noqa: BLE001 — saklanamasa da bellekte kullanılır
                    log.warning("school_visits: okuma saklanamadı: %s", e)
            return snap

    def _notify(self, snap: dict[str, Any]) -> None:
        for fn in self._listeners:
            try:
                fn(snap)
            except Exception as e:  # noqa: BLE001
                log.warning("school_visits: okuma sonrası hazırlık başarısız: %s", e)

    def read(self) -> dict[str, Any]:
        st = self._settings()
        schema = self._schema()
        today = datetime.now(TZ).date()
        since = date.fromisoformat(st["historyFrom"])
        warnings: list[str] = []
        reads: list[dict[str, Any]] = []
        t0 = time.monotonic()
        crm = _Logged("crm", self._crm(), reads)
        try:
            schools = rows(crm.execute(schools_sql(schema, tuple(st["kurumTipleri"])), MAX_ROWS, key="okullar"))
            visits = rows(crm.execute(visits_sql(schema), MAX_ROWS, key="ziyaretler"))
            history = rows(crm.execute(dealer_history_sql(schema), MAX_ROWS, key="bayi_gecmisi"))
            orders = rows(crm.execute(orders_sql(schema, since), MAX_ROWS, key="siparisler"))
            dealers = rows(crm.execute(dealers_sql(schema), MAX_ROWS, key="bayiler"))
            books = rows(crm.execute(books_sql(schema), MAX_ROWS, key="kitaplar"))
            users = rows(crm.execute(users_sql(schema), MAX_ROWS, key="kullanicilar"))
            districts = rows(crm.execute(districts_sql(schema), MAX_ROWS, key="ilceler"))
        finally:
            _close(crm)
        crm_ms = int((time.monotonic() - t0) * 1000)
        t1 = time.monotonic()
        stock: dict[str, float] = {}
        prices: list[dict[str, Any]] = []
        clcards: list[dict[str, Any]] = []
        dealer_items: list[dict[str, Any]] = []
        dealer_months: list[dict[str, Any]] = []
        firms: dict[int, str] = {}
        try:
            logo = _Logged("logo", self._logo(), reads)
            try:
                firms = firms_by_year(rows(logo.execute(periods_sql(), 10_000, key="donemler")))
                if not firms:
                    raise SourceError("Logo dönem listesi boş.")
                cur = firms[max(firms)]
                for r in rows(logo.execute(stock_sql(cur), MAX_ROWS, key="stok")):
                    code = s(r.get("stok_kodu"))
                    if code:
                        stock[code.upper()] = float(r.get("bakiye") or 0)
                prices = rows(logo.execute(price_sql(cur, today), MAX_ROWS, key="fiyat"))
                clcards = rows(logo.execute(clcard_sql(cur), MAX_ROWS, key="cariler"))
                lo = date(today.year, today.month, 1) - timedelta(days=int(st["dealerMonths"]) * 31)
                lo = date(lo.year, lo.month, 1)
                hi = today + timedelta(days=1)
                for y in range(lo.year, hi.year + 1):
                    firm = firms.get(y)
                    if not firm:
                        warnings.append(f"Logo'da {y} yılının kopyası yok; bayi satışı o yıl için okunmadı.")
                        continue
                    a, b = max(lo, date(y, 1, 1)), min(hi, date(y + 1, 1, 1))
                    dealer_items += rows(logo.execute(dealer_sales_sql(firm, a, b), MAX_ROWS, key="bayi_satisi"))
                    dealer_months += rows(logo.execute(dealer_months_sql(firm, a, b), MAX_ROWS, key="bayi_aylik"))
            finally:
                _close(logo)
        except Exception as e:  # noqa: BLE001 — Logo düşerse CRM ile devam; ekranda söylenir
            log.warning("school_visits: Logo okunamadı: %s", e)
            warnings.append("Logo'ya şu an ulaşılamıyor; stok, fiyat ve bayi satışı gösterilemiyor.")
        logo_ms = int((time.monotonic() - t1) * 1000)
        return {"schools": schools, "visits": visits, "history": history, "orders": orders, "dealers": dealers,
                "books": books, "users": users, "districts": districts, "stock": stock, "prices": prices,
                "clcards": clcards, "dealerItems": dealer_items, "dealerMonths": dealer_months,
                "firms": firms, "since": since.isoformat(), "at": time.time(), "asOf": today.isoformat(),
                "crmMs": crm_ms, "logoMs": logo_ms, "warnings": warnings, "sorgular": reads}
