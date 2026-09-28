"""M23 İşbirlikleri: CRM okumaları (yalnız `SELECT`; CRM'e hiçbir yoldan yazılmaz).

- **Kitap bilgisi** (aday sırası ve brief için): `new_kitap` kartı — ad, stok kodu, yazar, tür metni (`new_turlertext`),
  raf türü (`new_rafturu`, metin), hedef kitle (seçenek kümesi, `StringMapBase` üzerinden adı), ağırlıklı hedef yaş
  aralığı (`new_hedefkitleyasbaslangic/bitis`), arka kapak (`new_ozet`) ve «Bu kitap neden önemli?»
  (`new_kitabinonecikanyanlari`). Uzun metin yalnız tek kitap okunurken seçilir.
- **Tanıtım gönderimi** (kişi kartındaki «gönderilen kitap»): «Pazarlama (Tanıtım Gönderimi)» tipli siparişler
  (`new_siparisBase.new_siparistipi = 12`) ve satırları; işbirliği kartına elle yazılan sipariş numaraları (`new_name`)
  üzerinden. Siparişin alıcısının CRM kişisi mi cari mi olduğu **ölçülecek**; bağ bu yüzden numarayla kurulur.
- **Geçmiş influencer harcaması**: «Pazarlama Bütçe Modülü» kayıtlarından mecra tipi 4 = 6 «Influencer»
  (`new_pazarlamamoduluBase.new_mecratipi4`, `new_tutar`, `new_baslangictarihi`). Rapor ekranında ayrı satırdır;
  portal kayıtlarıyla toplanmaz (aynı işin iki yerde kaydı olabilir).
- **Sosyal kullanıcı adı olan CRM kişileri** (kayıt defterine eşleşme önerisi): `ContactBase.new_Instagram`,
  `new_YoutubeKullancAd`, `new_TwitterKullaniciAdi`. Yazar (`new_yazarmi = 1`) ayrı sayılır.

Hedef kişiye ait herkese açık hesap sayıları için resmî API istemcisi ikinci sürümdedir (`INFLUENCER_API_ENABLED`);
kazıma yoktur, bu dosyada dış ağa giden hiçbir çağrı yoktur.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

from semantic_bridge import budget_sources as bsrc

Runner = Callable[[str], list[dict[str, Any]]]
_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_GUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_CODE = re.compile(r"^[0-9A-Za-z._/\- ]{1,60}$")
_ORDER = re.compile(r"^[0-9A-Za-zÇĞİÖŞÜçğıöşü._/\- ]{1,60}$")
_HANDLE = re.compile(r"^[0-9A-Za-z._\-]{1,80}$")

#: «Pazarlama (Tanıtım Gönderimi)» sipariş tipi (CRM seçenek kümesi `new_siparistipi`).
PROMO_ORDER_TYPE = 12
#: Pazarlama bütçe modülünde mecra tipi 4 = «Influencer».
INFLUENCER_MEDIUM = 6
#: Sosyal kullanıcı adı alanları: platform → CRM kolonu.
SOCIAL_FIELDS = {"instagram": "new_Instagram", "youtube": "new_YoutubeKullancAd", "x": "new_TwitterKullaniciAdi"}


class SourceError(RuntimeError):
    pass


def runner(path: str) -> Runner:
    try:
        return bsrc.runner(path)
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


def guid(v: Any) -> Optional[str]:
    s = str(v or "").strip().strip("{}")
    return s.lower() if _GUID.match(s) else None


def code(v: Any) -> Optional[str]:
    s = str(v or "").strip()
    return s.replace("'", "''") if _CODE.match(s) else None


def order_no(v: Any) -> Optional[str]:
    s = str(v or "").strip()
    return s.replace("'", "''") if _ORDER.match(s) else None


def handle(v: Any) -> Optional[str]:
    """`@ad`, `https://instagram.com/ad/` ya da `ad` → `ad` (küçük harf). Geçersizse None."""
    s = str(v or "").strip()
    s = re.sub(r"^https?://(www\.)?[^/]+/", "", s, flags=re.I).split("?")[0].strip("/").lstrip("@")
    s = s.split("/")[-1] if s.startswith(("c/", "channel/", "user/")) else s.split("/")[0]
    s = s.lstrip("@").lower()
    return s if _HANDLE.match(s) else None


def _utc_bound(d: date) -> str:
    """İstanbul günü başlangıcının UTC karşılığı (CRM tarihi UTC saklar)."""
    return (datetime(d.year, d.month, d.day) - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")


def _long(v: Any) -> Optional[str]:
    if v is None:
        return None
    s = re.sub(r"<br\s*/?>|</p>", "\n", str(v), flags=re.I)
    s = re.sub(r"<[^>]+>", "", s).replace("&nbsp;", " ").replace("&amp;", "&")
    s = "\n".join(" ".join(x.split()) for x in s.splitlines())
    return re.sub(r"\n{3,}", "\n\n", s).strip() or None


def _s(v: Any) -> Optional[str]:
    return bsrc._clean(v)


# ------------------------------------------------------------------ SQL

_HK = ("LEFT JOIN {p}StringMapBase AS hk ON hk.AttributeName = 'new_hedefkitle' AND hk.AttributeValue = k.new_hedefkitle "
       "AND hk.LangId = 1055 AND hk.ObjectTypeCode = (SELECT ObjectTypeCode FROM {p}EntityView WHERE Name = 'new_kitap')")


def book_sql(schema: str, key: str) -> str:
    """Tek kitap: CRM kitap kimliği (GUID) ya da stok kodu."""
    p = prefix(schema)
    g, c = guid(key), code(key)
    if g:
        where = f"k.new_kitapId = '{g}'"
    elif c:
        where = f"k.new_stokkodu = '{c}'"
    else:
        raise SourceError("Kitap kimliği ya da stok kodu geçerli değil.")
    return f"""
