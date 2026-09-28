"""M28 Kurumsal ilişkiler: CRM okuması (yalnız okuma, `SELECT`).

Kaynaklar (analiz `docs/analiz/kullanici-ihtiyaclari/M28-kanaat-onderleri-kurumsal-iliskiler.md` §6, §13):

- **Kişiler** — `ContactBase`: ad, iş unvanı, rol (`AccountRoleCode` 1 Karar Veren / 2 Çalışan / 3 Etkileyen), kurumu
  (`ParentCustomerId` → `AccountBase.Name`, kurum rolü `new_KurumRolu`), il (`new_il`), ünvan (`new_unvanBase`), akademik
  titr (`new_akademiktitrBase`), meslek (`new_meslekBase`), iş e-postası ve iş telefonu. Uzmanlık alanı N:N
  (`new_contact_new_uzmanlikalaniBase` → `new_uzmanlikalaniBase`), kişi rolü N:N (`new_contact_new_kisiroluBase` →
  `new_kisiroluBase`). **KVKK:** milliyet, medeni durum, çocuk, ev adresi, doğum yılı gibi kolonlar hiçbir sorguda
  seçilmez; inanç/siyaset alanı CRM'de de yok, burada da üretilmez.
- **Kurumlar** — `new_ziyaretyerleriBase` (68.713 ziyaret yeri; kurum tipi 1 Okul, 3 Üniversite, 5 Milli Eğitim,
  6 Belediye, 7 Kaymakamlık, 8 Valilik, 4 Diğer). Öğrenci/öğretmen/kitap sayısı **metin** kolonudur: `TRY_CONVERT(int,
  NULLIF(…,''))` ile sayılır, çevrilemeyen satır ayrıca sayılır (0 yazılmaz). İl `new_illerBase`.
- **Hediye/tanıtım gönderimleri** — `new_siparisBase` sipariş tipi 12 Pazarlama (Tanıtım Gönderimi), 15 Deprem Bağış,
  10 Okul Örneği, 11 Öğretmen Örneği (ayar: `REL_ORDER_TYPES`); adet `new_siparissatiriBase.new_adet`. Sayılmayan
  sipariş durumları ayardan (`REL_ORDER_EXCLUDED_STATUS`, varsayılan 100000001 İptal Edildi, 100000003 Birleştirildi —
  birleştirilen siparişin satırları yeni siparişte de durur, iki kez sayılmasın). Durum etiketleri `StringMapBase`'ten.
- **Kitaplar** — `new_kitapBase` (ad, stok kodu, türler, web kategorileri, hedef kitle, yaş, arka kapak metni, ilk baskı
  tarihi); yazar `new_eserkatilimBase` «Yazar» katılımcısı.

CRM tarihleri UTC saklanır: yıl sınırı İstanbul gece yarısının UTC karşılığıyla verilir. CRM'e hiçbir şey yazılmaz.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Any, Iterable, Optional

from semantic_bridge import budget_sources as bsrc
from semantic_bridge.relations_core import TZ, crm_prefix, guid, like

SourceError = bsrc.SourceError
Runner = bsrc.Runner
runner = bsrc.runner

PAGE_SIZE = 20

KURUM_TIPI = {1: "Okul", 3: "Üniversite", 5: "Milli Eğitim", 6: "Belediye", 7: "Kaymakamlık", 8: "Valilik", 4: "Diğer"}
KURUM_TURU = {1: "Devlet", 2: "Özel", 3: "Vakıf"}
ROLE = {1: "Karar Veren", 2: "Çalışan", 3: "Etkileyen"}
KURUM_ROLU = {1: "Müşteri", 2: "Devlet Kurumu", 3: "Resmi", 4: "Özel STK"}
HEDEF_KITLE = {1: "Çocuk", 2: "Genç", 3: "Yetişkin"}
#: `new_siparistipi` değerleri (CRM seçim listesi, bilgi paketi 2026-09-09).
ORDER_TYPE_LABELS = {10: "Okul örneği", 11: "Öğretmen örneği", 12: "Tanıtım gönderimi", 13: "Okul satışı", 15: "Deprem bağışı"}
#: Kitabın yayıncılık statüsü: iptal, süresiz ertelendi, artık bizim değil, hakları devredildi (M31 ile aynı).
BOOK_EXCLUDED_STATUS = (100000001, 100000003, 100000005, 100000006)

_ORDER_NO = re.compile(r"^[A-Za-z0-9\-_/.]{1,40}$")


def _ints(values: Iterable[Any]) -> str:
    out = sorted({int(v) for v in values})
    if not out:
        raise SourceError("Boş kod listesi.")
    return ", ".join(str(v) for v in out)


def _guids(ids: Iterable[str]) -> str:
    out = sorted({guid(i, "CRM kimliği") for i in ids})
    if not out:
        raise SourceError("Boş kimlik listesi.")
    return ", ".join(f"'{i}'" for i in out)


def order_no(v: Any) -> str:
    t = str(v or "").strip()
    if not _ORDER_NO.match(t):
        raise SourceError("CRM sipariş numarası yalnız harf, rakam ve - _ / . içerebilir.")
    return t


def year_bounds_utc(year: int) -> tuple[str, str]:
    """İstanbul'da [yıl başı, sonraki yıl başı) aralığının UTC karşılığı ('YYYY-AA-GGTHH:MM:SS')."""
    a = datetime(year, 1, 1, tzinfo=TZ).astimezone(timezone.utc).replace(tzinfo=None)
    b = datetime(year + 1, 1, 1, tzinfo=TZ).astimezone(timezone.utc).replace(tzinfo=None)
    return a.isoformat(timespec="seconds"), b.isoformat(timespec="seconds")


