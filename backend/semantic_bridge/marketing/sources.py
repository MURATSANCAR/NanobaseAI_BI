"""Pazarlama çekirdeğinin kaynak okuması (yalnız okuma).

- **CRM** (`SEMANTIC_CRM_CONNECTION_FILE`, şema Yönetim → CRM şeması): kitap kartı (`new_kitap` görünümü; M10'un
  `crm_kitaplar.sql`'iyle aynı ad/yayınevi/kitaplık/hedef kitle çözümü), bağlı proje kartı (`new_kitapBase.new_projekarti`
  → `new_projeBase`; pazarlama sorumlusu, bütçe alanları, yayın tarihi), ilk baskının üretim kartı (`new_UretimBase`,
  baskı tekrarı olmayan ilk kart; dağılım planı ve depo girişi), rakip kitaplar, özel gün bağı, pazarlama bütçe modülü
  kayıtları (`new_pazarlamamoduluBase` + kitap bağı). CRM tarihleri UTC saklanır; gün İstanbul saatine (+3) çevrilir.
- **Logo** buradan okunmaz: satış rakamları M46'nın Logo gerçekleşme önbelleğinden (`semantic_budget_sales_actuals`,
  faturalı satır, net ciro = VATMATRAH) ve M10'un veri kümesinden (emsallerin ilk 3/6/12 ayı) gelir. Böylece karne,
  bütçe ve ilk baskı ekranıyla aynı rakamı gösterir ve Logo'ya ikinci kez yük bindirmez.

Yazma yok: bu modülde CRM'e/Logo'ya giden tek komut `SELECT`tir.
"""
from __future__ import annotations

import os
import re
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

from semantic_bridge import budget_sources as bsrc