-- M23: aday sırası ve brief için tek kitap (CRM, yalnız okuma).
SELECT TOP 1 k.new_kitapId AS kitap_id, k.new_stokkodu AS stok_kodu, k.new_name AS ad, k.new_yazartext AS yazar,
       k.new_yayineviidName AS yayinevi, k.new_turlertext AS turler, k.new_rafturu AS raf, hk.Value AS hedef_kitle,
       k.new_hedefkitleyasbaslangic AS yas_bas, k.new_hedefkitleyasbitis AS yas_bit,
       CAST(k.new_ozet AS nvarchar(max)) AS ozet, CAST(k.new_kitabinonecikanyanlari AS nvarchar(max)) AS one_cikan,
       CAST(DATEADD(HOUR, 3, k.new_ilkyayintarihi) AS DATE) AS ilk_yayin
FROM {p}new_kitap AS k
{_HK.format(p=p)}
WHERE k.statecode = 0 AND {where}""".strip()


def promo_orders_sql(schema: str, numbers: list[str]) -> str:
    """Kartın sipariş numaralarındaki tanıtım gönderimi satırları. Kabul testi 1 bu sorgunun toplamıyla karşılaştırır."""
    p = prefix(schema)
    ok = sorted({n for n in (order_no(x) for x in numbers) if n})
    if not ok:
        raise SourceError("Geçerli sipariş numarası yok.")
    inlist = ", ".join(f"N'{n}'" for n in ok)
    return f"""
-- M23: tanıtım gönderimi siparişleri (tip {PROMO_ORDER_TYPE}) ve satırları (CRM, yalnız okuma).
SELECT s.new_name AS siparis_no, CAST(DATEADD(HOUR, 3, s.CreatedOn) AS DATE) AS tarih,
       ss.new_StokKodu AS stok_kodu, ss.new_adet AS adet
FROM {p}new_siparisBase AS s
JOIN {p}new_siparissatiriBase AS ss ON ss.new_siparisid = s.new_siparisId
WHERE s.new_siparistipi = {PROMO_ORDER_TYPE} AND s.new_name IN ({inlist})""".strip()


def crm_spend_sql(schema: str, frm: date, to: date) -> str:
    """Pazarlama bütçe modülündeki «Influencer» mecra kayıtları, başlangıç tarihi [frm, to] (İstanbul günü)."""
    p = prefix(schema)
    return f"""
-- M23: CRM pazarlama bütçe modülü, mecra tipi 4 = {INFLUENCER_MEDIUM} «Influencer» (yalnız okuma).
SELECT m.new_pazarlamamoduluId AS id, m.new_name AS ad, m.new_tutar AS tutar, m.new_sosyalmedyahesabi AS hesap,
       CAST(DATEADD(HOUR, 3, m.new_baslangictarihi) AS DATE) AS baslangic
FROM {p}new_pazarlamamoduluBase AS m
WHERE m.statecode = 0 AND m.new_mecratipi4 = {INFLUENCER_MEDIUM}
  AND m.new_baslangictarihi >= '{_utc_bound(frm)}' AND m.new_baslangictarihi < '{_utc_bound(to + timedelta(days=1))}'""".strip()


def social_contacts_sql(schema: str, handles: dict[str, list[str]]) -> str:
    """Kullanıcı adı eşleşen aktif CRM kişileri. `handles`: platform → küçük harf kullanıcı adları."""
    p = prefix(schema)
    ors = []
    for platform, col in SOCIAL_FIELDS.items():
        vals = sorted({h for h in (handle(x) for x in handles.get(platform, [])) if h})
        if vals:
            inlist = ", ".join(f"N'{v}'" for v in vals)
            ors.append(f"LOWER(REPLACE(LTRIM(RTRIM(c.{col})), '@', '')) IN ({inlist})")
    if not ors:
        raise SourceError("Eşleştirilecek kullanıcı adı yok.")
    return f"""