def _page(page: int) -> str:
    return f" OFFSET {max(0, int(page)) * PAGE_SIZE} ROWS FETCH NEXT {PAGE_SIZE} ROWS ONLY"


# ------------------------------------------------------------------------------------------ kişiler

_CONTACT_COLS = (
    "k.ContactId AS id, k.FullName AS ad, k.JobTitle AS is_unvani, CAST(k.AccountRoleCode AS int) AS rol,"
    " k.ParentCustomerId AS kurum_id, a.Name AS kurum, CAST(a.new_KurumRolu AS int) AS kurum_rolu,"
    " i.new_name AS il, u.new_unvanname AS unvan, t.new_name AS akademik_titr, m.new_name AS meslek,"
    " k.EMailAddress1 AS eposta, k.Telephone1 AS telefon, k.ModifiedOn AS degisti"
)


def _contact_from(p: str) -> str:
    return (f" FROM {p}ContactBase k"
            f" LEFT JOIN {p}AccountBase a ON a.AccountId = k.ParentCustomerId"
            f" LEFT JOIN {p}new_illerBase i ON i.new_illerId = k.new_il"
            f" LEFT JOIN {p}new_unvanBase u ON u.new_unvanId = k.new_unvan"
            f" LEFT JOIN {p}new_akademiktitrBase t ON t.new_akademiktitrId = k.new_AkademikTitrid"
            f" LEFT JOIN {p}new_meslekBase m ON m.new_meslekId = k.new_Meslekid")


def contacts_sql(schema: str, q: str = "", role: Optional[int] = None, page: int = 0) -> str:
    """Etkin CRM kişileri (ad, kurum ya da iş unvanında arama), sayfa + toplam (`COUNT(*) OVER ()`)."""
    p = crm_prefix(schema)
    where = " WHERE k.StateCode = 0"
    words = [w for w in re.split(r"\s+", (q or "").strip()) if len(w) >= 2][:4]
    for w in words:
        lw = like(w)
        where += f" AND (k.FullName LIKE N'%{lw}%' OR a.Name LIKE N'%{lw}%' OR k.JobTitle LIKE N'%{lw}%')"
    if role is not None:
        if int(role) not in ROLE:
            raise SourceError("Rol geçerli değil.")
        where += f" AND k.AccountRoleCode = {int(role)}"
    return f"SELECT {_CONTACT_COLS}, COUNT(*) OVER () AS toplam{_contact_from(p)}{where} ORDER BY k.FullName, k.ContactId{_page(page)}"


def contact_sql(schema: str, contact_id: str) -> str:
    p = crm_prefix(schema)
    return f"SELECT {_CONTACT_COLS}{_contact_from(p)} WHERE k.ContactId = '{guid(contact_id)}'"