Runner = Callable[[str], list[dict[str, Any]]]
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_CODE = re.compile(r"^[0-9A-Za-z._/\- ]{1,60}$")
#: Kitap kartı tipi «Kitap» (M46 ile aynı: `new_Tip = 1`).
BOOK_TIP = 1
#: Üretim kartı türü «baskı tekrarı» (production.CARD_REPRINT ile aynı).
CARD_REPRINT = 1
CACHE_TTL = 300


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
    """İstanbul günü başlangıcının UTC karşılığı (CRM tarihi UTC saklar)."""
    return (datetime(d.year, d.month, d.day) - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")


# ------------------------------------------------------------------ SQL

_HK = ("LEFT JOIN {p}StringMapBase AS hk ON hk.AttributeName = 'new_hedefkitle' AND hk.AttributeValue = k.new_hedefkitle "
       "AND hk.LangId = 1055 AND hk.ObjectTypeCode = (SELECT ObjectTypeCode FROM {p}EntityView WHERE Name = 'new_kitap')")
_FIRST_PRINT = ("OUTER APPLY (SELECT TOP 1 r.new_dagilimtarihi AS dagilim, r.new_DepoGiriTarihi AS depo "
                "FROM {p}new_UretimBase AS r WHERE r.new_kitapid = k.new_kitapId AND r.statecode = 0 "
                "AND ISNULL(CAST(r.new_baskikartidurumu AS int), 0) <> " + str(CARD_REPRINT) + " "
                "ORDER BY r.new_BaskiNo, r.CreatedOn) AS u")
_PROJ_DATE = "COALESCE(j.new_yayintarihi, j.new_nerilenYaynTarihi, j.new_hedeflenenbaskitarihi)"

_BOOK_COLS = """
    k.new_kitapId                                            AS kitap_id,
    k.new_stokkodu                                           AS stok_kodu,
    COALESCE(p.[Ürün Adı], k.new_name)                       AS ad,
    COALESCE(p.Yazar, k.new_yazartext)                       AS yazar,
    COALESCE(p.Yayınevi, k.new_yayineviidName)               AS yayinevi,
    COALESCE(p.Kitaplık, k.new_kitaplikidName)               AS kitaplik,
    COALESCE(p.HedefKitle, hk.Value)                         AS hedef_kitle,
    p.Statü                                                  AS statu,
    k.new_resimurl                                           AS kapak,
    CAST(DATEADD(HOUR, 3, k.new_ilkyayintarihi) AS DATE)     AS t_kitap,
    CAST(DATEADD(HOUR, 3, {proj}) AS DATE)                   AS t_proje,
    CAST(DATEADD(HOUR, 3, u.dagilim) AS DATE)                AS t_uretim_dagilim,
    CAST(DATEADD(HOUR, 3, u.depo) AS DATE)                   AS t_uretim_depo,
    j.new_projeId                                            AS proje_id,
    j.new_name                                               AS proje_adi,
    su.FullName                                              AS sorumlu_ad,
    su.DomainName                                            AS sorumlu_hesap"""


def new_books_sql(schema: str, frm: date, to: date) -> str:
    """Yayın günü [frm, to] içinde olan kitap kartları: kitap ilk baskı tarihi, bağlı projenin yayın tarihi ya da ilk
    baskının üretim dağılım/depo tarihi bu aralıkta. Hangisinin esas olduğu köprüde `MARKETING_PUBLISH_DATE_ORDER`
    ile seçilir; üçü de ekranda kaynağıyla görünür."""
    p = prefix(schema)
    lo, hi = _utc_bound(frm), _utc_bound(to + timedelta(days=1))
    rng = lambda col: f"({col} >= '{lo}' AND {col} < '{hi}')"  # noqa: E731
    return f"""
-- Yayın günü aralıktaki yeni kitaplar (CRM, yalnız okuma). Tarihler UTC saklanır: aralık İstanbul gününe çevrildi.
SELECT {_BOOK_COLS.format(proj=_PROJ_DATE)}
FROM {p}new_kitap AS k
LEFT JOIN {p}powerbikitap AS p ON p.StokKodu = k.new_stokkodu
{_HK.format(p=p)}
LEFT JOIN {p}new_projeBase AS j ON j.new_projeId = k.new_projekarti
LEFT JOIN {p}SystemUserBase AS su ON su.SystemUserId = j.new_pazarlamasorumlusuid
{_FIRST_PRINT.format(p=p)}
WHERE k.statecode = 0 AND k.new_Tip = {BOOK_TIP} AND k.new_stokkodu IS NOT NULL
  AND ({rng('k.new_ilkyayintarihi')} OR {rng(_PROJ_DATE)} OR {rng('u.dagilim')} OR {rng('u.depo')})""".strip()


def book_sql(schema: str, stok: str) -> str:
    """Tek kitabın kartı: künye, tarihler, proje bütçe/öncelik alanları ve CRM'deki pazarlama metinleri."""
    p = prefix(schema)
    return f"""
-- Kitap karnesinin CRM kısmı (yalnız okuma).
SELECT {_BOOK_COLS.format(proj=_PROJ_DATE)},
    k.new_turlertext AS turler, k.new_hedefkitleyasbaslangic AS yas_bas, k.new_hedefkitleyasbitis AS yas_bit,
    COALESCE(NULLIF(p.Üzeri_Fiyat, 0), NULLIF(k.new_kdvdahilfiyat, 0), NULLIF(k.new_PerakendeBirimFiyat, 0)) AS fiyat,
    COALESCE(NULLIF(p.SayfaSayısı, 0), NULLIF(k.new_sayfasayisi, 0)) AS sayfa,
    k.new_ozet AS new_ozet, k.new_kitapspotu AS new_kitapspotu, k.new_TantmFyMetni AS new_TantmFyMetni,
    k.new_tanitimfoymetni AS new_tanitimfoymetni, k.new_BasnBlteni AS new_BasnBlteni,
    k.new_sosyalmedyametni AS new_sosyalmedyametni, k.new_hastag AS new_hastag, k.new_AnahtarKelimeler AS new_AnahtarKelimeler,
    k.new_kitabinenonemlicumlesi AS new_kitabinenonemlicumlesi, k.new_alintlar AS new_alintlar,
    k.new_KitabnPlanlananTantmveReklamMecralar AS new_KitabnPlanlananTantmveReklamMecralar,
    k.new_kitabinonecikanyanlari AS new_kitabinonecikanyanlari,
    j.new_toplampazarlamabutcesi AS p_toplam, j.new_toplampazarlamabutcesi_kurulsonucu AS p_toplam_kurul,
    j.new_basinbutcesi AS p_basin, j.new_kampanyabutcesi AS p_kampanya, j.new_internetbutcesi AS p_internet,
    j.new_okulbutcesi AS p_okul, j.new_prestijbutcesi AS p_prestij, j.new_pazarlamaonceligi AS p_oncelik,
    j.new_pazarlamaayrintisi AS p_ayrinti, j.new_potansiyelsatisucay AS p_satis3, j.new_PotansiyelNetSatisonikiay AS p_satis12
FROM {p}new_kitap AS k
LEFT JOIN {p}powerbikitap AS p ON p.StokKodu = k.new_stokkodu
{_HK.format(p=p)}
LEFT JOIN {p}new_projeBase AS j ON j.new_projeId = k.new_projekarti
LEFT JOIN {p}SystemUserBase AS su ON su.SystemUserId = j.new_pazarlamasorumlusuid
{_FIRST_PRINT.format(p=p)}
WHERE k.statecode = 0 AND k.new_stokkodu = '{code(stok)}'""".strip()


def rivals_sql(schema: str, kitap_id: str) -> str:
    p = prefix(schema)
    return f"""
-- Kitap kartına bağlı rakip kitaplar (CRM «Rakip Kitap»; web kazıma yok).
SELECT r.new_name AS ad, r.new_Yaynevi AS yayinevi, r.new_Yazarlar AS yazarlar, r.new_SatisAdedi AS satis_adedi,
       r.new_ListeFiyat AS liste_fiyati, r.new_Kategoriler AS kategoriler, r.new_TanitimMetni AS tanitim
FROM {p}new_new_kitap_new_rakipkitapBase AS b
JOIN {p}new_rakipkitapBase AS r ON r.new_rakipkitapId = b.new_rakipkitapid
WHERE b.new_kitapid = '{guid(kitap_id)}' AND r.statecode = 0""".strip()


def special_days_sql(schema: str, kitap_id: str) -> str:
    p = prefix(schema)
    return f"""
-- Kitaba bağlı özel günler (tarih yöntemi SEO sezon takvimiyle aynı: seo_geo.seasons.resolve).
SELECT o.new_ozelgunlerId AS id, o.new_name AS ad, o.new_ozelgunhafta1 AS hafta1, o.new_ozelgunlerhafta2 AS hafta2,
       CAST(DATEADD(HOUR, 3, o.new_Tarih) AS DATE) AS tarih
FROM {p}new_new_kitap_new_ozelgunlerBase AS l
JOIN {p}new_ozelgunlerBase AS o ON o.new_ozelgunlerId = l.new_ozelgunlerid
WHERE l.new_kitapid = '{guid(kitap_id)}' AND o.statecode = 0""".strip()


def spend_sql(schema: str, since: date) -> str:
    """Pazarlama bütçe modülü kayıtları (kayıt × bağlı kitap). Kanal payının emsal/şirket tabanı."""
    p = prefix(schema)
    return f"""
-- CRM «Pazarlama Bütçe Modülü» kayıtları ve bağlı kitaplar (yalnız okuma). Tutar baz para biriminde.
SELECT m.new_pazarlamamoduluId AS id, m.new_name AS ad, CAST(m.new_pazarlamatipi AS int) AS tip, sm.Value AS tip_adi,
       COALESCE(m.new_tutar_Base, m.new_tutar) AS tutar,
       CAST(DATEADD(HOUR, 3, COALESCE(m.new_baslangictarihi, m.CreatedOn)) AS DATE) AS baslangic,
       k.new_StokKodu AS stok_kodu
FROM {p}new_pazarlamamoduluBase AS m
LEFT JOIN {p}StringMapBase AS sm ON sm.AttributeName = 'new_pazarlamatipi' AND sm.AttributeValue = m.new_pazarlamatipi
      AND sm.LangId = 1055 AND sm.ObjectTypeCode = (SELECT ObjectTypeCode FROM {p}EntityView WHERE Name = 'new_pazarlamamodulu')
LEFT JOIN {p}new_new_pazarlamamodulu_new_kitapBase AS l ON l.new_pazarlamamoduluid = m.new_pazarlamamoduluId
LEFT JOIN {p}new_kitapBase AS k ON k.new_kitapId = l.new_kitapid
WHERE m.statecode = 0 AND COALESCE(m.new_baslangictarihi, m.CreatedOn) >= '{_utc_bound(since)}'""".strip()


def email_sql(schema: str, user: str) -> str:
    p = prefix(schema)
    u = re.sub(r"[^A-Za-z0-9._\-]", "", str(user or ""))[:80]
    return (f"SELECT TOP 1 InternalEMailAddress AS mail FROM {p}SystemUserBase "
            f"WHERE IsDisabled = 0 AND DomainName LIKE N'%\\{u}'")


# ------------------------------------------------------------------ M18: ay planı ve föy


def campaigns_sql(schema: str, frm: date, to: date) -> str:
    """Ay ile kesişen etkin CRM kampanyaları (B2B/CRM mecrası, ek iskonto, planlanan/gerçekleşen ciro, ürün sayısı).
    Tarihler UTC saklanır: sınırlar İstanbul gününe çevrildi."""
    p = prefix(schema)
    lo, hi = _utc_bound(frm), _utc_bound(to + timedelta(days=1))
    return f"""
-- Ay ile kesişen CRM kampanyaları (yalnız okuma).
SELECT c.new_kampanyaId AS id, c.new_name AS ad, CAST(c.new_tip AS int) AS tip,
       CAST(DATEADD(HOUR, 3, c.new_baslangictarihi) AS DATE) AS baslangic,
       CAST(DATEADD(HOUR, 3, c.new_bitistarihi) AS DATE) AS bitis,
       CAST(c.new_kampanyamecra AS int) AS mecra, c.new_ekiskonto AS ek_iskonto, c.new_netiskonto AS net_iskonto,
       COALESCE(c.new_planlananciro_Base, c.new_planlananciro) AS planlanan_ciro,
       COALESCE(c.new_gerceklesenciro_Base, c.new_gerceklesenciro) AS gerceklesen_ciro,
       (SELECT COUNT(*) FROM {p}new_new_kampanya_productBase AS x WHERE x.new_kampanyaid = c.new_kampanyaId) AS urun_sayisi
FROM {p}new_kampanyaBase AS c
WHERE c.statecode = 0 AND c.new_baslangictarihi < '{hi}' AND c.new_bitistarihi >= '{lo}'""".strip()


def all_special_days_sql(schema: str) -> str:
    """Etkin özel günlerin tamamı ve her birine bağlı etkin kitap sayısı (tarih yöntemi SEO sezon takvimiyle aynı)."""
    p = prefix(schema)
    return f"""
-- CRM özel günleri ve bağlı kitap sayısı (yalnız okuma).
SELECT o.new_ozelgunlerId AS id, o.new_name AS ad, o.new_ozelgunhafta1 AS hafta1, o.new_ozelgunlerhafta2 AS hafta2,
       CAST(DATEADD(HOUR, 3, o.new_Tarih) AS DATE) AS tarih,
       (SELECT COUNT(*) FROM {p}new_new_kitap_new_ozelgunlerBase AS l
        JOIN {p}new_kitapBase AS k ON k.new_kitapId = l.new_kitapid AND k.statecode = 0
        WHERE l.new_ozelgunlerid = o.new_ozelgunlerId) AS kitap_sayisi
FROM {p}new_ozelgunlerBase AS o
WHERE o.statecode = 0""".strip()


def _values(codes: list[str]) -> str:
    return ", ".join("(N'" + code(c) + "')" for c in codes)


def foy_books_sql(schema: str, codes: list[str]) -> str:
    """Föy alanları (CRM kitap kartı): künye, fiyat, barkod, hedef kitle, tanıtım metinleri. Hangi kolonun föyde neye
    karşılık geldiği `foy.FIELDS`'te."""
    p = prefix(schema)
    return f"""
-- Föy alanları: kitap kartı künyesi, fiyat, barkod, hedef kitle ve tanıtım metinleri (yalnız okuma).
SELECT k.new_kitapId AS kitap_id, k.new_stokkodu AS stok_kodu,
       COALESCE(p.[Ürün Adı], k.new_name) AS ad, COALESCE(p.Yazar, k.new_yazartext) AS yazar,
       COALESCE(p.Yayınevi, k.new_yayineviidName) AS yayinevi, COALESCE(p.Kitaplık, k.new_kitaplikidName) AS kitaplik,
       COALESCE(p.Dizi_Tür, k.new_diziidName) AS dizi, COALESCE(p.HedefKitle, hk.Value) AS hedef_kitle,
       k.new_hedefkitleyasbaslangic AS yas_bas, k.new_hedefkitleyasbitis AS yas_bit, k.new_siniflartext AS siniflar,
       k.new_ean13 AS ean13, k.new_isbn13 AS isbn13, k.new_kdvdahilfiyat AS kdv_dahil_fiyat,
       k.new_PerakendeBirimFiyat AS perakende_fiyat, p.Üzeri_Fiyat AS uzeri_fiyat, k.new_FyinTaslakFiyat AS foy_taslak_fiyat,
       COALESCE(NULLIF(p.SayfaSayısı, 0), NULLIF(k.new_sayfasayisi, 0)) AS sayfa, k.new_Ebat AS ebat,
       COALESCE(cs.Value, k.new_KapakveCilt) AS cilt, k.new_resimurl AS kapak,
       CAST(DATEADD(HOUR, 3, k.new_ilkyayintarihi) AS DATE) AS ilk_yayin,
       k.new_TantmFyMetni AS new_TantmFyMetni, k.new_tanitimfoymetni AS new_tanitimfoymetni,
       k.new_kitapspotu AS new_kitapspotu, k.new_ozet AS new_ozet,
       k.new_kitabinonecikanyanlari AS new_kitabinonecikanyanlari,
       k.new_editorunkitabaveyazaradairgorusleri AS new_editorunkitabaveyazaradairgorusleri
FROM {p}new_kitap AS k
JOIN (VALUES {_values(codes)}) AS kod(k) ON kod.k = k.new_stokkodu
LEFT JOIN {p}powerbikitap AS p ON p.StokKodu = k.new_stokkodu
{_HK.format(p=p)}
LEFT JOIN {p}StringMapBase AS cs ON cs.AttributeName = 'new_ciltlemesekli' AND cs.AttributeValue = k.new_ciltlemesekli
      AND cs.LangId = 1055 AND cs.ObjectTypeCode = (SELECT ObjectTypeCode FROM {p}EntityView WHERE Name = 'new_kitap')
WHERE k.statecode = 0""".strip()


#: CRM «Satış Hedefleri» yıl seçenek değeri (tablo sözlüğü 2026-09-09: 1=2023, 2=2024, 3=2025, 100000000=2026).
REGION_TARGET_YEAR = {2023: 1, 2024: 2, 2025: 3, 2026: 100000000}
REGION_MONTH_COLS = ("new_ocak", "new_subat", "new_Mart", "new_Nisan", "new_mayis", "new_Haziran", "new_Temmuz",
                     "new_agustos", "new_eylul", "new_Ekim", "new_kasim", "new_aralik")


def region_targets_sql(schema: str, year_value: int, month: int, codes: list[str]) -> str:
    """CRM bölge × kitap satış hedefi (adet) o ay için, kitap başına toplam. Yalnız bilgi: M46 hedefiyle ilişkisi
    ölçülmedi (M46 bu tabloyu okumuyor); iki hedef karıştırılmaz."""
    p = prefix(schema)
    col = REGION_MONTH_COLS[month - 1]
    return f"""
-- CRM bölge satış hedefleri (bilgi amaçlı; M46 hedefi esastır).
SELECT t.new_StokKodu AS stok_kodu, SUM(COALESCE(t.{col}, 0)) AS adet, COUNT(DISTINCT t.new_bolge) AS bolge
FROM {p}new_satishedefleriBase AS t
JOIN (VALUES {_values(codes)}) AS kod(k) ON kod.k = t.new_StokKodu
WHERE t.statecode = 0 AND t.new_yil = {int(year_value)}
GROUP BY t.new_StokKodu""".strip()


# ------------------------------------------------------------------ okuma


def account(domain_name: Any) -> Optional[str]:
    """`TIMAS\\ahmet` → `ahmet` (portal oturumu AD sAMAccountName'dir)."""
    s = str(domain_name or "").strip()
    if not s:
        return None
    return s.split("\\")[-1].split("@")[0].lower() or None


def _d(v: Any) -> Optional[str]:
    d = bsrc._day(v)
    if d is None or d.year < 1950:  # 1899/1900: boş tarih
        return None
    return d.isoformat()


def _s(v: Any) -> Optional[str]:
    return bsrc._clean(v)


def _long(v: Any) -> Optional[str]:
    """Çok satırlı metin: satır sonları korunur, fazla boşluk atılır; HTML etiketleri sökülür."""
    if v is None:
        return None
    from semantic_bridge.crm_text import rich_text   # ZEKI-23: ortak kural, bütün HTML varlıkları çözülür
    return rich_text(v, keep_blank=True)


def book_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "kitapId": (_s(r.get("kitap_id")) or "").lower() or None, "stokKodu": _s(r.get("stok_kodu")), "ad": _s(r.get("ad")),
        "yazar": _s(r.get("yazar")), "yayinevi": _s(r.get("yayinevi")), "kitaplik": _s(r.get("kitaplik")),
        "hedefKitle": _s(r.get("hedef_kitle")), "statu": _s(r.get("statu")), "kapak": _s(r.get("kapak")),
        "tarihler": {"crm-kitap": _d(r.get("t_kitap")), "crm-proje": _d(r.get("t_proje")),
                     "uretim-dagilim": _d(r.get("t_uretim_dagilim")), "uretim-depo": _d(r.get("t_uretim_depo"))},
        "projeId": (_s(r.get("proje_id")) or "").lower() or None, "projeAdi": _s(r.get("proje_adi")),
        "sorumlu": _s(r.get("sorumlu_ad")), "sorumluHesap": account(r.get("sorumlu_hesap")),
    }


