"""Pazarlama çekirdeğinin kaynak okuması (yalnız okuma).

- **CRM** (`SEMANTIC_CRM_CONNECTION_FILE`, şema Yönetim → CRM şeması): kitap kartı (`new_kitap` görünümü; M10'un
  `crm_kitaplar.sql`'iyle aynı ad/yayınevi/kitaplık/hedef kitle çözümü), bağlı proje kartı (`new_kitapBase.new_projekarti`
  → `new_projeBase`; pazarlama sorumlusu, bütçe alanları, yayın tarihi), ilk baskının üretim kartı (`new_UretimBase`,
  baskı tekrarı olmayan ilk kart; dağılım planı ve depo girişi), rakip kitaplar, özel gün bağı, pazarlama bütçe modülü
  kayıtları (`new_pazarlamamoduluBase` + kitap bağı). CRM tarihleri UTC saklanır; gün İstanbul saatine (+3) çevrilir.
- **Logo** buradan okunmaz: satış rakamları M46'nın Logo gerçekleşme önbelleğinden (`semantic_budget_sales_actuals`,
  faturalı satır, net ciro = LINENET) ve M10'un veri kümesinden (emsallerin ilk 3/6/12 ayı) gelir. Böylece karne,
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
    s = re.sub(r"<br\s*/?>|</p>", "\n", str(v), flags=re.I)
    s = re.sub(r"<[^>]+>", "", s).replace("&nbsp;", " ").replace("&amp;", "&")
    s = "\n".join(" ".join(x.split()) for x in s.splitlines())
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s or None


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
    """CRM okumaları; liste 5 dakika bellekte tutulur («yenile» kaynağa gider)."""

    def __init__(self, schema: Callable[[], str], runner: Callable[[], Runner] = crm_runner):
        self.schema = schema
        self.runner = runner
        self._cache: dict[Any, tuple[float, Any]] = {}
        self._lock = threading.Lock()

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

    def new_books(self, frm: date, to: date, fresh: bool = False) -> list[dict[str, Any]]:
        def load() -> list[dict[str, Any]]:
            by: dict[str, dict[str, Any]] = {}
            for r in self._run(new_books_sql(self.schema(), frm, to)):
                b = book_row(r)
                if not b["stokKodu"]:
                    continue
                # powerbikitap aynı stok kodunda birden çok satır verebilir: ilk dolu olan kalır.
                by.setdefault(b["stokKodu"], b)
            return list(by.values())
        return self._cached(("new", frm, to), fresh, load)

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

    def email_of(self, user: str) -> Optional[str]:
        if not user:
            return None
        try:
            rows = self._cached(("mail", user.lower()), False, lambda: self._run(email_sql(self.schema(), user)))
        except SourceError:
            return None
        mail = _s(rows[0].get("mail")) if rows else None
        return mail if mail and "@" in mail else None