def contact_tags_sql(schema: str, ids: Iterable[str]) -> str:
    """Kişilerin CRM uzmanlık alanları ve kişi rolleri (tür: 'uzmanlik' | 'rol')."""
    p = crm_prefix(schema)
    inn = _guids(ids)
    return (
        "SELECT x.contactid AS kisi, 'uzmanlik' AS tur, z.new_name AS ad"
        f" FROM {p}new_contact_new_uzmanlikalaniBase x JOIN {p}new_uzmanlikalaniBase z ON z.new_uzmanlikalaniId = x.new_uzmanlikalaniid"
        f" WHERE x.contactid IN ({inn})"
        " UNION ALL"
        " SELECT y.contactid AS kisi, 'rol' AS tur, r.new_name AS ad"
        f" FROM {p}new_contact_new_kisiroluBase y JOIN {p}new_kisiroluBase r ON r.new_kisiroluId = y.new_kisiroluid"
        f" WHERE y.contactid IN ({inn})"
    )


def decision_makers_sql(schema: str) -> str:
    """Kabul 4: CRM'de «Karar Veren» rolündeki etkin kişi sayısı."""
    p = crm_prefix(schema)
    return f"SELECT COUNT(*) AS n FROM {p}ContactBase k WHERE k.StateCode = 0 AND k.AccountRoleCode = 1"


def person_roles_sql(schema: str) -> str:
    """CRM kişi rolleri ve kaç kişide kullanıldığı (kanaat önderi diye bir rol var mı — ekranda gösterilir)."""
    p = crm_prefix(schema)
    return (f"SELECT r.new_kisiroluId AS id, r.new_name AS ad, COUNT(y.contactid) AS kisi"
            f" FROM {p}new_kisiroluBase r LEFT JOIN {p}new_contact_new_kisiroluBase y ON y.new_kisiroluid = r.new_kisiroluId"
            " WHERE r.statecode = 0 GROUP BY r.new_kisiroluId, r.new_name ORDER BY r.new_name")


# ------------------------------------------------------------------------------------------ kurumlar (ziyaret yerleri)

_PLACE_COLS = (
    "z.new_ziyaretyerleriId AS id, COALESCE(NULLIF(z.new_kurumadi, ''), z.new_okuladi) AS ad, z.new_okuladi AS okul_adi,"
    " CAST(z.new_KurumTipi AS int) AS kurum_tipi, CAST(z.new_kurumturu AS int) AS kurum_turu,"
    " TRY_CONVERT(int, NULLIF(z.new_renciSays, '')) AS ogrenci, TRY_CONVERT(int, NULLIF(z.new_ogretmensayisi, '')) AS ogretmen,"
    " TRY_CONVERT(int, NULLIF(z.new_kitapsayisi, '')) AS kitap_sayisi,"
    " TRY_CONVERT(int, NULLIF(z.new_toplamogrencisayisi, '')) AS toplam_ogrenci,"
    " z.new_ili AS il_id, i.new_name AS il, c.new_name AS ilce, z.new_Telefon AS telefon"
)


def _place_from(p: str) -> str:
    return (f" FROM {p}new_ziyaretyerleriBase z"
            f" LEFT JOIN {p}new_illerBase i ON i.new_illerId = z.new_ili"
            f" LEFT JOIN {p}new_ilceBase c ON c.new_ilceId = z.new_ilcesi")


def places_sql(schema: str, q: str = "", kurum_tipi: Optional[int] = None, il_id: str = "", page: int = 0) -> str:
    p = crm_prefix(schema)
    where = " WHERE z.statecode = 0"
    words = [w for w in re.split(r"\s+", (q or "").strip()) if len(w) >= 2][:4]
    for w in words:
        lw = like(w)
        where += f" AND (z.new_kurumadi LIKE N'%{lw}%' OR z.new_okuladi LIKE N'%{lw}%')"
    if kurum_tipi is not None:
        if int(kurum_tipi) not in KURUM_TIPI:
            raise SourceError("Kurum tipi geçerli değil.")
        where += f" AND z.new_KurumTipi = {int(kurum_tipi)}"
    if il_id:
        where += f" AND z.new_ili = '{guid(il_id, 'İl')}'"
    return (f"SELECT {_PLACE_COLS}, COUNT(*) OVER () AS toplam{_place_from(p)}{where}"
            f" ORDER BY COALESCE(NULLIF(z.new_kurumadi, ''), z.new_okuladi), z.new_ziyaretyerleriId{_page(page)}")


def places_by_id_sql(schema: str, ids: Iterable[str]) -> str:
    p = crm_prefix(schema)
    return f"SELECT {_PLACE_COLS}{_place_from(p)} WHERE z.new_ziyaretyerleriId IN ({_guids(ids)})"


