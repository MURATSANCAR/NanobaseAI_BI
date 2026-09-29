"""M20 Basın ilişkilerinin kaynak okuması (yalnız okuma; CRM'e, Logo'ya, T-soft'a giden tek komut `SELECT`tir).

- **CRM** (`SEMANTIC_CRM_CONNECTION_FILE`, şema Yönetim → CRM şeması; canlı .28):
  - ayın kitapları: `new_kitap` görünümü, etkin «Kitap» kartı (`statecode = 0 AND new_Tip = 1`, M15 ile aynı tanım),
    ilk baskı tarihi aralıkta (CRM tarihi UTC saklar; gün İstanbul saatine çevrilir);
  - kitap kartı: künye + basın metinleri (arka kapak, kısa/uzun tanıtım, «Basın Bülteni», «Bu Kitap Neden Önemli?»,
    «Kitabın En Önemli Cümlesi»), eser katılımından yazar kişileri;
  - medya kişileri: etkin kişi ve (1) «Basın medya Mecrası» dolu, ya da (2) Haber kaydında «Haberi Yapan Kişi» /
    «Basında Görüşülen Kişi», ya da (3) Yönetim ayarındaki CRM «Kişi Rolü» adlarından birine bağlı. Hangi bağın
    gerçekten gazeteci olduğu **ölçülecek** (kabul 3). Parola/token kolonu seçilmez;
  - Haber modülü arşivi (`new_haberler`, son değişiklik 2025-06; yalnız okunur): başlık, tarih, bağlantı, üç mecra
    alanının adı, haberi yapan ve görüşülen kişi; kitap bağı N:N tablo + «Kitap» alanı birleşimi;
  - tanıtım gönderimi: `new_siparisBase.new_siparistipi = 12` «Pazarlama (Tanıtım Gönderimi)» satırları, stok koduyla.
- **Basın ve web** (`semantic_web_*`, yalnız `WEB_WATCH_ENABLED` açık ortamda dolar): modelin ilgili bulduğu kayıtlar.
- **Tek sayfa okuma** (yansıma bağlantısı yapıştırılınca): yalnız o sayfa, robots.txt'e ve Content-Signal'e uyarak
  (`web_watch.allowed`), açık kimlikle; özel ağ adresine gidilmez. Ortamda web okuma kapalıysa hiç istek yapılmaz.
"""
from __future__ import annotations

import html
import ipaddress
import os
import re
import socket
import urllib.parse
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

from semantic_bridge import budget_sources as bsrc
from semantic_bridge import hizli_kaynak as HK

Runner = Callable[[str], list[dict[str, Any]]]
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_CODE = re.compile(r"^[0-9A-Za-z._/\- ]{1,60}$")
BOOK_TIP = 1
PROMO_ORDER_TYPE = 12
CACHE_TTL = 600
SEARCH_PAGE = 50


class SourceError(RuntimeError):
    pass


def crm_file() -> str:
    return os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")


def crm_runner() -> Runner:
    try:
        return bsrc.runner(crm_file())
    except bsrc.SourceError as e:
        raise SourceError(f"CRM okunamıyor: {e}") from None


def prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise SourceError(f"CRM şeması «{schema}» geçerli bir ad değil.")
    if not sch:
        raise SourceError("CRM şeması girilmemiş; CRM okunamıyor.")
    return (f"{db}." if db else "") + f"{sch}."


def guid(v: Any) -> str:
    s = str(v or "").strip().strip("{}")
    if not _GUID.match(s):
        raise SourceError("Geçersiz CRM kimliği.")
    return s


def code(v: Any) -> str:
    s = str(v or "").strip()
    if not _CODE.match(s):
        raise SourceError("Geçersiz stok kodu.")
    return s.replace("'", "''")