-- M23: sosyal kullanıcı adı eşleşen CRM kişileri (yalnız okuma).
SELECT c.ContactId AS id, c.FullName AS ad, c.new_Instagram AS instagram, c.new_YoutubeKullancAd AS youtube,
       c.new_TwitterKullaniciAdi AS x, CAST(ISNULL(c.new_yazarmi, 0) AS int) AS yazar
FROM {p}ContactBase AS c
WHERE c.statecode = 0 AND ({' OR '.join(ors)})""".strip()


def social_summary_sql(schema: str) -> str:
    """Sosyal alanı dolu aktif kişi sayısı (yazar ayrı). Kabul testi 3."""
    p = prefix(schema)
    has = " OR ".join(f"NULLIF(LTRIM(c.{col}), '') IS NOT NULL" for col in SOCIAL_FIELDS.values())
    return f"""
-- M23: sosyal kullanıcı adı olan CRM kişileri (yalnız okuma).
SELECT COUNT(*) AS kisi, SUM(CASE WHEN ISNULL(c.new_yazarmi, 0) = 1 THEN 1 ELSE 0 END) AS yazar
FROM {p}ContactBase AS c
WHERE c.statecode = 0 AND ({has})""".strip()


# ------------------------------------------------------------------ okuma


class Crm:
    def __init__(self, run: Callable[[], Runner], schema: Callable[[], str]):
        self._run = run
        self.schema = schema

    def _q(self, sql: str) -> list[dict[str, Any]]:
        try:
            return self._run()(sql)
        except bsrc.SourceError as e:
            raise SourceError(str(e)) from None

    def book(self, key: str) -> Optional[dict[str, Any]]:
        rows = self._q(book_sql(self.schema(), key))
        if not rows:
            return None
        r = rows[0]
        return {"kitapId": (_s(r.get("kitap_id")) or "").lower() or None, "stokKodu": _s(r.get("stok_kodu")),
                "ad": _s(r.get("ad")), "yazar": _s(r.get("yazar")), "yayinevi": _s(r.get("yayinevi")),
                "turler": _s(r.get("turler")), "raf": _s(r.get("raf")), "hedefKitle": _s(r.get("hedef_kitle")),
                "yas": [_int(r.get("yas_bas")), _int(r.get("yas_bit"))], "ozet": _long(r.get("ozet")),
                "oneCikan": _long(r.get("one_cikan")), "ilkYayin": _day(r.get("ilk_yayin"))}

    def promo_orders(self, numbers: list[str]) -> dict[str, Any]:
        rows = self._q(promo_orders_sql(self.schema(), numbers))
        orders: dict[str, dict[str, Any]] = {}
        for r in rows:
            no = _s(r.get("siparis_no")) or ""
            o = orders.setdefault(no, {"siparisNo": no, "tarih": _day(r.get("tarih")), "adet": 0.0, "satir": []})
            qty = bsrc._num(r.get("adet")) or 0.0
            o["adet"] += qty
            o["satir"].append({"stokKodu": _s(r.get("stok_kodu")), "adet": qty})
        found = set(orders)
        return {"siparisler": list(orders.values()), "toplamAdet": sum(o["adet"] for o in orders.values()),
                "bulunamayan": sorted({str(n).strip() for n in numbers if str(n).strip() and str(n).strip() not in found})}

    def crm_spend(self, frm: date, to: date) -> dict[str, Any]:
        rows = self._q(crm_spend_sql(self.schema(), frm, to))
        items = [{"id": _s(r.get("id")), "ad": _s(r.get("ad")), "tutar": bsrc._num(r.get("tutar")) or 0.0,
                  "hesap": _s(r.get("hesap")), "baslangic": _day(r.get("baslangic"))} for r in rows]
        return {"kayit": len(items), "toplam": round(sum(i["tutar"] for i in items), 2), "items": items}

    def social_contacts(self, handles: dict[str, list[str]]) -> list[dict[str, Any]]:
        return [{"id": (_s(r.get("id")) or "").lower(), "ad": _s(r.get("ad")), "instagram": _s(r.get("instagram")),
                 "youtube": _s(r.get("youtube")), "x": _s(r.get("x")), "yazar": bool(r.get("yazar"))}
                for r in self._q(social_contacts_sql(self.schema(), handles))]

    def social_summary(self) -> dict[str, int]:
        rows = self._q(social_summary_sql(self.schema()))
        r = rows[0] if rows else {}
        return {"kisi": int(bsrc._num(r.get("kisi")) or 0), "yazar": int(bsrc._num(r.get("yazar")) or 0)}


def _int(v: Any) -> Optional[int]:
    n = bsrc._num(v)
    return int(n) if n is not None else None


def _day(v: Any) -> Optional[str]:
    d = bsrc._day(v)
    return d.isoformat() if d and d.year >= 1950 else None