def city_stats_sql(schema: str, il_id: str, kurum_tipi: int = 1) -> str:
    """Kabul 1: seçilen ilde bir kurum tipinin (varsayılan okul) sayısı, öğrenci toplamı ve öğrenci sayısı
    sayıya çevrilemeyen satır."""
    p = crm_prefix(schema)
    if int(kurum_tipi) not in KURUM_TIPI:
        raise SourceError("Kurum tipi geçerli değil.")
    return (
        "SELECT COUNT(*) AS kurum, SUM(TRY_CONVERT(int, NULLIF(z.new_renciSays, ''))) AS ogrenci,"
        " SUM(CASE WHEN TRY_CONVERT(int, NULLIF(z.new_renciSays, '')) IS NULL THEN 1 ELSE 0 END) AS sayisiz"
        f" FROM {p}new_ziyaretyerleriBase z WHERE z.statecode = 0 AND z.new_KurumTipi = {int(kurum_tipi)}"
        f" AND z.new_ili = '{guid(il_id, 'İl')}'"
    )


def cities_sql(schema: str) -> str:
    p = crm_prefix(schema)
    return f"SELECT i.new_illerId AS id, i.new_name AS ad FROM {p}new_illerBase i WHERE i.statecode = 0 ORDER BY i.new_name"


# ------------------------------------------------------------------------------------------ siparişler (hediye/tanıtım)


def promo_totals_sql(schema: str, year: int, types: Iterable[int], excluded: Iterable[int]) -> str:
    """Kabul 2–3: yılın tanıtım/bağış/örnek siparişleri, tip başına sipariş sayısı ve kitap adedi."""
    p = crm_prefix(schema)
    a, b = year_bounds_utc(int(year))
    ex = list(excluded)
    return (
        "SELECT CAST(s.new_siparistipi AS int) AS tip, COUNT(DISTINCT s.new_siparisId) AS siparis, SUM(ss.new_adet) AS adet"
        f" FROM {p}new_siparisBase s JOIN {p}new_siparissatiriBase ss ON ss.new_siparisid = s.new_siparisId"
        f" WHERE s.new_siparistipi IN ({_ints(types)}) AND s.new_siparistarihi >= '{a}' AND s.new_siparistarihi < '{b}'"
        + (f" AND s.statuscode NOT IN ({_ints(ex)})" if ex else "")
        + " GROUP BY s.new_siparistipi"
    )


def orders_by_no_sql(schema: str, numbers: Iterable[str]) -> str:
    """Hediye satırına yazılan CRM sipariş numaralarının durumu (günlük eşitleme)."""
    p = crm_prefix(schema)
    nos = sorted({order_no(n) for n in numbers})
    if not nos:
        raise SourceError("Boş sipariş listesi.")
    inn = ", ".join(f"N'{n}'" for n in nos)
    return (
        "SELECT s.new_siparisId AS id, s.new_name AS no, CAST(s.new_siparistipi AS int) AS tip, CAST(s.statuscode AS int) AS durum,"
        " s.new_siparistarihi AS tarih, s.new_sevktarihi AS sevk, s.new_tamamlanditarihi AS tamamlandi, a.Name AS firma"
        f" FROM {p}new_siparisBase s LEFT JOIN {p}AccountBase a ON a.AccountId = s.new_firmaid"
        f" WHERE s.new_name IN ({inn})"
    )


def order_lines_sql(schema: str, order_ids: Iterable[str]) -> str:
    """Siparişlerin kitap satırları (stok kodu × adet): hediyenin kitabı siparişte var mı, projenin dağıttığı adet."""
    p = crm_prefix(schema)
    return (
        "SELECT ss.new_siparisid AS siparis, ss.new_StokKodu AS stok_kodu, SUM(ss.new_adet) AS adet"
        f" FROM {p}new_siparissatiriBase ss WHERE ss.new_siparisid IN ({_guids(order_ids)})"
        " GROUP BY ss.new_siparisid, ss.new_StokKodu"
    )


def order_status_labels_sql(schema: str) -> str:
    p = crm_prefix(schema)
    return ("SELECT s.AttributeValue AS code, s.Value AS label"
            f" FROM {p}StringMapBase s"
            f" WHERE s.ObjectTypeCode = (SELECT TOP 1 e.ObjectTypeCode FROM {p}EntityView e WHERE e.Name = 'new_siparis')"
            " AND s.AttributeName = 'statuscode' AND s.LangId = 1055")


# ------------------------------------------------------------------------------------------ kitaplar