def _utc_bound(d: date) -> str:
    return (datetime(d.year, d.month, d.day) - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")


def _nstr(v: str) -> str:
    return "N'" + str(v).replace("'", "''") + "'"


# ------------------------------------------------------------------ SQL

def _map(p: str, alias: str, attr: str, col: str, entity: str) -> str:
    return (f"LEFT JOIN {p}StringMapBase AS {alias} ON {alias}.AttributeName = '{attr}' AND {alias}.AttributeValue = {col} "
            f"AND {alias}.LangId = 1055 AND {alias}.ObjectTypeCode = (SELECT ObjectTypeCode FROM {p}EntityView WHERE Name = '{entity}')")


_BOOK = """
    k.new_kitapId                                        AS kitap_id,
    k.new_stokkodu                                       AS stok_kodu,
    k.new_name                                           AS ad,
    k.new_yazartext                                      AS yazar,
    k.new_yayineviidName                                 AS yayinevi,
    k.new_kitaplikidName                                 AS kitaplik,
    hk.Value                                             AS hedef_kitle,
    k.new_turlertext                                     AS turler,
    CAST(DATEADD(HOUR, 3, k.new_ilkyayintarihi) AS DATE) AS yayin,
    CAST(k.new_OnemDerecesi AS int)                      AS onem,
    od.Value                                             AS onem_adi,
    k.new_resimurl                                       AS kapak"""


def _book_from(p: str) -> str:
    return (f"FROM {p}new_kitap AS k\n{_map(p, 'hk', 'new_hedefkitle', 'k.new_hedefkitle', 'new_kitap')}\n"
            f"{_map(p, 'od', 'new_onemderecesi', 'k.new_OnemDerecesi', 'new_kitap')}")


def month_books_sql(schema: str, frm: date, to: date) -> str:
    """İlk baskı tarihi [frm, to] (İstanbul günü) olan etkin kitap kartları."""
    p = prefix(schema)
    return f"""
-- M20: dönemde çıkan/çıkacak kitaplar (CRM, yalnız okuma). Tarih UTC saklanır; aralık İstanbul gününe çevrildi.
SELECT {_BOOK}
{_book_from(p)}
WHERE k.statecode = 0 AND k.new_Tip = {BOOK_TIP}
  AND k.new_ilkyayintarihi >= '{_utc_bound(frm)}' AND k.new_ilkyayintarihi < '{_utc_bound(to + timedelta(days=1))}'""".strip()


def book_sql(schema: str, kitap_id: str) -> str:
    p = prefix(schema)
    return f"""
-- M20: PR dosyasının kitap kartı (künye + basın metinleri; yalnız okuma).
SELECT {_BOOK},
    COALESCE(NULLIF(k.new_kdvdahilfiyat, 0), NULLIF(k.new_PerakendeBirimFiyat, 0)) AS fiyat,
    NULLIF(k.new_sayfasayisi, 0) AS sayfa, k.new_hedefkitleyasbaslangic AS yas_bas, k.new_hedefkitleyasbitis AS yas_bit,
    k.new_ozet AS t_ozet, k.new_kisabilgi AS t_kisa, k.new_uzunbilgi AS t_uzun, k.new_BasnBlteni AS t_bulten,
    k.new_kitapspotu AS t_spot, k.new_kitabinonecikanyanlari AS t_onem, k.new_kitabinenonemlicumlesi AS t_cumle
{_book_from(p)}
WHERE k.new_kitapId = '{guid(kitap_id)}'""".strip()


def book_authors_sql(schema: str, kitap_id: str) -> str:
    p = prefix(schema)
    return f"""
-- M20: kitabın yazar kişileri (eser katılımı, katılımcı tipi «Yazar»).
SELECT DISTINCT c.ContactId AS id, c.FullName AS ad
FROM {p}new_eserkatilimBase AS e
JOIN {p}new_katilimcitipiBase AS t ON t.new_katilimcitipiId = e.new_katilimciTipi
JOIN {p}ContactBase AS c ON c.ContactId = e.new_Katilimsaglayan
WHERE e.statecode = 0 AND c.StateCode = 0 AND t.new_name = N'Yazar' AND e.new_Kitap = '{guid(kitap_id)}'""".strip()


def book_search_sql(schema: str, q: str, page: int) -> tuple[str, str]:
    """Kitap adı, yazar ya da stok koduyla arama; sayfalı (sayfa başı 50, toplam ayrıca sayılır — tavan yok)."""
    p = prefix(schema)
    term = "%" + re.sub(r"[%_\[\]]", " ", str(q or "").strip())[:80] + "%"
    where = (f"WHERE k.statecode = 0 AND k.new_Tip = {BOOK_TIP} AND (k.new_name LIKE {_nstr(term)} "
             f"OR k.new_yazartext LIKE {_nstr(term)} OR k.new_stokkodu LIKE {_nstr(term)})")
    rows = f"""
SELECT {_BOOK}
{_book_from(p)}
{where}
ORDER BY k.new_ilkyayintarihi DESC, k.new_name
OFFSET {max(0, int(page)) * SEARCH_PAGE} ROWS FETCH NEXT {SEARCH_PAGE} ROWS ONLY""".strip()
    count = f"SELECT COUNT(*) AS n FROM {p}new_kitap AS k {where}"
    return rows, count


def media_contacts_sql(schema: str, roles: list[str]) -> str:
    p = prefix(schema)
    role = ""
    if roles:
        role = (f"\n   OR c.ContactId IN (SELECT cr.contactid FROM {p}new_contact_new_kisiroluBase AS cr "
                f"JOIN {p}new_kisiroluBase AS r ON r.new_kisiroluId = cr.new_kisiroluid WHERE r.new_name IN ("
                + ", ".join(_nstr(x) for x in roles) + "))")
    return f"""
-- M20: CRM medya kişileri (yalnız okuma). E-posta izni alanları seçilir; parola/token yok.
SELECT c.ContactId AS id, c.FullName AS ad, c.EMailAddress1 AS eposta,
       COALESCE(NULLIF(LTRIM(RTRIM(c.Telephone1)), ''), c.MobilePhone) AS telefon, c.JobTitle AS unvan,
       NULLIF(LTRIM(RTRIM(c.new_ilgilioldugumecra)), '') AS mecra, a.Name AS kurum,
       CAST(ISNULL(c.DoNotEMail, 0) AS int) AS eposta_yok, CAST(ISNULL(c.DoNotBulkEMail, 0) AS int) AS toplu_yok,
       CAST(c.new_iysonayi AS int) AS iys
FROM {p}ContactBase AS c
LEFT JOIN {p}AccountBase AS a ON a.AccountId = c.ParentCustomerId
WHERE c.StateCode = 0 AND (
   NULLIF(LTRIM(RTRIM(c.new_ilgilioldugumecra)), '') IS NOT NULL
   OR c.ContactId IN (SELECT h.new_HaberinYazari FROM {p}new_haberlerBase AS h WHERE h.new_HaberinYazari IS NOT NULL)
   OR c.ContactId IN (SELECT h.new_basindagorusulenkisi FROM {p}new_haberlerBase AS h WHERE h.new_basindagorusulenkisi IS NOT NULL){role})""".strip()


def archive_sql(schema: str) -> str:
    p = prefix(schema)
    return f"""
-- M20: CRM Haber modülü arşivi (son değişiklik 2025-06; yalnız okunur). Mecra adları CRM görünümünden.
SELECT h.new_haberlerId AS id, COALESCE(NULLIF(LTRIM(h.new_HaberBasligi), ''), h.new_name) AS baslik,
       NULLIF(LTRIM(h.new_HaberLinki), '') AS link, NULLIF(LTRIM(h.new_YoutubeLinki), '') AS youtube,
       CAST(DATEADD(HOUR, 3, h.new_HaberTarihi) AS DATE) AS tarih, CAST(ISNULL(h.new_haberyayinlandi, 0) AS int) AS yayinlandi,
       CAST(ISNULL(h.new_kitapgonderimi, 0) AS int) AS kitap_gonderimi, CAST(ISNULL(h.new_basinziyareti, 0) AS int) AS basin_ziyareti,
       h.new_HaberMecraName AS mecra1, h.new_habermecrasiName AS mecra2, h.new_HaberMecrasName AS mecra3,
       h.new_mecratipiName AS mecra_tipi, h.new_HaberinYazari AS muhabir_id, h.new_HaberinYazariName AS muhabir,
       h.new_basindagorusulenkisi AS gorusulen_id, h.new_basindagorusulenkisiName AS gorusulen,
       h.new_YazaridName AS yazar, h.new_yazartext AS yazar_text, h.new_kitaptext AS kitap_text
FROM {p}new_haberler AS h
WHERE h.statecode = 0""".strip()


def archive_base_sql(schema: str) -> str:
    """Yedek yol: CRM görünümü (`new_haberler`) okunamazsa temel tablo. Mecra alanlarının hedef varlığı metaveride
    yazmıyor; `new_habermecrasi` → Haber Mecrası (4 kayıt), `new_HaberMecra` → Mecra (230 kayıt), `new_mecratipi` →
    Mecra Tipi kabul edildi (**ölçülecek**, kabul 1'de görünüm yolu tutarsa bu yol hiç kullanılmaz). Haberi yapan kişi
    önce ContactBase'de, yoksa SystemUserBase'de aranır."""
    p = prefix(schema)
    return f"""
-- M20: CRM Haber arşivi, temel tablo yolu (yalnız okuma).
SELECT h.new_haberlerId AS id, COALESCE(NULLIF(LTRIM(h.new_HaberBasligi), ''), h.new_name) AS baslik,
       NULLIF(LTRIM(h.new_HaberLinki), '') AS link, NULLIF(LTRIM(h.new_YoutubeLinki), '') AS youtube,
       CAST(DATEADD(HOUR, 3, h.new_HaberTarihi) AS DATE) AS tarih, CAST(ISNULL(h.new_haberyayinlandi, 0) AS int) AS yayinlandi,
       CAST(ISNULL(h.new_kitapgonderimi, 0) AS int) AS kitap_gonderimi, CAST(ISNULL(h.new_basinziyareti, 0) AS int) AS basin_ziyareti,
       m1.new_name AS mecra1, m2.new_name AS mecra2, NULL AS mecra3, mt.new_name AS mecra_tipi,
       h.new_HaberinYazari AS muhabir_id, COALESCE(c1.FullName, u1.FullName) AS muhabir,
       h.new_basindagorusulenkisi AS gorusulen_id, COALESCE(c2.FullName, u2.FullName) AS gorusulen,
       cy.FullName AS yazar, h.new_yazartext AS yazar_text, h.new_kitaptext AS kitap_text
FROM {p}new_haberlerBase AS h
LEFT JOIN {p}new_mecraBase AS m1 ON m1.new_mecraId = h.new_HaberMecra
LEFT JOIN {p}new_habermecrasiBase AS m2 ON m2.new_habermecrasiId = h.new_habermecrasi
LEFT JOIN {p}new_mecratipiBase AS mt ON mt.new_mecratipiId = h.new_mecratipi
LEFT JOIN {p}ContactBase AS c1 ON c1.ContactId = h.new_HaberinYazari
LEFT JOIN {p}SystemUserBase AS u1 ON u1.SystemUserId = h.new_HaberinYazari
LEFT JOIN {p}ContactBase AS c2 ON c2.ContactId = h.new_basindagorusulenkisi
LEFT JOIN {p}SystemUserBase AS u2 ON u2.SystemUserId = h.new_basindagorusulenkisi
LEFT JOIN {p}ContactBase AS cy ON cy.ContactId = h.new_Yazarid
WHERE h.statecode = 0""".strip()


def archive_books_sql(schema: str) -> str:
    p = prefix(schema)
    return f"""
-- M20: haber ↔ kitap bağı (N:N tablo ∪ haberin «Kitap» alanı; UNION tekrarları atar).
SELECT x.haber_id, k.new_kitapId AS kitap_id, k.new_stokkodu AS stok_kodu, k.new_name AS ad, k.new_yazartext AS yazar,
       k.new_kitaplikidName AS kitaplik, hk.Value AS hedef_kitle, k.new_turlertext AS turler
FROM (SELECT l.new_haberlerid AS haber_id, l.new_kitapid AS kitap_id FROM {p}new_new_haberler_new_kitapBase AS l
      UNION
      SELECT h.new_haberlerId, h.new_Kitapid FROM {p}new_haberlerBase AS h WHERE h.statecode = 0 AND h.new_Kitapid IS NOT NULL) AS x
JOIN {p}new_kitap AS k ON k.new_kitapId = x.kitap_id
{_map(p, 'hk', 'new_hedefkitle', 'k.new_hedefkitle', 'new_kitap')}""".strip()


def promo_orders_sql(schema: str, stok: str) -> str:
    p = prefix(schema)
    return f"""
-- M20: «Pazarlama (Tanıtım Gönderimi)» siparişleri (tip {PROMO_ORDER_TYPE}) bu stok koduyla; alıcı fatura carisi.
SELECT s.new_name AS siparis_no, CAST(DATEADD(HOUR, 3, COALESCE(s.new_siparistarihi, s.CreatedOn)) AS DATE) AS tarih,
       a.Name AS cari, SUM(ISNULL(ss.new_adet, 0)) AS adet
FROM {p}new_siparissatiriBase AS ss
JOIN {p}new_siparisBase AS s ON s.new_siparisId = ss.new_siparisid
LEFT JOIN {p}AccountBase AS a ON a.AccountId = s.new_faturacarisiid
WHERE s.new_siparistipi = {PROMO_ORDER_TYPE} AND ss.new_StokKodu = N'{code(stok)}'
GROUP BY s.new_name, COALESCE(s.new_siparistarihi, s.CreatedOn), a.Name
ORDER BY 2 DESC""".strip()


def email_sql(schema: str, user: str) -> str:
    p = prefix(schema)
    u = re.sub(r"[^A-Za-z0-9._\-]", "", str(user or ""))[:80]
    return f"SELECT TOP 1 InternalEMailAddress AS mail FROM {p}SystemUserBase WHERE IsDisabled = 0 AND DomainName LIKE N'%\\{u}'"


# ------------------------------------------------------------------ satır biçimi


def _s(v: Any) -> Optional[str]:
    return bsrc._clean(v)


def _d(v: Any) -> Optional[str]:
    d = bsrc._day(v)
    if d is None or d.year < 1950:          # 1899/1900: boş tarih
        return None
    return d.isoformat()


def _id(v: Any) -> Optional[str]:
    s = _s(v)
    return s.strip("{}").lower() if s else None


def _long(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = re.sub(r"<br\s*/?>|</p>", "\n", str(v), flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    s = "\n".join(" ".join(x.split()) for x in s.splitlines())
    return re.sub(r"\n{3,}", "\n\n", s).strip() or None


def book_row(r: dict[str, Any]) -> dict[str, Any]:
    return {"kitapId": _id(r.get("kitap_id")), "stokKodu": _s(r.get("stok_kodu")), "ad": _s(r.get("ad")), "yazar": _s(r.get("yazar")),
            "yayinevi": _s(r.get("yayinevi")), "kitaplik": _s(r.get("kitaplik")), "hedefKitle": _s(r.get("hedef_kitle")),
            "turler": _s(r.get("turler")), "yayinTarihi": _d(r.get("yayin")), "onem": r.get("onem"), "onemAdi": _s(r.get("onem_adi")),
            "kapak": _s(r.get("kapak"))}


TEXT_FIELDS = (("t_ozet", "new_ozet", "Arka kapak metni"), ("t_kisa", "new_kisabilgi", "Kitap tanıtım – kısa bilgi"),
               ("t_uzun", "new_uzunbilgi", "Kitap tanıtım – uzun bilgi"), ("t_bulten", "new_BasnBlteni", "Basın bülteni"),
               ("t_spot", "new_kitapspotu", "Kitap spotu"), ("t_onem", "new_kitabinonecikanyanlari", "Bu kitap neden önemli?"),
               ("t_cumle", "new_kitabinenonemlicumlesi", "Kitabın en önemli cümlesi"))


def detail_row(r: dict[str, Any]) -> dict[str, Any]:
    out = book_row(r)
    out.update({"fiyat": bsrc._num(r.get("fiyat")), "sayfa": bsrc._num(r.get("sayfa")),
                "yas": [r.get("yas_bas"), r.get("yas_bit")],
                "metinler": [{"alan": crm, "ad": label, "metin": t} for key, crm, label in TEXT_FIELDS if (t := _long(r.get(key)))]})
    return out


def contact_row(r: dict[str, Any]) -> dict[str, Any]:
    return {"id": _id(r.get("id")), "ad": _s(r.get("ad")), "eposta": _s(r.get("eposta")), "telefon": _s(r.get("telefon")),
            "unvan": _s(r.get("unvan")), "mecra": _s(r.get("mecra")), "kurum": _s(r.get("kurum")),
            "epostaYok": bool(r.get("eposta_yok")), "topluYok": bool(r.get("toplu_yok")),
            "iys": None if r.get("iys") is None else bool(r.get("iys"))}


def archive_rows(heads: list[dict[str, Any]], links: list[dict[str, Any]]) -> list[dict[str, Any]]:
    books: dict[str, list[dict[str, Any]]] = {}
    for b in links:
        hid = _id(b.get("haber_id"))
        if not hid:
            continue
        books.setdefault(hid, []).append({"kitapId": _id(b.get("kitap_id")), "stokKodu": _s(b.get("stok_kodu")), "ad": _s(b.get("ad")),
                                          "yazar": _s(b.get("yazar")), "kitaplik": _s(b.get("kitaplik")),
                                          "hedefKitle": _s(b.get("hedef_kitle")), "turler": _s(b.get("turler"))})
    out = []
    for h in heads:
        hid = _id(h.get("id"))
        mecra = [m for m in (_s(h.get("mecra1")), _s(h.get("mecra2")), _s(h.get("mecra3"))) if m]
        out.append({"id": hid, "baslik": _s(h.get("baslik")), "link": _s(h.get("link")) or _s(h.get("youtube")), "tarih": _d(h.get("tarih")),
                    "yayinlandi": bool(h.get("yayinlandi")), "kitapGonderimi": bool(h.get("kitap_gonderimi")),
                    "basinZiyareti": bool(h.get("basin_ziyareti")),
                    "mecra": " · ".join(dict.fromkeys(mecra)) or None, "mecraTipi": _s(h.get("mecra_tipi")),
                    "muhabirId": _id(h.get("muhabir_id")), "muhabir": _s(h.get("muhabir")),
                    "gorusulenId": _id(h.get("gorusulen_id")), "gorusulen": _s(h.get("gorusulen")),
                    "yazar": _s(h.get("yazar")) or _s(h.get("yazar_text")), "kitapText": _s(h.get("kitap_text")),
                    "books": books.get(hid or "", [])})
    return out


# ------------------------------------------------------------------ CRM okuyucu


class Crm:
    """CRM okumaları bellekte (`hizli_kaynak`): 10 dakikadan (`CACHE_TTL`) tazeyse hemen; eskiyse eldeki hemen döner ve
    CRM arkada yeniden okunur; hiç yoksa beklenir. Ekrandaki «Yenile» (`fresh`) kaynağı bekler.

    Hız (2026-09-29): medya kişileri ekranı (`/pr/contacts`) test sunucusunda 14,1 / 9,4 sn sürüyordu — kişi listesi, haber
    arşivi (görünüm; olmazsa temel tablo) ve haber–kitap bağları her biri yeni bağlantıyla CRM'den okunuyor, eski
    önbellek 10 dakika dolunca ekranı açan kişi üç okumayı bekliyordu. Şimdi süre dolunca eldeki liste gösterilir ve CRM
    arkada okunur; köprü açılışında bir kez ısıtılır (`pr_api`). Rakamlar aynı SQL'in sonucudur."""

    def __init__(self, schema: Callable[[], str], roles: Callable[[], list[str]], runner: Callable[[], Runner] = crm_runner):
        self.schema = schema
        self.roles = roles
        self.runner = runner
        self._bellek = HK.bellek("pr.crm", CACHE_TTL)

    def _cached(self, key: Any, fresh: bool, fn: Callable[[], Any]) -> Any:
        return HK.oku(self._bellek, key, fn, zorla=fresh)

    def _run(self, sql: str) -> list[dict[str, Any]]:
        try:
            return self.runner()(sql)
        except bsrc.SourceError as e:
            raise SourceError(str(e)) from None

    def month_books(self, frm: date, to: date, fresh: bool = False) -> list[dict[str, Any]]:
        def load() -> list[dict[str, Any]]:
            by: dict[str, dict[str, Any]] = {}
            for r in self._run(month_books_sql(self.schema(), frm, to)):
                b = book_row(r)
                if b["kitapId"]:
                    by.setdefault(b["kitapId"], b)
            return list(by.values())
        return self._cached(("month", frm, to), fresh, load)

    def book(self, kitap_id: str, fresh: bool = False) -> Optional[dict[str, Any]]:
        def load() -> Optional[dict[str, Any]]:
            rows = self._run(book_sql(self.schema(), kitap_id))
            if not rows:
                return None
            out = detail_row(rows[0])
            out["yazarlar"] = [{"id": _id(r.get("id")), "ad": _s(r.get("ad"))} for r in self._run(book_authors_sql(self.schema(), kitap_id))]
            return out
        return self._cached(("book", kitap_id.lower()), fresh, load)

    def search_books(self, q: str, page: int) -> dict[str, Any]:
        rows_sql, count_sql = book_search_sql(self.schema(), q, page)
        total = self._run(count_sql)
        return {"items": [book_row(r) for r in self._run(rows_sql)], "total": int((total[0] or {}).get("n") or 0) if total else 0,
                "page": max(0, int(page)), "pageSize": SEARCH_PAGE}

    def media_contacts(self, fresh: bool = False) -> list[dict[str, Any]]:
        roles = list(self.roles() or [])

        def load() -> list[dict[str, Any]]:
            by: dict[str, dict[str, Any]] = {}
            for r in self._run(media_contacts_sql(self.schema(), roles)):
                c = contact_row(r)
                if c["id"]:
                    by.setdefault(c["id"], c)
            return list(by.values())
        return self._cached(("contacts", tuple(roles)), fresh, load)

    def archive(self, fresh: bool = False) -> list[dict[str, Any]]:
        def load() -> list[dict[str, Any]]:
            try:
                heads = self._run(archive_sql(self.schema()))
                self.archive_path = "gorunum"
            except SourceError:
                heads = self._run(archive_base_sql(self.schema()))
                self.archive_path = "temel-tablo"
            return archive_rows(heads, self._run(archive_books_sql(self.schema())))
        return self._cached(("archive",), fresh, load)

    archive_path: Optional[str] = None

    def promo_orders(self, stok: str) -> list[dict[str, Any]]:
        return [{"siparisNo": _s(r.get("siparis_no")), "tarih": _d(r.get("tarih")), "cari": _s(r.get("cari")),
                 "adet": bsrc._num(r.get("adet")) or 0} for r in self._run(promo_orders_sql(self.schema(), stok))]

    def email_of(self, user: str) -> Optional[str]:
        if not user:
            return None
        try:
            rows = self._cached(("mail", user.lower()), False, lambda: self._run(email_sql(self.schema(), user)))
        except SourceError:
            return None
        mail = _s(rows[0].get("mail")) if rows else None
        return mail if mail and "@" in mail else None


def with_archive_counts(contacts: list[dict[str, Any]], archive: list[dict[str, Any]]) -> list[dict[str, Any]]:
    n: dict[str, int] = {}
    for a in archive:
        for k in {a.get("muhabirId"), a.get("gorusulenId")} - {None}:
            n[k] = n.get(k, 0) + 1
    return [{**c, "haberSayisi": n.get(c["id"], 0)} for c in contacts]


# ------------------------------------------------------------------ Basın ve web


def web_candidates(engine: Any, tenant: str, since: Optional[datetime]) -> list[dict[str, Any]]:
    """Basın ve web taramasının ilgili (olumlu/olumsuz/nötr) bulduğu kayıtlar; `since` sonrasında etiketlenenler."""
    import json

    import sqlalchemy as sa

    from semantic_bridge import web_watch as W

    W.ensure(engine)
    cond = [W.MENTIONS.c.tenant_id == tenant, W.MENTIONS.c.label.in_(W.SHOWN)]
    if since is not None:
        cond.append(sa.func.coalesce(W.MENTIONS.c.labelled_at, W.MENTIONS.c.created_at) > since)
    with engine.connect() as c:
        rows = c.execute(sa.select(W.MENTIONS.c.contact_id, W.MENTIONS.c.author, W.MENTIONS.c.books_json, W.MENTIONS.c.label,
                                   W.ITEMS.c.id.label("item_id"), W.ITEMS.c.source, W.ITEMS.c.url, W.ITEMS.c.title, W.ITEMS.c.summary,
                                   W.ITEMS.c.published_at, W.ITEMS.c.fetched_at)
                         .select_from(W.MENTIONS.join(W.ITEMS, W.ITEMS.c.id == W.MENTIONS.c.item_id)).where(*cond)).all()
    out = []
    for r in rows:
        at = r.published_at or r.fetched_at
        out.append({"itemId": r.item_id, "url": r.url, "title": r.title, "summary": r.summary,
                    "publishedAt": (at.date().isoformat() if at else None), "outlet": W.FEED_LABEL.get(r.source, r.source),
                    "author": r.author, "contactId": r.contact_id, "books": json.loads(r.books_json or "[]"), "label": r.label})
    return out


# ------------------------------------------------------------------ tek sayfa okuma


def _public_host(host: str) -> bool:
    """Bağlantı yalnız herkese açık adrese gidebilir (iç ağ, döngü, bağlantı-yerel adres okunmaz)."""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return False
    return bool(infos)


def _meta(page: str, *names: str) -> Optional[str]:
    for n in names:
        for pat in (rf'<meta[^>]+(?:property|name|itemprop)=["\']{re.escape(n)}["\'][^>]*content=["\']([^"\']+)["\']',
                    rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]*(?:property|name|itemprop)=["\']{re.escape(n)}["\']'):
            m = re.search(pat, page, re.I)
            if m:
                return html.unescape(m.group(1)).strip() or None
    return None


def parse_page(page: str, url: str) -> dict[str, Any]:
    title = _meta(page, "og:title", "twitter:title")
    if not title:
        m = re.search(r"<title[^>]*>(.*?)</title>", page, re.I | re.S)
        title = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else None
    when = _meta(page, "article:published_time", "og:published_time", "datePublished", "pubdate", "date")
    if not when:
        m = re.search(r'"datePublished"\s*:\s*"([^"]+)"', page) or re.search(r'<time[^>]+datetime=["\']([^"\']+)["\']', page, re.I)
        when = m.group(1) if m else None
    published = None
    if when:
        m = re.match(r"(\d{4}-\d{2}-\d{2})", when.strip())
        published = m.group(1) if m else None
    host = urllib.parse.urlsplit(url).hostname or ""
    outlet = _meta(page, "og:site_name") or re.sub(r"^www\.", "", host)
    desc = _meta(page, "og:description", "description", "twitter:description")
    return {"title": (title or "")[:500] or None, "publishedAt": published, "outlet": outlet[:200] if outlet else None,
            "summary": desc, "host": host}


def fetch_page(url: str, get: Optional[Callable[[str], bytes]] = None, allowed: Optional[Callable[[str], bool]] = None) -> dict[str, Any]:
    """Yapıştırılan tek sayfanın başlığı, tarihi, mecrası ve kısa açıklaması. Okunamazsa `error` döner; ekran elle girişe
    geçer. Haber metni alınmaz."""
    from semantic_bridge import web_watch as W

    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        return {"error": "Bağlantı http:// ya da https:// ile başlamalı."}
    if get is None and not _public_host(parts.hostname):
        return {"error": "Bu adres herkese açık bir site değil; bilgileri elle girin."}
    if not (allowed or W.allowed)(url):
        return {"error": "Site bu sayfanın otomatik okunmasına izin vermiyor (robots.txt); bilgileri elle girin."}
    try:
        body = (get or (lambda u: W._get(u, timeout=20)))(url)
    except Exception as e:  # noqa: BLE001 — okunamayan sayfa: elle giriş
        return {"error": f"Sayfa okunamadı ({str(e)[:120]}); bilgileri elle girin."}
    page = body[:2_000_000].decode("utf-8", "replace")
    return parse_page(page, url)