MATERIAL_FIELDS = ("new_ozet", "new_kitapspotu", "new_TantmFyMetni", "new_tanitimfoymetni", "new_BasnBlteni",
                   "new_sosyalmedyametni", "new_hastag", "new_AnahtarKelimeler", "new_kitabinenonemlicumlesi", "new_alintlar",
                   "new_KitabnPlanlananTantmveReklamMecralar", "new_kitabinonecikanyanlari")
FIELD_LABELS = {
    "new_ozet": "Arka kapak metni", "new_kitapspotu": "Kitap spotu", "new_TantmFyMetni": "Tanıtım / föy metni (tek satır)",
    "new_tanitimfoymetni": "Tanıtım – föy metni", "new_BasnBlteni": "Basın bülteni", "new_sosyalmedyametni": "Sosyal medya metni",
    "new_hastag": "Hashtag", "new_AnahtarKelimeler": "Anahtar kelimeler", "new_kitabinenonemlicumlesi": "Kitabın en önemli cümlesi",
    "new_alintlar": "Kitaptan alıntılar", "new_KitabnPlanlananTantmveReklamMecralar": "Planlanan tanıtım ve reklam mecraları",
    "new_kitabinonecikanyanlari": "Bu kitap neden önemli?",
}


def detail_row(r: dict[str, Any]) -> dict[str, Any]:
    out = book_row(r)
    out.update({
        "turler": _s(r.get("turler")), "yas": [r.get("yas_bas"), r.get("yas_bit")], "fiyat": bsrc._num(r.get("fiyat")),
        "sayfa": bsrc._num(r.get("sayfa")),
        "metinler": {f: _long(r.get(f.lower()) if r.get(f) is None else r.get(f)) for f in MATERIAL_FIELDS},
        "proje": {"toplam": bsrc._num(r.get("p_toplam")), "toplamKurul": bsrc._num(r.get("p_toplam_kurul")),
                  "basin": bsrc._num(r.get("p_basin")), "kampanya": bsrc._num(r.get("p_kampanya")),
                  "internet": bsrc._num(r.get("p_internet")), "okul": bsrc._num(r.get("p_okul")),
                  "prestij": bsrc._num(r.get("p_prestij")), "oncelik": bsrc._num(r.get("p_oncelik")),
                  "ayrinti": _long(r.get("p_ayrinti")), "potansiyelSatis3": bsrc._num(r.get("p_satis3")),
                  "potansiyelSatis12": bsrc._num(r.get("p_satis12"))},
    })
    return out