_BOOK_COLS = (
    "b.new_kitapId AS id, b.new_name AS ad, b.new_StokKodu AS stok_kodu, b.new_turlertext AS turler,"
    " b.new_webkategorileritext AS kategoriler, CAST(b.new_hedefkitle AS int) AS hedef_kitle, b.new_yaslartext AS yaslar,"
    " b.new_hedefkitleyasbaslangic AS yas_bas, b.new_hedefkitleyasbitis AS yas_bit, b.new_ilkyayintarihi AS ilk_baski,"
    " yz.yazar AS yazar"
)


def _book_from(p: str) -> str:
    # Yazar: «Yazar» katılımcı tipli ilk etkin eser katılımı (takma adlar dışta kullanılmaz).
    return (f" FROM {p}new_kitapBase b"
            " OUTER APPLY (SELECT TOP 1 kk.FullName AS yazar"
            f" FROM {p}new_eserkatilimBase ek JOIN {p}new_katilimcitipiBase kt ON kt.new_katilimcitipiId = ek.new_katilimciTipi"
            f" JOIN {p}ContactBase kk ON kk.ContactId = ek.new_Katilimsaglayan"
            " WHERE ek.statecode = 0 AND kt.new_name = N'Yazar' AND ek.new_Kitap = b.new_kitapId ORDER BY ek.CreatedOn) yz")


def _book_where() -> str:
    return (" WHERE b.statecode = 0 AND b.new_StokKodu IS NOT NULL AND b.new_StokKodu <> ''"
            f" AND ISNULL(CAST(b.new_kitap_yayincilikstatusu AS int), 0) NOT IN ({_ints(BOOK_EXCLUDED_STATUS)})")


def books_sql(schema: str, q: str = "", page: int = 0) -> str:
    p = crm_prefix(schema)
    where = _book_where()
    words = [w for w in re.split(r"\s+", (q or "").strip()) if len(w) >= 2][:4]
    for w in words:
        lw = like(w)
        where += f" AND (b.new_name LIKE N'%{lw}%' OR b.new_StokKodu LIKE N'%{lw}%')"
    return (f"SELECT {_BOOK_COLS}, COUNT(*) OVER () AS toplam{_book_from(p)}{where}"
            f" ORDER BY b.new_ilkyayintarihi DESC, b.new_name, b.new_kitapId{_page(page)}")


def books_published_sql(schema: str, first: date, until: date) -> str:
    """İlk baskı tarihi [first, until) arasındaki kitaplar (ayın yeni kitapları; tarih İstanbul günü, UTC'ye çevrilir)."""
    p = crm_prefix(schema)
    a = datetime(first.year, first.month, first.day, tzinfo=TZ).astimezone(timezone.utc).replace(tzinfo=None)
    b = datetime(until.year, until.month, until.day, tzinfo=TZ).astimezone(timezone.utc).replace(tzinfo=None)
    return (f"SELECT {_BOOK_COLS}{_book_from(p)}{_book_where()}"
            f" AND b.new_ilkyayintarihi >= '{a.isoformat(timespec='seconds')}' AND b.new_ilkyayintarihi < '{b.isoformat(timespec='seconds')}'"
            " ORDER BY b.new_ilkyayintarihi, b.new_name")


def books_by_id_sql(schema: str, ids: Iterable[str], *, summary: bool = False) -> str:
    p = crm_prefix(schema)
    extra = ", b.new_ozet AS ozet" if summary else ""
    return f"SELECT {_BOOK_COLS}{extra}{_book_from(p)} WHERE b.new_kitapId IN ({_guids(ids)})"


# ------------------------------------------------------------------------------------------ satır yardımcıları


def lower_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{str(k).lower(): v for k, v in r.items()} for r in rows]


def s(v: Any) -> Optional[str]:
    if v is None:
        return None
    t = re.sub(r"\s+", " ", str(v)).strip()
    return t or None


def ival(v: Any) -> Optional[int]:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    return int(n) if n == n else None


def lid(v: Any) -> Optional[str]:
    t = s(v)
    return t.strip("{}").lower() if t else None


def plain(html: Optional[str], limit: int = 600) -> Optional[str]:
    """CRM arka kapak metni HTML'dir: etiketler ve varlıklar atılır, boşluk sadeleşir."""
    if not html:
        return None
    t = re.sub(r"<[^>]+>", " ", str(html))
    t = (t.replace("&nbsp;", " ").replace("&amp;", "&").replace("&quot;", '"').replace("&#39;", "'")
         .replace("&lt;", "<").replace("&gt;", ">"))
    t = re.sub(r"&[a-zA-Z#0-9]+;", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:limit] or None