class Crm:
    """CRM okumaları; liste 5 dakika bellekte tutulur («yenile» kaynağa gider).

    Yeni kitap listesi (hız 4. tur, 2026-09-29): kişiden bağımsız CRM okumasıdır (yayın günü aralıktaki kitap kartları +
    ilk baskı + proje; soğuk CRM'de 7–10 sn, ekranda eşzamanlı açılışla 51 sn ölçüldü). `hizli_kaynak` belleğinde: 5 dk
    tazeyse hemen, eskiyse eldeki liste hemen + CRM arkada bir kez; `motor` verilirse son okuma `semantic_hizli_okuma`
    tablosunda da durur (köprü yeniden başlayınca da beklenmez). «Yenile» (`fresh`) CRM'i bekler. Kişi süzgeci
    («benim»), plan/hedef birleşimi ve bütçe gizleme okumanın üstünde, istekte yapılır."""

    def __init__(self, schema: Callable[[], str], runner: Callable[[], Runner] = crm_runner,
                 motor: Optional[Callable[[], Optional[tuple[Any, str]]]] = None):
        from semantic_bridge import hizli_kaynak as HK

        self.schema = schema
        self.runner = runner
        self._cache: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()
        self._yeni = HK.bellek("pazarlama.yeni-kitaplar", CACHE_TTL, en_cok=64, kalici=HK.Kalici(
            "pazarlama.yeni-kitaplar", motor, bicim=new_books_sql("s.dbo", date(2000, 1, 1), date(2000, 1, 2)))
            if motor is not None else None)

    def _cached(self, key: Any, fresh: bool, fn: Callable[[], Any]) -> Any:
        with self._lock:
            hit = self._cache.get(key)
        if hit and not fresh and time.monotonic() - hit[0] < CACHE_TTL:
            return hit[1]
        val = fn()
        with self._lock:
            self._cache[key] = (time.monotonic(), val)
        return val

    def _run(self, sql: str) -> list[dict[str, Any]]:
        try:
            return self.runner()(sql)
        except bsrc.SourceError as e:
            raise SourceError(str(e)) from None

    def _new_books_read(self, frm: date, to: date) -> list[dict[str, Any]]:
        by: dict[str, dict[str, Any]] = {}
        for r in self._run(new_books_sql(self.schema(), frm, to)):
            b = book_row(r)
            if not b["stokKodu"]:
                continue
            # powerbikitap aynı stok kodunda birden çok satır verebilir: ilk dolu olan kalır.
            by.setdefault(b["stokKodu"], b)
        return list(by.values())

    def new_books(self, frm: date, to: date, fresh: bool = False) -> list[dict[str, Any]]:
        from semantic_bridge import hizli_kaynak as HK

        return HK.oku(self._yeni, ("new", self.schema(), frm, to), lambda: self._new_books_read(frm, to), zorla=fresh)

    def new_books_isit(self, frm: date, to: date) -> bool:
        """Köprü açılışı ve gece turu: aralığın listesi tazeyse bir şey yapmaz, değilse CRM arkada okunur."""
        return self._yeni.isit_gerekirse(("new", self.schema(), frm, to), lambda: self._new_books_read(frm, to))

    def book(self, stok: str, fresh: bool = False) -> Optional[dict[str, Any]]:
        def load() -> Optional[dict[str, Any]]:
            rows = self._run(book_sql(self.schema(), stok))
            return detail_row(rows[0]) if rows else None
        return self._cached(("book", stok), fresh, load)

    def rivals(self, kitap_id: str) -> list[dict[str, Any]]:
        return [{"ad": _s(r.get("ad")), "yayinevi": _s(r.get("yayinevi")), "yazarlar": _s(r.get("yazarlar")),
                 "satisAdedi": r.get("satis_adedi"), "listeFiyati": bsrc._num(r.get("liste_fiyati")),
                 "kategoriler": _s(r.get("kategoriler")), "tanitim": _long(r.get("tanitim"))}
                for r in self._run(rivals_sql(self.schema(), kitap_id))]

    def special_days(self, kitap_id: str) -> list[dict[str, Any]]:
        return [{"id": _s(r.get("id")), "ad": _s(r.get("ad")), "hafta1": r.get("hafta1"), "hafta2": r.get("hafta2"),
                 "tarih": _d(r.get("tarih"))} for r in self._run(special_days_sql(self.schema(), kitap_id))]

    def spend(self, since: date, fresh: bool = False) -> list[dict[str, Any]]:
        def load() -> list[dict[str, Any]]:
            return [{"id": _s(r.get("id")), "ad": _s(r.get("ad")), "tip": r.get("tip"), "tipAdi": _s(r.get("tip_adi")),
                     "tutar": bsrc._num(r.get("tutar")) or 0.0, "baslangic": _d(r.get("baslangic")),
                     "stokKodu": _s(r.get("stok_kodu"))} for r in self._run(spend_sql(self.schema(), since))]
        return self._cached(("spend", since), fresh, load)

    # ---- M18

    def campaigns(self, frm: date, to: date, fresh: bool = False) -> list[dict[str, Any]]:
        def load() -> list[dict[str, Any]]:
            return [{"id": (_s(r.get("id")) or "").lower() or None, "ad": _s(r.get("ad")), "tip": r.get("tip"),
                     "baslangic": _d(r.get("baslangic")), "bitis": _d(r.get("bitis")), "mecra": r.get("mecra"),
                     "ekIskonto": bsrc._num(r.get("ek_iskonto")), "netIskonto": bsrc._num(r.get("net_iskonto")),
                     "planlananCiro": bsrc._num(r.get("planlanan_ciro")), "gerceklesenCiro": bsrc._num(r.get("gerceklesen_ciro")),
                     "urunSayisi": int(r.get("urun_sayisi") or 0)}
                    for r in self._run(campaigns_sql(self.schema(), frm, to))]
        return self._cached(("camp", frm, to), fresh, load)

    def all_special_days(self, fresh: bool = False) -> list[dict[str, Any]]:
        def load() -> list[dict[str, Any]]:
            return [{"id": (_s(r.get("id")) or "").lower() or None, "ad": _s(r.get("ad")), "hafta1": r.get("hafta1"),
                     "hafta2": r.get("hafta2"), "tarih": _d(r.get("tarih")), "kitapSayisi": int(r.get("kitap_sayisi") or 0)}
                    for r in self._run(all_special_days_sql(self.schema()))]
        return self._cached(("days",), fresh, load)

    def foy_books(self, codes: list[str], fresh: bool = False) -> dict[str, dict[str, Any]]:
        """Stok kodu → föy için CRM satırı (ham; `foy.from_crm` yorumlar). Kodlar 500'lük parçalarla okunur, tavan yok."""
        want = sorted({c for c in codes if c})
        if not want:
            return {}

        def load() -> dict[str, dict[str, Any]]:
            out: dict[str, dict[str, Any]] = {}
            for i in range(0, len(want), 500):
                for r in self._run(foy_books_sql(self.schema(), want[i:i + 500])):
                    k = _s(r.get("stok_kodu"))
                    if k:
                        out.setdefault(k, r)  # powerbikitap aynı kodda birden çok satır verebilir: ilki kalır
            return out
        return self._cached(("foy", tuple(want)), fresh, load)

    def region_targets(self, year: int, month: int, codes: list[str]) -> Optional[dict[str, dict[str, Any]]]:
        """Kitap → CRM bölge hedefi (adet, bölge sayısı) o ay. Yıl CRM seçeneğinde yoksa None."""
        yv = REGION_TARGET_YEAR.get(int(year))
        want = sorted({c for c in codes if c})
        if yv is None or not want:
            return None
        out: dict[str, dict[str, Any]] = {}
        for i in range(0, len(want), 500):
            for r in self._run(region_targets_sql(self.schema(), yv, month, want[i:i + 500])):
                k = _s(r.get("stok_kodu"))
                if k:
                    out[k] = {"adet": bsrc._num(r.get("adet")) or 0.0, "bolge": int(r.get("bolge") or 0)}
        return out

    def email_of(self, user: str) -> Optional[str]:
        if not user:
            return None
        try:
            rows = self._cached(("mail", user.lower()), False, lambda: self._run(email_sql(self.schema(), user)))
        except SourceError:
            return None
        mail = _s(rows[0].get("mail")) if rows else None
        return mail if mail and "@" in mail else None
